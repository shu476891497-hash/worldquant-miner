import json
import logging
import os
import sys
import time
import threading
import random
import re
from pathlib import Path
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
# ④-B 蓝海字段池构建（userCount低、alphaCount低、但覆盖率够的字段）
#     这些字段竞争度极低，生成的因子更不容易 SELF_CORRELATION
# =========================================================
def _build_blue_ocean_pool(cache_path: str, max_users: int = 30,
                           max_alphas: int = 50, min_coverage: float = 0.30) -> list:
    """
    从 data_fields_cache JSON 中筛选蓝海字段。
    筛选条件：userCount < max_users AND alphaCount < max_alphas AND coverage >= min_coverage
    返回: list[dict] 每个元素含 id, category, userCount, alphaCount, coverage
    """
    try:
        if not os.path.exists(cache_path) or os.path.getsize(cache_path) < 10:
            return []
        with open(cache_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            return []

        pool = []
        # 排除纯标识符/布尔字段
        _SKIP_PREFIXES = ('top', 'isin', 'cusip', 'sedol', 'ticker', 'currency',
                          'exchange', 'country', 'is_')
        for item in raw:
            fid = item.get('id', '')
            if not fid or any(fid.startswith(p) for p in _SKIP_PREFIXES):
                continue
            uc = item.get('userCount', 9999)
            ac = item.get('alphaCount', 9999)
            cov = item.get('coverage', 0)
            if uc < max_users and ac < max_alphas and cov >= min_coverage:
                cat_raw = item.get('category', {})
                cat_name = cat_raw.get('name', '?') if isinstance(cat_raw, dict) else str(cat_raw)
                pool.append({
                    'id': fid,
                    'category': cat_name,
                    'userCount': uc,
                    'alphaCount': ac,
                    'coverage': cov,
                })
        # 按 userCount 升序（最冷门的优先）
        pool.sort(key=lambda x: (x['userCount'], x['alphaCount']))
        if pool:
            logging.info(
                f"🌊 蓝海字段池: {len(pool)} 个 (users<{max_users}, alphas<{max_alphas}, cov>={min_coverage}) | "
                f"头部: {[p['id'] for p in pool[:5]]}"
            )
        return pool
    except Exception as e:
        logging.warning(f"蓝海字段池构建失败: {e}")
        return []


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
# 🔁 AI缓存闭环 — 三层复用历史高分因子
#    [1] 启动时注入知识池（genetic evolution 的优质种子）
#    [2] 每代"来源 0"直接复用 + 变异（不花 DeepSeek 的钱）
#    [3] AI Prompt 里注入历史成功样本（让模型学习正确方向）
# =========================================================
def _load_ai_cache_seeds(min_sharpe: float = 0.5, limit: int = 30) -> list:
    """
    读取 ai_alpha_cache.jsonl，按 Sharpe 降序返回高分 AI 因子列表。
    返回格式: [(expr, theme), ...]
    """
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_alpha_cache.jsonl")
    if not os.path.exists(cache_path):
        return []
    candidates = []
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    sharpe = entry.get("sharpe")
                    expr   = entry.get("expr", "")
                    if sharpe is not None and sharpe >= min_sharpe and len(expr) > 15:
                        candidates.append((sharpe, expr, entry.get("theme", "")))
                except Exception:
                    continue
        candidates.sort(key=lambda x: x[0], reverse=True)
        seeds = [(expr, theme) for _, expr, theme in candidates[:limit]]
        if seeds:
            top = candidates[0][0] if candidates else 0
            logging.info(f"[AI缓存] 加载 {len(seeds)} 条高分历史因子 (min_sharpe={min_sharpe}, 最高 Sharpe={top:.3f})")
        return seeds
    except Exception as e:
        logging.debug(f"[AI缓存] 加载失败: {e}")
        return []


# =========================================================
# ② AI Manager — 优先使用 DeepSeek API，回退到本地 Ollama
#    DeepSeek-V3 (deepseek-chat): ~¥0.5/M input, ¥2/M output，速度快，质量远超本地小模型
#    配置文件: generation_two/ai_config.json
# =========================================================
def _build_ollama_manager():
    """
    初始化 AI 生成器。
    优先级：DeepSeek API (云端) > 本地 Ollama
    DeepSeek-V3 推荐用 deepseek-chat，性价比最高。
    """
    # ---- 优先尝试 DeepSeek API ----
    try:
        ai_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_config.json")
        if os.path.exists(ai_config_path):
            with open(ai_config_path, "r", encoding="utf-8") as f:
                ai_cfg = json.load(f)
            if ai_cfg.get("provider") == "deepseek" and ai_cfg.get("api_key"):
                from generation_two.ollama.deepseek_manager import DeepSeekManager
                manager = DeepSeekManager(
                    api_key=ai_cfg["api_key"],
                    model=ai_cfg.get("model", "deepseek-chat"),
                    timeout=ai_cfg.get("timeout", 60),
                    max_retries=ai_cfg.get("max_retries", 3),
                )
                if manager._check_availability():
                    logging.info(f"[DeepSeek] 已连接，使用模型: {manager.model} (性价比最优)")
                    return manager
                else:
                    logging.warning("[DeepSeek] API Key 验证失败，回退到本地 Ollama")
    except Exception as e:
        logging.warning(f"[DeepSeek] 初始化失败，回退到本地 Ollama: {e}")

    # ---- 回退到本地 Ollama ----
    try:
        from generation_two.ollama.ollama_manager import OllamaManager
        manager = OllamaManager(
            base_url="http://localhost:11434",
            model="qwen2.5-coder:7b",
            timeout=90,
            max_retries=2,
            rate_limit=1.0
        )
        if manager._check_availability():
            logging.info(f"[Ollama] 已连接，使用模型: {manager.model}")
            return manager
        else:
            logging.warning("[Ollama] 服务不可用，AI 生成功能已禁用")
            return None
    except Exception as e:
        logging.warning(f"[Ollama] 初始化失败，AI 生成功能已禁用: {e}")
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
    # ════════════════════════════════════════════════════════════════
    # 🌊 蓝海研究主题（覆盖 News/Sentiment/Social/Model/Event 等低竞争数据集）
    # ════════════════════════════════════════════════════════════════
    {
        "name": "📰 新闻情绪动量 (News Sentiment Momentum)",
        "hypothesis": "新闻发布密度和情绪极值包含短期方向性信息，新闻VWAP的变化速度预示价格趋势",
        "hint": "使用 nws12_afterhsz_prevwap, news_all_vwap, news_mov_vol, nws12_afterhsz_nstories 字段，"
                "研究新闻VWAP的时序动量、新闻数量异常、新闻波动率极值信号"
    },
    {
        "name": "📱 社交媒体热度异常 (Social Buzz Anomaly)",
        "hypothesis": "社交媒体讨论量的突然变化揭示零售投资者情绪极端，可作反转信号",
        "hint": "使用 scl12_buzz, scl12_buzzvec, scl12_alltype_buzzvec 字段，"
                "研究buzz的时序z-score、buzz与returns的负相关、buzz极值反转"
    },
    {
        "name": "🎭 复合情绪信号 (Composite Sentiment Signal)",
        "hypothesis": "多来源情绪指标（新闻+社媒+分析师）的分歧或共振包含alpha信息",
        "hint": "使用 snt5_* 情绪字段和 news_* 新闻字段，研究情绪指标之间的相关性变化、"
                "情绪极端值与基本面的背离"
    },
    {
        "name": "🤖 模型因子交互 (Model-Derived Factor Interaction)",
        "hypothesis": "WQ预构建的模型因子（如多因子模型残差）与原始基本面的偏差揭示定价错误",
        "hint": "使用 mdl3_* 模型字段，研究模型信号的时序排名、模型信号与行业内排名的交互"
    },
    {
        "name": "📋 事件驱动季报 (Event-Driven Quarterly Reports)",
        "hypothesis": "季报事件前后的财务指标异常变化（非连续性）预示后续股价反应",
        "hint": "使用 fnd6_newqeventv110_* 和 fnd6_eventv110_* 字段（如 pncwiepq, rcaq, prcepsq），"
                "这些是极低竞争度字段(2-5用户)，研究事件变量的时序排名和截面异常"
    },
    {
        "name": "🎯 期权Greeks截面 (Option Greeks Cross-Section)",
        "hypothesis": "期权Greeks（delta/gamma/theta/vega）的截面分布揭示做市商对冲行为和隐含方向",
        "hint": "使用 opt11_delta, opt11_gamma, put_breakeven_*, call_breakeven_* 字段，"
                "研究Greeks的行业内排名、Greeks之间的比率信号"
    },
    {
        "name": "📊 分析师指引差异 (Analyst Guidance Divergence)",
        "hypothesis": "管理层指引值与分析师预期之间的差距（guidance gap）包含内部信息",
        "hint": "使用 anl4_fsguidanceafv4_minguidance, anl4_fsguidanceafv4_maxguidance, "
                "operating_profit_before_depr_amort_max_guidance_qtr 字段，"
                "研究指引范围的宽度变化、指引与实际值的偏差"
    },
    {
        "name": "🌐 宏观政策敏感度 (Macro Policy Sensitivity)",
        "hypothesis": "个股对宏观政策风险指标（GPR/EPU）的敏感度差异预示不同宏观环境下的收益",
        "hint": "使用 mdf_gpr, mdf_epu 等宏观字段，与基本面字段交互，"
                "研究个股收益率与宏观指标的ts_corr及其变化"
    },
]


