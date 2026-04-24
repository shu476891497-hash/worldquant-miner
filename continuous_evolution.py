import json
import logging
import os
import sys
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor

# Add the parent directory to sys.path to allow imports from generation_two
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generation_two.core.credential_manager import CredentialManager
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings
from generation_two.evolution.alpha_evolution_engine import AlphaEvolutionEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =========================================================
# ③ BacktestStorage — 持久化数据库（SQLite）
#    作用：把每次仿真结果存盘，防止重启丢失；下次启动自动加载历史精英因子
# =========================================================
def _build_storage():
    """初始化 BacktestStorage，连接本地 SQLite 数据库"""
    try:
        from generation_two.storage.backtest_storage import BacktestStorage
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generation_two_backtests.db")
        storage = BacktestStorage(db_path=db_path)
        stats = storage.get_statistics(region="USA")
        logging.info(f"💾 BacktestStorage 已连接: 历史共 {stats.get('total', 0)} 条记录，"
                     f"成功率 {stats.get('success_rate', 0)*100:.1f}%，"
                     f"最高 Sharpe {stats.get('max_sharpe', 0):.2f}")
        return storage
    except Exception as e:
        logging.warning(f"⚠️ BacktestStorage 初始化失败（数据将不会持久化）: {e}")
        return None


def _load_historical_seeds(storage, min_sharpe: float = 1.25, limit: int = 10) -> list:
    """
    从数据库加载历史高分因子作为种子，让每次重启都能继承上次的成果。
    """
    if storage is None:
        return []
    try:
        records = storage.get_results(region="USA", min_sharpe=min_sharpe, success_only=True, limit=limit)
        seeds = [r.template for r in records if r.template]
        if seeds:
            logging.info(f"🧬 从数据库加载了 {len(seeds)} 条历史精英因子作为初始种子")
        return seeds
    except Exception as e:
        logging.warning(f"加载历史种子失败: {e}")
        return []
# =========================================================
# ④ 动态加载字段表（从 WQ Brain API 缓存读取全量 140 个字段）
#    远比手写 20 个字段丰富；AI 和遗传算法可以使用更多原材料
# =========================================================
def _load_wq_fields_from_cache(region: str = "USA", delay: int = 1,
                               universe: str = "TOP3000"):
    """
    从本地 constants/ 缓存加载该地区所有可用数据字段。
    同时返回：
      field_ids    : list[str]   全量字段 ID
      fields_by_cat: dict[str, list[str]]  按类别分组的字段 ID
    """
    fields_by_cat = {}   # category_id -> [field_id, ...]
    try:
        cache_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "constants",
            f"data_fields_cache_{region}_{delay}_{universe}.json"
        )
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 10:
            with open(cache_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            field_ids = []
            if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                for item in raw:
                    fid = item.get('id')
                    if not fid:
                        continue
                    field_ids.append(fid)
                    # 类别可能是 dict {'id':..., 'name':...} 或字符串
                    cat_raw = item.get('category', 'unknown')
                    cat_id = cat_raw.get('id', 'unknown') if isinstance(cat_raw, dict) else str(cat_raw)
                    fields_by_cat.setdefault(cat_id, []).append(fid)
            elif isinstance(raw, list):
                field_ids = [str(x) for x in raw if x]
            else:
                field_ids = []
            logging.info(
                f"📦 从缓存加载了 {len(field_ids)} 个 {region} 数据字段（"
                + ", ".join(f"{k}:{len(v)}" for k, v in sorted(fields_by_cat.items(), key=lambda x: -len(x[1])))
                + ")"
            )
            return field_ids, fields_by_cat
        else:
            logging.warning(f"⚠️ 字段缓存不存在或为空: {cache_file}，使用内置字段列表")
            return [], {}
    except Exception as e:
        logging.warning(f"加载字段缓存失败: {e}，使用内置字段列表")
        return [], {}


# =========================================================
# ⑤ 优质因子发现报告（解决"看不到 Ollama 生成了什么"的问题）
# =========================================================
_discovery_log_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "discovered_alphas.txt"
)

def _log_discovery(alpha_expr: str, sharpe: float, fitness: float,
                   alpha_id: str, source: str = "evolution"):
    """
    把每个通过 Sharpe > 1.25 门槛的因子记录到 discovered_alphas.txt，
    让用户不用看日志就能看到挖出了什么好因子。
    """
    try:
        line = (f"[{time.strftime('%Y-%m-%d %H:%M')}] "
                f"Sharpe={sharpe:.3f} Fitness={fitness:.3f} "
                f"Source={source} ID={alpha_id}\n"
                f"  EXPR: {alpha_expr}\n"
                f"{'─'*80}\n")
        with open(_discovery_log_path, 'a', encoding='utf-8') as f:
            f.write(line)
        logging.warning(f"🏆 新发现！已写入 discovered_alphas.txt: {alpha_expr[:80]}")
    except Exception as e:
        logging.debug(f"写入发现日志失败: {e}")



# =========================================================
# ① TemplateValidator — 提交前的合法性过滤器
#    作用：拦截括号不平衡、字段名违法等低级错误，避免浪费 API 配额
# =========================================================
def _build_validator():
    """轻量初始化 TemplateValidator（不启用 AST 语法树，只做基础括号/语法检查）"""
    try:
        from generation_two.core.template_validator import TemplateValidator
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generation_two_backtests.db")
        validator = TemplateValidator(use_ast=False, db_path=db_path)
        logging.info("✅ TemplateValidator 已启用（基础语法校验模式）")
        return validator
    except Exception as e:
        logging.warning(f"⚠️ TemplateValidator 初始化失败，将跳过校验: {e}")
        return None


def validate_alpha(validator, expr: str) -> tuple:
    """
    校验一条因子表达式。
    返回: (is_valid: bool, cleaned_expr: str)
    如果 validator 未加载，默认放行。
    """
    if validator is None:
        return True, expr
    try:
        is_valid, error_msg, suggested_fix = validator.validate_template(expr)
        if not is_valid:
            # 如果有建议修复版本，优先使用修复后的版本再校验一次
            if suggested_fix and suggested_fix != expr:
                is_valid2, _, _ = validator.validate_template(suggested_fix)
                if is_valid2:
                    logging.debug(f"🔧 Validator 自动修复: {expr[:60]} → {suggested_fix[:60]}")
                    return True, suggested_fix
            logging.debug(f"❌ 非法因子 [{error_msg}]: {expr[:80]}")
            return False, expr
        return True, expr
    except Exception as e:
        logging.debug(f"Validator 异常（放行）: {e}")
        return True, expr


# =========================================================
# ② OllamaManager — AI 智能因子生成器（免费本地推理）
#    作用：让 Qwen/llama 等本地模型直接"发明"新因子结构
#    频率: 每代调用一次，生成 3–5 条 AI 原创因子混入候选池
# =========================================================
def _build_ollama_manager():
    """
    初始化 OllamaManager，自动探测本地已安装的模型。
    默认尝试 qwen2.5-coder:7b（中等大小，因子生成质量好）
    若不存在则自动 fallback 到任何可用模型。
    """
    try:
        from generation_two.ollama.ollama_manager import OllamaManager
        manager = OllamaManager(
            base_url="http://localhost:11434",
            model="qwen2.5-coder:7b",   # 优先使用，没有会自动 fallback
            timeout=90,
            max_retries=2,
            rate_limit=1.0
        )
        # 触发一次可用性检测
        if manager._check_availability():
            logging.info(f"🤖 Ollama 已连接，使用模型: {manager.model}")
            return manager
        else:
            logging.warning("⚠️ Ollama 服务不可用（是否已运行 `ollama serve`？），AI 生成功能已禁用")
            return None
    except Exception as e:
        logging.warning(f"⚠️ OllamaManager 初始化失败，AI 生成功能已禁用: {e}")
        return None


# WQ Brain FASTEXPR 合法算子速查表（供 AI Prompt 参考）
_WQ_OPERATOR_CHEATSHEET = """
时间序列算子（必须带 lookback 整数参数）:
  ts_mean(x, n)          - n日均值
  ts_rank(x, n)          - n日百分位排名 [0,1]
  ts_zscore(x, n)        - n日 z-score 标准化
  ts_delta(x, n)         - x - delay(x, n)
  ts_std_dev(x, n)       - n日标准差
  ts_decay_linear(x, n)  - n日线性衰减加权
  ts_sum(x, n)           - n日累加
  ts_delay(x, n)         - 滞后 n 期
  ts_av_diff(x, n)       - x - ts_mean(x, n)

截面算子（无 lookback）:
  rank(x)                - 截面百分位 [0,1]
  group_rank(x, grp)     - 组内排名，grp ∈ {subindustry, industry, sector}
  group_neutralize(x, grp) - 组内中性化
  group_zscore(x, grp)   - 组内 z-score
  winsorize(x, std=n)    - 去极值，如 winsorize(close, std=4)

条件 / 其他:
  trade_when(cond, x, y) - 条件: cond>0.5 取 x，否则 y
  divide(x, y)           - 安全除法
  log(x)                 - 自然对数

标准数据字段（可直接使用）:
  close, open, high, low, volume, vwap, returns, cap
  sales, ebitda, net_income, operating_income, equity, assets
  debt_lt, capex, cashflow_dividends
  implied_volatility_call_120, implied_volatility_put_120
  implied_volatility_call_30, implied_volatility_put_30
  actual_eps_value_quarterly, actual_sales_value_quarterly
  anl4_adjusted_netincome_ft, anl4_bvps_flag, anl4_capex_flag
  fnd6_teq, income

分组标识（仅用于 group_* 算子的第二参数）:
  subindustry, industry, sector
"""