# =========================================================
# D0 专属研究主题（供 Ollama D0 因子生成使用）
# D0 因子的核心信号：跳空缺口 open/ts_delay(close,1)-1、隔夜收益率、
# 滞后价量、以及这些信号与基本面/情绪的交互
# =========================================================
_D0_RESEARCH_THEMES = [
    {
        "name": "🌅 跳空缺口信号 (Opening Gap Signal)",
        "hypothesis": "隔夜信息在开盘跳空中被定价，跳空方向与基本面/情绪的交互预测日内收益",
        "hint": "使用 open/ts_delay(close,1)-1 作为核心跳空信号，结合 fundamental/analyst 字段，"
                "研究跳空幅度与盈利质量、杠杆率、现金流的关系"
    },
    {
        "name": "📰 隔夜新闻定价 (Overnight News Pricing)",
        "hypothesis": "新闻和社交媒体情绪在隔夜累积，次日开盘价反映这些信息的边际定价",
        "hint": "使用 news/sentiment/socialmedia 类别字段的 ts_rank/ts_zscore，与 open/ts_delay(close,1) 交互，"
                "研究情绪极值时跳空信号的预测能力变化"
    },
    {
        "name": "⚡ 期权隐含波动率日内择时 (IV Intraday Timing)",
        "hypothesis": "IV 的时序变化方向暗示做市商对次日波动的预期，可作为 D0 择时信号",
        "hint": "使用 implied_volatility_call_120, implied_volatility_put_120, implied_volatility_call_30, implied_volatility_put_30，"
                "研究 IV 变化速度与跳空信号的组合"
    },
    {
        "name": "🔮 分析师修正 × 跳空反应 (Analyst Revision × Gap Reaction)",
        "hypothesis": "分析师预测修正后的首个交易日，跳空方向和幅度揭示市场对修正的真实反应",
        "hint": "使用 anl4_adjusted_netincome_ft, anl4_bvps_flag, anl4_capex_flag 的 ts_delta/days_from_last_change，"
                "与 open/ts_delay(close,1) 交互"
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

# =========================================================
# D0 专属 Near-Miss 重试配置
# D0 门槛更高：Sharpe >= 2.0, Fitness >= 1.3
# 因此 D0 Near-Miss 捕获"差一点就到"的 D0 因子进行参数优化
# =========================================================
# -- D0 Layer-C：Sharpe 1.5~2.0 优化（目标推过 2.0）--
D0_NEAR_MISS_SHARPE_MIN  = 1.5
D0_NEAR_MISS_SHARPE_MAX  = 2.0
D0_NEAR_MISS_FITNESS_REQ = 1.0
D0_MAX_NEAR_MISS_SHARPE  = 4

D0_NEAR_MISS_VARIANTS_SHARPE = [
    # D0 寻婁: 优先缩小宇宙至 TOP1000，确保流动性
    {"name": "[D0-S]TOP1000",          "decay": 0,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-S]decay=6+TOP1000",  "decay": 6,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-S]SUBINDUSTRY+1000","decay": 4,  "truncation": 0.08, "neutralization": "SUBINDUSTRY", "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-S]TOP500+SUBIND",    "decay": 6,  "truncation": 0.06, "neutralization": "SUBINDUSTRY", "universe": "TOP500",  "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-S]backfill+TOP1000", "decay": 4,  "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[D0-S]3Y+TOP1000",       "decay": 4,  "truncation": 0.06, "neutralization": "SUBINDUSTRY", "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P3Y0M0D"},
]

# -- D0 Layer-D：Fitness 1.0~1.3 优化（目标推过 1.3）--
D0_NEAR_MISS_FIT_MIN     = 1.0
D0_NEAR_MISS_FIT_MAX     = 1.3
D0_NEAR_MISS_SHARPE_REQ  = 1.5
D0_MAX_NEAR_MISS_FIT     = 4

D0_NEAR_MISS_VARIANTS_FITNESS = [
    {"name": "[D0-F]trunc=0.04+1000",  "decay": 0,  "truncation": 0.04, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-F]decay=8+TOP1000",  "decay": 8,  "truncation": 0.03, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-F]TOP500+trunc",     "decay": 4,  "truncation": 0.04, "neutralization": "INDUSTRY",    "universe": "TOP500",  "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-F]SUBIND+1000",      "decay": 4,  "truncation": 0.04, "neutralization": "SUBINDUSTRY", "universe": "TOP1000", "nanHandling": "OFF", "testPeriod": "P5Y0M0D"},
    {"name": "[D0-F]backfill+TOP1000", "decay": 6,  "truncation": 0.04, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[D0-F]extreme+500",      "decay": 8,  "truncation": 0.03, "neutralization": "SUBINDUSTRY", "universe": "TOP500",  "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
]

# =========================================================
# Layer-E: VRP 精英种子专属优化层（用户指定 implied_vol/parkinson_vol）
# 基准: TOP1000 + truncation=0.1, 围绕该基准做全参数扫描
# =========================================================
VRP_SEED_EXPR = "implied_volatility_call_120 / parkinson_volatility_120"
VRP_NEAR_MISS_SHARPE_MIN = 1.3   # D0 VRP 开始 near-miss 的 Sharpe 门槛
VRP_MAX_NEAR_MISS       = 6      # 每代最多重试 VRP 变体数

VRP_NEAR_MISS_VARIANTS = [
    # 围绕 TOP1000 + trunc=0.1 做全参数扫描
    {"name": "[VRP]base-TOP1000-t0.1",      "decay": 0, "truncation": 0.10, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[VRP]SUBIND-TOP1000-t0.1",    "decay": 0, "truncation": 0.10, "neutralization": "SUBINDUSTRY", "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[VRP]decay4-TOP1000-t0.1",    "decay": 4, "truncation": 0.10, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[VRP]TOP500-t0.1",            "decay": 0, "truncation": 0.10, "neutralization": "SUBINDUSTRY", "universe": "TOP500",  "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[VRP]TOP1000-t0.08",          "decay": 0, "truncation": 0.08, "neutralization": "INDUSTRY",    "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P5Y0M0D"},
    {"name": "[VRP]TOP1000-3Y-t0.1",        "decay": 0, "truncation": 0.10, "neutralization": "SUBINDUSTRY", "universe": "TOP1000", "nanHandling": "ON",  "testPeriod": "P3Y0M0D"},
]

# VRP 候选表达式池（供 near-miss 重试时选用）
VRP_EXPR_POOL = [
    "group_neutralize(rank(implied_volatility_call_120 / parkinson_volatility_120), subindustry)",
    "group_neutralize(-rank(implied_volatility_call_120 / parkinson_volatility_120), subindustry)",
    "group_neutralize(ts_rank(implied_volatility_call_120 / parkinson_volatility_120, 60), subindustry)",
    "group_neutralize(ts_zscore(implied_volatility_call_120 / parkinson_volatility_120, 60), subindustry)",
    "group_neutralize(ts_delta(implied_volatility_call_120 / parkinson_volatility_120, 5), subindustry)",
    "group_neutralize(rank(implied_volatility_put_120 / parkinson_volatility_120), subindustry)",
    "group_neutralize(rank(implied_volatility_call_120 / implied_volatility_put_120), subindustry)",
    "trade_when(ts_rank(implied_volatility_call_120 / parkinson_volatility_120, 60) > 0.8, group_neutralize(-rank(implied_volatility_call_120 / parkinson_volatility_120), subindustry), 0)",
    "trade_when(ts_delay(volume,1) / adv20 > 1.5, group_neutralize(rank(implied_volatility_call_120 / parkinson_volatility_120), subindustry), 0)",
]

_ALPHA_TEMPLATES = [
    # ════════════════════════════════════════════════════════════════
    # 全新模板库 v3 —— 极致蓝海版
    # 核心: ① 零硬编码热门字段 ② 全部用占位符 {F}/{F1}/{F2}
    # ③ 算子骨架 100% 互不相同 ④ 大量冷门/生僻算子
    # ════════════════════════════════════════════════════════════════

    # ── S1. 时序回归残差 ──
    "group_rank(ts_regression({F1}, {F2}, {W}, 0, 2), subindustry)",
    "group_neutralize(ts_regression({F1}, {F2}, {W}, 1, 2), subindustry)",

    # ── S2. 协方差 / 相关性 ──
    "group_neutralize(ts_corr({F1}, {F2}, {W}), subindustry)",
    "group_rank(ts_covariance({F1}, {F2}, {W}) / (ts_std_dev({F1}, {W}) + 1e-6), subindustry)",

    # ── S3. 非线性幂次 signed_power ──
    "group_rank(signed_power(ts_zscore({F}, {W}), 0.5), subindustry)",
    "group_neutralize(signed_power(rank({F1}) - rank({F2}), 3), subindustry)",

    # ── S4. 跳跃衰减 / 驼峰 ──
    "group_rank(jump_decay({F}, {W}, 0.5, 252), subindustry)",
    "group_neutralize(hump({F}, 0.3) * rank({F2}), subindustry)",

    # ── S5. 分位数 / 第k元素 ──
    "group_rank(ts_quantile({F}, 0.25, {W}), subindustry)",
    "group_neutralize(kth_element({F}, 3, {W}), subindustry)",
    "group_rank(ts_quantile({F}, 0.75, {W}) - ts_quantile({F}, 0.25, {W}), subindustry)",

    # ── S6. 连乘累积 ──
    "group_rank(ts_product({F1}/({F2}+1e-6), {W}), subindustry)",

    # ── S7. 极值时间位置 ──
    "group_neutralize(ts_arg_max({F}, {W}) - ts_arg_min({F}, {W}), subindustry)",
    "group_rank(({W} - ts_arg_max({F}, {W})) / {W}, subindustry)",
    "group_neutralize(ts_arg_min({F1}, {W}) - ts_arg_min({F2}, {W}), subindustry)",

    # ── S8. 数据质量 / NaN ──
    "group_neutralize(ts_count_nans({F}, {W}), subindustry)",
    "group_rank(days_from_last_change({F}), subindustry)",
    "group_neutralize(last_diff_value({F}, {W}), subindustry)",

    # ── S9. 条件触发（纯占位符版）──
    "trade_when(ts_rank({F1}, {W}) > 0.8, group_rank({F2}, subindustry), 0)",
    "trade_when(ts_zscore({F1}, {W}) > 1.5, group_neutralize(-rank({F2}), subindustry), 0)",
    "trade_when(ts_zscore({F1}, {W}) < -1.5, group_rank({F2}, subindustry), 0)",

    # ── S10. 比率信号 ──
    "group_rank({F1} / ({F2} + 1e-6), subindustry)",
    "group_neutralize(ts_delta({F1} / ({F2} + 1e-6), {W}), subindustry)",

    # ── S11. 缺失值补丁 ──
    "group_neutralize(if_else(is_nan({F1}), ts_zscore({F2}, 20), {F1}), industry)",

    # ── S12. 波动率截面 ──
    "group_rank(ts_std_dev({F}, {W}) / (ts_mean(abs({F}), {W}) + 1e-6), subindustry)",

    # ── S13. 二阶差分 ──
    "group_neutralize(ts_delta(ts_delta({F}, 5), 5), subindustry)",
    "group_rank(ts_delta({F}, 5) / (ts_std_dev({F}, {W}) + 1e-6), subindustry)",

    # ── S14. 非线性交互残差 ──
    "group_neutralize(rank({F1}) * rank({F2}) - rank({F1} * {F2}), subindustry)",

    # ── S15. 加权衰减混合 ──
    "ts_decay_exp_window(0.6 * group_rank({F1}, subindustry) + 0.4 * group_neutralize({F2}, subindustry), {W}, 2)",

    # ══════════ v3 新增冷门算子骨架 ══════════

    # ── S16. 信息比率 ts_ir ──
    "group_rank(ts_ir({F}, {W}), subindustry)",
    "group_neutralize(ts_ir({F1}, {W}) - ts_ir({F2}, {W}), subindustry)",

    # ── S17. 偏度 / 峰度 ──
    "group_rank(ts_skewness({F}, {W}), subindustry)",
    "group_neutralize(ts_kurtosis({F}, {W}), subindustry)",

    # ── S18. ts_moment (高阶矩) ──
    "group_rank(ts_moment({F}, {W}, 3), subindustry)",
    "group_neutralize(ts_moment({F1}, {W}, 4) - ts_moment({F2}, {W}, 4), subindustry)",

    # ── S19. 截面分位数 (group_quantile) ──
    "group_rank(group_quantile({F}, 0.1, subindustry), sector)",
    "group_neutralize(group_rank({F1}, sector) - group_rank({F2}, sector), subindustry)",

    # ── S20. ts_theilsen (稳健回归) ──
    "group_rank(ts_theilsen({F1}, {F2}, {W}), subindustry)",
    "group_neutralize(ts_theilsen({F}, ts_step(1), {W}), subindustry)",

    # ── S21. 离散度 / 集中度 ──
    "group_rank(ts_herfindahl({F}, {W}), subindustry)",
    "group_neutralize(ts_entropy({F}, {W}), subindustry)",

    # ── S22. ts_decay_linear (线性衰减) ──
    "ts_decay_linear({F}, {W})",
    "group_neutralize(ts_decay_linear(rank({F1}) * rank({F2}), {W}), subindustry)",

    # ── S23. 多重条件嵌套 ──
    "trade_when(ts_rank({F1}, {W}) > 0.9 & ts_rank({F2}, {W}) < 0.1, rank({F1})-rank({F2}), 0)",

    # ── S24. zscore of rank spread ──
    "group_rank(ts_zscore(group_rank({F1}, subindustry) - group_rank({F2}, subindustry), {W}), sector)",

    # ── S25. 加速度 × 非线性 ──
    "group_neutralize(signed_power(ts_delta(ts_delta({F}, 5), 5), 0.5), subindustry)",
]

# ★★★ 骨架工厂扩容：从 40 个手工骨架 → 2200+ 个有金融意义的骨架 ★★★
# ★★★ 冷门算子优先：90% 概率抽冷门骨架（pasteurize/bucket/kth_element/ts_entropy...）★★★
_sample_skeleton_func = None  # 冷门优先抽样函数
try:
    from generation_two.skeleton_factory import get_skeleton_pool as _get_factory_skeletons
    from generation_two.skeleton_factory import sample_skeleton as _sample_skeleton_func_impl
    _sample_skeleton_func = _sample_skeleton_func_impl
    _factory_pool = _get_factory_skeletons()
    _existing = set(_ALPHA_TEMPLATES)
    _new_skeletons = [s for s in _factory_pool if s not in _existing]
    _ALPHA_TEMPLATES.extend(_new_skeletons)
    logging.info(f"🏭 骨架工厂: 手工={len(_existing)} + 工厂={len(_new_skeletons)} = 总计 {len(_ALPHA_TEMPLATES)} 个骨架")
except ImportError:
    try:
        from skeleton_factory import get_skeleton_pool as _get_factory_skeletons
        from skeleton_factory import sample_skeleton as _sample_skeleton_func_impl
        _sample_skeleton_func = _sample_skeleton_func_impl
        _factory_pool = _get_factory_skeletons()
        _existing = set(_ALPHA_TEMPLATES)
        _new_skeletons = [s for s in _factory_pool if s not in _existing]
        _ALPHA_TEMPLATES.extend(_new_skeletons)
        logging.info(f"🏭 骨架工厂: 手工={len(_existing)} + 工厂={len(_new_skeletons)} = 总计 {len(_ALPHA_TEMPLATES)} 个骨架")
    except ImportError:
        logging.warning("⚠️ skeleton_factory.py 未找到，使用原始 40 个手工骨架")


_D0_ALPHA_TEMPLATES = [
    # ════════════════════════════════════════════════════════════════
    # D0 模板库 v3 —— 极致蓝海版
    # 核心: 全部用 {FUND_F}/{BLUE_F}/{ANALYST_F} 占位符填充
    # 去除所有 open/close/volume 硬编码，用 {FUND_F} 代替
    # ════════════════════════════════════════════════════════════════

    # ── D0-S1. 纯回归残差 ──
    "group_rank(ts_regression(ts_delay({FUND_F},1), ts_delay({BLUE_F},1), {W}, 0, 2), subindustry)",
    "group_neutralize(ts_regression(ts_delay({FUND_F},1), ts_delay({ANALYST_F},1), {W}, 1, 2), subindustry)",

    # ── D0-S2. 跨字段相关/协方差 ──
    "group_rank(ts_corr(ts_delay({FUND_F},1), ts_delay({BLUE_F},1), {W}), subindustry)",
    "group_neutralize(ts_covariance(ts_delay({FUND_F},1), ts_delay({ANALYST_F},1), {W}), subindustry)",

    # ── D0-S3. 非线性幂次 ──
    "group_rank(signed_power(rank(ts_delay({FUND_F},1)) - rank(ts_delay({BLUE_F},1)), 2), subindustry)",
    "group_neutralize(signed_power(ts_zscore(ts_delay({FUND_F},1), {W}), 0.5), subindustry)",

    # ── D0-S4. 极值时间位置 ──
    "group_neutralize(ts_arg_max(ts_delay({FUND_F},1), {W}) - ts_arg_min(ts_delay({BLUE_F},1), {W}), subindustry)",
    "group_rank(({W} - ts_arg_max(ts_delay({FUND_F},1), {W})) / {W}, subindustry)",

    # ── D0-S5. 分位数 / 第k元素 ──
    "group_neutralize(ts_quantile(ts_delay({FUND_F},1), 0.25, {W}), subindustry)",
    "group_rank(kth_element(ts_delay({FUND_F},1), 3, {W}), subindustry)",
    "group_rank(ts_quantile(ts_delay({BLUE_F},1), 0.75, {W}) - ts_quantile(ts_delay({BLUE_F},1), 0.25, {W}), subindustry)",

    # ── D0-S6. 数据质量 / NaN ──
    "group_neutralize(ts_count_nans(ts_delay({BLUE_F},1), {W}), subindustry)",
    "group_rank(days_from_last_change({FUND_F}), subindustry)",

    # ── D0-S7. 条件触发 ──
    "trade_when(ts_rank(ts_delay({BLUE_F},1), {W}) > 0.8, group_rank(ts_delay({FUND_F},1), subindustry), 0)",
    "trade_when(ts_zscore(ts_delay({FUND_F},1), {W}) > 1.5, group_neutralize(-rank(ts_delay({BLUE_F},1)), subindustry), 0)",

    # ── D0-S8. 比率信号 ──
    "group_rank(ts_delay({FUND_F},1) / (ts_delay({ANALYST_F},1) + 1e-6), subindustry)",
    "group_neutralize(ts_delta(ts_delay({FUND_F},1) / (ts_delay({BLUE_F},1) + 1e-6), 5), subindustry)",

    # ── D0-S9. 二阶差分 ──
    "group_neutralize(ts_delta(ts_delta(ts_delay({FUND_F},1), 5), 5), subindustry)",
    "group_rank(ts_delta(ts_delay({FUND_F},1), 5) / (ts_std_dev(ts_delay({FUND_F},1), {W}) + 1e-6), subindustry)",

    # ── D0-S10. 衰减复合 ──
    "ts_decay_exp_window(0.6 * group_rank(ts_delay({FUND_F},1), subindustry) + 0.4 * group_neutralize(ts_delay({BLUE_F},1), subindustry), {W}, 2)",

    # ── D0-S11. 连乘 ──
    "group_rank(ts_product(ts_delay({FUND_F},1) / (ts_delay({ANALYST_F},1) + 1e-6), {W}), subindustry)",

    # ── D0-S12. 波动率截面 ──
    "group_rank(ts_std_dev(ts_delay({FUND_F},1), {W}) / (ts_mean(abs(ts_delay({FUND_F},1)), {W}) + 1e-6), subindustry)",

    # ══════════ v3 新增: 极致冷门算子 ══════════

    # ── D0-S13. 信息比率 ──
    "group_rank(ts_ir(ts_delay({FUND_F},1), {W}), subindustry)",
    "group_neutralize(ts_ir(ts_delay({FUND_F},1), {W}) - ts_ir(ts_delay({BLUE_F},1), {W}), subindustry)",

    # ── D0-S14. 偏度 / 峰度 ──
    "group_rank(ts_skewness(ts_delay({FUND_F},1), {W}), subindustry)",
    "group_neutralize(ts_kurtosis(ts_delay({BLUE_F},1), {W}), subindustry)",

    # ── D0-S15. 高阶矩 ──
    "group_rank(ts_moment(ts_delay({FUND_F},1), {W}, 3), subindustry)",

    # ── D0-S16. 稳健回归 ts_theilsen ──
    "group_rank(ts_theilsen(ts_delay({FUND_F},1), ts_delay({BLUE_F},1), {W}), subindustry)",
    "group_neutralize(ts_theilsen(ts_delay({FUND_F},1), ts_step(1), {W}), subindustry)",

    # ── D0-S17. 熵 / 集中度 ──
    "group_rank(ts_herfindahl(ts_delay({FUND_F},1), {W}), subindustry)",
    "group_neutralize(ts_entropy(ts_delay({BLUE_F},1), {W}), subindustry)",

    # ── D0-S18. 线性衰减 ──
    "ts_decay_linear(group_rank(ts_delay({FUND_F},1), subindustry), {W})",

    # ── D0-S19. zscore of rank spread ──
    "group_rank(ts_zscore(group_rank(ts_delay({FUND_F},1), subindustry) - group_rank(ts_delay({BLUE_F},1), subindustry), {W}), sector)",
]

# D0 禁用的日频字段（提交前必须净化）
_D0_FORBIDDEN_FIELDS = [
    "returns", "close", "volume", "high", "low", "vwap", "turnover",
    "adv20", "adv60", "adv120",
]

# D0 价格字段（用这些的应该走 D0 track）
_D0_PRICE_FIELDS = set(_D0_FORBIDDEN_FIELDS) | {"open"}

import re as _re

def _classify_d0_or_d1(expr: str) -> str:
    """
    判断一个表达式应该归属 D0 还是 D1。
    规则：含有裸露价格字段（close/returns/volume等）-> D0
          只含基本面/分析师字段 -> D1
    Returns: 'd0' or 'd1'
    """
    # 保护已有的 ts_delay(price, n) 形式（这类在D1里是合法的）
    stripped = _re.sub(r'ts_delay\s*\([^,)]+,\s*\d+\)', '__DELAYED__', expr)
    # 如果去掉已包裹的 ts_delay 后还有裸露价格字段，就是 D0
    for field in ["close", "returns", "volume", "high", "low", "vwap",
                  "turnover", "adv20", "adv60", "adv120"]:
        if _re.search(rf'\b{field}\b', stripped):
            return 'd0'
    return 'd1'


def fix_divide_group_rank(expr: str) -> str:
    """
    修复 Warning: 'Incompatible unit for divide - found Group:1'
    原因：divide() 的任一参数中含 group_rank()/group_zscore() 时，
          该参数带 Group:1 单位，和其他字段量纲不兼容。
    修复策略：把 divide(A, B) 替换为 (A - B) / (abs(A) + abs(B) + 1e-6)
    更简单的替代：检测 divide() 的参数里是否含 group_rank/group_zscore，
                  若有则用减法替代除法（两者都是标准化信号，相减比相除更合法）
    """
    result = expr
    
    # 模式1: divide(X, Y) 其中 X 或 Y 含 group_rank/group_zscore/group_neutralize
    # 替换为 subtract(X, Y) 更安全（两个Group信号相减仍是Group单位）
    def _replace_divide(m):
        full = m.group(0)
        if any(kw in full for kw in ['group_rank', 'group_zscore', 'group_neutralize']):
            # 把 divide( 替换成 subtract(  (subtract 不检查单位)
            return 'subtract(' + full[7:]
        return full
    
    result = _re.sub(r'divide\s*\(', _replace_divide, result)
    
    # 模式2: 直接出现在 divide 分子/分母中的 group_rank 结果
    # 例如: ts_delta(divide(assets, cap), n) 但 ts_delta 前有 group_rank 包裹
    # -> 这种情况需要把内层 divide 替换，先保护已处理的
    
    return result


def sanitize_for_d0(expr: str) -> str:
    """
    将 D1 因子表达式净化为 D0 合规版本。
    采用"保护-替换-还原"三步法，避免对已有 ts_delay 二次套娃包装。
    同时自动修复 divide(group_rank()) 量纲 warning。
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
# 🚫 禁用结构黑名单（自动记录 SELF_CORRELATION 失败的因子骨架）
# 每次因 SELF_CORRELATION 失败的因子，提取其“骨架”加入黑名单
# 后续生成的因子如果骨架匹配黑名单，直接跳过，避免浪费 API 配额
# =========================================================
_FORBIDDEN_STRUCTURES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "forbidden_structures.txt"
)

# [H1 fix] _extract_skeleton 的正式定义在 line 1142（含算子识别）
# 此处旧版简陋定义已删除

def _load_forbidden_skeletons() -> set:
    """加载禁用骨架集合"""
    if not os.path.exists(_FORBIDDEN_STRUCTURES_PATH):
        return set()
    try:
        with open(_FORBIDDEN_STRUCTURES_PATH, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception:
        return set()

def _is_forbidden_structure(expr: str, forbidden_set: set = None) -> bool:
    """检查因子骨架是否在黑名单中"""
    if forbidden_set is None:
        forbidden_set = _load_forbidden_skeletons()
    if not forbidden_set:
        return False
    skeleton = _extract_skeleton(expr)
    return skeleton in forbidden_set

def _add_forbidden_structure(expr: str):
    """把因子骨架加入黑名单"""
    skeleton = _extract_skeleton(expr)
    try:
        with open(_FORBIDDEN_STRUCTURES_PATH, 'a', encoding='utf-8') as f:
            f.write(skeleton + '\n')
        logging.info(f"🚫 已将失败骨架加入黑名单: {skeleton[:80]}")
    except Exception as e:
        logging.debug(f"写入禁用骨架失败: {e}")


# =========================================================
# 🔪 字段耗尽黑名单（Field Exhaustion Kill List）
# 挖到好因子后，提取其主字段加入永久黑名单，强制探索其他蓝海字段
# 解决"贪婪锁定"问题：发现一个好字段后反复利用，忽略其他蓝海
# =========================================================
_EXHAUSTED_FIELDS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "exhausted_fields.json"
)

def _extract_primary_fields(expr: str) -> set:
    """从因子表达式中提取所有使用的数据字段名。
    排除算子名、数字、分组标识符等，只保留真正的数据字段。"""
    import re as _r
    # 提取所有看起来像标识符的 token
    tokens = set(_r.findall(r'\b([a-z][a-z0-9_]{2,})\b', expr.lower()))
    # 排除已知的算子/关键词/分组标识符
    _OPERATORS = {
        'ts_mean', 'ts_rank', 'ts_zscore', 'ts_delta', 'ts_std_dev',
        'ts_decay_linear', 'ts_decay_exp_window', 'ts_sum', 'ts_delay',
        'ts_av_diff', 'ts_corr', 'ts_covariance', 'ts_regression',
        'ts_arg_max', 'ts_arg_min', 'ts_product', 'ts_quantile',
        'ts_count_nans', 'ts_ir', 'ts_skewness', 'ts_kurtosis',
        'ts_moment', 'ts_theilsen', 'ts_herfindahl', 'ts_entropy',
        'ts_step', 'rank', 'group_rank', 'group_neutralize',
        'group_zscore', 'group_quantile', 'winsorize', 'trade_when',
        'divide', 'subtract', 'log', 'abs', 'signed_power',
        'jump_decay', 'hump', 'kth_element', 'days_from_last_change',
        'last_diff_value', 'if_else', 'is_nan',
        'subindustry', 'industry', 'sector',  # 分组标识符
    }
    # 排除纯标价格字段（这些是公共的，不需要 kill）
    _COMMON_FIELDS = {
        'close', 'open', 'high', 'low', 'volume', 'vwap', 'returns',
        'cap', 'adv20', 'adv60', 'adv120', 'turnover',
    }
    fields = tokens - _OPERATORS - _COMMON_FIELDS
    # 再排除纯数字 token 和太短的
    fields = {f for f in fields if not f.isdigit() and len(f) > 2}
    return fields


def _load_exhausted_fields() -> dict:
    """加载已耗尽字段集合。
    返回: dict {field_id: {"killed_at": timestamp, "alpha_expr": ..., "sharpe": ...}}
    """
    if not os.path.exists(_EXHAUSTED_FIELDS_PATH):
        return {}
    try:
        with open(_EXHAUSTED_FIELDS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_exhausted_fields(exhausted: dict):
    """持久化已耗尽字段集合。"""
    try:
        with open(_EXHAUSTED_FIELDS_PATH, 'w', encoding='utf-8') as f:
            json.dump(exhausted, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.debug(f"保存耗尽字段失败: {e}")


def _get_exhausted_field_set() -> set:
    """快速获取所有已耗尽字段 ID 的集合。"""
    return set(_load_exhausted_fields().keys())


def _kill_fields_from_alpha(expr: str, sharpe: float = 0, fitness: float = 0):
    """从成功的 alpha 中提取主字段并加入耗尽黑名单。
    只 kill 非公共字段（排除 close/volume 等通用字段）。"""
    fields = _extract_primary_fields(expr)
    if not fields:
        return
    exhausted = _load_exhausted_fields()
    newly_killed = []
    for f in fields:
        if f not in exhausted:
            exhausted[f] = {
                "killed_at": time.strftime('%Y-%m-%d %H:%M'),
                "alpha_expr": expr[:120],
                "sharpe": round(sharpe, 3),
                "fitness": round(fitness, 3),
            }
            newly_killed.append(f)
    if newly_killed:
        _save_exhausted_fields(exhausted)
        logging.warning(
            f"🔪 字段耗尽! 已杀死 {len(newly_killed)} 个字段: {newly_killed} | "
            f"总耗尽={len(exhausted)} | 来源: {expr[:60]}"
        )


def _filter_exhausted_from_list(field_list: list, exhausted_set: set = None) -> list:
    """从字段列表中移除已耗尽的字段。"""
    if exhausted_set is None:
        exhausted_set = _get_exhausted_field_set()
    if not exhausted_set:
        return field_list
    return [f for f in field_list if f not in exhausted_set]


# =========================================================
# 🧊 骨架冷却系统（Skeleton Cooldown）
# 同一骨架连续产出好因子后，冷却 N 代，强制引擎切换到新骨架
# 不永久杀死——冷却到期自动解封，防止骨架枯竭
# =========================================================
_SKELETON_COOLDOWN_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "skeleton_cooldown.json"
)
_SKELETON_COOLDOWN_GENERATIONS = 20   # 冷却代数（到期自动解封）
_SKELETON_KILL_THRESHOLD = 3          # 同骨架产出 N 个好因子后触发冷却


def _extract_skeleton(expr: str) -> str:
    """提取表达式的结构骨架指纹。
    将所有字段名替换为 {F}，数字替换为 {N}，只保留算子结构。
    例如: ts_rank(implied_volatility_call_30, 60) → ts_rank({F}, {N})
    """
    import re as _r
    # Step 1: 用已知算子/关键词列表来识别非字段 token
    _KNOWN_OPS = {
        'ts_mean', 'ts_rank', 'ts_zscore', 'ts_delta', 'ts_std_dev',
        'ts_decay_linear', 'ts_decay_exp_window', 'ts_sum', 'ts_delay',
        'ts_av_diff', 'ts_corr', 'ts_covariance', 'ts_regression',
        'ts_arg_max', 'ts_arg_min', 'ts_product', 'ts_quantile',
        'ts_count_nans', 'ts_ir', 'ts_skewness', 'ts_kurtosis',
        'ts_moment', 'ts_theilsen', 'ts_herfindahl', 'ts_entropy',
        'ts_step', 'ts_backfill', 'ts_decay_exp',
        'rank', 'group_rank', 'group_neutralize', 'group_zscore',
        'group_quantile', 'winsorize', 'trade_when', 'bucket',
        'divide', 'subtract', 'log', 'abs', 'signed_power', 'power',
        'sqrt', 'sign', 'inverse', 'normalize', 'scale', 'zscore',
        'jump_decay', 'hump', 'kth_element', 'days_from_last_change',
        'last_diff_value', 'if_else', 'is_nan', 'not', 'and', 'or',
        'vec_avg', 'vec_sum', 'vec_min', 'vec_max',
        'reduce_ir', 'reduce_skewness', 'reduce_avg', 'reduce_sum',
        'subindustry', 'industry', 'sector', 'std', 'range',
    }
    # Step 2: 先替换数字（保留算子名不变）
    skeleton = _r.sub(r'(?<!\w)\d+\.?\d*(?!\w)', '{N}', expr)
    # Step 3: 替换字段名（非算子/关键词的标识符 → {F}）
    def _replace_field(m):
        token = m.group(0)
        if token.lower() in _KNOWN_OPS:
            return token
        return '{F}'
    skeleton = _r.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', _replace_field, skeleton)
    # Step 4: 归一化空白
    skeleton = _r.sub(r'\s+', ' ', skeleton).strip()
    return skeleton


def _load_skeleton_cooldown() -> dict:
    """加载骨架冷却状态。
    返回: {skeleton_fingerprint: {"hits": N, "cooldown_until_gen": M, "last_alpha": ..., "first_hit": ...}}
    """
    if not os.path.exists(_SKELETON_COOLDOWN_PATH):
        return {}
    try:
        with open(_SKELETON_COOLDOWN_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_skeleton_cooldown(data: dict):
    """持久化骨架冷却状态。"""
    try:
        with open(_SKELETON_COOLDOWN_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.debug(f"保存骨架冷却失败: {e}")


def _record_skeleton_hit(expr: str, current_gen: int, sharpe: float = 0):
    """记录一个骨架的成功命中。当命中达到阈值时，触发冷却。"""
    skeleton = _extract_skeleton(expr)
    if not skeleton or len(skeleton) < 10:
        return
    cooldown = _load_skeleton_cooldown()
    entry = cooldown.get(skeleton, {
        "hits": 0, "cooldown_until_gen": 0,
        "last_alpha": "", "first_hit": current_gen
    })
    entry["hits"] = entry.get("hits", 0) + 1
    entry["last_alpha"] = expr[:120]
    entry["last_sharpe"] = round(sharpe, 3)

    if entry["hits"] >= _SKELETON_KILL_THRESHOLD and entry.get("cooldown_until_gen", 0) <= current_gen:
        entry["cooldown_until_gen"] = current_gen + _SKELETON_COOLDOWN_GENERATIONS
        logging.warning(
            f"🧊 骨架冷却! 骨架已产出 {entry['hits']} 个好因子，冷却至第 {entry['cooldown_until_gen']} 代 | "
            f"骨架: {skeleton[:80]}"
        )
    cooldown[skeleton] = entry
    _save_skeleton_cooldown(cooldown)


def _is_skeleton_cooled(expr: str, current_gen: int) -> bool:
    """检查表达式的骨架是否在冷却期内。"""
    skeleton = _extract_skeleton(expr)
    if not skeleton:
        return False
    cooldown = _load_skeleton_cooldown()
    entry = cooldown.get(skeleton)
    if not entry:
        return False
    return entry.get("cooldown_until_gen", 0) > current_gen


def _get_cooled_skeletons(current_gen: int) -> set:
    """获取当前仍在冷却中的骨架指纹集合。"""
    cooldown = _load_skeleton_cooldown()
    return {sk for sk, v in cooldown.items() if v.get("cooldown_until_gen", 0) > current_gen}


def _enforce_pool_diversity(pool: list, max_per_skeleton: int = 2) -> list:
    """强制精英池多样性：同一骨架最多保留 max_per_skeleton 个种子。
    保证池中骨架种类最大化，防止近亲繁殖。"""
    skeleton_counts = {}
    diverse_pool = []
    for expr in pool:
        sk = _extract_skeleton(expr)
        count = skeleton_counts.get(sk, 0)
        if count < max_per_skeleton:
            diverse_pool.append(expr)
            skeleton_counts[sk] = count + 1
    return diverse_pool


# =========================================================

# =========================================================
# Phase 1: Systematic Sweep Engine (GrandMaster Core Strategy)
# Deterministic field x skeleton x window Cartesian product scan
# Uses sweep_state.json for persistent progress tracking
# =========================================================
_SWEEP_STATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sweep_state.json"
)

_SWEEP_SKELETONS = [
    # ═══ v3 极致蓝海扫描骨架（25种完全不同的算子结构）═══
    # 零硬编码热门字段，全部用 {F} 占位符

    # 经典保留（3个）
    ("rank_ts_rank",      "group_rank(ts_rank({F}, {W}), subindustry)"),
    ("neut_ts_zscore",    "group_neutralize(ts_zscore({F}, {W}), subindustry)"),
    ("rank_delta_ratio",  "group_rank(ts_delta({F}, {W}) / (ts_std_dev({F}, {W}) + 1e-6), subindustry)"),

    # 稀有算子（结构性差异最大化）
    ("regression_resid",  "group_rank(ts_regression({F}, ts_step(1), {W}, 0, 2), subindustry)"),
    ("signed_sqrt",       "group_rank(signed_power(ts_zscore({F}, {W}), 0.5), subindustry)"),
    ("arg_max_signal",    "group_neutralize(({W} - ts_arg_max({F}, {W})) / {W}, subindustry)"),
    ("product_accum",     "group_rank(ts_product({F}, {W}), subindustry)"),
    ("quantile_25",       "group_rank(ts_quantile({F}, 0.25, {W}), subindustry)"),
    ("quantile_iqr",      "group_rank(ts_quantile({F}, 0.75, {W}) - ts_quantile({F}, 0.25, {W}), subindustry)"),
    ("kth_elem",          "group_neutralize(kth_element({F}, 3, {W}), subindustry)"),
    ("nan_count",         "group_neutralize(ts_count_nans({F}, {W}), subindustry)"),
    ("vol_ratio",         "group_rank(ts_std_dev({F}, {W}) / (ts_mean(abs({F}), {W}) + 1e-6), subindustry)"),
    ("accel_2nd",         "group_neutralize(ts_delta(ts_delta({F}, 5), 5), subindustry)"),
    ("jump_decay_sig",    "group_rank(jump_decay({F}, {W}, 0.5, 252), subindustry)"),
    ("hump_signal",       "group_neutralize(hump({F}, 0.3), subindustry)"),

    # v3 新增极致冷门
    ("info_ratio",        "group_rank(ts_ir({F}, {W}), subindustry)"),
    ("skewness",          "group_rank(ts_skewness({F}, {W}), subindustry)"),
    ("kurtosis",          "group_neutralize(ts_kurtosis({F}, {W}), subindustry)"),
    ("moment_3rd",        "group_rank(ts_moment({F}, {W}, 3), subindustry)"),
    ("theilsen_trend",    "group_neutralize(ts_theilsen({F}, ts_step(1), {W}), subindustry)"),
    ("herfindahl",        "group_rank(ts_herfindahl({F}, {W}), subindustry)"),
    ("entropy",           "group_neutralize(ts_entropy({F}, {W}), subindustry)"),
    ("decay_linear",      "ts_decay_linear({F}, {W})"),
    ("days_change",       "group_rank(days_from_last_change({F}), subindustry)"),
    ("last_diff",         "group_neutralize(last_diff_value({F}, {W}), subindustry)"),
]

_SWEEP_WINDOWS = [5, 10, 15, 20, 30, 60, 120, 252]


def _load_sweep_state():
    if os.path.exists(_SWEEP_STATE_PATH):
        try:
            with open(_SWEEP_STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"field_idx": 0, "skeleton_idx": 0, "window_idx": 0, "total_generated": 0}


def _save_sweep_state(state):
    try:
        with open(_SWEEP_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f)
    except Exception:
        pass


def generate_systematic_sweep(wq_fields, wq_fields_by_category,
                               evaluated_alphas, n=20, fund_fields=None):
    """
    Systematic sweep generator -- GrandMaster core strategy.
    ★ 改进: 使用类别轮询（Round-Robin）而非线性字段索引，
           确保每一代都能覆盖不同数据集类别（含蓝海类别）。
    """
    state = _load_sweep_state()
    results = []

    all_fields = wq_fields if wq_fields else _FUNDAMENTAL_FIELDS
    if not fund_fields:
        fund_fields = [f for f in _FUNDAMENTAL_FIELDS if f in set(all_fields)] or _FUNDAMENTAL_FIELDS
    # ★ 字段耗尽过滤：跳过已产出好因子的字段
    _exhausted = _get_exhausted_field_set()
    if _exhausted:
        all_fields = _filter_exhausted_from_list(all_fields, _exhausted) or all_fields
        fund_fields = _filter_exhausted_from_list(fund_fields, _exhausted) or fund_fields
        # 也过滤类别内的字段
        if wq_fields_by_category:
            wq_fields_by_category = {
                cat: _filter_exhausted_from_list(flds, _exhausted) or flds
                for cat, flds in wq_fields_by_category.items()
            }

    # ★ 类别轮询：从 state 恢复当前类别和每类别的进度
    cat_list = sorted(wq_fields_by_category.keys()) if wq_fields_by_category else []
    cat_idx = state.get("cat_idx", 0)
    cat_field_progress = state.get("cat_field_progress", {})  # {category: field_idx_within_category}

    # 兼容旧 state（没有 cat_idx 的情况下退化为线性扫描）
    field_idx = state.get("field_idx", 0)
    skeleton_idx = state.get("skeleton_idx", 0)
    window_idx = state.get("window_idx", 0)
    total = state.get("total_generated", 0)

    attempts = 0
    max_attempts = n * 5

    while len(results) < n and attempts < max_attempts:
        attempts += 1

        # ★ 类别轮询选字段：优先按类别轮流取字段
        if cat_list:
            if cat_idx >= len(cat_list):
                cat_idx = 0
            current_cat = cat_list[cat_idx]
            cat_fields = wq_fields_by_category.get(current_cat, [])
            c_progress = cat_field_progress.get(current_cat, 0)
            if c_progress >= len(cat_fields):
                c_progress = 0  # 本类别已扫完一轮，重置
                cat_field_progress[current_cat] = 0
            if cat_fields:
                field = cat_fields[c_progress]
                cat_field_progress[current_cat] = c_progress + 1
            else:
                cat_idx += 1
                continue
            # 每取一个字段后切换到下一个类别
            cat_idx += 1
        else:
            # 无类别信息，退化为线性扫描
            if field_idx >= len(all_fields):
                field_idx = 0
                logging.info(f"[Sweep] Full field scan complete! Total={total}. Next round...")
            field = all_fields[field_idx]
            field_idx += 1

        if skeleton_idx >= len(_SWEEP_SKELETONS):
            skeleton_idx = 0
        if window_idx >= len(_SWEEP_WINDOWS):
            window_idx = 0
            skeleton_idx += 1
            continue

        skel_name, skel_template = _SWEEP_SKELETONS[skeleton_idx]
        window = _SWEEP_WINDOWS[window_idx]

        window_idx += 1

        expr = skel_template.replace("{F}", field).replace("{W}", str(window))
        if "{F2}" in expr:
            # ★ 跨类别 F2 选取：从不同类别选 F2
            if cat_list:
                f2_cat = cat_list[(cat_idx + 1) % len(cat_list)]
                f2_candidates = wq_fields_by_category.get(f2_cat, fund_fields)
                f2 = f2_candidates[(skeleton_idx + window_idx) % len(f2_candidates)]
            else:
                f2_idx = (field_idx + skeleton_idx) % len(fund_fields)
                f2 = fund_fields[f2_idx]
            if f2 == field:
                f2 = fund_fields[(skeleton_idx + 1) % len(fund_fields)]
            expr = expr.replace("{F2}", f2)

        if expr in evaluated_alphas:
            continue
        if expr.count("(") != expr.count(")"):
            continue

        results.append(expr)
        total += 1

    state["field_idx"] = field_idx
    state["skeleton_idx"] = skeleton_idx
    state["window_idx"] = window_idx
    state["total_generated"] = total
    state["cat_idx"] = cat_idx
    state["cat_field_progress"] = cat_field_progress
    _save_sweep_state(state)

    if results:
        cat_info = f"cat={cat_list[cat_idx % len(cat_list)]}" if cat_list else f"field {field_idx}/{len(all_fields)}"
        logging.info(
            f"[Sweep] Generated {len(results)} factors | "
            f"Progress: {cat_info} skel={skeleton_idx} win={window_idx} | Total={total}"
        )

    return results


# =========================================================
# Phase 2: Skeleton Similarity Filter (pre-submission SELF_CORR check)
# Token-level Jaccard > 0.8 => skip
# =========================================================
def _tokenize_expr(expr):
    return set(re.findall(r'[a-z_][a-z0-9_]*|\d+', expr.lower()))


def skeleton_similarity(expr_a, expr_b):
    tokens_a = _tokenize_expr(expr_a)
    tokens_b = _tokenize_expr(expr_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def filter_by_skeleton_similarity(candidates, existing_pool, threshold=0.80):
    """Filter candidates with Jaccard > threshold against knowledge pool."""
    if not existing_pool:
        return candidates

    pool_tokens = [_tokenize_expr(e) for e in existing_pool]

    filtered = []
    rejected = 0
    for candidate in candidates:
        cand_tokens = _tokenize_expr(candidate)
        is_similar = False
        for pt in pool_tokens:
            if not cand_tokens or not pt:
                continue
            intersection = len(cand_tokens & pt)
            union = len(cand_tokens | pt)
            jaccard = intersection / union if union > 0 else 0.0
            if jaccard > threshold:
                is_similar = True
                break
        if is_similar:
            rejected += 1
        else:
            filtered.append(candidate)

    if rejected > 0:
        logging.info(f"[SkeletonFilter] Blocked {rejected} similar (Jaccard>{threshold}), passed {len(filtered)}")

    return filtered


# =========================================================
# Phase 3: Decay Sweep Automation
# For high-Sharpe factors, auto-scan decay=0,2,4,6,8,10
# =========================================================
def generate_decay_sweep_variants(high_sharpe_results, base_settings_d0,
                                   base_settings_d1, d0_template_set,
                                   decay_values=None):
    """Generate decay sweep variants for high-Sharpe factors."""
    if decay_values is None:
        decay_values = [0, 2, 4, 6, 8, 10]

    variants = []
    for res in high_sharpe_results:
        if not res.success or res.sharpe is None:
            continue
        if abs(res.sharpe) < 1.5:
            continue

        is_d0 = res.template in d0_template_set
        base = base_settings_d0 if is_d0 else base_settings_d1

        for decay_val in decay_values:
            if decay_val == getattr(base, 'decay', 0):
                continue
            variant_settings = SimulationSettings(
                region=base.region,
                universe=base.universe,
                delay=base.delay,
                decay=decay_val,
                neutralization=base.neutralization,
                truncation=base.truncation,
                nanHandling=base.nanHandling,
                testPeriod=base.testPeriod,
            )
            variants.append((res.template, variant_settings, f"decay={decay_val}"))

    if variants:
        logging.info(f"[DecaySweep] {len(variants)} decay variants for high-Sharpe factors")

    return variants


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
                       theme: str = None, evaluated_alphas: set = None, db_path: str = None) -> list:
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

    if theme is None:
        theme_dict = random.choice(_RESEARCH_THEMES)
    elif isinstance(theme, str):
        theme_dict = {'name': theme, 'hypothesis': f'基于 {theme} 逻辑进行因子挖掘。', 'hint': '请发挥创造力，使用任何相关字段。'}
    else:
        theme_dict = theme

    logging.info(f"🎯 本代 AI 探索主题: {theme_dict['name']}")

    # 从知识库中抽几条示例，仅作"避开相似"的参考
    examples = random.sample(knowledge_pool, min(3, len(knowledge_pool)))
    avoid_text = "\n".join(f"  - {e[:120]}" for e in examples)

    prompt = f"""你是一位顶级量化研究员，专精 WorldQuant Brain 平台的 FASTEXPR 语言。
今天的研究课题是：{theme_dict['name']}

===【研究假设】===
{theme_dict['hypothesis']}

===【推荐数据字段和思路】===
{theme_dict['hint']}

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

# =========================================================
# 🔥 探索引擎（Exploration Engine）— 反重复温度采样
# 用过的降温（减少被选概率），没用过的升温（增加被选概率）
# 防止在 81 个算子 × 5906 字段的空间里原地打转
# =========================================================
class ExplorationTracker:
    """基于使用频次的反重复采样器。
    
    原理：每个 item 有一个"热度"计数器。
    - 每次被选中 → 热度+1
    - 采样概率 ∝ 1/(热度+1)  → 用得越多越不容易被选
    - 定期衰减（每N代全体热度减半）→ 防止永久冻结
    """
    def __init__(self, name: str = "default", decay_interval: int = 50):
        self.name = name
        self.heat = {}  # item → 使用次数
        self.total_picks = 0
        self.decay_interval = decay_interval
    
    def pick(self, items: list, n: int = 1):
        """从 items 中反重复采样 n 个（不放回），优先选冷门。"""
        if not items:
            return []
        if n >= len(items):
            return list(items)
        
        # 计算每个 item 的反热度权重
        weights = []
        for item in items:
            heat = self.heat.get(item, 0)
            weights.append(1.0 / (heat + 1))  # 用过越多，权重越低
        
        # 归一化
        total_w = sum(weights)
        if total_w <= 0:
            return random.sample(items, min(n, len(items)))
        probs = [w / total_w for w in weights]
        
        # 带权采样（不放回）
        result = []
        available = list(range(len(items)))
        avail_probs = list(probs)
        for _ in range(min(n, len(items))):
            if not available:
                break
            # 归一化当前可用概率
            sp = sum(avail_probs)
            if sp <= 0:
                idx = random.choice(available)
            else:
                normalized = [p / sp for p in avail_probs]
                idx_in_avail = random.choices(range(len(available)), weights=normalized, k=1)[0]
                idx = available[idx_in_avail]
                available.pop(idx_in_avail)
                avail_probs.pop(idx_in_avail)
            
            chosen = items[idx]
            result.append(chosen)
            self.heat[chosen] = self.heat.get(chosen, 0) + 1
            self.total_picks += 1
        
        # 定期衰减（每 decay_interval 次采样，全体热度减半）
        if self.total_picks % (self.decay_interval * len(items) + 1) == 0 and self.heat:
            for k in self.heat:
                self.heat[k] = max(0, self.heat[k] // 2)
        
        return result
    
    def pick_one(self, items: list):
        """反重复采样单个 item。"""
        result = self.pick(items, 1)
        return result[0] if result else random.choice(items)
    
    def stats(self) -> str:
        """返回探索统计：覆盖率和热度分布。"""
        if not self.heat:
            return f"{self.name}: 空"
        used = sum(1 for v in self.heat.values() if v > 0)
        total = len(self.heat)
        max_heat = max(self.heat.values()) if self.heat else 0
        return f"{self.name}: {used}/{total} 已探索, max_heat={max_heat}"

# 全局探索追踪器（跨代持久化）
_tracker_template = ExplorationTracker("模板骨架", decay_interval=30)
_tracker_operator = ExplorationTracker("算子", decay_interval=50)
_tracker_field_cat = ExplorationTracker("字段类别", decay_interval=20)


def generate_template_alphas(n: int, wq_fields: list, evaluated_alphas: set = None,
                              wq_fields_by_category: dict = None,
                              blue_ocean_fields: list = None) -> list:
    """
    从 _ALPHA_TEMPLATES 模板库随机填充字段，生成结构多样的候选因子。

    每次随机选一个模板骨架 + 从 wq_fields 随机填充 {F}/{F1}/{F2} 占位符，
    确保每代都有完全不同结构的因子进入候选池，与遗传变异互补。

    参数:
        n: 目标生成数量
        wq_fields: 完整字段列表（2663个，从缓存加载）
        evaluated_alphas: 已评估因子集合（用于去重，避免重复提交）
        blue_ocean_fields: 蓝海字段池（list[dict] with 'id' key），30% 概率强制从此池采样 F1
    返回: 填充后的因子表达式列表
    """
    results = []
    all_fields = wq_fields if wq_fields else _FUNDAMENTAL_FIELDS
    # 基本面字段优先用于双字段模板的 F2（分母/配对字段）
    fund_fields = [f for f in _FUNDAMENTAL_FIELDS if f in all_fields] or _FUNDAMENTAL_FIELDS
    # ★ 字段耗尽过滤：移除已产出好因子的字段，强制探索新领域
    _exhausted = _get_exhausted_field_set()
    if _exhausted:
        all_fields = _filter_exhausted_from_list(all_fields, _exhausted) or all_fields
        fund_fields = _filter_exhausted_from_list(fund_fields, _exhausted) or fund_fields
    # 蓝海字段 ID 列表（用于 30% 强制采样）— 同样过滤已耗尽字段
    _blue_ids = [b['id'] for b in blue_ocean_fields if b['id'] not in _exhausted] if blue_ocean_fields else []

    # 准备数据集类别列表——蓝海冷门类别优先排列
    _COLD_CATEGORIES = ['model', 'sentiment', 'socialmedia', 'macro', 'news', 'option', 'analyst']
    _HOT_CATEGORIES  = ['fundamental', 'pv']  # 热门类别排最后
    if wq_fields_by_category:
        cold = [c for c in _COLD_CATEGORIES if c in wq_fields_by_category and wq_fields_by_category[c]]
        hot  = [c for c in _HOT_CATEGORIES  if c in wq_fields_by_category and wq_fields_by_category[c]]
        rest = [c for c in wq_fields_by_category if c not in _COLD_CATEGORIES + _HOT_CATEGORIES and wq_fields_by_category[c]]
        category_list = cold + rest + hot   # 冷门优先
        random.shuffle(cold)  # 冷门之间打乱
    else:
        category_list = []

    blue_count = 0  # 统计蓝海采样次数
    attempts = 0
    while len(results) < n and attempts < n * 15:
        attempts += 1
        try:
            # ★ 冷门算子优先抽样：90% 概率选含冷门算子的骨架 ★
            if _sample_skeleton_func:
                template = _sample_skeleton_func(cold_ratio=0.90)
            else:
                template = _tracker_template.pick_one(_ALPHA_TEMPLATES)
            window = random.choice(_TEMPLATE_WINDOWS)

            # ★★★ 蓝海强制采样：80% 概率从蓝海池选 F1（大幅降低自相关）★★★
            use_blue_ocean = _blue_ids and random.random() < 0.45  # 45% 蓝海（平衡冷门探索和热门成功率）
            if use_blue_ocean:
                f1 = random.choice(_blue_ids)
                blue_count += 1
                # F2 从不同来源
                if "{F2}" in template or "{F1}" in template:
                    # F2 从基本面或另一个蓝海字段
                    f2_pool = [b for b in _blue_ids if b != f1]
                    if f2_pool and random.random() < 0.5:
                        f2 = random.choice(f2_pool)
                    else:
                        f2 = random.choice(fund_fields)
                else:
                    f2 = random.choice(fund_fields)
            # 跨数据集强制融合：F1 和 F2 强制从不同类别采样（降低自相关）
            elif category_list:
                # ★ 反重复类别采样：已探索过的类别降温
                chosen_cat = _tracker_field_cat.pick_one(category_list)
                cat_fields = wq_fields_by_category[chosen_cat]
                f1 = random.choice(cat_fields) if cat_fields else random.choice(all_fields)
                # F2 强制选不同类别（跨域融合）
                if "{F2}" in template or "{F1}" in template:
                    other_cats = [c for c in category_list if c != chosen_cat and wq_fields_by_category.get(c)]
                    if other_cats:
                        cat2 = _tracker_field_cat.pick_one(other_cats)
                        f2 = random.choice(wq_fields_by_category[cat2])
                    else:
                        f2_pool = [f for f in fund_fields if f != f1] or fund_fields
                        f2 = random.choice(f2_pool)
                else:
                    f2_pool = [f for f in fund_fields if f != f1] or fund_fields
                    f2 = random.choice(f2_pool)
            else:
                f1 = random.choice(all_fields)
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
        logging.info(
            f"🧱 模板工厂生成了 {len(results)} 个结构化因子 (🌊蓝海={blue_count}) | "
            f"探索: {_tracker_template.stats()} | {_tracker_field_cat.stats()}"
        )
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

    # ── D0 字段白名单过滤（防止使用 D0 不支持的字段）──────────────
    _whitelist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "constants", "d0_fields_whitelist.json")
    _d0_whitelist_set = None
    if os.path.exists(_whitelist_path):
        try:
            _wl = json.load(open(_whitelist_path, encoding='utf-8'))
            _d0_whitelist_set = set(_wl.get('field_ids', []))
            logging.debug(f"[D0白名单] 已加载 {len(_d0_whitelist_set)} 个D0合规字段")
        except Exception as _e:
            logging.debug(f"[D0白名单] 加载失败: {_e}，跳过白名单过滤")

    def _filter_by_whitelist(fields: list) -> list:
        """用D0白名单过滤字段列表，若白名单未加载则原样返回"""
        if _d0_whitelist_set is None or not fields:
            return fields
        filtered = [f for f in fields if f in _d0_whitelist_set]
        return filtered if filtered else fields  # 若过滤后为空，保留原始（安全回退）

    # 构建 D0 专属字段采样池（按类别）并应用白名单过滤
    fund_pool   = _filter_by_whitelist(wq_fields_by_category.get("fundamental", []) or _FUNDAMENTAL_FIELDS)
    blue_pool   = _filter_by_whitelist(
        wq_fields_by_category.get("sentiment", []) +
        wq_fields_by_category.get("socialmedia", []) +
        wq_fields_by_category.get("option", []) +
        wq_fields_by_category.get("news", []) +
        wq_fields_by_category.get("model", []) +
        wq_fields_by_category.get("macro", [])
    )
    analyst_pool = _filter_by_whitelist(wq_fields_by_category.get("analyst", []))

    if _d0_whitelist_set:
        logging.info(f"[D0白名单] 字段池过滤后: fund={len(fund_pool)} blue={len(blue_pool)} analyst={len(analyst_pool)}")



    # --- 来源 -1：预填充注入队列（最高优先级，消费后删除）---
    # 由 d0_fill_and_submit.py 预先填充好的具体 D0 表达式，直接放进当代提交
    _inject_queue = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "constants", "d0_inject_queue.jsonl")
    if os.path.exists(_inject_queue):
        try:
            _queue_lines = open(_inject_queue, encoding="utf-8").readlines()
            _remaining = []
            _consumed = 0
            for _ql in _queue_lines:
                _ql = _ql.strip()
                if not _ql:
                    continue
                if len(results) >= n:   # 本代已满
                    _remaining.append(_ql)
                    continue
                try:
                    _qe = json.loads(_ql)
                    _expr = _qe.get("expr", "")
                    if _expr and _expr not in evaluated_alphas and _expr not in results:
                        if _expr.count("(") == _expr.count(")") and len(_expr) >= 20:
                            results.append(_expr)
                            _consumed += 1
                    else:
                        _remaining.append(_ql)  # 已评估，但保留位置给统计
                except Exception:
                    pass
            # 未消费的留回去
            with open(_inject_queue, "w", encoding="utf-8") as _qf:
                _qf.writelines(l + "\n" for l in _remaining)
            if _consumed:
                logging.info(f"[注入队列] 消费 {_consumed} 个预填充 D0 因子 | 剩余 {len(_remaining)} 个")
        except Exception as _qex:
            logging.debug(f"[注入队列] 读取失败: {_qex}")


    # --- 来源 0：AI缓存精英复用（免费！直接择取历史高分因子 + 轻微变异）---
    # 高分 AI 因子却就是已经验证的优质模板，直接复用成本越低
    target_from_cache = max(3, int(n * 0.15))   # 目标 15%，前费割减 50% -> 35%
    _cache_seeds = _load_ai_cache_seeds(min_sharpe=0.8, limit=20)
    if _cache_seeds:
        for _cached_expr, _cached_theme in _cache_seeds:
            if len(results) >= target_from_cache:
                break
            try:
                # 直接复用（原模型）
                if _cached_expr not in evaluated_alphas and _cached_expr not in results:
                    results.append(_cached_expr)
                # 变异体 1： ai_smart_mutate
                _mut1 = ai_smart_mutate(ollama_manager, _cached_expr) if ollama_manager else _cached_expr
                if _mut1 and _mut1 != _cached_expr and _mut1 not in evaluated_alphas and _mut1 not in results:
                    results.append(inject_neutralization(_mut1))
            except Exception:
                continue
        cache_count = len(results)
        if cache_count > 0:
            logging.info(f"[AI缓存] 复用 {cache_count} 条历史高分因子（免费）")
    else:
        cache_count = 0
    _cache_elite_examples = [expr for expr, _ in _cache_seeds[:3]]  # 供 AI Prompt 示例

    # --- 来源 1：D0 专属模板填充（目标 35%，主力）---
    # 每次同时随机决定 FUND_F + ANALYST_F 以支持双字段模板
    d0_windows = [5, 10, 15, 20, 30, 40, 60]   # 🔴 修复：d0_windows 未定义导致每次抛 NameError 被静默吞掉，输出0因子
    target_from_template = int(n * 0.35) + 2
    attempts = 0
    while len(results) < target_from_template and attempts < n * 30:
        attempts += 1
        try:
            tmpl = _tracker_template.pick_one(_D0_ALPHA_TEMPLATES)
            expr = tmpl

            # 随机选双字段（保证每次不同）
            # 80% 概率用蓝海字段替代基本面字段（强制跨域融合，最大化降低自相关）
            if random.random() < 0.80 and blue_pool:
                fund_f = random.choice(blue_pool)
            else:
                fund_f  = random.choice(fund_pool)   if fund_pool   else "sales"
            blue_f  = random.choice(blue_pool)   if blue_pool   else None
            anlst_f = random.choice(analyst_pool) if analyst_pool else None
            window  = random.choice(d0_windows)

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
            # 填充窗口占位符 {W}
            if "{W}" in expr:
                expr = expr.replace("{W}", str(window))

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

    d0_template_count = len(results)

    # --- 来源 2：D1 模板 → D0 净化（目标 25%）---
    # 利用已有的 28 个 D1 模板 + sanitize_for_d0() 自动交叉授粉
    target_from_d1 = max(2, int(n * 0.25))
    d1_sanitized_count = 0
    for _ in range(target_from_d1 * 8):  # 多试几次确保足够
        if len(results) >= target_from_template + target_from_d1:
            break
        try:
            # ★ 冷门算子优先抽样
            if _sample_skeleton_func:
                tmpl = _sample_skeleton_func(cold_ratio=0.90)
            else:
                tmpl = _tracker_template.pick_one(_ALPHA_TEMPLATES)
            f1 = random.choice(wq_fields)
            f2 = random.choice(fund_pool) if fund_pool else "sales"
            window = random.choice(d0_windows)
            expr = tmpl.replace("{F1}", f1).replace("{F2}", f2)
            expr = expr.replace("{F}", f1).replace("{W}", str(window))
            # 净化为 D0（自动把裸露 close/volume/returns 等包裹 ts_delay）
            expr = sanitize_for_d0(expr)
            expr = inject_neutralization(expr)
            if expr.count("(") != expr.count(")"):
                continue
            if len(expr) < 15 or len(expr) > 500:
                continue
            if expr in evaluated_alphas or expr in results:
                continue
            results.append(expr)
            d1_sanitized_count += 1
        except Exception:
            continue

    # --- 来源 3：AI D0 专属生成（目标 25%，补充创意因子）---
    if ollama_manager and len(results) < n:
        need = n - len(results)
        try:
            # 随机选择一个 D0 研究主题来驱动 AI 生成方向
            d0_theme = random.choice(_D0_RESEARCH_THEMES)
            logging.info(f"🎯 [D0 AI] 本代探索主题: {d0_theme['name']}")

            # 采样真实字段名注入 prompt（解决 Qwen 编造虚假字段的问题）
            _fund_sample = random.sample(fund_pool, min(10, len(fund_pool))) if fund_pool else ["sales"]
            _blue_sample = random.sample(blue_pool, min(5, len(blue_pool))) if blue_pool else []
            _analyst_sample = random.sample(analyst_pool, min(5, len(analyst_pool))) if analyst_pool else []

            d0_system = (
                "You are a WorldQuant Brain Delay-0 alpha expert.\n"
                "STRICT RULES:\n"
                "1. NEVER use raw: close, volume, returns, high, low, vwap, turnover.\n"
                "2. Price/volume data MUST be wrapped: ts_delay(close,1), ts_delay(volume,1), ts_delay(returns,1).\n"
                "3. You MAY freely use: open, cap, and ALL fundamental/analyst/sentiment/option fields.\n"
                "4. Every alpha MUST combine at least TWO independent signals (e.g. gap signal + fundamental, or analyst + lagged price).\n"
                "5. Outer layer MUST be group_neutralize(..., subindustry) or group_rank(..., subindustry/industry/sector).\n"
                "6. ONLY use field names from the AVAILABLE FIELDS list below. Do NOT invent field names.\n"
                "Output ONLY a JSON array of expression strings. No wrapper objects, no keys, just [\"expr1\", \"expr2\", ...]."
            )
            d0_prompt = (
                f"Today's D0 research theme: {d0_theme['name']}\n"
                f"Hypothesis: {d0_theme['hypothesis']}\n"
                f"Recommended approach: {d0_theme['hint']}\n\n"
                f"Generate {need} Delay-0 alpha expressions based on this theme.\n"
                "Key D0 patterns to use:\n"
                "- Opening gap signal: open/ts_delay(close,1)-1\n"
                "- Lagged price/volume: ts_delay(close,1), ts_delay(volume,1)\n"
                "- Combine with fundamental/analyst/sentiment/option fields\n"
                "Examples of good D0 patterns:\n"
                "  group_rank((open/ts_delay(close,1)-1) * rank(sales/cap), subindustry)\n"
                "  trade_when(ts_rank(anl4_adjusted_netincome_ft,10)>0.7, group_rank(open/ts_delay(close,1)-1,subindustry), 0)\n"
                "  group_neutralize(ts_rank(implied_volatility_call_30,20)*(open/ts_delay(close,1)-1), subindustry)\n"
                + (
                    "\nPROVEN HIGH-SHARPE EXAMPLES (learn from these, DO NOT copy exactly, create NEW variations):\n"
                    + "\n".join(f"  {e}" for e in _cache_elite_examples)
                    + "\n"
                    if _cache_elite_examples else ""
                )
                + f"\nAVAILABLE FIELDS (use ONLY these, do NOT invent field names):\n"
                f"Fundamental: {', '.join(_fund_sample)}\n"
                + (f"Sentiment/Option: {', '.join(_blue_sample)}\n" if _blue_sample else "")
                + (f"Analyst: {', '.join(_analyst_sample)}\n" if _analyst_sample else "")
                + f"Also available: open, cap, ts_delay(close,1), ts_delay(volume,1), ts_delay(returns,1)\n\n"
                f"Output JSON array of {need} expressions:"
            )
            raw = ollama_manager.generate(
                d0_prompt,
                system_prompt=d0_system,
                temperature=0.75,
                max_tokens=800
            )
            if raw:
                ai_d0 = _parse_ai_alpha_response(raw)
                # 构建合法字段集用于校验
                _valid_fields = set(wq_fields) | {'open', 'cap', 'close', 'volume', 'returns', 'high', 'low', 'vwap', 'turnover'}
                _known_tokens = {
                    'ts_rank', 'ts_zscore', 'ts_delta', 'ts_delay', 'ts_mean', 'ts_std_dev',
                    'ts_decay_linear', 'ts_decay_exp_window', 'ts_sum', 'ts_av_diff',
                    'ts_corr', 'ts_covariance', 'ts_regression', 'ts_scale', 'ts_product',
                    'ts_arg_max', 'ts_arg_min', 'ts_backfill', 'ts_count_nans', 'ts_quantile',
                    'ts_max', 'ts_min', 'ts_step', 'days_from_last_change', 'last_diff_value',
                    'hump', 'jump_decay', 'kth_element',
                    'group_rank', 'group_neutralize', 'group_zscore',
                    'rank', 'winsorize', 'zscore', 'normalize', 'scale', 'scale_down', 'quantile',
                    'trade_when', 'if_else', 'is_nan', 'sign', 'abs', 'log', 'sqrt',
                    'min', 'max', 'add', 'subtract', 'multiply', 'divide', 'power', 'inverse',
                    'signed_power', 'reverse', 'densify', 'to_nan', 'vector_neut',
                    'vec_avg', 'vec_sum', 'vec_min', 'vec_max',
                    'subindustry', 'sector', 'industry', 'bucket',
                    'std', 'true', 'false', 'nan', 'dense', 'filter',
                    'expression', 'not', 'and', 'or', 'equal', 'greater', 'less',
                }
                for a in ai_d0:
                    # 清理 JSON wrapper（Qwen 有时输出 "expression": "..."  格式）
                    a = re.sub(r'^["\s]*expression["\s]*:\s*["\s]*', '', a).strip().rstrip('"')
                    a = sanitize_for_d0(a)  # 防漏网之鱼
                    # 字段校验：提取所有标识符，检查是否在真实字段集中
                    tokens = re.findall(r'\b([a-z][a-z0-9_]{2,})\b', a)
                    unknown = [t for t in tokens if t not in _valid_fields and t not in _known_tokens]
                    if unknown:
                        logging.debug(f"[D0 AI] 丢弃含虚假字段的因子: {unknown[:3]} | {a[:60]}")
                        continue
                    if a not in evaluated_alphas and a not in results and len(a) > 15:
                        results.append(a)

                # 💾 持久化缓存：把所有 AI 生成的因子立刻存盘（花了 DeepSeek 的钱，绝对不能丢）
                ai_this_round = results[d0_template_count + d1_sanitized_count:]
                if ai_this_round:
                    try:
                        cache_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "ai_alpha_cache.jsonl"
                        )
                        with open(cache_path, "a", encoding="utf-8") as _cf:
                            for _expr in ai_this_round:
                                _cf.write(json.dumps({
                                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "theme": d0_theme.get("name", "unknown") if 'd0_theme' in dir() else "unknown",
                                    "expr": _expr
                                }, ensure_ascii=False) + "\n")
                        logging.info(f"💾 [AI缓存] {len(ai_this_round)} 条 AI 因子已存盘 → ai_alpha_cache.jsonl")
                    except Exception as _ce:
                        logging.debug(f"[AI缓存] 存盘失败: {_ce}")

        except Exception as e:
            logging.debug(f"[D0腿] Ollama D0生成跳过: {e}")

    ai_count = max(0, len(results) - d0_template_count - d1_sanitized_count)
    logging.info(
        f"\ud83d\udfe2 [D0腿] 生成了 {len(results)} 个 D0 候选因子 "
        f"(D0模板={d0_template_count} + D1净化={d1_sanitized_count} + AI={ai_count})"
    )
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
                        # 自动将失败骨架加入黑名单，防止后续生成同结构因子
                        try:
                            _add_forbidden_structure(template)
                        except Exception:
                            pass
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
    """Intelligently wraps formula in neutralization to avoid LOW_SUB_UNIVERSE_SHARPE.
    Also fixes divide(group_rank()) unit incompatibility warning."""
    # 修复 divide(group_rank()) 量纲不兼容 warning
    base_alpha = fix_divide_group_rank(base_alpha)
    if "group_neutralize" in base_alpha or "group_rank" in base_alpha:
        return base_alpha
    return f"group_neutralize({base_alpha}, subindustry)"