def _parse_ai_alpha_response(raw: str) -> list:
    """
    从 Ollama 返回的原始文本中解析出合法的 alpha 表达式列表。
    策略：逐行扫描，提取看起来像函数调用或算术表达式的行。
    """
    results = []
    if not raw:
        return results

    # 先按 JSON 数组解析试试
    try:
        stripped = raw.strip()
        start = stripped.find('[')
        end = stripped.rfind(']')
        if start != -1 and end != -1:
            candidates = json.loads(stripped[start:end+1])
            if isinstance(candidates, list):
                for c in candidates:
                    if isinstance(c, str) and '(' in c and len(c) > 10:
                        results.append(c.strip())
                if results:
                    return results
    except Exception:
        pass

    # 逐行解析
    for line in raw.splitlines():
        line = line.strip()
        # 去掉序号前缀 "1. " "- " 等
        line = line.lstrip('0123456789.-) ').strip()
        # 去掉代码块标记
        if line.startswith('```') or line.startswith('`'):
            continue
        # 过滤：必须包含括号（函数调用）且长度合理
        if '(' in line and ')' in line and 10 < len(line) < 400:
            # 去掉末尾逗号
            line = line.rstrip(',')
            results.append(line)

    return results[:6]  # 最多取 6 条


# =========================================================
# 量化因子研究主题库（驱动 AI 每代探索不同"新大陆"）
# 每次随机选一个主题，Prompt 指引 AI 在该特定领域生成因子
# 这是解决 SELF_CORRELATION 的根本手段 ——
# 让每代因子来自不同的经济学逻辑家族
# =========================================================
_RESEARCH_THEMES = [
    {
        "name": "📊 波动率曲面 (Vol Surface)",
        "hypothesis": "期权隐含波动率的期限结构和偏斜包含市场对个股未来风险的预期信息",
        "hint": "使用 implied_volatility_call_120, implied_volatility_put_120, implied_volatility_call_30, implied_volatility_put_30 字段，"
                "研究不同期限/方向的隐含波动率差异、比率、变化速度"
    },
    {
        "name": "💰 盈利质量突变 (Earnings Quality Shock)",
        "hypothesis": "资产负债表中权益/收入比例的异常变化预示利润质量的真实改变",
        "hint": "使用 fnd6_teq, income, net_income, operating_income, ebitda 字段，研究比率的时间变化和截面异常"
    },
    {
        "name": "🔄 资本结构动态 (Capital Structure Dynamics)",
        "hypothesis": "公司主动改变杠杆率和资本密度的行为，预示未来股票收益",
        "hint": "使用 debt_lt, equity, assets, cap, capex, cashflow_dividends 字段，"
                "研究杠杆变化速度、资产增长减去收益增长的异常"
    },
    {
        "name": "📈 分析师修正动量 (Analyst Revision Momentum)",
        "hypothesis": "分析师对未来财务预测的修正方向和幅度包含私有信息",
        "hint": "使用 anl4_adjusted_netincome_ft, anl4_bvps_flag, anl4_capex_flag 字段，研究预测变化的持续性"
    },
    {
        "name": "📉 中短期均值回复 (Mean Reversion)",
        "hypothesis": "过度反应导致短期价格偏离基本面，之后发生回复",
        "hint": "使用 close, returns, vwap 字段，研究 ts_zscore, ts_av_diff 等标准化偏差，"
                "然后取负号做反转信号，窗口 5-20 天"
    },
    {
        "name": "🌊 成交量-价格交互 (Volume-Price Interaction)",
        "hypothesis": "成交量与价格变化的组合模式揭示机构资金流向",
        "hint": "使用 volume, close, vwap, returns 字段，研究成交量放大时的价格方向、量价背离"
    },
    {
        "name": "🏭 行业相对强弱 (Sector Relative Strength)",
        "hypothesis": "行业内部相对强度因子比绝对值因子有更强的选股能力",
        "hint": "大量使用 group_rank(x, subindustry), group_zscore(x, industry), group_neutralize(x, sector)，"
                "在组内比较而非全市场比较"
    },
    {
        "name": "📦 现金流生成能力 (Free Cash Flow Generation)",
        "hypothesis": "自由现金流（经营现金流 - 资本支出）的生成能力和稳定性预示价值",
        "hint": "使用 cashflow_dividends, capex, ebitda, sales 字段，研究现金转化率、FCF/市值、FCF 增长稳定性"
    },
    {
        "name": "⚡ 价格动量衰减 (Momentum Decay Structure)",
        "hypothesis": "不同时间窗口的动量信号的半衰期不同，组合多窗口动量可以捕捉趋势转折",
        "hint": "使用 close, returns 字段，构建 ts_decay_linear 或 ts_decay_exp_window 加权的多窗口动量组合"
    },
    {
        "name": "🎯 盈利预期差 (Earnings Surprise)",
        "hypothesis": "实际盈利数据与预期之间的差距（超预期/低于预期）驱动后续股价反应",
        "hint": "使用 actual_eps_value_quarterly, actual_sales_value_quarterly, actual_cashflow_per_share_value_quarterly 字段，"
                "研究实际值的时序变化（ts_delta, ts_av_diff）作为惊喜代理"
    },
    {
        "name": "🔬 微观结构流动性 (Microstructure Liquidity)",
        "hypothesis": "相对成交量（相对于历史均值的异动）反映机构交易意图",
        "hint": "使用 volume, vwap, close 字段，研究成交量相对历史均值的偏离、高低波动率时期的成交量特征"
    },
    {
        "name": "🌐 长期基本面趋势 (Long-Term Fundamental Trend)",
        "hypothesis": "销售额、EBITDA、净利润在更长时间尺度（1-2年）的增长趋势包含价值信息",
        "hint": "使用 sales, ebitda, net_income 字段，使用 ts_delta(x, 252), ts_delta(x, 504) 等长窗口，"
                "研究同比增速的加速/减速"
    },
]


# =========================================================
# ⚙️ Near-Miss 自适应重试配置
# 当因子 fitness 接近但未达标时，自动用不同 settings 重新提交
# 覆盖维度：decay/truncation/neutralization/universe/nanHandling/testPeriod
# =========================================================
# ── Layer-A：Sharpe 优化变体（针对 Sharpe 1.0~1.25，目标推过 1.25）──────────
# 策略：提升信噪比（decay）、缩小宇宙（TOP2000）、细粒度中性化（SUBINDUSTRY）
NEAR_MISS_SHARPE_MIN_A  = 1.0    # Layer-A: Sharpe 下限
NEAR_MISS_SHARPE_MAX_A  = 1.25   # Layer-A: Sharpe 上限（未过1.25门槛）
NEAR_MISS_FITNESS_MIN_A = 0.9    # Layer-A: Fitness 至少要有这么高才值得重试
MAX_NEAR_MISS_A_PER_GEN = 3      # Layer-A 每代最多重试几个

NEAR_MISS_VARIANTS_SHARPE = [
    # 提升 Sharpe 的核心手段：平滑 + 缩小宇宙 + 细粒度中性化
    {"name": "[S]decay=4平滑",        "decay": 4,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[S]TOP2000宇宙",        "decay": 0,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP2000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[S]SUBINDUSTRY",        "decay": 0,  "truncation": 0.08, "neutralization": "SUBINDUSTRY", "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[S]backfill",           "decay": 0,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[S]TOP2000+SUBIND",     "decay": 4,  "truncation": 0.08, "neutralization": "SUBINDUSTRY", "universe": "TOP2000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[S]3年测试期",           "decay": 0,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P3Y0M0D"},
]

# ── Layer-B：Fitness 优化变体（针对 Fitness 0.85~1.0，目标推过 1.0）────────────
# 策略：严格截断（去极值稳fitness）、decay平滑（降波动）、backfill（补数据）
NEAR_MISS_FITNESS_MIN_B = 0.85   # Layer-B: Fitness 下限
NEAR_MISS_FITNESS_MAX_B = 1.0    # Layer-B: Fitness 上限（未过1.0门槛）
NEAR_MISS_SHARPE_MIN_B  = 1.0    # Layer-B: Sharpe 至少要有这么高才值得重试
MAX_NEAR_MISS_B_PER_GEN = 3      # Layer-B 每代最多重试几个