def main(mode: str = "d0"):
    """
    mode: 挖掘模式
      - 'd0'   : 只挖 D0 因子（默认，团队重点）
      - 'd1'   : 只挖 D1 因子
      - 'both'  : D0 + D1 双引擎（原来的行为）
    """
    assert mode in ("d0", "d1", "both"), f"Invalid mode: {mode}, must be 'd0', 'd1', or 'both'"
    logging.info(f"🎮 挖掘模式: {mode.upper()}")

    # ── 初始化认证 ──────────────────────────────────────────
    cm = CredentialManager(base_path=os.path.dirname(os.path.abspath(__file__)))
    if not cm.authenticate(auto_load=True, auto_prompt=False):
        logging.error("❌ Authentication failed - cannot proceed without valid credentials")
        logging.error("Failed to authenticate.")
        return

    sess = cm.get_session()
    logging.info("🌟 Connected to WQ Brain for Infinite Evolution!")

    # ── 初始化三大可选模块（任一失败均不影响主流程）──
    validator = _build_validator()
    # 强制关闭 AI 模块以追求极致速度和并发量（根据用户要求）
    ollama_manager = None 
    storage = _build_storage()

    # ── 初始化模拟器 ─────────────────────────────────────────
    # 🔴 修复：扩大HTTP连接池，防止"Connection pool is full"死锁崩溃
    from requests.adapters import HTTPAdapter
    _adapter = HTTPAdapter(pool_connections=50, pool_maxsize=100)
    sess.mount('https://', _adapter)
    sess.mount('http://', _adapter)

    region_configs = {}
    region_configs["USA"] = type('RegionConfig', (), {
        'region': "USA",
        'universe': "TOP1000" if mode == "d0" else "TOP3000",
        'delay': 0 if mode == "d0" else 1
    })()

    tester = SimulatorTester(session=sess, region_configs=region_configs)
    # 线程数控制在6，避免连接池被打爆

    settings = SimulationSettings(
        region="USA",
        testPeriod="P5Y0M0D",
        neutralization="INDUSTRY",
        truncation=0.08
    )

    # ── 从数据库加载历史精英因子作为启动种子 ────────────────────
    historical_seeds = _load_historical_seeds(storage, min_sharpe=1.25, limit=10)

    # ── 从数据库恢复已评估因子集合 ──────────────────────────────
    # D1 去重：加载最近 30 天 / 最多 20000 条。D1 搜索空间极大（遗传变异），
    # 适当历史去重可避免浪费 API 重跑。
    # D0 去重：单独用会话内集合（不从 DB 加载），因为 D0 只有 65 个模板×有限字段，
    # 全量历史会把组合空间耗尽，导致每代生成 0 个候选。
    evaluated_alphas = set()   # D1 去重集（含历史）
    if storage:
        try:
            import sqlite3
            from datetime import datetime, timedelta
            conn = sqlite3.connect(storage.db_path)
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            try:
                cursor.execute(
                    'SELECT DISTINCT template FROM backtest_results '
                    'WHERE region = "USA" AND timestamp >= ? LIMIT 20000',
                    (cutoff,)
                )
            except Exception:
                cursor.execute(
                    'SELECT DISTINCT template FROM backtest_results '
                    'WHERE region = "USA" ORDER BY rowid DESC LIMIT 20000'
                )
            for (tmpl,) in cursor.fetchall():
                if tmpl:
                    evaluated_alphas.add(tmpl)
            conn.close()
            logging.info(f"📚 D1去重：恢复近30天历史 {len(evaluated_alphas)} 条 | D0去重：会话内独立维护")
        except Exception as e:
            logging.warning(f"恢复已评估集合失败（将重新测试历史因子）: {e}")

    evaluated_d0_alphas: set = set()  # D0 专属去重集：只在当前会话内去重，不加载历史

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
        # --- [用户原版 Spectacular 因子及极简护航版] ---
        # 0. 你的原版（绝对原汁原味）
        "ts_mean(group_neutralize(ts_decay_linear(winsorize(implied_volatility_call_120 - implied_volatility_put_120, std=5), 5), subindustry), 15)",
        # 1. 极简护航版 A：最外层加 rank()，强制打散权重，专治 Weight 集中度超标
        "rank(ts_mean(group_neutralize(ts_decay_linear(winsorize(implied_volatility_call_120 - implied_volatility_put_120, std=5), 5), subindustry), 15))",
        # 2. 极简护航版 B：最外层加 group_zscore()，强行拉平行业间波动率差异，专治 Sub-universe Sharpe
        "group_zscore(ts_mean(group_neutralize(ts_decay_linear(winsorize(implied_volatility_call_120 - implied_volatility_put_120, std=5), 5), subindustry), 15), subindustry)",
        # 3. 极简护航版 C：最外层再加一次 winsorize，仅仅切掉最后的极端尾巴（对原逻辑破坏最小）
        "winsorize(ts_mean(group_neutralize(ts_decay_linear(winsorize(implied_volatility_call_120 - implied_volatility_put_120, std=5), 5), subindustry), 15), std=3)",
        # ----------------------------------------
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

    # ── 构建蓝海字段优先池（低用户/低因子数/足够覆盖率的字段）────────────
    _blue_ocean_cache = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "constants",
        "data_fields_cache_USA_1_TOP3000.json"
    )
    _blue_ocean_pool = _build_blue_ocean_pool(
        _blue_ocean_cache, max_users=30, max_alphas=50, min_coverage=0.30
    )
    if _blue_ocean_pool:
        # ★ 从蓝海池中移除已耗尽字段
        _exhausted_init = _get_exhausted_field_set()
        if _exhausted_init:
            _before = len(_blue_ocean_pool)
            _blue_ocean_pool = [b for b in _blue_ocean_pool if b['id'] not in _exhausted_init]
            if _before != len(_blue_ocean_pool):
                logging.info(f"🔪 蓝海池耗尽过滤: {_before} → {len(_blue_ocean_pool)} (已杀死 {_before - len(_blue_ocean_pool)} 个)")
        # 按类别统计蓝海分布
        _bo_cats = {}
        for bo in _blue_ocean_pool:
            _bo_cats[bo['category']] = _bo_cats.get(bo['category'], 0) + 1
        logging.info(
            f"🌊 蓝海类别分布: " +
            " | ".join(f"{k}({v}个)" for k, v in sorted(_bo_cats.items(), key=lambda x: -x[1]))
        )
        logging.info(f"🔪 已耗尽字段总数: {len(_exhausted_init)} | 剩余蓝海: {len(_blue_ocean_pool)}")

    
    # ── 从 operatorRAW.json 动态加载全量算子池 ──────────────────────
    # 不再硬编码！从 JSON 自动分类全部 98 个算子
    _SKIP_OPS = {'generate_stats', 'universe_size', 'self_corr', 'in',
                 'combo_a', 'to_nan', 'is_nan', 'not', 'and', 'or',
                 'equal', 'not_equal', 'greater', 'greater_equal',
                 'less', 'less_equal', 'if_else'}  # 逻辑/元算子不用于变异
    _op_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "constants", "operatorRAW.json")
    wq_ts_ops_1arg = []
    wq_ts_ops_2arg = []
    wq_cs_ops = []        # 截面算子: rank, zscore, normalize...
    wq_group_ops_all = [] # 全量 group 算子
    wq_arith_1arg = []    # 一元算术: abs, log, sqrt, sign...
    wq_arith_2arg = []    # 二元算术: signed_power, power, min, max...
    wq_vec_ops = []       # 向量聚合: vec_avg, vec_sum, vec_min, vec_max
    wq_reduce_ops = []    # 降维统计: reduce_ir, reduce_skewness, reduce_avg...
    wq_trade_ops = []     # 条件交易: trade_when, bucket
    try:
        _all_ops = json.load(open(_op_json_path, encoding='utf-8'))
        for _op in _all_ops:
            _name = _op.get('name', '')
            _cat = _op.get('category', '')
            _defn = _op.get('definition', '')
            if _name in _SKIP_OPS or not _name:
                continue
            if _cat == 'Time Series':
                if 'x, y' in _defn or '(x, y' in _defn:
                    wq_ts_ops_2arg.append(_name)
                else:
                    wq_ts_ops_1arg.append(_name)
            elif _cat == 'Cross Sectional':
                wq_cs_ops.append(_name)
            elif _cat == 'Group':
                wq_group_ops_all.append(_name)
            elif _cat == 'Arithmetic':
                # 解析一元/二元：定义中只有 (x) 的是一元
                if '(x)' in _defn or _defn.endswith('(x)'):
                    wq_arith_1arg.append(_name)
                elif _name in ('abs', 'log', 'sqrt', 'sign', 'inverse',
                               'reverse', 'densify'):
                    wq_arith_1arg.append(_name)
                else:
                    wq_arith_2arg.append(_name)
            elif _cat == 'Transformational':
                if _name in ('trade_when', 'bucket'):
                    wq_trade_ops.append(_name)
                # generate_stats 不加入（纯辅助工具）
            elif _cat == 'Vector':
                wq_vec_ops.append(_name)    # vec_avg(x1,x2), vec_sum(x1,x2)...
            elif _cat == 'Reduce':
                wq_reduce_ops.append(_name) # reduce_ir(x), reduce_skewness(x)...
        _total_ops = (len(wq_ts_ops_1arg) + len(wq_ts_ops_2arg) + len(wq_cs_ops)
                      + len(wq_group_ops_all) + len(wq_arith_1arg) + len(wq_arith_2arg)
                      + len(wq_vec_ops) + len(wq_reduce_ops) + len(wq_trade_ops))
        logging.info(
            f"📦 从 operatorRAW.json 动态加载算子: "
            f"ts_1arg={len(wq_ts_ops_1arg)} ts_2arg={len(wq_ts_ops_2arg)} "
            f"cs={len(wq_cs_ops)} group={len(wq_group_ops_all)} "
            f"arith_1={len(wq_arith_1arg)} arith_2={len(wq_arith_2arg)} "
            f"vec={len(wq_vec_ops)} reduce={len(wq_reduce_ops)} trade={len(wq_trade_ops)} "
            f"| 总计={_total_ops}"
        )
    except Exception as _ope:
        logging.warning(f"⚠️ 算子JSON加载失败({_ope})，使用内置最小集")
        wq_ts_ops_1arg = ["ts_mean", "ts_rank", "ts_zscore", "ts_delta", "ts_std_dev",
                          "ts_decay_linear", "ts_sum", "ts_av_diff"]
        wq_ts_ops_2arg = ["ts_corr", "ts_covariance", "ts_regression"]
        wq_cs_ops = ["rank", "zscore", "normalize", "scale"]
        wq_group_ops_all = ["group_rank", "group_zscore", "group_neutralize"]
        wq_arith_1arg = ["abs", "log", "sqrt", "sign", "inverse"]
        wq_arith_2arg = ["signed_power", "power", "divide"]
        wq_vec_ops = ["vec_avg", "vec_sum", "vec_min", "vec_max"]
        wq_reduce_ops = ["reduce_avg", "reduce_ir", "reduce_skewness", "reduce_sum"]
        wq_trade_ops = ["trade_when"]

    # 合并后的变换池（用于 smart_mutate 的截面/算术包裹）
    wq_transform_ops = wq_cs_ops + wq_arith_1arg
    # 特殊算子（需要额外参数模板）
    wq_special_ops = [
        ("signed_power", "signed_power({X}, 2)"),
        ("winsorize", "winsorize({X}, std=3)"),
        ("hump", "hump({X}, 0.3)"),
        ("kth_element", "kth_element({X}, 3, {W})"),
        ("jump_decay", "jump_decay({X}, {W}, 0.5, 252)"),
        ("last_diff_value", "last_diff_value({X}, {W})"),
        ("days_from_last_change", "days_from_last_change({X})"),
        ("power", "power({X}, 0.5)"),
        ("sqrt", "sqrt(abs({X}))"),
        ("ts_step", "ts_step(1)"),
        ("quantile", "quantile({X}, 0.5)"),
        ("vector_neut", "vector_neut({X})"),
        # ── Reduce 系列（时间序列降维统计）──
        ("reduce_ir", "reduce_ir({X})"),
        ("reduce_skewness", "reduce_skewness({X})"),
        ("reduce_kurtosis", "reduce_kurtosis({X})"),
        ("reduce_norm", "reduce_norm({X})"),
        ("reduce_range", "reduce_range({X})"),
        ("reduce_avg", "reduce_avg({X})"),
        ("reduce_sum", "reduce_sum({X})"),
        ("reduce_min", "reduce_min({X})"),
        ("reduce_max", "reduce_max({X})"),
        ("reduce_stddev", "reduce_stddev({X})"),
        ("reduce_percentage", "reduce_percentage({X}, 0.5)"),
        ("reduce_count", "reduce_count({X}, 0)"),
        ("reduce_powersum", "reduce_powersum({X}, 2)"),
        ("reduce_choose", "reduce_choose({X}, 1)"),
    ]
    # 向后兼容
    wq_ts_ops = wq_ts_ops_1arg
    wq_group_ops = [op for op in wq_group_ops_all if op in
                    ("group_rank", "group_zscore", "group_neutralize")]
    wq_neutralizers = ["subindustry", "sector", "industry"]
    
    def smart_mutate(expr: str) -> str:
        """真正做字段/算子/参数替换的变异
        
        变异类型概率分布（v4 深度变异版）：
          0.00-0.30 (30%) 字段替换（按类别均匀采样，强制换字段）
          0.30-0.40 (10%) ★ 双字段强制替换（同时换2个字段，最大结构变化）
          0.40-0.46 (6%)  参数微调（±30%）
          0.46-0.56 (10%) 外层包裹（单字段 ts 算子）
          0.56-0.66 (10%) ★ 算子注入（双字段/特殊/截面变换）
          0.66-0.72 (6%)  中性化方式变异
          0.72-0.80 (8%)  结构移植（冷门复合结构替换字段）
          0.80-0.86 (6%)  内层算子替换（ts_rank→ts_corr 等）
          0.86-0.92 (6%)  ★ vec/reduce 聚合注入
          0.92-0.96 (4%)  ★ trade_when 条件包裹
          0.96-1.00 (4%)  符号翻转
        """
        import re
        mutated = expr
        roll = random.random()
        
        if roll < 0.30:
            # 字段替换：按类别均匀采样（强制换字段，最重要的多样性来源）
            present = [f for f in wq_fields if f in mutated]
            if present:
                old_f = random.choice(present)
                if wq_fields_by_category and random.random() < 0.75:
                    chosen_cat = _tracker_field_cat.pick_one(list(wq_fields_by_category.keys()))
                    cat_fields = [f for f in wq_fields_by_category[chosen_cat] if f != old_f]
                    new_f = random.choice(cat_fields) if cat_fields else random.choice(
                        [f for f in wq_fields if f != old_f])
                else:
                    new_f = random.choice([f for f in wq_fields if f != old_f])
                mutated = mutated.replace(old_f, new_f, 1)

        elif roll < 0.40:
            # ★ 双字段强制替换：同时换2个字段，最大化结构变化
            present = [f for f in wq_fields if f in mutated]
            if len(present) >= 2:
                fields_to_replace = random.sample(present, 2)
                for old_f in fields_to_replace:
                    if wq_fields_by_category:
                        chosen_cat = _tracker_field_cat.pick_one(list(wq_fields_by_category.keys()))
                        cat_fields = [f for f in wq_fields_by_category[chosen_cat] if f not in present and f not in mutated]
                        new_f = random.choice(cat_fields) if cat_fields else random.choice(
                            [f for f in wq_fields if f != old_f and f not in mutated])
                    else:
                        new_f = random.choice([f for f in wq_fields if f != old_f and f not in mutated])
                    mutated = mutated.replace(old_f, new_f, 1)
            elif present:
                old_f = present[0]
                new_f = random.choice([f for f in wq_fields if f != old_f])
                mutated = mutated.replace(old_f, new_f, 1)

        elif roll < 0.46:
            # 参数微调：把数字 ±30%
            def tweak(m):
                n = int(m.group())
                if n < 1: return m.group()
                delta = max(1, int(n * 0.3))
                return str(max(1, n + random.choice([-delta, delta])))
            mutated = re.sub(r'(?<!\w)\d+(?!\w)', tweak, mutated)

        elif roll < 0.56:
            # 外层包裹：加一层单字段时间序列算子（从全量27个 ts_1arg 中选）
            op = _tracker_operator.pick_one(wq_ts_ops_1arg)
            window = random.choice([5, 8, 10, 15, 20, 30, 60])
            if op == "ts_quantile":
                q = random.choice([0.1, 0.25, 0.5, 0.75, 0.9])
                mutated = f"{op}({mutated}, {q}, {window})"
            else:
                mutated = f"{op}({mutated}, {window})"

        elif roll < 0.66:
            # ★ 算子注入（核心新增！）：用冷门算子替换/包裹内层结构
            inject_roll = random.random()
            present = [f for f in wq_fields if f in mutated]
            
            if inject_roll < 0.35 and len(present) >= 2:
                # 类型A：双字段算子注入 — 找到表达式中两个不同字段，用 ts_corr/ts_covariance/ts_regression 包裹
                f1, f2 = random.sample(present, 2)
                op = _tracker_operator.pick_one(wq_ts_ops_2arg)
                window = random.choice([10, 20, 30, 60])
                if op == "ts_regression":
                    new_sub = f"{op}({f1}, {f2}, {window}, 0, 2)"
                else:
                    new_sub = f"{op}({f1}, {f2}, {window})"
                # 替换第一个字段为新结构
                mutated = mutated.replace(f1, new_sub, 1)
            
            elif inject_roll < 0.65 and present:
                # 类型B：特殊算子包裹 — 用 signed_power/winsorize/hump 等包裹一个字段
                target_f = random.choice(present)
                op_name, op_template = random.choice(wq_special_ops)  # special_ops uses (name, tmpl) tuples
                window = random.choice([10, 20, 30, 60])
                new_sub = op_template.replace("{X}", target_f).replace("{W}", str(window))
                mutated = mutated.replace(target_f, new_sub, 1)
            
            else:
                # 类型C：无状态变换注入 — 用 rank/log/abs/sign 包裹字段
                if present:
                    target_f = random.choice(present)
                    op = _tracker_operator.pick_one(wq_transform_ops)
                    mutated = mutated.replace(target_f, f"{op}({target_f})", 1)

        elif roll < 0.72:
            # 中性化方式变异
            neutralizer = random.choice(wq_neutralizers)
            if "group_neutralize" in mutated:
                for n in wq_neutralizers:
                    mutated = mutated.replace(n, neutralizer)
            else:
                mutated = f"group_neutralize({mutated}, {neutralizer})"

        elif roll < 0.80:
            # 结构移植：把内层字段替换为冷门算子复合结构
            _cold_f1 = random.choice(wq_fields)
            _cold_f2 = random.choice([f for f in wq_fields if f != _cold_f1] or wq_fields)
            _cold_w = random.choice([10, 20, 30, 60])
            cold_structures = [
                f"ts_corr({_cold_f1}, {_cold_f2}, {_cold_w})",
                f"ts_regression({_cold_f1}, {_cold_f2}, {_cold_w}, 0, 2)",
                f"signed_power(rank({_cold_f1}), 2)",
                f"ts_quantile({_cold_f1}, 0.25, {_cold_w})",
                f"ts_covariance({_cold_f1}, {_cold_f2}, {_cold_w})",
                f"ts_arg_max({_cold_f1}, {_cold_w})",
                f"kth_element({_cold_f1}, 3, {_cold_w})",
            ]
            present = [f for f in wq_fields if f in mutated]
            if present:
                old_f = random.choice(present)
                mutated = mutated.replace(old_f, random.choice(cold_structures), 1)

        elif roll < 0.86:
            # ★ 内层算子替换：把已有的 ts_rank/ts_zscore 替换为其他 ts 算子
            # 这是直接改变因子骨架结构的最有效手段
            replaceable_ops = [
                "ts_rank", "ts_zscore", "ts_mean", "ts_delta", "ts_std_dev",
                "ts_decay_linear", "ts_sum", "ts_av_diff",
            ]
            present_ops = [op for op in replaceable_ops if op in mutated]
            if present_ops:
                old_op = random.choice(present_ops)
                # 从全量单字段算子池中选替换（排除自己）
                new_op = _tracker_operator.pick_one([op for op in wq_ts_ops_1arg if op != old_op])
                mutated = mutated.replace(old_op, new_op, 1)

        elif roll < 0.92:
            # ★ vec/reduce 聚合注入（新增！）
            # vec_xxx: 把两个字段聚合 → vec_avg(F1, F2) / vec_sum(F1, F2)
            # reduce_xxx: 时间序列降维 → reduce_ir(x) 提取信息比率
            inject_type = random.random()
            present = [f for f in wq_fields if f in mutated]
            if inject_type < 0.5 and wq_vec_ops and len(present) >= 2:
                # vec 聚合：把两个字段用 vec_avg/vec_sum 合并
                f1, f2 = random.sample(present, 2)
                vec_op = _tracker_operator.pick_one(wq_vec_ops)
                new_sub = f"{vec_op}({f1}, {f2})"
                mutated = mutated.replace(f1, new_sub, 1)
            elif wq_reduce_ops and present:
                # reduce 降维：把一个字段用 reduce_ir/reduce_skewness 包裹
                target_f = random.choice(present)
                red_op = _tracker_operator.pick_one(wq_reduce_ops)
                # 部分 reduce 算子有额外参数
                if red_op in ('reduce_percentage',):
                    new_sub = f"{red_op}({target_f}, 0.5)"
                elif red_op in ('reduce_count',):
                    new_sub = f"{red_op}({target_f}, 0)"
                elif red_op in ('reduce_powersum',):
                    new_sub = f"{red_op}({target_f}, 2)"
                elif red_op in ('reduce_choose',):
                    new_sub = f"{red_op}({target_f}, 1)"
                elif red_op in ('reduce_avg', 'reduce_stddev'):
                    new_sub = f"{red_op}({target_f})"
                else:
                    new_sub = f"{red_op}({target_f})"
                mutated = mutated.replace(target_f, new_sub, 1)

        elif roll < 0.96:
            # ★ trade_when 条件交易包裹（新增！）
            # trade_when(condition, alpha, -1) — 只在条件满足时持仓
            present = [f for f in wq_fields if f in mutated]
            if present:
                cond_field = random.choice(wq_fields)
                cond_window = random.choice([5, 10, 20, 30])
                cond_threshold = random.choice([0.3, 0.5, 0.7])
                condition = f"rank(ts_delta({cond_field}, {cond_window})) > {cond_threshold}"
                mutated = f"trade_when({condition}, {mutated}, -1)"
            else:
                mutated = f"-1 * ({mutated})"

        else:
            # 符号翻转：对整个因子取反（捕捉反向信号）
            mutated = f"-1 * ({mutated})"
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

    _prefetch_lock = threading.Lock()
    _prefetch_ai_pool = []      # 后台预生成的因子缓冲池
    _prefetch_strategy_fields = [] # 后台生成的战略字段缓冲
    _prefetch_thread = None     # 后台线程引用
    _intel_d1_pool = []         # 情报爬虫转化的 D1 模板缓冲
    _intel_d0_pool = []         # 情报爬虫转化的 D0 模板缓冲

    _AI_STRATEGY_THEMES = [
        "趋势跟随 (Trend Following)",
        "均值回归 (Mean Reversion)",
        "统计套利 (Statistical Arbitrage)",
        "量价背离 (Price-Volume Divergence)",
        "基本面动量 (Fundamental Momentum)",
        "多因子组合 (Multi-factor Combination)",
    ]

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

            # ── 每日情报爬虫（利用模拟等待时间，每天只跑一次）──────────
            try:
                from generation_two.intelligence.factor_spider import run_daily_spider, get_expression_templates
                from generation_two.intelligence.intel_to_template import text_to_templates

                new_intel = run_daily_spider(session=sess, force=False)
                if new_intel:
                    logging.info(f"📡 [情报爬虫] 今日新增 {len(new_intel)} 条灵感，启动 Qwen 转化...")
                    converted = text_to_templates(
                        ollama_manager, new_intel, n_per_idea=2, include_d0=True
                    )
                    d1_t = converted.get("d1_templates", [])
                    d0_t = converted.get("d0_templates", [])
                    with _prefetch_lock:
                        _intel_d1_pool.extend(d1_t)
                        _intel_d0_pool.extend(d0_t)
                    logging.info(
                        f"📡 [情报爬虫] Qwen转化完成: D1模板+{len(d1_t)} D0模板+{len(d0_t)}"
                    )

                # 直接从 WQ 排名 alpha 获取的表达式模板（无需 Qwen）
                expr_templates = get_expression_templates()
                if expr_templates:
                    import random as _rnd
                    sample = _rnd.sample(expr_templates, min(10, len(expr_templates)))
                    # 按 D0/D1 分类注入正确的池（修复：之前全部扔进 D1 池）
                    d0_expr = [sanitize_for_d0(t) for t in sample if _classify_d0_or_d1(t) == 'd0']
                    d1_expr = [inject_neutralization(t) for t in sample if _classify_d0_or_d1(t) == 'd1']
                    with _prefetch_lock:
                        _intel_d0_pool.extend(d0_expr)
                        _prefetch_ai_pool.extend(d1_expr)
                    logging.info(
                        f"📡 [情报爬虫] WQ ranked 表达式分类注入: D0={len(d0_expr)} D1={len(d1_expr)}"
                    )

                # ── WQ Brain 中文论坛爬虫（Playwright，每日一次）────────
                try:
                    from generation_two.intelligence.wq_forum_spider import (
                        run_forum_spider, get_forum_templates
                    )
                    # 读取凭据
                    import json as _json
                    _cred_path = Path(__file__).parent / "credential.txt"
                    if _cred_path.exists():
                        _raw = _cred_path.read_text(encoding="utf-8").strip()
                        try:
                            _cred = _json.loads(_raw)
                            _wq_user, _wq_pass = _cred[0], _cred[1]
                        except Exception:
                            _lines = _raw.split("\n")
                            _wq_user, _wq_pass = _lines[0].strip(), _lines[1].strip()

                        logging.info("📡 [情报爬虫] 启动 WQ 中文论坛无头浏览器...")
                        forum_result = run_forum_spider(_wq_user, _wq_pass)
                        forum_templates = get_forum_templates()

                        if forum_templates:
                            # 按 D0/D1 分类注入（含 close/returns/volume 等裸露价格字段 -> D0）
                            d0_forum = [fix_divide_group_rank(sanitize_for_d0(t))
                                       for t in forum_templates
                                       if _classify_d0_or_d1(t) == 'd0']
                            d1_forum = [fix_divide_group_rank(inject_neutralization(t))
                                       for t in forum_templates
                                       if _classify_d0_or_d1(t) == 'd1']

                            forum_sample_d0 = _rnd.sample(d0_forum, min(4, len(d0_forum)))
                            forum_sample_d1 = _rnd.sample(d1_forum, min(4, len(d1_forum)))

                            with _prefetch_lock:
                                # D0 论坛模板 → D0池
                                _intel_d0_pool.extend(forum_sample_d0)
                                # D1 论坛模板 → D1池
                                _intel_d1_pool.extend(forum_sample_d1)
                            logging.info(
                                f"🌐 [中文论坛] 注入 D0={len(forum_sample_d0)} D1={len(forum_sample_d1)} 条论坛FASTEXPR"
                                f" (论坛总计 {forum_result['total']} 篇帖子)"
                            )
                except Exception as _fe:
                    logging.debug(f"[WQ论坛爬虫] 跳过: {_fe}")

            except Exception as _ie:
                logging.debug(f"[情报爬虫] 跳过: {_ie}")

        except Exception as e:
            logging.warning(f"🤖 [后台AI任务] 异常（不影响主流程）: {e}")

    prev_high_performers = []
    prev_losers = []
    
    # 自动分离初始种子池的 D0 和 D1 因子（防止 D0 价格字段污染 D1 遗传裂变）
    d0_knowledge_pool = []   # D0 独立精英池（不混入 D1 遗传池）
    d1_knowledge_pool = []
    for seed in knowledge_pool:
        if _classify_d0_or_d1(seed) == 'd0':
            d0_knowledge_pool.append(seed)
        else:
            d1_knowledge_pool.append(seed)
    knowledge_pool = d1_knowledge_pool
    knowledge_pool_backup = list(knowledge_pool)  # 安全备份：用于骨架全冷却时的兜底恢复
    logging.info(f"🧬 初始种子池自动分流: D1遗传池={len(knowledge_pool)}个 | D0特种池={len(d0_knowledge_pool)}个")

    # ── 从 WQ API 拉取你的 D0 历史精英因子（已验证的高分 delay=0 alpha）─────
    if mode in ("d0", "both"):
        try:
            _wq_d0_elites = []
            for _stage in ["RANKED", "RESEARCH"]:
                try:
                    _resp = sess.get(
                        "https://api.worldquantbrain.com/alphas",
                        params={"limit": 50, "stage": _stage, "order": "-sharpe",
                                "settings.delay": 0, "settings.region": "USA"},
                        timeout=15
                    )
                    if _resp.status_code == 200:
                        for _a in _resp.json().get("results", []):
                            _expr = _a.get("regular", {}).get("code", "")
                            _sharpe = _a.get("is", {}).get("sharpe", 0)
                            if _expr and abs(_sharpe) >= 1.3 and _expr not in evaluated_alphas:  # D0门槛提高到1.3
                                _wq_d0_elites.append(_expr)
                except Exception:
                    pass
            if _wq_d0_elites:
                d0_knowledge_pool = list(dict.fromkeys(_wq_d0_elites + d0_knowledge_pool))[:20]
                logging.info(f"🏆 [WQ API] 拉取到 {len(_wq_d0_elites)} 个 D0 历史精英（delay=0, Sharpe≥1.0），D0种子池={len(d0_knowledge_pool)}")
            else:
                logging.info("🏆 [WQ API] 未找到 D0 历史精英（正常，继续用模板生成）")
        except Exception as _e:
            logging.debug(f"[WQ API D0精英] 跳过: {_e}")
    settings = SimulationSettings(
        region="USA", universe="TOP3000", delay=1, decay=0,
        neutralization="INDUSTRY", truncation=0.08,
        nanHandling="ON", testPeriod="P5Y0M0D"
    )
    # 官方文档要求 D0 使用 TOP1000 或更高流动性宇宙
    # 原因: D0 在收盘前入场，必须确保仓位可成交
    d0_settings = SimulationSettings(
        region="USA", universe="TOP1000", delay=0, decay=0,
        neutralization="INDUSTRY", truncation=0.08,
        nanHandling="ON", testPeriod="P5Y0M0D"
    )

    while True:

        logging.info(f"========= GENERATION {generation} =========")
        alphas_to_test = []

        # ── 骨架冷却状态报告 ──
        _cooled_set = _get_cooled_skeletons(generation)
        if _cooled_set:
            logging.info(f"🧊 当前冷却中骨架: {len(_cooled_set)} 个 | 精英池骨架种类: {len(set(_extract_skeleton(s) for s in knowledge_pool))}")

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

            # 消耗情报爬虫转化的 D1 模板（每代最多 3 个，避免占用太多配额）
            if _intel_d1_pool:
                intel_d1 = [inject_neutralization(t) for t in _intel_d1_pool[:3]
                            if t not in evaluated_alphas]
                alphas_to_test.extend(intel_d1)
                _intel_d1_pool[:] = _intel_d1_pool[3:]
                if intel_d1:
                    logging.info(f"  📡 [情报注入] D1模板 {len(intel_d1)} 个 | 池剩余 {len(_intel_d1_pool)}")

            # D0 情报模板暂存，交给 d0_candidates 使用（在 generate_d0_leg 之前 append）
            intel_d0_this_gen = []
            if _intel_d0_pool:
                intel_d0_this_gen = [t for t in _intel_d0_pool[:2] if t not in evaluated_alphas]
                _intel_d0_pool[:] = _intel_d0_pool[2:]
                if intel_d0_this_gen:
                    logging.info(f"  📡 [情报注入] D0模板 {len(intel_d0_this_gen)} 个 | 池剩余 {len(_intel_d0_pool)}")

        pool_snapshot = knowledge_pool[:21]

        # ━━━ 三条腿因子生成 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 腿一：D0 因子（mode=d0 时 ~20个，mode=both 时 ~8个）
        d0_candidates = []
        if mode in ("d0", "both"):
            d0_count = 20  # 稳定并发：避免连接池爆炸，20个D0/代
            d0_candidates = generate_d0_leg(
                d0_count, wq_fields, wq_fields_by_category,
                d0_knowledge_pool or knowledge_pool, evaluated_d0_alphas, ollama_manager
            )
            # 把本代 D0 候选加入 D0 去重集，下代不重复
            evaluated_d0_alphas.update(d0_candidates)
            # 追加今日情报爬虫的 D0 模板（已由 Qwen 转化，含 {FUND_F} 等占位符需填充）
            if intel_d0_this_gen:
                for raw_t in intel_d0_this_gen:
                    # 简单填充：随机选一个 fundamental 字段替换占位符
                    fund_fields = wq_fields_by_category.get("fundamental", wq_fields[:10])
                    t = raw_t.replace("{FUND_F}", random.choice(fund_fields) if fund_fields else "sales")
                    analyst_fields = wq_fields_by_category.get("analyst", [])
                    t = t.replace("{ANALYST_F}", random.choice(analyst_fields) if analyst_fields else "anl4_adjusted_netincome_ft")
                    blue_fields = wq_fields_by_category.get("option", []) or wq_fields_by_category.get("sentiment", [])
                    t = t.replace("{BLUE_F}", random.choice(blue_fields) if blue_fields else "implied_volatility_call_30")
                    t = t.replace("{FIELD}", random.choice(fund_fields) if fund_fields else "sales")
                    if t.count("(") == t.count(")") and t not in evaluated_alphas:
                        d0_candidates.append(t)

        # 腿二：遗传裂变（精简版，D1，单因子变异+杂交）— 仅 D1/both 模式
        # ★ 从 30→15 seeds，减少裂变腿对种子池的过度依赖，降低自相关
        d1_genetic = []
        if mode in ("d1", "both"):
            # ★ 过滤掉冷却中的骨架种子，强制骨架轮换
            _active_seeds = [s for s in pool_snapshot if not _is_skeleton_cooled(s, generation)]
            if len(_active_seeds) < 5:
                # 冷却太多？从蓝海模板注入新鲜血液
                _fresh = generate_template_alphas(
                    10, wq_fields, evaluated_alphas, wq_fields_by_category,
                    blue_ocean_fields=_blue_ocean_pool
                )
                _active_seeds = _active_seeds + _fresh
                logging.info(f"🧊 骨架冷却导致种子不足，注入 {len(_fresh)} 个新鲜模板")
            for seed in _active_seeds[:8]:  # 减少裂变浪费（15→8），匹配 d1_limit=15
                neutralized_seed = inject_neutralization(seed)
                d1_genetic += [
                    neutralized_seed,
                    f"ts_decay_exp_window({neutralized_seed}, 5, 2)",
                    inject_neutralization(smart_mutate(seed)),
                ]
            num_crossovers = min(15, len(_active_seeds))
            for _ in range(num_crossovers):
                pa = random.choice(_active_seeds)
                pb = random.choice([s for s in _active_seeds if s != pa] or _active_seeds)
                d1_genetic.append(crossover_factors(pa, pb))

        # 腿三：蓝海模板工厂（★ 扩容 20→40，D1，Round-Robin 均衡采样 + 30% 蓝海强制采样）
        d1_blueocean = []
        if mode in ("d1", "both"):
            d1_blueocean = generate_template_alphas(
                15, wq_fields, evaluated_alphas, wq_fields_by_category,  # 40→15，减少浪费
                blue_ocean_fields=_blue_ocean_pool
            )
            d1_blueocean = [inject_neutralization(a) for a in d1_blueocean]

        # [C3 fix] 移除了重复的预加载消耗代码（已在 3170-3181 行处理）

        # 旧逻辑兼容：把所有 D1 因子合并打包
        # Phase 1: Systematic sweep (GrandMaster strategy)
        d1_sweep = []
        if mode in ("d1", "both"):
            d1_sweep = generate_systematic_sweep(
                wq_fields, wq_fields_by_category, evaluated_alphas,
                n=10, fund_fields=None  # 30→10，匹配 d1_limit=15
            )
            d1_sweep = [inject_neutralization(a) for a in d1_sweep]

        logging.info(
            f"  📊 D0腿={len(d0_candidates)} | 裂变腿={len(d1_genetic)} | 蓝海腿={len(d1_blueocean)} | 遍历腿={len(d1_sweep)} | 模式={mode.upper()}\n"
            f"  🔥 探索覆盖: {_tracker_operator.stats()} | {_tracker_template.stats()}"
        )

        d1_combined = d1_genetic + d1_blueocean + d1_sweep
        alphas_to_test = alphas_to_test + d1_combined  # 保留预加载的 AI/情报因子
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # ---- 阶段 4：Validator 过滤非法表达式 + 禁用骨架黑名单过滤 ----
        validated_alphas = []
        rejected_count = 0
        forbidden_count = 0
        _forbidden_set = _load_forbidden_skeletons()  # 每代只加载一次
        for expr in set(alphas_to_test):
            # 骨架黑名单检查（跳过已知会 SELF_CORRELATION 失败的结构）
            if _is_forbidden_structure(expr, _forbidden_set):
                forbidden_count += 1
                continue
            is_valid, cleaned = validate_alpha(validator, expr)
            if is_valid:
                validated_alphas.append(cleaned)
            else:
                rejected_count += 1
        
        if rejected_count > 0 or forbidden_count > 0:
            logging.info(f"  🛡️  Validator 拦截 {rejected_count} 条非法因子 | 🚫 黑名单拦截 {forbidden_count} 条")

        # ---- dedup (skip already evaluated + submission dedup) ----
        try:
            from generation_two.submission_dedup import is_duplicate as _is_sub_dup, record_submission as _record_sub, dedup_stats as _dedup_stats
        except ImportError:
            _is_sub_dup = lambda x: False
            _record_sub = lambda x: None
            _dedup_stats = lambda: "dedup N/A"
        unique_alphas = []
        _sub_dedup_count = 0
        for x in validated_alphas:
            if x not in evaluated_alphas:
                if _is_sub_dup(x):
                    _sub_dedup_count += 1
                    continue
                unique_alphas.append(x)
                evaluated_alphas.add(x)
                _record_sub(x)
        if _sub_dedup_count > 0:
            logging.info(f"  dedup: {_sub_dedup_count} near-duplicates skipped | {_dedup_stats()}")

        # Phase 2: Skeleton similarity filter (pre-submission SELF_CORR check)
        if unique_alphas and knowledge_pool:
            unique_alphas = filter_by_skeleton_similarity(
                unique_alphas, knowledge_pool + d0_knowledge_pool, threshold=0.80
            )
                
        # Memory protection: keep only recent 50k entries (LRU-style)
        if len(evaluated_alphas) > 100000:
            # Keep the most recent 50k instead of full clear to avoid re-submitting
            _eval_list = list(evaluated_alphas)
            evaluated_alphas.clear()
            evaluated_alphas.update(_eval_list[-50000:])
            logging.info(f"Trimmed evaluated_alphas: 100k -> {len(evaluated_alphas)}")
                
        if not unique_alphas:
            logging.info("Diversity collapsed. Introducing fresh blood...")
            # 多样性崩溃时也尝试用 AI 补充
            ai_emergency = generate_ai_alphas(ollama_manager, pool_snapshot, n=5)
            if ai_emergency:
                unique_alphas = [inject_neutralization(a) for a in ai_emergency]
            else:
                engine = AlphaEvolutionEngine()
                unique_alphas = [engine.mutate(knowledge_pool[0]) for _ in range(5)]
            
        # 从模拟器中取出上一代 429 失败被暂存的因子
        retries = getattr(tester, 'get_retry_queue', lambda: [])() if hasattr(tester, 'get_retry_queue') else []
        if retries:
            logging.info(f"♻️ 从重试队列取出 {len(retries)} 个因子优先处理")
            # 优先处理重试因子
            unique_alphas = retries + [a for a in unique_alphas if a not in retries]
            
        # Hard limit：匹配 WQ 实际并发能力（~3 个同时模拟）
        d0_limit = 15 if mode in ("d0", "both") else 0
        d1_limit = 15 if mode in ("d1", "both") else 0

        # [C5 fix] D0 候选也需要经过 Validator + dedup 过滤
        if d0_candidates:
            validated_d0 = []
            _forbidden_set_d0 = _load_forbidden_skeletons()
            for expr in set(d0_candidates):
                if _is_forbidden_structure(expr, _forbidden_set_d0):
                    continue
                is_valid, cleaned = validate_alpha(validator, expr)
                if is_valid and cleaned not in evaluated_alphas:
                    if not _is_sub_dup(cleaned):
                        validated_d0.append(cleaned)
                        _record_sub(cleaned)
            d0_candidates = validated_d0
            logging.info(f"  🛡️ D0 Validator: {len(d0_candidates)} 条通过")

        d0_candidates = d0_candidates[:d0_limit]
        unique_alphas = unique_alphas[:d1_limit]
        logging.info(f"Submitting D0={len(d0_candidates)}(优先) + D1={len(unique_alphas)} to simulator. [mode={mode.upper()}]")

        try:
            logging.info(f"  🎯 提交 D0={len(d0_candidates)}(优先) + D1={len(unique_alphas)} 个，模式={mode.upper()}...")
            # ★ D0 先提交，抢占模拟器资源
            futures_d0 = tester.simulate_batch(d0_candidates, "USA", d0_settings) if (d0_candidates and mode in ("d0", "both")) else []
            futures_d1 = tester.simulate_batch(unique_alphas, "USA", settings) if (unique_alphas and mode in ("d1", "both")) else []
            all_futures = futures_d0 + futures_d1  # D0 在前，优先处理结果

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

                # ★★★ 骨架冷却：每个好因子都记录骨架命中（低门槛）★★★
                _record_skeleton_hit(res.template, generation, res.sharpe)

                # ★★★ 字段耗尽：只有真正优秀的因子才杀字段（高门槛防误杀）★★★
                # 门槛: Sharpe>1.5 & Fitness>1.25 & Turnover<30% & Returns>15%
                _should_kill = (
                    abs(res.sharpe) > 1.5
                    and abs(res.fitness) > 1.25
                    and res.turnover is not None and 0 < res.turnover < 0.30
                    and res.returns is not None and abs(res.returns) > 0.15
                )
                if _should_kill:
                    _kill_fields_from_alpha(res.template, res.sharpe, res.fitness)
                    # 动态更新蓝海池：移除刚被杀死的字段
                    _newly_exhausted = _get_exhausted_field_set()
                    _blue_ocean_pool[:] = [b for b in _blue_ocean_pool if b['id'] not in _newly_exhausted]
                else:
                    logging.info(
                        f"  ⏳ 字段暂不杀死 (未达门槛): S={res.sharpe:.3f} F={res.fitness:.3f} "
                        f"T={res.turnover:.2f} R={res.returns:.3f}"
                    )

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
        
        # Phase 3: Decay Sweep for high-Sharpe factors
        _high_sharpe_for_sweep = [
            r for r in results
            if r.success and r.sharpe is not None and abs(r.sharpe) >= 1.5
        ]
        if _high_sharpe_for_sweep:
            _sweep_variants = generate_decay_sweep_variants(
                _high_sharpe_for_sweep, d0_settings, settings, _d0_template_set
            )
            if _sweep_variants:
                _sweep_exprs = [v[0] for v in _sweep_variants[:12]]  # Cap at 12 variants per gen
                _sweep_settings_list = [v[1] for v in _sweep_variants[:12]]
                _sweep_futures = []
                for _se, _ss in zip(_sweep_exprs, _sweep_settings_list):
                    _sweep_futures.append(tester.simulate_template_concurrent(_se, "USA", _ss))
                try:
                    _sweep_results = tester.wait_for_results(_sweep_futures, timeout=400)
                    for _sr in _sweep_results:
                        if (_sr.success and _sr.sharpe is not None and _sr.fitness is not None
                                and abs(_sr.sharpe) > 1.25 and abs(_sr.fitness) > 1.0):
                            if _sr.sharpe < 0:
                                _sr.template = f"-1 * ({_sr.template})"
                                _sr.sharpe = abs(_sr.sharpe)
                                _sr.fitness = abs(_sr.fitness)
                            _pool = d0_high_performers if _sr.template in _d0_template_set else high_performers
                            _pool.append(_sr.template)
                            _log_discovery(_sr.template, _sr.sharpe, _sr.fitness,
                                           _sr.alpha_id, source="DecaySweep")
                    if storage:
                        storage.store_batch(_sweep_results)
                except Exception as _dse:
                    logging.debug(f"[DecaySweep] Error: {_dse}")

        # ━━━ Near-Miss 四层自适应重试系统 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # D1: Layer-A Sharpe 1.0~1.25 → 推过1.25  |  Layer-B Fitness 0.85~1.0 → 推过1.0
        # D0: Layer-C Sharpe 1.5~2.0 → 推过2.0    |  Layer-D Fitness 1.0~1.3 → 推过1.3
        def _run_near_miss_layer(candidates, variants, layer_name, timeout=350,
                                 target_sharpe=1.25, target_fitness=1.0,
                                 target_pool=None):
            """通用Near-Miss重试执行器（支持 D0/D1 不同门槛和目标池）"""
            if target_pool is None:
                target_pool = high_performers
            if not candidates:
                return
            logging.info(f"  [{layer_name}] 发现 {len(candidates)} 个候选，开始重试...")
            nm_futures, nm_names = [], []
            for nm_res in candidates:
                variant = random.choice(variants)
                is_d0_candidate = nm_res.template in _d0_template_set
                correct_delay = 0 if is_d0_candidate else 1
                retry_settings = SimulationSettings(
                    region="USA",
                    universe=variant["universe"],
                    delay=correct_delay,
                    decay=variant["decay"],
                    neutralization=variant["neutralization"],
                    truncation=variant["truncation"],
                    nanHandling=variant["nanHandling"],
                    testPeriod=variant["testPeriod"],
                )
                logging.info(
                    f"    [{layer_name}] sharpe={nm_res.sharpe:.3f} fitness={nm_res.fitness:.3f} "
                    f"delay={'D0' if is_d0_candidate else 'D1'} 变体={variant['name']} | {nm_res.template[:55]}"
                )
                nm_futures.append(tester.simulate_template_concurrent(nm_res.template, "USA", retry_settings))
                nm_names.append(variant["name"])
            try:
                nm_results = tester.wait_for_results(nm_futures, timeout=timeout)
                for nm_r, vname in zip(nm_results, nm_names):
                    if (nm_r.success and nm_r.sharpe is not None and nm_r.fitness is not None
                            and abs(nm_r.sharpe) > target_sharpe and abs(nm_r.fitness) > target_fitness):
                        if nm_r.sharpe < 0:
                            nm_r.template = f"-1 * ({nm_r.template})"
                            nm_r.sharpe = abs(nm_r.sharpe)
                            nm_r.fitness = abs(nm_r.fitness)
                            logging.warning(
                                f"  🎯 [{layer_name}] 重试成功并反转！变体={vname} "
                                f"Sharpe={nm_r.sharpe:.3f} Fitness={nm_r.fitness:.3f}"
                            )
                        else:
                            logging.warning(
                                f"  🎯 [{layer_name}] 重试成功！变体={vname} "
                                f"Sharpe={nm_r.sharpe:.3f} Fitness={nm_r.fitness:.3f}"
                            )
                        target_pool.append(nm_r.template)
                        _log_discovery(nm_r.template, nm_r.sharpe, nm_r.fitness,
                                       nm_r.alpha_id, source=f"{layer_name}-{vname}")
                    else:
                        logging.info(f"    [{layer_name}] 未过线: sharpe={nm_r.sharpe:.3f} fitness={nm_r.fitness:.3f}")
                if storage:
                    storage.store_batch(nm_results)
            except Exception as e:
                logging.warning(f"[{layer_name}] 重试异常（不影响主流程）: {e}")

        # ── D1 Layer-A：Sharpe 1.0~1.25 优化 ───────────────────────────
        layer_a = [
            res for res in results
            if res.success and res.template
            and res.sharpe is not None and res.fitness is not None
            and NEAR_MISS_SHARPE_MIN_A <= abs(res.sharpe) < NEAR_MISS_SHARPE_MAX_A
            and abs(res.fitness) >= NEAR_MISS_FITNESS_MIN_A
            and res.template not in _d0_template_set  # D0 有自己的层
        ][:MAX_NEAR_MISS_A_PER_GEN]

        # ── D1 Layer-B：Fitness 0.85~1.0 优化 ──────────────────────────
        layer_b = [
            res for res in results
            if res.success and res.template
            and res.fitness is not None and res.sharpe is not None
            and NEAR_MISS_FITNESS_MIN_B <= abs(res.fitness) < NEAR_MISS_FITNESS_MAX_B
            and abs(res.sharpe) >= NEAR_MISS_SHARPE_MIN_B
            and res.template not in _d0_template_set  # D0 有自己的层
            and not (NEAR_MISS_SHARPE_MIN_A <= abs(res.sharpe) < NEAR_MISS_SHARPE_MAX_A
                     and abs(res.fitness) >= NEAR_MISS_FITNESS_MIN_A)
        ][:MAX_NEAR_MISS_B_PER_GEN]

        if layer_a or layer_b:
            logging.info(f"🔄 D1 Near-Miss: Layer-A(Sharpe→1.25)={len(layer_a)} Layer-B(Fitness→1.0)={len(layer_b)}")
            _run_near_miss_layer(layer_a, NEAR_MISS_VARIANTS_SHARPE, "D1-Sharpe优化",
                                 target_sharpe=1.25, target_fitness=1.0, target_pool=high_performers)
            _run_near_miss_layer(layer_b, NEAR_MISS_VARIANTS_FITNESS, "D1-Fitness优化",
                                 target_sharpe=1.25, target_fitness=1.0, target_pool=high_performers)

        # ── D0 Layer-C：Sharpe 1.5~2.0 优化（目标推过 2.0）─────────────
        d0_layer_c = [
            res for res in results
            if res.success and res.template
            and res.sharpe is not None and res.fitness is not None
            and res.template in _d0_template_set
            and D0_NEAR_MISS_SHARPE_MIN <= abs(res.sharpe) < D0_NEAR_MISS_SHARPE_MAX
            and abs(res.fitness) >= D0_NEAR_MISS_FITNESS_REQ
        ][:D0_MAX_NEAR_MISS_SHARPE]

        # ── D0 Layer-D：Fitness 1.0~1.3 优化（目标推过 1.3）────────────
        d0_layer_d = [
            res for res in results
            if res.success and res.template
            and res.sharpe is not None and res.fitness is not None
            and res.template in _d0_template_set
            and D0_NEAR_MISS_FIT_MIN <= abs(res.fitness) < D0_NEAR_MISS_FIT_MAX
            and abs(res.sharpe) >= D0_NEAR_MISS_SHARPE_REQ
            and not (D0_NEAR_MISS_SHARPE_MIN <= abs(res.sharpe) < D0_NEAR_MISS_SHARPE_MAX
                     and abs(res.fitness) >= D0_NEAR_MISS_FITNESS_REQ)
        ][:D0_MAX_NEAR_MISS_FIT]

        if d0_layer_c or d0_layer_d:
            logging.info(
                f"🔄 D0 Near-Miss: Layer-C(Sharpe→2.0)={len(d0_layer_c)} Layer-D(Fitness→1.3)={len(d0_layer_d)}"
            )
            _run_near_miss_layer(d0_layer_c, D0_NEAR_MISS_VARIANTS_SHARPE, "D0-Sharpe优化",
                                 target_sharpe=2.0, target_fitness=1.3, target_pool=d0_high_performers)
            _run_near_miss_layer(d0_layer_d, D0_NEAR_MISS_VARIANTS_FITNESS, "D0-Fitness优化",
                                 target_sharpe=2.0, target_fitness=1.3, target_pool=d0_high_performers)

        # ── VRP Layer-E：波动率风险溢价专属持续优化（用户指定精英）─────────
        # 触发条件：任何含 implied_volatility_call_120 的因子 Sharpe >= 1.3
        vrp_layer_e = [
            res for res in results
            if res.success and res.template
            and res.sharpe is not None
            and abs(res.sharpe) >= VRP_NEAR_MISS_SHARPE_MIN
            and "implied_volatility_call_120" in (res.template or "")
        ][:VRP_MAX_NEAR_MISS]
        # 每代随机选3个VRP候选做轮替注入
        _vrp_inject = [e for e in random.sample(VRP_EXPR_POOL, min(3, len(VRP_EXPR_POOL)))
                       if e not in evaluated_alphas]
        if vrp_layer_e or _vrp_inject:
            logging.info(f"🎯 VRP Layer-E: near-miss命中={len(vrp_layer_e)} + 轮替注入={len(_vrp_inject)}")
            # 对命中的 near-miss 结果做参数扫描（已经是并行的）
            if vrp_layer_e:
                _run_near_miss_layer(vrp_layer_e, VRP_NEAR_MISS_VARIANTS, "VRP-专属优化",
                                     target_sharpe=2.0, target_fitness=1.3, target_pool=d0_high_performers)
            # 轮替注入：batch 并行提交（替代串行 simulate_alpha）
            if _vrp_inject:
                _vrp_settings = SimulationSettings(
                    region="USA", universe="TOP1000", delay=0, decay=0,
                    neutralization="INDUSTRY", truncation=0.1,
                    nanHandling="ON", testPeriod="P5Y0M0D"
                )
                _vrp_futures = tester.simulate_batch(_vrp_inject, "USA", _vrp_settings)
                try:
                    _vrp_results = tester.wait_for_results(_vrp_futures, timeout=300)
                    for _vrp_expr, _vrp_r in zip(_vrp_inject, _vrp_results):
                        evaluated_alphas.add(_vrp_expr)
                        if _vrp_r.success and _vrp_r.sharpe:
                            logging.info(f"🎯 VRP注入: Sharpe={_vrp_r.sharpe:.3f} Fitness={_vrp_r.fitness:.3f} | {_vrp_expr[:70]}")
                            if abs(_vrp_r.sharpe) >= VRP_NEAR_MISS_SHARPE_MIN:
                                d0_high_performers.append(_vrp_expr)
                                _log_discovery(_vrp_expr, _vrp_r.sharpe, _vrp_r.fitness,
                                               _vrp_r.alpha_id, source="VRP-轮替注入")
                except Exception as _ve:
                    logging.debug(f"VRP batch注入异常: {_ve}")
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
            # ★ 骨架多样性强制：同骨架最多占 2 个席位，防止近亲繁殖
            knowledge_pool = _enforce_pool_diversity(list(dict.fromkeys(knowledge_pool)), max_per_skeleton=2)[:15]
            # ★ 过滤掉冷却中的骨架种子
            knowledge_pool = [s for s in knowledge_pool if not _is_skeleton_cooled(s, generation)]
            if not knowledge_pool:
                # 安全兜底：如果全部冷却了，从初始种子池恢复
                knowledge_pool = d1_knowledge_pool[:5] if d1_knowledge_pool else knowledge_pool_backup[:5]
            _sk_types = len(set(_extract_skeleton(s) for s in knowledge_pool))
            logging.info(f"🧬 精英池更新: {len(knowledge_pool)} 条种子 | {_sk_types} 种不同骨架")

        # D0 精英池独立更新（不混入 D1 遗传池）
        if d0_high_performers:
            d0_knowledge_pool = d0_high_performers + d0_knowledge_pool
            d0_knowledge_pool = list(dict.fromkeys(d0_knowledge_pool))[:10]
            logging.info(f"🟢 D0精英池更新: {len(d0_high_performers)} 条新精英 | 池总量={len(d0_knowledge_pool)}")

            # 🔬 D0 成功模式放大器：用 Qwen 分析高分 D0 因子并生成同族变体
            if ollama_manager:
                for _elite in d0_high_performers[:2]:  # 最多放大 2 个
                    try:
                        # 采样真实字段供 Qwen 使用
                        _amp_fields = random.sample(
                            list(wq_fields_by_category.get('fundamental', wq_fields[:20])),
                            min(8, len(wq_fields_by_category.get('fundamental', wq_fields[:20])))
                        )
                        _amp_prompt = (
                            f"This Delay-0 alpha achieved high Sharpe: {_elite}\n"
                            f"Analyze WHY this pattern works, then generate 4 VARIATIONS that:\n"
                            "1. Keep the same structural pattern but swap the data fields\n"
                            "2. Try different time windows (5, 10, 20, 60)\n"
                            "3. Add an extra signal layer (e.g. trade_when condition)\n"
                            f"AVAILABLE FIELDS: {', '.join(_amp_fields)}\n"
                            "D0 RULES: Never use raw close/volume/returns. Use ts_delay(close,1) instead.\n"
                            "Output ONLY a JSON array of 4 expression strings:"
                        )
                        _amp_raw = ollama_manager.generate(
                            _amp_prompt,
                            system_prompt="Output ONLY a JSON array of FASTEXPR strings. No explanation.",
                            temperature=0.7, max_tokens=600
                        )
                        if _amp_raw:
                            _amp_parsed = _parse_ai_alpha_response(_amp_raw)
                            _amp_valid = []
                            for _v in _amp_parsed:
                                _v = re.sub(r'^["\s]*expression["\s]*:\s*["\s]*', '', _v).strip().rstrip('"')
                                _v = sanitize_for_d0(_v)
                                if (_v not in evaluated_alphas and _v not in d0_knowledge_pool
                                        and _v.count('(') == _v.count(')') and len(_v) > 15):
                                    _amp_valid.append(_v)
                            if _amp_valid:
                                with _prefetch_lock:
                                    _intel_d0_pool.extend(_amp_valid)
                                logging.info(
                                    f"🔬 [D0放大器] 从精英 '{_elite[:50]}...' 生成 {len(_amp_valid)} 个同族变体"
                                )
                    except Exception as _ae:
                        logging.debug(f"[D0放大器] 跳过: {_ae}")

        logging.info(
            f"Generation {generation} completed. "
            f"D1精英={len(high_performers)} D0精英={len(d0_high_performers)}. "
            f"Sleeping 5 seconds..."
        )
        # 无空窗期：立即开始下一代（WQ Brain 并发仿真本身就是节流器）
        time.sleep(1)
        generation += 1


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WorldQuant Continuous Evolution Engine")
    parser.add_argument("--mode", choices=["d0", "d1", "both"], default="both",
                        help="挖掘模式: d0=只挖D0, d1=只挖D1, both=双引擎(默认)")
    args = parser.parse_args()
    main(mode=args.mode)