NEAR_MISS_VARIANTS_FITNESS = [
    # 提升 Fitness 的核心手段：严格截断 + 重度平滑 + 组合
    {"name": "[F]truncation=0.05",    "decay": 0,  "truncation": 0.05, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[F]decay=6+截断0.04",   "decay": 6,  "truncation": 0.04, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[F]backfill+截断",      "decay": 0,  "truncation": 0.05, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[F]TOP2000+截断",       "decay": 0,  "truncation": 0.05, "neutralization": "INDUSTRY",    "universe": "TOP2000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[F]全局最优",            "decay": 4,  "truncation": 0.05, "neutralization": "SUBINDUSTRY", "universe": "TOP2000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[F]3年+截断",           "decay": 2,  "truncation": 0.05, "neutralization": "INDUSTRY",    "universe": "TOP3000", "nanHandling": "OFF", "testPeriod": "P3Y0M0D"},
]

_ALPHA_TEMPLATES = [
    # === A. 基本面/市值比率行业排名（借鉴比率结构）===
    "group_rank({F}/cap, subindustry)",
    "group_rank({F}/({F2}+1e-6), industry)",
    "group_neutralize(rank({F}/cap) - rank({F2}/cap), subindustry)",   # 双字段市值比率差
    # === B. 时序排名中性化 ===
    "group_neutralize(ts_rank({F}, {W}), subindustry)",
    "group_neutralize(ts_zscore({F}, {W}), industry)",
    "group_rank(ts_decay_linear(rank({F}), {W}), sector)",              # 衰减加权排名
    # === C. 反转信号（做空长期强势）===
    "-group_rank(ts_rank({F}, 252), sector)",
    "group_neutralize(-ts_av_diff({F}, {W}), subindustry)",
    "group_rank(-ts_zscore({F}, 60), subindustry)",                     # 长窗口反转
    # === D. 变化速度（动量加速度，借鉴tree结构）===
    "group_rank(ts_delta({F}, 5) / (abs({F}) + 1e-6), industry)",
    "group_rank(ts_delta({F}, {W}) / (ts_std_dev({F}, {W}) + 1e-6), sector)",
    "group_neutralize(ts_rank(ts_delta({F}, 5), {W}), subindustry)",   # 嵌套：速度的排名
    # === E. 双字段组合（借鉴brownian motion多字段思路）===
    "group_rank(ts_zscore({F1}, 20) - ts_zscore({F2}, 20), subindustry)",
    "group_neutralize(rank({F1}) - rank({F2}), subindustry)",
    "group_rank(rank({F1}) * rank({F2}), sector)",
    "group_neutralize(ts_rank({F1}, {W}) - ts_rank({F2}, {W}), industry)",   # 双字段时序差
    # === F. 条件触发（借鉴event-driven思路）===
    "trade_when(ts_rank({F1}, 10) > 0.7, group_rank({F2}, subindustry), -1)",
    "trade_when(rank({F1}) > 0.5, ts_rank({F2}, {W}), -ts_rank({F2}, {W}))",
    "trade_when(ts_zscore({F1}, 20) > 1.0, group_neutralize({F2}, subindustry), 0)",  # Z分数条件
    # === G. 波动率/流动性截面 ===
    "group_rank(ts_std_dev({F}, 20), subindustry)",
    "group_neutralize(winsorize(ts_zscore({F}, 60), std=3), subindustry)",
    # === H. 三层嵌套（借鉴algorithmic_generator的tree_generation）===
    "group_rank(ts_rank(ts_delta({F}, 5), {W}), subindustry)",                        # 速度→排名→行业
    "group_neutralize(rank(ts_decay_linear(ts_zscore({F}, 20), 5)), subindustry)",    # Z分数→衰减→排名→中性
    # === I. 蓝海断代/NaN 平滑补丁（如果没数据，就用基本面或价量兜底）===
    "group_neutralize(if_else(is_nan({F}), ts_zscore(assets/cap, 20), {F}), industry)",
    "group_rank(if_else(is_nan({F}), group_rank(sales/cap, subindustry), {F}), subindustry)",
    "group_neutralize(if_else(is_nan(ts_delta({F}, 5)), ts_zscore(-returns, 20), ts_delta({F}, 5)), sector)",
]


# D0 禁用的日频字段（提交前必须净化）
_D0_FORBIDDEN_FIELDS = [
    "returns", "close", "volume", "high", "low", "vwap", "turnover",
    "adv20", "adv60", "adv120",
]

import re as _re

def sanitize_for_d0(expr: str) -> str:
    """
    将 D1 因子表达式净化为 D0 合规版本。
    采用"保护-替换-还原"三步法，避免对已有 ts_delay 二次套娃包装。
    """
    protected = {}
    counter = [0]

    def protect(m):
        key = f"__P{counter[0]}__"
        protected[key] = m.group(0)
        counter[0] += 1
        return key

    # Step 1: 保护所有现有的 ts_delay(...) 调用
    result = _re.sub(r'ts_delay\s*\([^)]+\)', protect, expr)

    # Step 2: 替换裸露的禁用字段
    for field in _D0_FORBIDDEN_FIELDS:
        result = _re.sub(rf'\b{_re.escape(field)}\b', f'ts_delay({field}, 1)', result)

    # Step 3: 还原保护片段
    for key, val in protected.items():
        result = result.replace(key, val)

    return result

# 适合做比率分子/分母的基本面字段（排除价格字段避免量纲问题）
_FUNDAMENTAL_FIELDS = [
    "sales", "ebitda", "net_income", "operating_income", "equity", "assets",
    "debt_lt", "capex", "cashflow_dividends", "income",
    "fnd6_teq", "fnd6_fopo", "fn_liab_fair_val_l1_a", "fn_assets_fair_val_a",
    "actual_eps_value_quarterly", "actual_sales_value_quarterly",
    "actual_cashflow_per_share_value_quarterly", "anl4_adjusted_netincome_ft",
]
_TEMPLATE_WINDOWS = [5, 8, 10, 15, 20, 30, 60]


# =========================================================
# 🤖 Ollama 角色拓展：从“写作机器”升级为“战略顾问”
# 当前只有 generate_ai_alphas() 一个角色（生成4个因子/代）
# 新增充3个角色：
#   [2] ai_strategist  — 每代结束后，分析胜败因子，给下一代推荐战略
#   [3] ai_smart_mutate — 用 AI 对具体因子进行“手术级”精准改良
#   [4] ai_failure_analyst — 分析失败因子，生成修复版本
# =========================================================


def ai_strategist(ollama_manager, winners: list, losers: list,
                  generation: int) -> dict:
    """
    角色 [2] — 战略居间人（每代结束后调用）

    分析本代胜超者和失败者，奏出：
    1. 下一代应该看哪个方向
    2. 建议的具体数据字段
    3. 应该避免哪些结构
    返回 dict: {"direction": str, "fields": list, "avoid": str}
    """
    if ollama_manager is None or not winners:
        return {}

    winners_text = "\n".join(f"  ✅ {w[:120]}" for w in winners[:5])
    losers_text  = "\n".join(f"  ❌ {l[:120]}" for l in losers[:5])

    prompt = f"""你是一位 WorldQuant Brain 量化研究居间人。
我们刚完成第 {generation} 代进化实验。

=== 本代高 Sharpe 胜出因子 ===
{winners_text}

=== 本代低 Sharpe / 失败因子 ===
{losers_text}

请分析胜败模式，给出下一代的三条具体建议：
1. 应该振大哪个研究方向？（一句话）
2. 建议添加哪几个具体的 FASTEXPR 数据字段？（列出 3-5 个字段名）
3. 应该避免哪些结构或特征？（一句话）

只输出 JSON，格式：
{{"direction": "下一代建议方向", "fields": ["字段A", "字段B", ...], "avoid": "应避免结构"}}

JSON:"""

    try:
        raw = ollama_manager.generate(
            prompt,
            system_prompt="你是量化研究居间人。只输出 JSON。",
            temperature=0.5,
            max_tokens=300
        )
        if not raw:
            return {}

        import re
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if m:
            result = json.loads(m.group())
            logging.info(f"💡 AI战略居间: 方向={result.get('direction','')} "
                         f"| 推荐字段={result.get('fields',[])}")
            return result
    except Exception as e:
        logging.debug(f"ai_strategist 异常: {e}")
    return {}


def ai_smart_mutate(ollama_manager, expr: str, hint: str = "") -> str:
    """
    角色 [3] — AI 精准改良工程师

    对一个具体的因子进行“手术级”改良而不是随机变异；
    可以传入战略居间的建议（hint）来引导改良方向。
    返回改良后的因子表达式字符串。
    """
    if ollama_manager is None:
        return expr

    prompt = f"""你是 WorldQuant Brain FASTEXPR 专家。

待改良因子：
  {expr}

{f'改良建议：{hint}' if hint else ''}

请对这个因子进行一个小但有意义的改良：
- 可以替换一个数据字段为更相关的字段
- 可以调整 lookback 窗口参数
- 可以增加一层 ts_zscore 或 group_rank 进行诺尔化
- 保持因子核心逻辑不变

只输出改良后的因子表达式字符串，不要任何解释。

改良后的因子:"""

    try:
        raw = ollama_manager.generate(
            prompt,
            system_prompt="只输出因子表达式，不要解释。",
            temperature=0.4,  # 低温度 = 迎採改良而非大创新
            max_tokens=200
        )
        if raw and len(raw.strip()) > 5:
            improved = raw.strip().split('\n')[0].strip()
            # 基本健康检查：括号平衡
            if improved.count('(') == improved.count(')'):
                logging.info(f"🔧 AI改良: {expr[:60]}... → {improved[:60]}...")
                return improved
    except Exception as e:
        logging.debug(f"ai_smart_mutate 异常: {e}")
    return expr  # fallback 返回原始表达式


def ai_failure_analyst(ollama_manager, failed_alphas: list, n_fixes: int = 3) -> list:
    """
    角色 [4] — AI 失败诊断师

    对少量具体失败的因子，让 AI 分析可能的失败原因
    并生成修复/改写版本加入稭子池。
    """
    if ollama_manager is None or not failed_alphas:
        return []

    sample = failed_alphas[:3]  # 每次最多分析3个（控制 token 消耗）
    sample_text = "\n".join(f"  {i+1}. {s[:150]}" for i, s in enumerate(sample))

    prompt = f"""你是 WorldQuant Brain 因子诊断少将。

以下因子在回测中表现差（低 Sharpe 或失败）：
{sample_text}

请分析常见失败原因（snall window、self-correlation、signal-too-weak等），
然后生成 {n_fixes} 个改写版本，修复这些问题。

只输出 JSON 数组，{n_fixes} 个修复后的因子表达式，不要解释。
["fix1", "fix2", ...]

JSON:"""

    try:
        raw = ollama_manager.generate(
            prompt,
            system_prompt="只输出 JSON 数组。",
            temperature=0.6,
            max_tokens=400
        )
        candidates = _parse_ai_alpha_response(raw)
        if candidates:
            logging.info(f"🔧 AI失败诊断师生成 {len(candidates)} 个修复因子")
        return candidates[:n_fixes]
    except Exception as e:
        logging.debug(f"ai_failure_analyst 异常: {e}")
    return []


def generate_ai_alphas(ollama_manager, knowledge_pool: list, n: int = 4,

                       evaluated_alphas: set = None, db_path: str = None) -> list:
    """
    主题驱动的 AI 原创因子生成。

    每次调用随机选择一个量化研究主题，指引 AI 在该特定经济学领域生成因子。
    不同主题生成的因子在结构上完全不同，从根本上解决 SELF_CORRELATION 问题。

    参数:
        ollama_manager: OllamaManager 实例
        knowledge_pool:  当前遗传精英池（作为"禁止抄袭"的反例）
        n:              目标生成数量
        evaluated_alphas: 已测试因子集合（用于去重检验）
        db_path:        SQLite 路径（用于 CorrelationTracker 过滤）

    返回: 新颖的因子表达式列表
    """
    if ollama_manager is None:
        return []

    # 随机选择本代研究主题
    theme = random.choice(_RESEARCH_THEMES)
    logging.info(f"🎯 本代 AI 探索主题: {theme['name']}")

    # 从知识库中抽几条示例，仅作"避开相似"的参考
    examples = random.sample(knowledge_pool, min(3, len(knowledge_pool)))
    avoid_text = "\n".join(f"  - {e[:120]}" for e in examples)

    prompt = f"""你是一位顶级量化研究员，专精 WorldQuant Brain 平台的 FASTEXPR 语言。
今天的研究课题是：{theme['name']}

===【研究假设】===
{theme['hypothesis']}

===【推荐数据字段和思路】===
{theme['hint']}

=== FASTEXPR 完整语法速查 ===
{_WQ_OPERATOR_CHEATSHEET}

===【已有因子（禁止雷同，必须在结构上完全创新）】===
{avoid_text}

===【设计要求】===
1. 严格基于今天的研究课题，不要偏离主题
2. 因子逻辑必须与已有因子完全不同（不同的数据字段组合 + 不同的算子结构）
3. 括号必须完全平衡
4. 时间序列算子必须带整数 lookback 参数：ts_rank(x, 20) ✓，ts_rank(x) ✗
5. 最外层必须用 group_neutralize(..., subindustry) 或 group_rank(..., subindustry) 中性化
6. 字段只能用语法速查中列出的标准字段名，不要自创字段名

===【输出格式】===
只输出 JSON 数组，{n} 个因子，不要任何解释文字、不要 markdown。
格式：["expr1", "expr2", ...]

JSON 数组:"""

    try:
        logging.info(f"🤖 调用 Ollama ({ollama_manager.model}) 以主题「{theme['name']}」生成 {n} 个新因子...")
        raw = ollama_manager.generate(
            prompt,
            system_prompt="你是量化因子设计专家。只输出 JSON 数组格式，不输出任何解释或 markdown。",
            temperature=0.82,   # 略高温度确保多样性
            max_tokens=700
        )
        if not raw:
            logging.warning("🤖 Ollama 返回空响应")
            return []

        candidates = _parse_ai_alpha_response(raw)
        logging.info(f"🤖 Ollama 初步生成 {len(candidates)} 个因子")

        # ---- 用 CorrelationTracker 过滤高相关候选（减少 SELF_CORRELATION）----
        if db_path and candidates:
            try:
                from generation_two.core.mining.correlation_tracker import CorrelationTracker
                tracker = CorrelationTracker(db_path=db_path)
                # 以 (template, region) 格式传入
                candidate_pairs = [(c, "USA") for c in candidates]
                filtered = tracker.get_low_correlation_templates(
                    candidate_pairs,
                    max_correlation=0.5,  # 超过 50% 相关的直接丢弃
                    limit=n + 2
                )
                if filtered:
                    candidates = [t for t, r, corr in filtered]
                    logging.info(f"🔗 CorrelationTracker 过滤后剩余 {len(candidates)} 个低相关因子")
            except Exception as e:
                logging.debug(f"CorrelationTracker 过滤跳过: {e}")

        # 去掉已评估过的
        if evaluated_alphas:
            candidates = [c for c in candidates if c not in evaluated_alphas]

        return candidates[:n]

    except Exception as e:
        logging.warning(f"🤖 Ollama 生成因子异常: {e}")
        return []


def generate_template_alphas(n: int, wq_fields: list, evaluated_alphas: set = None, wq_fields_by_category: dict = None) -> list:
    """
    从 _ALPHA_TEMPLATES 模板库随机填充字段，生成结构多样的候选因子。

    每次随机选一个模板骨架 + 从 wq_fields 随机填充 {F}/{F1}/{F2} 占位符，
    确保每代都有完全不同结构的因子进入候选池，与遗传变异互补。

    参数:
        n: 目标生成数量
        wq_fields: 完整字段列表（2663个，从缓存加载）
        evaluated_alphas: 已评估因子集合（用于去重，避免重复提交）
    返回: 填充后的因子表达式列表
    """
    results = []
    all_fields = wq_fields if wq_fields else _FUNDAMENTAL_FIELDS
    # 基本面字段优先用于双字段模板的 F2（分母/配对字段）
    fund_fields = [f for f in _FUNDAMENTAL_FIELDS if f in all_fields] or _FUNDAMENTAL_FIELDS

    # 准备数据集类别列表用于轮询（Round-Robin），确保每个 Dataset 必定被选中
    category_list = list(wq_fields_by_category.keys()) if wq_fields_by_category else []
    if category_list:
        random.shuffle(category_list)  # 打乱顺序，避免每次生成的头几个类别都是固定的

    attempts = 0
    while len(results) < n and attempts < n * 15:
        attempts += 1
        try:
            template = random.choice(_ALPHA_TEMPLATES)
            window = random.choice(_TEMPLATE_WINDOWS)

            # {F}/{F1} 强制轮询所有数据集类别（你说的“每一个data set都要选一个”）
            if category_list:
                chosen_cat = category_list[len(results) % len(category_list)]
                cat_fields = wq_fields_by_category[chosen_cat]
                f1 = random.choice(cat_fields) if cat_fields else random.choice(all_fields)
            else:
                f1 = random.choice(all_fields)
            # {F2} 从基本面字段中选（避免与 f1 重复，且适合做配对/比率）
            f2_pool = [f for f in fund_fields if f != f1] or fund_fields
            f2 = random.choice(f2_pool)

            expr = template
            expr = expr.replace("{F1}", f1).replace("{F2}", f2)
            expr = expr.replace("{F}", f1)   # {F} 用 F1 填充
            expr = expr.replace("{W}", str(window))

            # 基本合法性检查
            if expr.count("(") != expr.count(")"):
                continue
            if len(expr) < 10 or len(expr) > 400:
                continue
            if evaluated_alphas and expr in evaluated_alphas:
                continue

            results.append(expr)
        except Exception:
            continue

    if results:
        logging.info(f"🧱 模板工厂生成了 {len(results)} 个结构化因子")
    return results


# =========================================================
# 🟢 D0 腿生成函数 v2
# 来源平垄：D0专属模板（70%）+ Ollama D0生成（30%）
# 已删除 D1精英净化来源（机械修改后仍是套小模拟、容易返回 429/self-corr）
# =========================================================
def generate_d0_leg(n: int, wq_fields: list, wq_fields_by_category: dict,
                    knowledge_pool: list, evaluated_alphas: set,
                    ollama_manager=None) -> list:
    """生成 D0（Delay=0）合规的因子批次 v2"""
    results = []

    # 构建 D0 专属字段采样池（按类别）
    fund_pool = [f for f in wq_fields
                 if wq_fields_by_category.get(f) == "fundamental"] or _FUNDAMENTAL_FIELDS
    blue_pool = [f for f in wq_fields
                 if wq_fields_by_category.get(f) in ("sentiment", "socialmedia", "option", "news")]
    analyst_pool = [f for f in wq_fields
                    if wq_fields_by_category.get(f) == "analyst"]

    # D0 模板窗口（不需要太长，D0 是日内交易信号）
    d0_windows = [5, 10, 20, 60, 120]

    # --- 来源 1：D0 专属模板填充（目标 70%）---
    # 每次同时随机决定 FUND_F + ANALYST_F 以支持双字段模板
    target_from_template = int(n * 0.7) + 2
    attempts = 0
    while len(results) < target_from_template and attempts < n * 30:
        attempts += 1
        try:
            tmpl = random.choice(_D0_ALPHA_TEMPLATES)
            expr = tmpl

            # 随机选双字段（保证每次不同)
            fund_f  = random.choice(fund_pool)   if fund_pool   else "sales"
            blue_f  = random.choice(blue_pool)   if blue_pool   else None
            anlst_f = random.choice(analyst_pool) if analyst_pool else None

            if "{FUND_F}" in expr:
                expr = expr.replace("{FUND_F}", fund_f)
            if "{BLUE_F}" in expr:
                if not blue_f:
                    continue
                expr = expr.replace("{BLUE_F}", blue_f)
            if "{ANALYST_F}" in expr:
                if not anlst_f:
                    continue
                expr = expr.replace("{ANALYST_F}", anlst_f)

            # 去重 + 括号检查
            if expr.count("(") != expr.count(")"):
                continue
            if len(expr) < 15 or len(expr) > 450:
                continue
            if expr in evaluated_alphas or expr in results:
                continue

            results.append(expr)
        except Exception:
            continue

    # --- 来源 2：Ollama D0 专属生成（30%，用高质量 Prompt）---
    if ollama_manager and len(results) < n:
        need = n - len(results)
        try:
            d0_system = (
                "You are a WorldQuant Brain Delay-0 alpha expert.\n"
                "STRICT RULES:\n"
                "1. NEVER use raw: close, volume, returns, high, low, vwap, turnover.\n"
                "2. Price/volume data MUST be wrapped: ts_delay(close,1), ts_delay(volume,1), ts_delay(returns,1).\n"
                "3. You MAY freely use: open, cap, and ALL fundamental/analyst/sentiment/option fields.\n"
                "4. Every alpha MUST combine at least TWO independent signals (e.g. gap signal + fundamental, or analyst + lagged price).\n"
                "5. Outer layer MUST be group_neutralize or group_rank.\n"
                "Output ONLY a JSON array of expressions."
            )
            d0_prompt = (
                f"Generate {need} Delay-0 alpha expressions that combine:\n"
                "- An opening gap signal (open/ts_delay(close,1)-1) OR lagged price/volume (ts_delay(x,1))\n"
                "- AND a fundamental/analyst/sentiment/option field as the primary anchor signal.\n"
                "Examples of good D0 patterns:\n"
                "  group_rank((open/ts_delay(close,1)-1) * rank(sales/cap), subindustry)\n"
                "  trade_when(ts_rank(anl4_adjusted_netincome_ft,10)>0.7, group_rank(open/ts_delay(close,1)-1,subindustry), 0)\n"
                "  group_neutralize(ts_rank(implied_volatility_call_30,20)*(open/ts_delay(close,1)-1), subindustry)\n"
                f"Output JSON array of {need} expressions:"
            )
            raw = ollama_manager.generate(
                d0_prompt,
                system_prompt=d0_system,
                temperature=0.75,
                max_tokens=600
            )
            if raw:
                from generation_two.continuous_evolution import _parse_ai_alpha_response
                ai_d0 = _parse_ai_alpha_response(raw)
                for a in ai_d0:
                    a = sanitize_for_d0(a)  # 防漏网之鱼
                    if a not in evaluated_alphas and a not in results and len(a) > 15:
                        results.append(a)
        except Exception as e:
            logging.debug(f"[D0腿] Ollama D0生成跳过: {e}")

    logging.info(f"\ud83d\udfe2 [D0腿] 生成了 {len(results)} 个 D0 候选因子 (模板={min(len(results), target_from_template)} + AI={max(0, len(results)-target_from_template)})")
    return results[:n]


# =========================================================
# 其余工具函数（保持不变）
# =========================================================

def check_final_submission_status(sess, alpha_id, template):
    """Wait and poll until SELF_CORRELATION check finishes PENDING state"""
    logging.info(f"⏳ Background Tracker: Following {alpha_id} for self-correlation results...")
    for _ in range(60): # Wait up to 30 mins
        time.sleep(30)
        try:
            poll = sess.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}")
            if poll.status_code == 200:
                data = poll.json()
                checks = data.get('is', {}).get('checks', [])
                
                corr_check = next((c for c in checks if c.get('name') == 'SELF_CORRELATION'), None)
                if corr_check:
                    res = corr_check.get('result')
                    if res == 'FAIL':
                        logging.warning(f"❌ FATAL: Self-correlation failed for {alpha_id}: {template}")
                        return
                    elif res == 'PASS':
                        success_msg = f"🏆🏆🏆 BINGO! 100% SUCCESS! Alpha ID: {alpha_id} | Blueprint: {template}"
                        logging.warning(success_msg)
                        
                        # Guard against accidental closure: save to desktop
                        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "success_alphas.txt")
                        with open(desktop_path, "a", encoding="utf-8") as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {success_msg}\n")
                        return
        except Exception:
            pass

def inject_neutralization(base_alpha: str) -> str:
    """Intelligently wraps formula in neutralization to avoid LOW_SUB_UNIVERSE_SHARPE"""
    if "group_neutralize" in base_alpha or "group_rank" in base_alpha:
        return base_alpha
    return f"group_neutralize({base_alpha}, subindustry)"

def main():
    # ── 初始化认证 ──────────────────────────────────────────
    cm = CredentialManager(base_path=os.path.dirname(os.path.abspath(__file__)))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        logging.error("Failed to authenticate.")
        return

    sess = cm.get_session()
    logging.info("🌟 Connected to WQ Brain for Infinite Evolution!")

    # ── 初始化三大可选模块（任一失败均不影响主流程）──
    validator = _build_validator()
    ollama_manager = _build_ollama_manager()
    storage = _build_storage()

    # ── 初始化模拟器 ─────────────────────────────────────────
    region_configs = {}
    region_configs["USA"] = type('RegionConfig', (), {
        'region': "USA",
        'universe': "TOP3000",
        'delay': 1
    })()

    tester = SimulatorTester(session=sess, region_configs=region_configs)
    tester.executor = ThreadPoolExecutor(max_workers=3)

    settings = SimulationSettings(
        region="USA",
        testPeriod="P5Y0M0D",
        neutralization="INDUSTRY",
        truncation=0.08
    )

    # ── 从数据库加载历史精英因子作为启动种子 ────────────────────
    historical_seeds = _load_historical_seeds(storage, min_sharpe=1.25, limit=10)

    # ── 从数据库恢复已评估因子集合，避免跨会话重复提交 ──────────
    evaluated_alphas = set()
    if storage:
        try:
            import sqlite3
            conn = sqlite3.connect(storage.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT template FROM backtest_results WHERE region = "USA"')
            for (tmpl,) in cursor.fetchall():
                if tmpl:
                    evaluated_alphas.add(tmpl)
            conn.close()
            logging.info(f"📚 从数据库恢复了 {len(evaluated_alphas)} 条已评估因子（本代将跳过）")
        except Exception as e:
            logging.warning(f"恢复已评估集合失败（将重新测试历史因子）: {e}")

    # ── Initial Seeds ────────────────────────────────────────

    knowledge_pool = [
        # ============================================================
        # === A. 基本面经典因子 (Fundamental Classics) ================
        # ============================================================
        "ts_mean(anl4_adjusted_netincome_ft, 5)",
        "anl4_adjusted_netincome_ft * anl4_capex_flag",
        "trade_when(ts_rank(ts_std_dev(returns,10),252)<0.9, anl4_bvps_flag, -1)",
        "ts_mean(actual_dividend_value_quarterly, 5)",
        "ts_mean(actual_cashflow_per_share_value_quarterly, 5)",
        "ts_mean(actual_eps_value_quarterly, 5)",
        "ts_mean(actual_sales_value_annual, 5)",
        "ts_mean(actual_sales_value_quarterly, 5)",
        "group_rank(ts_rank(0.6 * (capex)/cap + 0.4 * (cashflow_dividends)/cap, 5), subindustry)",
        # --- 盈利增长 (BARRA Growth Proxy) ---
        "group_neutralize(rank(0.24 * ts_delta(net_income, 252)/abs(ts_delay(net_income, 252)) + 0.47 * ts_delta(sales, 252)/abs(ts_delay(sales, 252))), subindustry)",
        # --- 营业收入动量 (Operating Income Momentum) ---
        # H: 若当前营业收入高于过去一年历史，买入；反之卖出
        "ts_rank(operating_income, 252)",
        # --- FFO 偿债能力 (Funds From Operations Quality) ---
        # H: 公司 FFO/长期债务比率越高，财务健康度越强
        "rank(fnd6_fopo / debt_lt)",

        # ============================================================
        # === B. 杠杆 + 资产密度 (Leverage & Asset Density) ==========
        # ============================================================
        "group_zscore(ts_mean(winsorize(log(divide(debt_lt, equity)), std=4), 180), industry)",
        "ts_decay_linear(group_rank(ts_zscore(ts_delta(divide(assets, cap), 2), 20), sector), 5)",
        "group_rank(ts_zscore(ts_delta(divide(assets, cap), 2), 20), sector)",
        # --- 公允价值负债风险 (Fair Value Liabilities Risk) ---
        # H: 公允价值负债近期上升 → 未来成本上升 → 做空信号
        "-ts_rank(fn_liab_fair_val_l1_a, 252)",
        # --- 资产公允价值 vs EBIT 增长潜力 (Asset FV vs EBIT) ---
        # H: 高资产公允价值但低 EBIT → 成长型公司，加倍做空低 EBIT
        "trade_when(group_rank(fn_assets_fair_val_a, industry) > 0.5, (-group_rank(fnd2_ebitdm, industry) - group_rank(fnd2_ebitfr, industry)) * 2, -group_rank(fnd2_ebitdm, industry) - group_rank(fnd2_ebitfr, industry))",
        # --- 短期流动性 (Short-Term Liquidity) ---
        # H: 现金/短期债务比率高 → 偿债能力强 → 安全做多
        "group_zscore(cash_st / debt_st, industry)",

        # ============================================================
        # === C. 期权隐含波动率 (Options Implied Volatility) ==========
        # ============================================================
        "ts_rank(implied_volatility_call_120, 30)",
        "group_neutralize(ts_decay_linear(winsorize(implied_volatility_call_120 - implied_volatility_put_120, std=3), 8), subindustry)",
        "group_neutralize(implied_volatility_call_120 - implied_volatility_put_120, bucket(rank(cap), range='0.1,1,0.1'))",
        "group_neutralize(ts_decay_linear(rank(rank(implied_volatility_call_30) * rank(operating_income / sales)), 8), subindustry)",

        # ============================================================
        # === D. 社交媒体情绪 (Social Sentiment) =====================
        # ============================================================
        # H: 社媒讨论量越高的股票往往是表现差的股票，做空高讨论量个股
        "-scl12_buzz",
        # H: 热度极高 + 近期涨幅极高 = 过热危险信号，反转做空
        "group_neutralize(ts_decay_linear(rank(-1 * returns * rank(vec_sum(scl12_alltype_buzzvec))), 6), subindustry)",

        # ============================================================
        # === E. 价格/成交量微观结构 (Price-Volume Microstructure) ===
        # ============================================================
        # H: vwap 和收盘价的差距反映日内资金流向，衰减加权平滑噪声
        "ts_decay_linear((vwap - close) / close, 2)",
        # --- 动量反转 (Momentum Reversal) ---
        "-1*ts_sum(close / ts_delay(close, 1) - 1, 20)",

        # ============================================================
        # === F. FX 管理能力 (Foreign Currency Risk Management) =======
        # ============================================================
        # H: 税后外汇折算调整收益高 → 财务风险管理有效 → 做多
        "fn_oth_income_loss_fx_transaction_and_tax_translation_adj_a",

        # ============================================================
        # === G. 盈利质量复合因子 (Earnings Quality Composite) ========
        # ============================================================
        "group_neutralize(ts_decay_linear(group_rank(trade_when(volume > ts_mean(volume, 20), -1 * ts_av_diff(fnd6_teq / income, 10), -1), subindustry), 6), subindustry)",
        "group_neutralize(ts_decay_linear(rank(rank(ts_delay(ebitda, 252) - ts_delay(ebitda, 505)) + group_rank(ts_delay(ebitda, 252) - ts_delay(ebitda, 505), subindustry)), 8), subindustry)",
    ]
    
    # 历史精英因子注入到种子池（放在手写种子之后，不覆盖）
    if historical_seeds:
        knowledge_pool = list(set(knowledge_pool + historical_seeds))
        logging.info(f"🧬 种子池扩充至 {len(knowledge_pool)} 条（含 {len(historical_seeds)} 条历史精英）")
    
    # ===== 遗传算法工具箱 =====
    
    # ── 动态加载完整字段表（从 WQ Brain API 缓存，约 140 个字段）────
    cached_fields, wq_fields_by_category = _load_wq_fields_from_cache("USA", 1, "TOP3000")
    # 内置关键字段（确保核心字段一定存在）
    _builtin_fields = [
        # -- 价格 & 成交量 --
        "close", "open", "high", "low", "volume", "vwap", "returns", "cap",
        # -- 基本面 --
        "sales", "ebitda", "net_income", "operating_income", "debt_lt", "equity",
        "assets", "capex", "cashflow_dividends", "income",
        # -- 期权波动率 --
        "implied_volatility_call_120", "implied_volatility_put_120",
        "implied_volatility_call_30", "implied_volatility_put_30",
        # -- 分析师预测 & 实际数据 --
        "actual_dividend_value_quarterly", "actual_eps_value_quarterly",
        "actual_sales_value_quarterly", "actual_cashflow_per_share_value_quarterly",
        "anl4_adjusted_netincome_ft", "anl4_capex_flag", "anl4_bvps_flag",
        # -- 资产负债表深度字段 --
        "fnd6_teq", "fnd6_fopo",
        "fn_liab_fair_val_l1_a", "fn_assets_fair_val_a",
        "fnd2_ebitdm", "fnd2_ebitfr",
        "cash_st", "debt_st",
        "fn_oth_income_loss_fx_transaction_and_tax_translation_adj_a",
        # -- 社交媒体情绪 --
        "scl12_buzz",
    ]
    # 合并：缓存字段优先，内置字段作为保底
    wq_fields = list(dict.fromkeys(cached_fields + _builtin_fields))  # 去重保序
    logging.info(f"📊 变异/交叉字段池: 共 {len(wq_fields)} 个字段")

    # ── 按类别分组的字段字典（用于均匀采样）──────────────────────────
    # 解决问题：Fundamental 斉1204个占45%，直接随机采样会大量重复挖最卷的类别
    # 解决方案：先随机选类别（各类别等概率）→再从该类别中随机选字段
    # 这样蓝海类别（Sentiment 17个、Social Media 20个、Model 40个）就不会被埋没
    if wq_fields_by_category:
        # 补充内置字段到对应类别中确保内置字段也参与均匀采样
        # 简单地把内置字段加入局部分组（如果不在已知类别）
        builtin_set = set(cached_fields)
        for bf in _builtin_fields:
            if bf not in builtin_set:
                wq_fields_by_category.setdefault('pv', []).append(bf)
        logging.info(
            f"📋 字段类别分布: " +
            " | ".join(
                f"{k}({len(v)}个)"
                for k, v in sorted(wq_fields_by_category.items(), key=lambda x: -len(x[1]))
            )
        )
    else:
        # 如果无类别信息，退化为全平池采样（兼容旧逻辑）
        wq_fields_by_category = {}
        logging.warning("⚠️ 无字段类别信息，将使用全平池随机采样（会偏向Fundamental）")

    
    wq_ts_ops = ["ts_mean", "ts_rank", "ts_zscore", "ts_delta", "ts_std_dev", 
                 "ts_decay_linear", "ts_decay_exp_window", "ts_sum", "ts_av_diff"]
    wq_group_ops = ["group_rank", "group_zscore", "group_neutralize"]
    wq_neutralizers = ["subindustry", "sector", "industry"]
    
    def smart_mutate(expr: str) -> str:
        """真正做字段/算子/参数替换的变异"""
        import re
        mutated = expr
        roll = random.random()
        
        if roll < 0.35:
            # 字段替换：按类别均匀采样（解决Fundamental 1204个/45%导致蓝海类别被埋没的问题）
            # 75%概率：先随机选类别（各类别等概率），再从该类别选字段 → 蓝海优先
            # 25%概率：全平池随机（保留多样性）
            present = [f for f in wq_fields if f in mutated]
            if present:
                old_f = random.choice(present)
                if wq_fields_by_category and random.random() < 0.75:
                    chosen_cat = random.choice(list(wq_fields_by_category.keys()))
                    cat_fields = [f for f in wq_fields_by_category[chosen_cat] if f != old_f]
                    new_f = random.choice(cat_fields) if cat_fields else random.choice(
                        [f for f in wq_fields if f != old_f])
                else:
                    new_f = random.choice([f for f in wq_fields if f != old_f])
                mutated = mutated.replace(old_f, new_f, 1)

        elif roll < 0.55:
            # 参数微调：把数字 ±30%
            def tweak(m):
                n = int(m.group())
                if n < 1: return m.group()
                delta = max(1, int(n * 0.3))
                return str(max(1, n + random.choice([-delta, delta])))
            mutated = re.sub(r'(?<!\w)\d+(?!\w)', tweak, mutated)
        elif roll < 0.75:
            # 外层包裹：加一层时间序列算子
            op = random.choice(wq_ts_ops)
            window = random.choice([5, 8, 10, 15, 20, 30])
            mutated = f"{op}({mutated}, {window})"
        else:
            # 中性化方式变异
            neutralizer = random.choice(wq_neutralizers)
            if "group_neutralize" in mutated:
                for n in wq_neutralizers:
                    mutated = mutated.replace(n, neutralizer)
            else:
                mutated = f"group_neutralize({mutated}, {neutralizer})"
        return mutated
    
    def crossover_factors(parent_a: str, parent_b: str) -> str:
        """真正的跨因子杂交：把两个不同家族的因子进行 DNA 重组"""
        roll = random.random()
        
        if roll < 0.25:
            # 算术组合：加权平均
            w = round(random.uniform(0.3, 0.7), 2)
            child = f"{w} * ({parent_a}) + {round(1-w, 2)} * ({parent_b})"
        elif roll < 0.45:
            # 乘法交互：捕捉非线性协同效应
            child = f"rank({parent_a}) * rank({parent_b})"
        elif roll < 0.60:
            # 条件触发：用 A 的信号强度来决定是否执行 B
            child = f"trade_when(rank({parent_a}) > 0.5, {parent_b}, -1)"
        elif roll < 0.75:
            # 差值信号：A 和 B 的相对强弱
            child = f"({parent_a}) - ({parent_b})"
        else:
            # 嵌套排名组合
            grp = random.choice(wq_neutralizers)
            child = f"group_rank(rank({parent_a}) + rank({parent_b}), {grp})"
        
        return inject_neutralization(child)
    
    # ── 主进化循环 ───────────────────────────────────────────
    generation = 1
    
    # ── 初始化 Near-Miss 重试队列 ─────────────────────────────────
    near_miss_queue = []

    # ── AI 后台预生成系统：模拟等待期间同步生成下一代因子 ────────────
    _prefetch_lock = threading.Lock()
    _prefetch_ai_pool = []      # 后台预生成的因子缓冲池
    _prefetch_strategy_fields = [] # 后台生成的战略字段缓冲
    _prefetch_thread = None     # 后台线程引用

    def _background_prefetch(high_performers_snap, losers_snap, pool_snap, gen_num):
        """后台预生成线程：执行所有的 AI 任务（战略、诊断、变异、原创生成）
        利用 API 轮询等待时间，实现 AI 与模拟真正并行。"""
        try:
            strategy = {}
            if ollama_manager and high_performers_snap:
                strategy = ai_strategist(ollama_manager, high_performers_snap, losers_snap, gen_num)
                if strategy.get("fields"):
                    with _prefetch_lock:
                        _prefetch_strategy_fields.clear()
                        _prefetch_strategy_fields.extend([f for f in strategy["fields"] if isinstance(f, str)])
                    logging.info(f"🧭 [后台AI] 战略字段已缓冲: {_prefetch_strategy_fields[:5]}")
            
            if ollama_manager and losers_snap:
                fixed = ai_failure_analyst(ollama_manager, losers_snap, n_fixes=5)
                if fixed:
                    with _prefetch_lock:
                        _prefetch_ai_pool.extend(fixed)
                    logging.info(f"🔧 [后台AI] 诊断生成缓冲: {len(fixed)} 条修复因子")
            
            if ollama_manager and high_performers_snap:
                direction_hint = strategy.get("direction", "")
                improved_list = []
                for elite in high_performers_snap[:4]:
                    improved = ai_smart_mutate(ollama_manager, elite, hint=direction_hint)
                    if improved != elite:
                        improved_list.append(improved)
                if improved_list:
                    with _prefetch_lock:
                        _prefetch_ai_pool.extend(improved_list)
                    logging.info(f"✨ [后台AI] 精准改良缓冲: {len(improved_list)} 条变异因子")
            
            # 主题探索原创生成
            if ollama_manager:
                theme = random.choice(_AI_STRATEGY_THEMES)
                db_path_for_tracker = storage.db_path if storage else None
                new_alphas = generate_ai_alphas(
                    ollama_manager, pool_snap[:15], n=15, theme=theme,
                    evaluated_alphas=evaluated_alphas,
                    db_path=db_path_for_tracker
                )
                if new_alphas:
                    with _prefetch_lock:
                        _prefetch_ai_pool.extend(new_alphas)
                    logging.info(f"🤖 [后台AI] 原创预生成缓冲: {len(new_alphas)} 条主题因子 ({theme})")
        except Exception as e:
            logging.warning(f"🤖 [后台AI任务] 异常（不影响主流程）: {e}")

    prev_high_performers = []
    prev_losers = []
    d0_knowledge_pool = []   # D0 独立精英池（不混入 D1 遗传池）
    settings = SimulationSettings(
        region="USA", universe="TOP3000", delay=1, decay=0,
        neutralization="INDUSTRY", truncation=0.08,
        nanHandling="ON", testPeriod="P5Y0M0D"
    )
    d0_settings = SimulationSettings(
        region="USA", universe="TOP3000", delay=0, decay=0,
        neutralization="INDUSTRY", truncation=0.08,
        nanHandling="ON", testPeriod="P5Y0M0D"
    )

    while True:

        logging.info(f"========= GENERATION {generation} =========")
        alphas_to_test = []

        # ── 优先消耗上一代后台预生成的 AI 因子及战略（如有）─────
        with _prefetch_lock:
            if _prefetch_strategy_fields:
                wq_fields[:] = _prefetch_strategy_fields + [f for f in wq_fields if f not in _prefetch_strategy_fields]
                logging.info(f"🧭 [主线程] 应用后台缓冲战略字段: {_prefetch_strategy_fields[:5]}")
                _prefetch_strategy_fields.clear()

            if _prefetch_ai_pool:
                prefetched = [inject_neutralization(a) for a in _prefetch_ai_pool
                              if a not in evaluated_alphas]
                alphas_to_test.extend(prefetched)
                logging.info(f"  🤖 [预加载] 消耗后台预生成缓冲: {len(prefetched)} 个 AI 因子")
                _prefetch_ai_pool.clear()

        pool_snapshot = knowledge_pool[:21]

        # ━━━ 三条腿因子生成 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 腿一：D0 因子（~8个，delay=0 专属，和 D1 低相关）
        d0_candidates = generate_d0_leg(
            8, wq_fields, wq_fields_by_category,
            d0_knowledge_pool or knowledge_pool, evaluated_alphas, ollama_manager
        )

        # 腿二：遗传裂变（~8个，D1，单因子变异+杂交）
        d1_genetic = []
        for seed in pool_snapshot[:8]:
            neutralized_seed = inject_neutralization(seed)
            d1_genetic += [
                neutralized_seed,
                f"ts_decay_exp_window({neutralized_seed}, 5, 2)",
                inject_neutralization(smart_mutate(seed)),
            ]
        num_crossovers = min(8, len(pool_snapshot))
        for _ in range(num_crossovers):
            pa = random.choice(pool_snapshot)
            pb = random.choice([s for s in pool_snapshot if s != pa] or pool_snapshot)
            d1_genetic.append(crossover_factors(pa, pb))

        # 腿三：蓝海模板工厂（~9个，D1，Round-Robin 均衡采样）
        d1_blueocean = generate_template_alphas(9, wq_fields, evaluated_alphas, wq_fields_by_category)
        d1_blueocean = [inject_neutralization(a) for a in d1_blueocean]

        # 预加载后台 AI 缓冲的 D1 因子
        with _prefetch_lock:
            if _prefetch_strategy_fields:
                wq_fields[:] = _prefetch_strategy_fields + [f for f in wq_fields if f not in _prefetch_strategy_fields]
                logging.info(f"🧭 [主线程] 应用后台缓冲战略字段: {_prefetch_strategy_fields[:5]}")
                _prefetch_strategy_fields.clear()
            if _prefetch_ai_pool:
                prefetched_d1 = [inject_neutralization(a) for a in _prefetch_ai_pool if a not in evaluated_alphas]
                d1_genetic.extend(prefetched_d1)
                logging.info(f"  🤖 [预加载] 消耗后台AI缓冲: {len(prefetched_d1)} 个 D1 因子")
                _prefetch_ai_pool.clear()

        logging.info(f"  📊 D0腿={len(d0_candidates)} | 裂变腿={len(d1_genetic)} | 蓝海腿={len(d1_blueocean)}")

        # 旧逻辑兼容：把所有 D1 因子合并打包
        d1_combined = d1_genetic + d1_blueocean
        alphas_to_test = d1_combined  # 留给下方 validator 使用
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # ---- 阶段 4：Validator 过滤非法表达式 ----
        validated_alphas = []
        rejected_count = 0
        for expr in set(alphas_to_test):
            is_valid, cleaned = validate_alpha(validator, expr)
            if is_valid:
                validated_alphas.append(cleaned)
            else:
                rejected_count += 1
        
        if rejected_count > 0:
            logging.info(f"  🛡️  Validator 拦截了 {rejected_count} 条非法因子（已过滤）")

        # ---- 去重（跳过已评估过的）----
        unique_alphas = []
        for x in validated_alphas:
            if x not in evaluated_alphas:
                unique_alphas.append(x)
                evaluated_alphas.add(x)
                
        if not unique_alphas:
            logging.info("Diversity collapsed. Introducing fresh blood...")
            # 多样性崩溃时也尝试用 AI 补充
            ai_emergency = generate_ai_alphas(ollama_manager, pool_snapshot, n=5)
            if ai_emergency:
                unique_alphas = [inject_neutralization(a) for a in ai_emergency]
            else:
                engine = AlphaEvolutionEngine()
                unique_alphas = [engine.mutate(knowledge_pool[0]) for _ in range(5)]
            
        # Hard limit：D1 最多 17 个，D0 最多 8 个
        unique_alphas = unique_alphas[:17]
        logging.info(f"Submitting D1={len(unique_alphas)} + D0={len(d0_candidates)} to simulator.")

        try:
            logging.info(f"  🎯 提交 D1={len(unique_alphas)} 个 + D0={len(d0_candidates)} 个，双引擎并发...")
            # 两套 Settings 同时飞出，不额外增加等待时间
            futures_d1 = tester.simulate_batch(unique_alphas, "USA", settings) if unique_alphas else []
            futures_d0 = tester.simulate_batch(d0_candidates, "USA", d0_settings) if d0_candidates else []
            all_futures = futures_d1 + futures_d0

            # 记录哪些 futures 属于 D0 批次
            _d0_template_set = set(d0_candidates)

            # ✨ 模拟提交后立刻启动后台 AI 预生成线程
            if ollama_manager and (_prefetch_thread is None or not _prefetch_thread.is_alive()):
                _prefetch_thread = threading.Thread(
                    target=_background_prefetch,
                    args=(prev_high_performers, prev_losers, pool_snapshot, generation),
                    daemon=True
                )
                _prefetch_thread.start()
                logging.info("🤖 [后台AI任务] Ollama 开始在后台诊断、总结、生成下一代因子...")

            results = tester.wait_for_results(all_futures, timeout=600)
        except Exception as e:
            logging.error(f"⚠️ WQ Matrix Connection Error or Rate Limit (429) hit: {e}. Sleeping 30s to cool down.")
            time.sleep(30)
            continue
        
        high_performers = []
        d0_high_performers = []

        for res in results:
            if not res.success or res.sharpe is None or res.fitness is None:
                pass
            elif abs(res.sharpe) > 1.25 and abs(res.fitness) > 1.0:
                # 遇到极度负数的因子，进行反向（乘 -1）
                if res.sharpe < 0:
                    inverted_template = f"-1 * ({res.template})"
                    res.template = inverted_template
                    res.sharpe = abs(res.sharpe)
                    res.fitness = abs(res.fitness)
                    logging.info(f"✅ INVERTED NEGATIVE SHARPE: {res.template} -> {res.sharpe}")
                else:
                    logging.info(f"✅ HIGH SHARPE: {res.template} -> {res.sharpe}")

                # D0 / D1 分流
                is_d0 = res.template in _d0_template_set
                if is_d0:
                    d0_high_performers.append(res.template)
                    logging.info(f"🟢 D0精英: Sharpe={res.sharpe:.3f} | {res.template[:60]}")
                else:
                    high_performers.append(res.template)

                # 判断来源标签
                is_d0 = res.template in _d0_template_set
                source = "D0-Template" if is_d0 else ("AI-Ollama" if res.template in locals().get("ai_alphas_neutralized", []) else "Genetic-D1")
                _log_discovery(res.template, res.sharpe, res.fitness, res.alpha_id, source=source)

                logging.warning(
                    f"📋 待手动提交: Alpha ID={res.alpha_id} | "
                    f"Sharpe={res.sharpe:.3f} | Fitness={res.fitness:.3f} | "
                    f"来源={source} | 表达式={res.template[:80]}"
                )

            # 让 Validator 从每次模拟失败中学习（如果有错误信息）
            if not res.success and res.error_message and validator:
                try:
                    validator.learn_from_simulation_error(res.template, res.error_message)
                except Exception:
                    pass

        # 💾 把本代所有仿真结果持久化到 SQLite
        if storage and results:
            stored_count = storage.store_batch(results)
            logging.info(f"💾 本代 {stored_count}/{len(results)} 条结果已存入数据库")
        
        # ━━━ Near-Miss 双层自适应重试系统 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Layer-A：Sharpe 1.0~1.25 → 用提升Sharpe的settings推过1.25
        # Layer-B：Fitness 0.85~1.0 → 用提升Fitness的settings推过1.0
        def _run_near_miss_layer(candidates, variants, layer_name, timeout=350):
            """通用Near-Miss重试执行器"""
            if not candidates:
                return
            logging.info(f"  [{layer_name}] 发现 {len(candidates)} 个候选，开始重试...")
            nm_futures, nm_names = [], []
            for nm_res in candidates:
                variant = random.choice(variants)
                retry_settings = SimulationSettings(
                    region="USA",
                    universe=variant["universe"],
                    delay=1,
                    decay=variant["decay"],
                    neutralization=variant["neutralization"],
                    truncation=variant["truncation"],
                    nanHandling=variant["nanHandling"],
                    testPeriod=variant["testPeriod"],
                )
                logging.info(
                    f"    [{layer_name}] sharpe={nm_res.sharpe:.3f} fitness={nm_res.fitness:.3f} "
                    f"变体={variant['name']} | {nm_res.template[:55]}"
                )
                nm_futures.append(tester.simulate_template_concurrent(nm_res.template, "USA", retry_settings))
                nm_names.append(variant["name"])
            try:
                nm_results = tester.wait_for_results(nm_futures, timeout=timeout)
                for nm_r, vname in zip(nm_results, nm_names):
                    if nm_r.success and nm_r.sharpe is not None and nm_r.fitness is not None and abs(nm_r.sharpe) > 1.25 and abs(nm_r.fitness) > 1.0:
                        if nm_r.sharpe < 0:
                            nm_r.template = f"-1 * ({nm_r.template})"
                            nm_r.sharpe = abs(nm_r.sharpe)
                            nm_r.fitness = abs(nm_r.fitness)
                            logging.warning(
                                f"  🎯 [{layer_name}] 重试成功并反转负夏普！变体={vname} "
                                f"Sharpe={nm_r.sharpe:.3f} Fitness={nm_r.fitness:.3f}"
                            )
                        else:
                            logging.warning(
                                f"  🎯 [{layer_name}] 重试成功！变体={vname} "
                                f"Sharpe={nm_r.sharpe:.3f} Fitness={nm_r.fitness:.3f}"
                            )
                        high_performers.append(nm_r.template)
                        _log_discovery(nm_r.template, nm_r.sharpe, nm_r.fitness,
                                       nm_r.alpha_id, source=f"{layer_name}-{vname}")
                    else:
                        logging.info(f"    [{layer_name}] 未过线: sharpe={nm_r.sharpe:.3f} fitness={nm_r.fitness:.3f}")
                if storage:
                    storage.store_batch(nm_results)
            except Exception as e:
                logging.warning(f"[{layer_name}] 重试异常（不影响主流程）: {e}")

        # ── Layer-A：Sharpe 1.0~1.25 优化 ───────────────────────────────
        layer_a = [
            res for res in results
            if res.success and res.template
            and res.sharpe is not None and res.fitness is not None
            and NEAR_MISS_SHARPE_MIN_A <= abs(res.sharpe) < NEAR_MISS_SHARPE_MAX_A
            and abs(res.fitness) >= NEAR_MISS_FITNESS_MIN_A
        ][:MAX_NEAR_MISS_A_PER_GEN]

        # ── Layer-B：Fitness 0.85~1.0 优化 ──────────────────────────────
        layer_b = [
            res for res in results
            if res.success and res.template
            and res.fitness is not None and res.sharpe is not None
            and NEAR_MISS_FITNESS_MIN_B <= abs(res.fitness) < NEAR_MISS_FITNESS_MAX_B
            and abs(res.sharpe) >= NEAR_MISS_SHARPE_MIN_B
            # 避免与Layer-A重复
            and not (NEAR_MISS_SHARPE_MIN_A <= abs(res.sharpe) < NEAR_MISS_SHARPE_MAX_A
                     and abs(res.fitness) >= NEAR_MISS_FITNESS_MIN_A)
        ][:MAX_NEAR_MISS_B_PER_GEN]

        if layer_a or layer_b:
            total = len(layer_a) + len(layer_b)
            logging.info(f"🔄 Near-Miss双层重试: Layer-A(Sharpe优化)={len(layer_a)}个, Layer-B(Fitness优化)={len(layer_b)}个, 共{total}个")
            _run_near_miss_layer(layer_a, NEAR_MISS_VARIANTS_SHARPE, "Sharpe优化")
            _run_near_miss_layer(layer_b, NEAR_MISS_VARIANTS_FITNESS, "Fitness优化")
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # ━━━ 代后 AI 顾问环节 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 收集本代的败者（低 Sharpe 的因子），供 AI 分析
        losers = [r.template for r in results
                  if r.success and r.sharpe < 1.0 and r.template][:8]

        # 更新上一代数据供下次后台线程使用
        prev_high_performers = high_performers
        prev_losers = losers
        # 同步的 AI 诊断和策略任务已全部移入后台线程 _background_prefetch
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # Self-Optimization / Genetic Feedback mechanism
        if high_performers:
            knowledge_pool = high_performers + knowledge_pool
            knowledge_pool = list(set(knowledge_pool))[:10]

        # D0 精英池独立更新（不混入 D1 遗传池）
        if d0_high_performers:
            d0_knowledge_pool = d0_high_performers + d0_knowledge_pool
            d0_knowledge_pool = list(dict.fromkeys(d0_knowledge_pool))[:10]
            logging.info(f"🟢 D0精英池更新: {len(d0_high_performers)} 条新精英 | 池总量={len(d0_knowledge_pool)}")

        logging.info(
            f"Generation {generation} completed. "
            f"D1精英={len(high_performers)} D0精英={len(d0_high_performers)}. "
            f"Sleeping 5 seconds..."
        )
        time.sleep(5)
        generation += 1


if __name__ == "__main__":
    main()
