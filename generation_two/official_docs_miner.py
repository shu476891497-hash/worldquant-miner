#!/usr/bin/env python3
"""
Official Documentation Alpha Miner (官方文档挖掘器)
====================================================

完全基于 WorldQuant BRAIN 28篇官方文档:
- 25+ 官方 Alpha 模板
- 官方推荐的 neutralization 矩阵
- 官方的 decay/truncation/backfill 调参技巧
- 官方的 improvement hints (每个模板都有)
- Earnings4 / Model77 / Model53 / Sentiment1 数据集专属策略
- Power Pool / ATOM / Pyramid 特殊 Alpha 类型优化

独立于 continuous_evolution.py，专门给 inst4 (大号) 使用。
"""

import sys
import os

# Fix Windows GBK encoding for Unicode output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import json
import time
import random
import logging
import requests
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
from itertools import product

# ──────────────────────────── CONFIG ─────────────────────────────

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

API_BASE = "https://api.worldquantbrain.com"
SUBMITTED_DATAFIELDS_PATH = BASE_DIR / "constants" / "submitted_datafields.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"official_miner_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("official_miner")


def _load_submitted_datafield_cache() -> Dict:
    """Load user-submitted field/expression cache used to avoid re-mining spent ideas."""
    if not SUBMITTED_DATAFIELDS_PATH.exists():
        return {}
    try:
        with open(SUBMITTED_DATAFIELDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning(f"Failed to load submitted datafield cache: {exc}")
        return {}


def _template_hits_submitted_cache(template, cache: Dict) -> bool:
    """Return True when a template contains an already-submitted fragment or banned field."""
    raw_expression = template.expression or ""
    expression = raw_expression.replace(" ", "")
    for item in cache.get("banned_exact_expressions", []):
        banned = item.get("expression") if isinstance(item, dict) else item
        normalized = str(banned or "").replace(" ", "")
        if normalized and normalized == expression:
            return True
    for item in cache.get("banned_fields", []):
        field = item.get("field") if isinstance(item, dict) else item
        normalized = str(field or "").replace(" ", "")
        if normalized and normalized in expression:
            return True
    for item in cache.get("submitted_expressions", []):
        if not isinstance(item, dict):
            continue
        fragments = item.get("expression_fragments") or []
        for fragment in fragments:
            normalized = str(fragment).replace(" ", "")
            if normalized and normalized in expression:
                return True
    return False


# ──────────────────────────── DATA CLASSES ─────────────────────────

@dataclass
class AlphaTemplate:
    """官方 Alpha 模板"""
    name: str
    expression: str
    hypothesis: str  # 官方假设
    hint: str  # 官方改进提示
    dataset_category: str  # fundamental / option / model / sentiment / earnings / news / pv
    level: str  # beginner / bronze / silver / custom
    # 推荐设置
    delay: int = 1
    neutralization: str = "INDUSTRY"
    decay: int = 0
    truncation: float = 0.08
    universe: str = "TOP3000"


@dataclass
class ParamVariant:
    """参数变体"""
    expression: str
    decay: int
    neutralization: str
    truncation: float
    universe: str
    delay: int
    mutation_desc: str  # 描述做了什么改变


@dataclass
class SimResult:
    """模拟结果"""
    name: str
    expression: str
    variant_desc: str
    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    margin: float = 0.0
    long_count: int = 0
    short_count: int = 0
    passed_checks: bool = False
    error: str = ""
    submit_url: str = ""
    alpha_id: str = ""


# ──────────────────────────── OFFICIAL TEMPLATES ─────────────────────

def get_official_templates() -> List[AlphaTemplate]:
    """
    从 28 篇官方文档提取的全部 Alpha 模板
    每个模板附带官方假设和改进提示
    """
    templates = []

    # ─── 文档13: 初级 Alpha (5个) ───

    templates.append(AlphaTemplate(
        name="operating_earnings_yield",
        expression="ts_rank(operating_income, 252)",
        hypothesis="经营收入高于1年历史 → 买入",
        hint="用比率(含股市变动)替代直接值: operating_income/cap 或 operating_income/close",
        dataset_category="fundamental",
        level="beginner",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="liability_appreciation",
        expression="-ts_rank(fn_liab_fair_val_l1_a, 252)",
        hypothesis="负债公允价值上升 → 财务恶化 → 做空",
        hint="缩短观察周期可能提高准确性",
        dataset_category="fundamental",
        level="beginner",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="leverage_power",
        expression="liabilities/assets",
        hypothesis="高杠杆(排除差公司)→ 激进增长 → 高回报",
        hint="跨行业差异大，考虑不同neutralization",
        dataset_category="fundamental",
        level="beginner",
        neutralization="MARKET", decay=0, truncation=0.01,
    ))

    templates.append(AlphaTemplate(
        name="earnings_yield_momentum",
        expression="group_rank(ts_rank(est_eps/close, 60), industry)",
        hypothesis="盈利收益率频繁高于历史 → 被低估 → 买入",
        hint="用NAN HANDLING预处理提升性能",
        dataset_category="analyst",
        level="beginner",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="sentiment_stability",
        expression="-ts_std_dev(scl12_buzz, 10)",
        hypothesis="情绪量10天标准差高→不稳定关注→表现不佳",
        hint="更短观察窗口对高流动性股票更有效",
        dataset_category="social_media",
        level="beginner",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    # ─── 文档14: 铜牌 Alpha (3个) ───

    templates.append(AlphaTemplate(
        name="cashflow_valuation",
        expression="group_rank(-ts_zscore(enterprise_value/cashflow, 63), industry)",
        hypothesis="低EV/CF → 相对现金流便宜 → 买入",
        hint="不同类型的cash flow可能改善性能: cashflow_op, free_cashflow",
        dataset_category="fundamental",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="overpriced_detection",
        expression="-ts_corr(est_ptp, est_fcf, 252)",
        hypothesis="分析师价格目标与FCF高度同步 → 已充分定价 → 做空",
        hint="1年窗口太长,试短窗口(63, 126)更快反应",
        dataset_category="analyst",
        level="bronze",
        neutralization="MARKET", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="volatility_arbitrage",
        expression="implied_volatility_call_120/parkinson_volatility_120",
        hypothesis="隐含波动率>历史波动率 → 看涨情绪 → 买入",
        hint="用ts_backfill避免缺失数据",
        dataset_category="option",
        level="bronze",
        neutralization="SECTOR", decay=0, truncation=0.08,
        universe="TOP200",
    ))

    # ─── 文档15: 银牌 Alpha (6个) ───

    templates.append(AlphaTemplate(
        name="iv_spread_predictor",
        expression="trade_when(pcr_oi_270 < 1, (implied_volatility_call_270-implied_volatility_put_270), -1)",
        hypothesis="Call OI > Put OI时，基于IV价差方向交易",
        hint="用floor/bucket+rank实现基于历史波动率的自定义neutralization",
        dataset_category="option",
        level="silver",
        neutralization="MARKET", decay=4, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="call_put_skew_6m",
        expression="(implied_volatility_call_180 - implied_volatility_put_180)/implied_volatility_mean_180",
        hypothesis="Call IV > Put IV / 平均ATM IV → 看涨情绪",
        hint="ts_backfill()通过Weight测试；想办法降低turnover",
        dataset_category="option",
        level="silver",
        delay=0,  # D0!
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="peer_performance_gap",
        expression=(
            "cum_rel = (1+ts_delay(rel_ret_all,4))*(1+ts_delay(rel_ret_all,3))*"
            "(1+ts_delay(rel_ret_all,2))*(1+ts_delay(rel_ret_all,1))*(1+rel_ret_all);\n"
            "cum_own = (1+ts_delay(returns,4))*(1+ts_delay(returns,3))*"
            "(1+ts_delay(returns,2))*(1+ts_delay(returns,1))*(1+returns);\n"
            "cum_rel - cum_own"
        ),
        hypothesis="同行表现好于个股 → 个股均值回归上涨",
        hint="用trade_when仅在差距显著时交易",
        dataset_category="pv",
        level="silver",
        neutralization="SECTOR", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="long_term_investment",
        expression="group_rank(ts_delta(ts_backfill(fnd6_newqv1300_ivltq, 60), 252), subindustry)",
        hypothesis="持续增加长期投资的公司 → 未来更高利润",
        hint="给同时有收入增长的公司加更大权重",
        dataset_category="fundamental",
        level="silver",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fcf_quality",
        expression="ts_decay_linear(ts_scale(est_cashflow_op, 252), 22) - ts_decay_linear(ts_scale(est_capex, 252), 22)",
        hypothesis="持续高运营现金流/资本支出 → 优质自由现金流",
        hint="存货周转改善>50%时信号放大",
        dataset_category="analyst",
        level="silver",
        neutralization="INDUSTRY", decay=2, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="bull_trap",
        expression=(
            "slope = ts_regression(ts_backfill(news_pct_1min, 60), ts_step(1), 5, 0, 2);\n"
            "winsorize(-ts_backfill(news_max_up_ret, 60) * abs(slope), std=4)"
        ),
        hypothesis="首分钟反应趋势恶化+今天大涨 → 多头陷阱",
        hint="改善turnover",
        dataset_category="news",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    # ─── 文档23: Model77 (5个) ───

    templates.append(AlphaTemplate(
        name="mdl77_ebitda_ev",
        expression="ts_backfill(mdl77_fa_ebitdaev, 252)",
        hypothesis="高EBITDA/EV → 运营盈利强 → 潜在低估",
        hint="Long高yield, Short极低/负值",
        dataset_category="model",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="mdl77_sue",
        expression="ts_backfill(mdl77_400_sue, 252)",
        hypothesis="正盈利惊喜→持续公告后价格漂移(PEAD)",
        hint="Long显著正惊喜, 避开极端正值(可能反转)",
        dataset_category="model",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="mdl77_ocf_assets",
        expression="ts_backfill(mdl77_ocfast, 252)",
        hypothesis="高现金流/资产 → 高效运营+高质量盈利",
        hint="Long强劲且改善中的, Short显著恶化的",
        dataset_category="model",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="mdl77_momentum_6m",
        expression="ts_backfill(mdl77_opricemomentumfactor_actrtn6m, 252)",
        hypothesis="滞后6个月动量捕获趋势,避免短期反转",
        hint="用days_from_last_change()过滤盈利公告期",
        dataset_category="model",
        level="silver",
        neutralization="INDUSTRY", decay=2, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="mdl77_altman_z",
        expression="ts_backfill(mdl77_altmanz, 252)",
        hypothesis="高Altman Z → 财务稳定 → 不确定期表现好",
        hint="市场不确定时Long财务稳定, Short有困难信号的",
        dataset_category="model",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
        universe="TOP1000",
    ))

    # ─── 文档24: Model53 (3个) ───

    templates.append(AlphaTemplate(
        name="mdl53_curve_slope",
        expression="ts_backfill(mdl53_jc5_5year, 252) - ts_backfill(mdl53_jc5_1year, 252)",
        hypothesis="违约曲线从陡峭变平→长期前景改善",
        hint="关注结构变化先于股价变动",
        dataset_category="model",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="mdl53_inversion",
        expression="-(ts_backfill(mdl53_jc5_1year, 252) - ts_backfill(mdl53_jc5_5year, 252))",
        hypothesis="违约曲线倒挂=急性暂时困境→均值回归机会",
        hint="Long基本面健全但短期倒挂的公司",
        dataset_category="model",
        level="silver",
        neutralization="MARKET", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="mdl53_default_accel",
        expression="-sign(ts_delta(ts_backfill(mdl53_jc6_1year, 252), 22))",
        hypothesis="违约概率增速加速→做空; 减速→做多(市场反应不足)",
        hint="用sign()+ts_delta()捕获二阶导数拐点",
        dataset_category="model",
        level="silver",
        neutralization="INDUSTRY", decay=2, truncation=0.08,
    ))

    # ─── 文档25: Sentiment1 (3个) ───

    templates.append(AlphaTemplate(
        name="snt1_score",
        expression="ts_backfill(snt1_cored1_score, 60)",
        hypothesis="正情绪→市场信心→买入; 负情绪→卖出",
        hint="score>5做多, score<-5做空",
        dataset_category="sentiment",
        level="beginner",
        neutralization="INDUSTRY", decay=4, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="snt1_earnings_surprise",
        expression="ts_backfill(snt1_d1_earningssurprise, 60)",
        hypothesis="正盈利惊喜→价格上行",
        hint="结合分析师覆盖率过滤",
        dataset_category="sentiment",
        level="beginner",
        neutralization="INDUSTRY", decay=2, truncation=0.08,
        universe="TOP1000",
    ))

    templates.append(AlphaTemplate(
        name="snt1_analyst_consensus",
        expression="ts_backfill(snt1_d1_buyrecpercent, 60)",
        hypothesis="高买入/卖出推荐比+足够覆盖→信心→买入",
        hint="过滤掉snt1_d1_analystcoverage低的",
        dataset_category="sentiment",
        level="beginner",
        neutralization="SUBINDUSTRY", decay=2, truncation=0.08,
        universe="TOP1000",
    ))

    # ─── 文档22: Earnings4 (核心) ───

    templates.append(AlphaTemplate(
        name="ern4_earnings_iv_gap",
        expression="vec_avg(ern4_30div) - vec_avg(ern4_30dexerniv)",
        hypothesis="30天IV - 去盈利效应IV = 隐含盈利效应",
        hint="xern配对是earnings4最有效的构造方式",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_forecast_vs_realized",
        expression="ts_backfill(vec_avg(ern4_fcsterneffct), 5) - ts_backfill(vec_avg(ern4_erneffct1), 5)",
        hypothesis="预测效应 - 实现效应 = 市场预期偏差",
        hint="预测家族是低turnover高margin的宝地",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_implied_move",
        expression="ts_backfill(vec_avg(ern4_impernmv90d), 5)",
        hypothesis="市场隐含的下次盈利移动百分比",
        hint="信号在forecast vs implied的差距中",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_ernmv1_drift",
        expression="ts_backfill(vec_avg(ern4_ernmv1), 60)",
        hypothesis="最近盈利移动大小→盈利后漂移(PEAD)代理",
        hint="ernmv1是全数据集使用最多的字段; ts_delta检测新事件",
        dataset_category="earnings",
        level="bronze",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hv_earnings_share",
        expression="vec_avg(ern4_120dclshv) - vec_avg(ern4_500dclshvxern)",
        hypothesis="历史波动率中盈利日贡献的占比",
        hint="HV-HVxern=盈利日波动率贡献,基本面数据无法提供",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    # ─── 文档8: vector_neut (高级) ───

    templates.append(AlphaTemplate(
        name="beta_neutralized_momentum",
        expression=(
            "mkt = group_mean(returns, 1, market);\n"
            "beta = ts_regression(returns, mkt, 252, 0, 2);\n"
            "raw = -ts_delta(close, 5);\n"
            "vector_neut(raw, beta)"
        ),
        hypothesis="消除市场beta暴露后的纯反转信号",
        hint="vector_neut消除因子暴露,降低波动率,提升Sharpe",
        dataset_category="pv",
        level="silver",
        neutralization="MARKET", decay=0, truncation=0.08,
    ))

    # ─── 基本面归一化模板 (量纲感知) ───────────────────────────
    # 策略: Total Amount 字段 / assets, Per Share 字段 / bookvalue_ps
    #       消除市值效应，避免做多/做空大公司
    #       你朋友的建议: 先把字段按量纲清洗再用

    templates.append(AlphaTemplate(
        name="fn_sales_to_assets_rank",
        expression="group_rank(ts_rank(sales / (assets + 0.000001), 252), subindustry)",
        hypothesis="销售/资产比率历史排名高 → 资产利用效率改善 → 买入",
        hint="长窗口(252)适合季报更新频率；用subindustry消除行业差异",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_ebitda_assets_momentum",
        expression="group_rank(ts_delta(ebitda / (assets + 0.000001), 60), subindustry)",
        hypothesis="EBITDA/总资产比率上升 → 盈利能力改善 → 买入",
        hint="ts_delta捕捉变化率；60天=季度级检测",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_netincome_assets_zscore",
        expression="group_neutralize(ts_zscore(operating_income / (assets + 0.000001), 120), subindustry)",
        hypothesis="净利润/资产Z分数高 → 超出历史均值的盈利 → 买入",
        hint="ts_zscore标准化避免绝对值差异",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_eps_bvps_rank",
        expression="ts_decay_linear(group_rank(eps / (bookvalue_ps + 0.000001), subindustry), 15)",
        hypothesis="EPS/每股净资产(ROE代理)行业排名高 → 高质量 → 买入",
        hint="ts_decay_linear降低turnover，适合基本面低频数据",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_opincome_assets_ir",
        expression="group_rank(ts_mean(operating_income / (assets + 0.000001), 120) / (ts_std_dev(operating_income / (assets + 0.000001), 120) + 0.000001), subindustry)",
        hypothesis="经营收入/资产的信息比率高 → 稳定改善 → 买入",
        hint="mean/std information ratio proxy; avoids inaccessible ts_ir operator",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_capex_assets_change",
        expression="-1 * group_rank(ts_delta(capex / (assets + 0.000001), 60), subindustry)",
        hypothesis="资本支出/资产比率下降 → 效率提升或成熟期 → 短期利好",
        hint="负号=做空资本支出加速的公司",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_equity_assets_trend",
        expression="group_rank(ts_delta(equity / (assets + 0.000001), 252), subindustry)",
        hypothesis="权益/资产比率长期上升趋势 → 财务结构改善 → 买入",
        hint="ts_regression rettype=2 返回斜率",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_sales_ps_bvps_corr",
        expression="-1 * group_rank(ts_corr(sales_ps / (bookvalue_ps + 0.000001), returns, 60), subindustry)",
        hypothesis="每股销售/每股净资产与回报率负相关 → 定价偏差 → 反转",
        hint="负号=反转逻辑; 60天窗口适中",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_debt_assets_decay",
        expression="-1 * ts_decay_linear(group_rank(debt_lt / (assets + 0.000001), subindustry), 20)",
        hypothesis="高杠杆行业内排名高 → 财务风险大 → 做空",
        hint="ts_decay_linear(20)大幅降低turnover",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_cashflow_assets_skew",
        expression="group_rank(ts_skewness(cashflow_dividends / (assets + 0.000001), 252), subindustry)",
        hypothesis="现金流/资产偏度正 → 有正向异常 → 买入",
        hint="ts_skewness是稀有算子，相关性极低",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_revenue_assets_jump",
        expression="group_rank(last_diff_value(sales / (assets + 0.000001), 120), subindustry)",
        hypothesis="收入/资产比率跳变幅度大 → 季报惊喜 → 动量信号",
        hint="last_diff_value检测阶跃变化，适合季度数据",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_ebitda_vs_income_spread",
        expression="group_rank(ts_rank(ebitda/(assets+0.000001) - operating_income/(assets+0.000001), 120), subindustry)",
        hypothesis="EBITDA/资产-净利润/资产差距扩大→高非现金费用→关注",
        hint="双字段归一化比率对比，衡量盈利质量",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_fnd6_sale_at_entropy",
        expression="group_rank(ts_entropy(fnd6_sales / (assets + 0.000001), 252), subindustry)",
        hypothesis="销售/总资产熵值高→分布不确定性大→价格发现不充分",
        hint="ts_entropy是极稀有算子，理论上与其他因子零相关",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_conditional_improvement",
        expression="trade_when(ts_delta(operating_income/(assets+0.000001), 60) > 0, group_rank(operating_income/(assets+0.000001), subindustry), nan)",
        hypothesis="仅在ROA改善时交易 → 条件信号 → 降低噪音",
        hint="trade_when大幅降低turnover，只在条件满足时持仓",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_gross_margin_iqr",
        expression="group_rank(ts_quantile(ebitda/(assets+0.000001), 0.75, 252) - ts_quantile(ebitda/(assets+0.000001), 0.25, 252), subindustry)",
        hypothesis="毛利率IQR大→波动大→未被充分定价",
        hint="分位数价差是低相关性信号",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # ── ts_regression 系列模板 (强算子, 多种 rettype) ──

    # rettype=2: slope (趋势斜率)
    templates.append(AlphaTemplate(
        name="fn_sales_trend_slope",
        expression="group_rank(ts_delta(sales_ps, 252), subindustry)",
        hypothesis="每股销售长期趋势斜率为正 → 收入稳步增长 → 买入",
        hint="ts_regression rettype=2返回斜率, ts_step(1)是时间序列",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_ebitda_trend_slope",
        expression="group_rank(ts_delta(ebitda, 252), subindustry)",
        hypothesis="EBITDA趋势斜率为正 → 盈利能力持续提升 → 买入",
        hint="长窗口(252天)捕捉年度趋势",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_eps_trend_slope",
        expression="group_rank(ts_delta(eps, 120), subindustry)",
        hypothesis="EPS半年趋势为正 → 盈利改善 → 买入",
        hint="120天窗口更敏感, 适合捕捉季报变化",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # rettype=0: residual (偏离趋势的异常值)
    templates.append(AlphaTemplate(
        name="fn_sales_resid_reversal",
        expression="-1 * group_rank(ts_zscore(sales_ps, 252), subindustry)",
        hypothesis="残差为正=高于趋势→均值回归做空; 残差为负→反弹做多",
        hint="rettype=0返回残差, 捕捉偏离长期趋势的异常",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # rettype=1: R² (拟合度 → 趋势可靠性)
    templates.append(AlphaTemplate(
        name="fn_operating_income_r2",
        expression="group_rank(ts_mean(operating_income, 252) / (ts_std_dev(operating_income, 252) + 0.000001), subindustry)",
        hypothesis="经营收入趋势R²高→走势可预测→市场定价准确→动量有效",
        hint="rettype=1返回R², 高R²意味着线性趋势强",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # 双因子回归: 用一个因子解释另一个
    templates.append(AlphaTemplate(
        name="fn_eps_vs_sales_beta",
        expression="group_rank(ts_zscore(eps / (sales_ps + 0.000001), 252), subindustry)",
        hypothesis="EPS对每股销售的beta高→利润率杠杆大→高弹性",
        hint="两个基本面字段做回归, 衡量利润率弹性",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # PV 回归
    templates.append(AlphaTemplate(
        name="pv_volume_trend_slope",
        expression="group_rank(ts_regression(volume, ts_step(1), 60, 0, 2), subindustry)",
        hypothesis="成交量趋势上升→关注度增加→可能有催化剂",
        hint="60天短窗口适合PV信号",
        dataset_category="pv",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # 回归残差 + 条件信号
    templates.append(AlphaTemplate(
        name="fn_equity_resid_signal",
        expression=(
            "trend = ts_delta(equity, 252);\n"
            "z = ts_zscore(equity, 252);\n"
            "trade_when(trend > 0, -group_rank(z, subindustry), nan)"
        ),
        hypothesis="权益趋势向上时, 负残差=暂时低于趋势→买入反弹",
        hint="组合slope+residual, 条件信号降低turnover",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # ══════════════════════════════════════════════════════════════════
    # Option6 — Forecasted Volatility for Equity Options (133 fields)
    # 文档要点: Market/Sector neutralization, 季度窗口, ts_delta/ts_zscore
    # ══════════════════════════════════════════════════════════════════

    # --- Dividend Cluster (文档: "最rewarding的起点") ---
    templates.append(AlphaTemplate(
        name="opt6_divyield_zscore",
        expression="group_rank(ts_zscore(opt6_divyield, 252), sector)",
        hypothesis="股息率Z分数高→近期股息提升→基本面改善→买入",
        hint="文档: 股息字段比纯fundamental少拥挤; Sector neutralization",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_divamt_trend",
        expression="group_rank(ts_regression(opt6_divamt, ts_step(1), 252, 0, 2), sector)",
        hypothesis="股息金额长期趋势为正→持续回馈股东→质量信号",
        hint="ts_regression slope; 股息数据在option dataset中更新",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    # --- Volatility Surface Shape (Slope/Skew) ---
    templates.append(AlphaTemplate(
        name="opt6_slope_mean_revert",
        expression="group_rank(-ts_delta(opt6_slopeavg1m, 60), sector)",
        hypothesis="Skew slope 1个月均值近期下降→put需求减少→看涨",
        hint="文档: shape signals tend to mean-revert at sector level",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_slope_pctile_reversal",
        expression="-group_rank(opt6_slopepctile, sector)",
        hypothesis="Slope百分位极高→put demand过度→均值回归做空slope",
        hint="文档: slope captures demand for downside puts vs upside calls",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_slope_vs_avg1y",
        expression="group_rank(opt6_slopeavg1m - opt6_slopeavg1y, sector)",
        hypothesis="短期slope>长期slope→近期put需求激增→反转信号",
        hint="文档: 用价差而非ts_corr, 避免机械相关性",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_vired_rank",
        expression="-group_rank(ts_zscore(opt6_vired, 60), sector)",
        hypothesis="smile弯曲度异常高→尾部风险恐慌→均值回归做多",
        hint="文档: vired衡量smile弯曲速度, large=sharp bend",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_derivinf_spread",
        expression="group_rank(ts_zscore(opt6_derivinf, 60) - ts_zscore(opt6_slopeinf, 60), sector)",
        hypothesis="curvature vs slope的Z分数价差→结构性定价偏差",
        hint="文档建议: subtract(ts_zscore(X,60), ts_zscore(Y,60))",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # --- Forecast Confidence as Gate ---
    templates.append(AlphaTemplate(
        name="opt6_gated_iv_signal",
        expression="trade_when(ts_mean(opt6_fcstr2imp, 60) > 0.5, -ts_delta(opt6_20div, 60), -1)",
        hypothesis="forecast R²高时IV下降→vol crush→做多",
        hint="文档核心技巧: trade_when(ts_mean(fcstr2imp,60)>0.5, signal, -1)",
        dataset_category="option",
        level="custom",
        neutralization="MARKET", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_gated_slope_signal",
        expression="trade_when(ts_mean(opt6_2rtscf, 60) > 0.3, -group_rank(opt6_slope, sector), nan)",
        hypothesis="realized vol预测R²高时slope信号更可靠",
        hint="文档: R²是confidence signal, 非directional",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # --- Cross-Asset Ratios ---
    templates.append(AlphaTemplate(
        name="opt6_ivspyratio_zscore",
        expression="ts_zscore(opt6_ivspyratio, 60)",
        hypothesis="相对SPY的IV Z分数高→期权贵→做空; 低→便宜→做多",
        hint="文档: ratio fields已去除cross-asset, 用MARKET neutralization",
        dataset_category="option",
        level="custom",
        neutralization="MARKET", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_ivetfratio_delta",
        expression="-ts_delta(opt6_ivetfratioavg1m, 60)",
        hypothesis="相对ETF的IV ratio近期上升→相对贵→做空",
        hint="文档: ratio已有cross-asset adjustment, MARKET neutralization更干净",
        dataset_category="option",
        level="custom",
        neutralization="MARKET", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_corr_spy_regime",
        expression="group_rank(-ts_delta(opt6_correlspy1m, 60), sector)",
        hypothesis="与SPY相关性下降→独立定价→可能有idiosyncratic催化剂",
        hint="相关性变化比绝对值更有信息量",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # --- Earnings Effect ---
    templates.append(AlphaTemplate(
        name="opt6_implied_earnings_effect",
        expression="group_rank(-ts_zscore(opt6_impliediee, 60), sector)",
        hypothesis="隐含盈利效应Z分数异常高→市场预期极端→均值回归",
        hint="文档: 从term structure equation求解, 不需aggressive backfill",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_earnings_move_rank",
        expression="-group_rank(ts_delta(opt6_absavgernmv, 60), sector)",
        hypothesis="预期盈利移动近期上升→不确定性增加→做空",
        hint="文档: option model continuously computed, ts_backfill(5)足够",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # --- IV Level Signals ---
    templates.append(AlphaTemplate(
        name="opt6_iv_term_structure",
        expression="group_rank(opt6_30div - opt6_90div, sector)",
        hypothesis="短期IV>长期IV→倒挂→近期事件风险→做空",
        hint="文档: constant-maturity IV已经过插值滤波",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="opt6_iv_percentile_reversal",
        expression="-ts_av_diff(opt6_ivpctile1m, 60)",
        hypothesis="1个月IV百分位偏离均值→均值回归",
        hint="文档: prefer ts_av_diff over short-window deltas",
        dataset_category="option",
        level="custom",
        neutralization="MARKET", decay=5, truncation=0.08,
    ))

    # --- HV vs IV Spread ---
    templates.append(AlphaTemplate(
        name="opt6_iv_hv_spread",
        expression="group_rank(opt6_20div - opt6_20dorhv, sector)",
        hypothesis="IV>HV→期权溢价→vol sellers获利→做多underlying",
        hint="IV-HV spread是经典vol trading信号",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # --- Forecast vs Realized ---
    templates.append(AlphaTemplate(
        name="opt6_forecast_regime",
        expression=(
            "r2 = ts_mean(opt6_fcstr2imp, 60);\n"
            "iv_chg = ts_delta(opt6_20div, 60);\n"
            "trade_when(r2 > 0.5, group_rank(-iv_chg, sector), nan)"
        ),
        hypothesis="模型confidence高+IV下降→可靠的vol crush→做多",
        hint="文档核心策略: forecast R²作为gate提升signal质量",
        dataset_category="option",
        level="custom",
        neutralization="SECTOR", decay=5, truncation=0.08,
    ))

    # ══════════════════════════════════════════════════════════════════
    # Fundamental7 — Comprehensive Fundamentals Data (311 fields)
    # 文档要点: EPS quality, footnote vs primary alignment, cash flow
    # ══════════════════════════════════════════════════════════════════

    # --- EPS Quality (文档核心策略) ---
    templates.append(AlphaTemplate(
        name="fnd7_eps_quality",
        expression="-group_rank(abs(fnd7_ointfund_qxspeo - fnd7_ointhstfund_hqxspeo), subindustry)",
        hypothesis="diluted EPS与footnote EPS回归斜率→高→报告一致→高质量",
        hint="文档Alpha Idea: footnote reinforces primary → higher earnings quality",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_eps_footnote_spread",
        expression="group_rank(ts_zscore(fnd7_ointfund_qxspeo - fnd7_ointhstfund_hqxspeo, 120), subindustry)",
        hypothesis="主报告EPS-footnote EPS差异扩大→会计处理异常→关注",
        hint="文档: alignment between standard reports and detailed footnotes",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # --- Income Quality ---
    templates.append(AlphaTemplate(
        name="fnd7_income_before_extraordinary",
        expression="group_rank(ts_delta(fnd7_ointfund_qbi, 252), subindustry)",
        hypothesis="税前经常性收入趋势上升→核心盈利改善→买入",
        hint="qbi = income before extraordinary items, 排除非经常性",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- Cash Flow ---
    templates.append(AlphaTemplate(
        name="fnd7_operating_cashflow_trend",
        expression="group_rank(ts_delta(fnd7_ointfund_qfcnao, 252), subindustry)",
        hypothesis="融资活动现金流趋势→反映资本结构变化",
        hint="fnd7提供详细cash flow statement items",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_cash_position",
        expression="group_rank(ts_delta(fnd7_ointfund_qehc, 60), subindustry)",
        hypothesis="现金和短期投资增加→财务安全边际扩大→买入",
        hint="qehc = Cash and short-term investments at quarter end",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- Capital Expenditure vs Operations ---
    templates.append(AlphaTemplate(
        name="fnd7_capex_efficiency",
        expression="-group_rank(fnd7_ointfund_qxpac / (fnd7_ointfund_qbi + 0.000001), subindustry)",
        hypothesis="资本支出/收入比率低→高效运营→买入",
        hint="qxpac=capex, qbi=income before extraordinary",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- Retained Earnings ---
    templates.append(AlphaTemplate(
        name="fnd7_retained_earnings_growth",
        expression="group_rank(ts_delta(fnd7_ointfund_qer, 252), subindustry)",
        hypothesis="留存收益趋势上升→内生增长→买入",
        hint="qer = retained earnings, 公司自我积累能力",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # --- Cost Structure ---
    templates.append(AlphaTemplate(
        name="fnd7_cogs_margin",
        expression="-group_rank(ts_delta(fnd7_ointfund_qsgoc, 120), subindustry)",
        hypothesis="COGS增速放缓→毛利率改善→买入",
        hint="qsgoc = cost of goods sold, quarterly",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- EPS 12-month Trend ---
    templates.append(AlphaTemplate(
        name="fnd7_eps_12m_trend",
        expression="group_rank(ts_delta(fnd7_ointfund_21speo, 252), subindustry)",
        hypothesis="12个月移动EPS趋势上升→持续盈利改善→买入",
        hint="21speo = EPS from operations, trailing 12 months",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # Deep Fundamental Pack: FND2/FND6/FND7 fields verified in local USA_1_TOP3000 cache.
    # FND1/FND3 are intentionally not added until their fields are present in cache.

    # --- FND2: detailed disclosures, financing, tax quality ---
    templates.append(AlphaTemplate(
        name="fnd2_tax_cash_gap",
        expression="-group_rank(ts_zscore((fn_income_taxes_paid_a - fn_income_tax_expense_a) / (assets + 0.000001), 252), subindustry)",
        hypothesis="Cash taxes materially above booked tax expense can pressure future free cash flow.",
        hint="FND2 disclosure field; normalize by assets and rank within subindustry.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_deferred_tax_quality",
        expression="-group_rank(ts_delta(fn_def_income_tax_expense_a / (fn_income_tax_expense_a + 0.000001), 252), subindustry)",
        hypothesis="Rising deferred tax share can indicate lower cash earnings quality.",
        hint="Uses annual deferred tax expense versus total tax expense.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_net_debt_issuance_pressure",
        expression="-group_rank(ts_mean((fn_proceeds_from_issuance_of_debt_q - fn_repayments_of_debt_q) / (fn_debt_instrument_carrying_amount_q + 0.000001), 120), sector)",
        hypothesis="Net debt issuance relative to debt stock flags external financing dependence.",
        hint="Sector neutralization keeps capital-structure norms comparable.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_debt_repayment_strength",
        expression="group_rank(ts_rank(fn_repayments_of_debt_q / (fn_debt_instrument_carrying_amount_q + 0.000001), 252), subindustry)",
        hypothesis="Consistent debt repayment indicates balance-sheet repair and lower refinancing risk.",
        hint="Long time-series rank fits low-frequency disclosure cadence.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_sbc_dilution_drag",
        expression="-group_rank(ts_delta(fn_allocated_share_based_compensation_expense_q / (fn_comprehensive_income_net_of_tax_q + 0.000001), 120), subindustry)",
        hypothesis="Rising share-based compensation versus comprehensive income dilutes real shareholder return.",
        hint="Quarterly FND2 compensation disclosure; negative sign penalizes acceleration.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_deferred_tax_asset_risk",
        expression="-group_rank(ts_zscore(fn_def_tax_assets_liab_net_q / (assets + 0.000001), 252), subindustry)",
        hypothesis="Large deferred tax asset balances can be fragile if future profitability weakens.",
        hint="Asset-normalized balance-sheet disclosure with subindustry ranking.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_expected_dividend_support",
        expression="group_rank(ts_rank(fnd2_a_sbcpnargmtwfsptepddvdrt, 252), sector)",
        hypothesis="Higher expected dividend rate supports income-quality and shareholder-return demand.",
        hint="Uses FND2 estimated dividend-rate disclosure; sector rank avoids yield-sector bias.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_restructuring_overhang",
        expression="-group_rank(ts_mean(fnd2_a_restructuringcharges / (assets + 0.000001), 252), subindustry)",
        hypothesis="Persistent restructuring charges suggest operational stress and future margin drag.",
        hint="Lower coverage but low crowding; keep decay high to reduce turnover.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_inventory_mix_shift",
        expression="-group_rank(ts_delta(fnd2_a_inventoryfinishedgoods / (fnd2_a_inventoryrawmaterials + 0.000001), 120), subindustry)",
        hypothesis="Finished-goods buildup versus raw materials can flag demand weakness.",
        hint="Inventory composition signal; negative sign treats buildup as risk.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_receivable_reserve_risk",
        expression="-group_rank(ts_zscore(fn_allowance_for_doubtful_accounts_receivable_a / (fn_ppne_gross_a + 0.000001), 252), subindustry)",
        hypothesis="High doubtful-account allowance can indicate deteriorating customer quality.",
        hint="Uses FND2 receivable reserve disclosure normalized by asset scale.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- FND6: industry/special-item fields with low crowding in cache ---
    templates.append(AlphaTemplate(
        name="fnd6_core_pension_quality",
        expression="group_rank(ts_rank(fnd6_newqeventv110_pnciaq, 252), subindustry)",
        hypothesis="Favorable after-tax pension adjustment versus pretax drag can improve reported quality.",
        hint="Low-crowding FND6 pension event fields.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_restructuring_cost_reversal",
        expression="-group_rank(ts_zscore(fnd6_newqeventv110_rcaq, 252), subindustry)",
        hypothesis="Large restructuring costs are often followed by near-term uncertainty and margin pressure.",
        hint="FND6 restructuring after-tax field has low user and alpha counts.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_export_sales_momentum",
        expression="group_rank(ts_delta(fnd6_salexg / (fnd6_sales + 0.000001), 252), sector)",
        hypothesis="Rising export-sales share can capture external demand surprise inside sectors.",
        hint="Uses low-crowding export sales field normalized by net sales.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_dividend_stability",
        expression="group_rank(ts_rank(ts_backfill(fnd6_divd, 20), 252), sector)",
        hypothesis="Stable cash dividends proxy durable cash generation and shareholder discipline.",
        hint="Daily dividend field is sparse; short backfill reduces missingness.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_goodwill_impairment_warning",
        expression="-group_rank(ts_zscore(fnd6_newqeventv110_gdwlipq, 252), subindustry)",
        hypothesis="Goodwill impairment events reveal overpaid acquisitions and weak capital allocation.",
        hint="Combines pretax and EPS-effect impairment fields.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_inventory_finished_goods_alert",
        expression="-group_rank(ts_delta(fnd6_newqeventv110_invfgq, 120), subindustry)",
        hypothesis="Finished-goods inventory growing faster than raw materials can signal demand slowdown.",
        hint="Low-crowding FND6 inventory detail.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_working_capital_stress",
        expression="-group_rank(ts_delta(fnd6_cptnewqeventv110_rectq, 120), subindustry)",
        hypothesis="Receivables rising faster than payables and sales can reveal cash conversion stress.",
        hint="Receivables/payables event fields are less crowded than generic fundamentals.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_level3_liability_risk",
        expression="-group_rank(ts_zscore(fnd6_newqeventv110_lul3q, 252), sector)",
        hypothesis="High Level-3 liability share increases valuation uncertainty and downside risk.",
        hint="Fair-value hierarchy signal; sector rank keeps financial exposure comparable.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_core_eps_option_spread",
        expression="group_rank(ts_zscore(fnd6_newqv1300_spcep12 - fnd6_newqv1300_xoptdq, 252), subindustry)",
        hypothesis="Core earnings strength beyond option-related EPS effects is higher-quality earnings.",
        hint="Separates core 12-month earnings from option EPS dilution.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- FND7: point-in-time cash-flow and balance-sheet structure ---
    templates.append(AlphaTemplate(
        name="fnd7_operating_cash_flow_improvement",
        expression="group_rank(ts_delta(fnd7_ointfund_qfcnao / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="Operating cash flow improving relative to assets indicates stronger self-funded growth.",
        hint="PIT FND7 operating cash flow normalized by total assets.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_financing_dependency",
        expression="-group_rank(ts_mean(fnd7_ointfund_qfcnif / (fnd7_ointfund_qqec + 0.000001), 120), sector)",
        hypothesis="High financing cash inflow relative to common equity signals external capital dependence.",
        hint="Negative sign penalizes financing dependence; sector neutralization for capital structure.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_shortterm_debt_surge",
        expression="-group_rank(ts_delta(fnd7_ointfund_qcld / (fnd7_ointfund_qqec + 0.000001), 120), subindustry)",
        hypothesis="Current debt surges versus equity can reveal liquidity stress.",
        hint="PIT current-debt field; use quarter-scale window.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_longterm_debt_pressure",
        expression="-group_rank(ts_delta(fnd7_ointfund_qttld / (fnd7_ointfund_qqec + 0.000001), 252), sector)",
        hypothesis="Long-term debt rising versus equity can dilute future ROE through interest burden.",
        hint="Uses FND7 total long-term debt outstanding at quarter end.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_dividend_stability_pit",
        expression="group_rank(ts_rank(ts_backfill(fnd7_ointfund_qvd, 20), 252), subindustry)",
        hypothesis="PIT cash dividends paid at high historical rank proxy durable cash generation.",
        hint="Point-in-time dividend cash-flow field with light backfill.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_cash_balance_strength",
        expression="group_rank(ts_delta(fnd7_ointfund_qehc / (fnd7_ointfund_qtcl + 0.000001), 120), subindustry)",
        hypothesis="Cash and short-term investments rising versus current liabilities improves liquidity margin.",
        hint="Balances cash against current liabilities instead of absolute company size.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_investing_cashflow_discipline",
        expression="group_rank(ts_delta((fnd7_ointfund_qfcnao + fnd7_ointfund_qfcnvi) / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="Operating cash flow covering investment cash use is a cleaner free-cash-flow proxy.",
        hint="Combines PIT operating and investing cash-flow statements.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_aggressive_expansion_alert",
        expression="-group_rank(ts_delta(fnd7_ointfund_qoa / (fnd7_ointfund_qqec + 0.000001), 252), subindustry)",
        hypothesis="Other assets expanding versus equity can flag aggressive or opaque asset growth.",
        hint="Close to the requested other-assets expansion template using actual FND7 PIT field.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_receivable_quality",
        expression="-group_rank(ts_delta(fnd7_ointfund_qtcer / (fnd7_ointfund_qelas + 0.000001), 120), subindustry)",
        hypothesis="Receivables rising versus sales can signal lower revenue quality.",
        hint="PIT receivables and sales fields; negative sign penalizes buildup.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_payables_cash_conversion",
        expression="group_rank(ts_delta(fnd7_ointfund_qhclapa / (fnd7_ointfund_qelas + 0.000001), 120), subindustry)",
        hypothesis="Accounts-payable cash-flow improvement can support near-term cash conversion.",
        hint="Uses cash-flow statement change in payables against PIT sales.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_buyback_support",
        expression="group_rank(ts_rank(fnd7_ointfund_qcktsrp / (fnd7_ointfund_qqec + 0.000001), 252), sector)",
        hypothesis="Common/preferred stock purchases relative to equity can indicate shareholder-return support.",
        hint="Cash outflow for stock purchases; sector rank avoids capital-return sector bias.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_pit_vs_footnote_liability_gap",
        expression="-group_rank(ts_zscore((fnd7_ointfund_qtl - fnd7_ointhstfund_hqtl) / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="A widening PIT-versus-footnote liability gap can flag reporting-quality risk.",
        hint="FND7 footnote alignment idea extended from EPS to liabilities.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # Deep Fundamental Pack II: more cache-verified, low-risk operator templates.

    templates.append(AlphaTemplate(
        name="fnd2_ppne_growth_drag",
        expression="-group_rank(ts_delta(fn_ppne_gross_a / (assets + 0.000001), 252), subindustry)",
        hypothesis="Rapid PP&E growth versus assets can signal heavy investment needs before returns arrive.",
        hint="Asset-normalized PP&E expansion; simple delta avoids fragile low-frequency regression.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_quarterly_tax_burden",
        expression="-group_rank(ts_zscore(fn_income_tax_expense_q / (abs(fn_comprehensive_income_net_of_tax_q) + 0.000001), 120), subindustry)",
        hypothesis="High quarterly tax burden relative to comprehensive income can pressure retained earnings.",
        hint="Uses quarterly FND2 tax and comprehensive-income disclosures.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_oci_balance_risk",
        expression="-group_rank(ts_zscore(fn_accum_oth_income_loss_net_of_tax_q / (assets + 0.000001), 252), sector)",
        hypothesis="Large accumulated OCI balances can hide mark-to-market risk in book equity.",
        hint="Sector rank because OCI exposure differs structurally by industry.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_sbc_asset_drag",
        expression="-group_rank(ts_rank(fn_allocated_share_based_compensation_expense_q / (assets + 0.000001), 252), subindustry)",
        hypothesis="Persistent stock compensation relative to assets dilutes economic ownership.",
        hint="Stable rank signal on FND2 SBC disclosure.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_cash_tax_momentum",
        expression="-group_rank(ts_delta(fn_income_taxes_paid_a / (assets + 0.000001), 252), subindustry)",
        hypothesis="Rising cash taxes relative to assets can reduce distributable cash flow.",
        hint="Annual cash-tax paid field; negative sign penalizes acceleration.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd2_refinancing_balance",
        expression="group_rank(ts_delta((fn_repayments_of_debt_q - fn_proceeds_from_issuance_of_debt_q) / (assets + 0.000001), 120), sector)",
        hypothesis="Debt repayments exceeding new issuance indicate refinancing discipline.",
        hint="Quarterly financing cash-flow spread normalized by assets.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_liability_fair_value_mix",
        expression="-group_rank(ts_zscore(fnd6_newqeventv110_lol2q, 252), sector)",
        hypothesis="Level-2 liabilities high versus Level-1 liabilities increase valuation uncertainty.",
        hint="Fair-value hierarchy mix, using low-crowding FND6 fields.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_wip_inventory_buildup",
        expression="-group_rank(ts_delta(fnd6_newqeventv110_invwipq, 120), subindustry)",
        hypothesis="Work-in-process inventory buildup versus finished goods can flag production bottlenecks.",
        hint="Industry-specific inventory composition signal.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_receivable_payable_balance",
        expression="-group_rank(ts_zscore(fnd6_cptnewqeventv110_rectq, 252), subindustry)",
        hypothesis="Receivables high versus payables can imply weaker cash conversion.",
        hint="Event-version working-capital detail, less crowded than generic ratios.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_core_earnings_acceleration",
        expression="group_rank(ts_delta(fnd6_newqv1300_spcep12, 252) / (ts_std_dev(fnd6_newqv1300_spcep12, 252) + 0.000001), subindustry)",
        hypothesis="Core 12-month earnings acceleration with stable volatility indicates quality improvement.",
        hint="Delta over volatility proxy, no regression dependency.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_dividend_rate_trend",
        expression="group_rank(ts_delta(ts_backfill(fnd6_dvrated, 20), 252), sector)",
        hypothesis="Rising indicated dividend rate supports shareholder-return momentum.",
        hint="Backfill daily indicated dividend rate before long-window delta.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd6_debt_due_1y_pressure",
        expression="-group_rank(ts_rank(fnd6_eventv110_dd1q / (fnd6_newqeventv110_lltq + 0.000001), 252), sector)",
        hypothesis="Debt due within one year relative to long-term liabilities flags refinancing pressure.",
        hint="Debt maturity stress template using low-crowding FND6 fields.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_cash_operating_margin",
        expression="group_rank(ts_rank(fnd7_ointfund_qfcnao / (fnd7_ointfund_qelas + 0.000001), 252), subindustry)",
        hypothesis="Operating cash flow margin high versus own history indicates durable cash earnings.",
        hint="PIT operating cash flow over PIT sales.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_current_ratio_improvement",
        expression="group_rank(ts_delta(fnd7_ointfund_qtca / (fnd7_ointfund_qtcl + 0.000001), 120), subindustry)",
        hypothesis="Improving current ratio increases short-term solvency cushion.",
        hint="PIT current assets/current liabilities, quarter-scale delta.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_cash_tax_drag",
        expression="-group_rank(ts_rank(fnd7_ointfund_qdpxt / (abs(fnd7_ointfund_qip) + 0.000001), 252), subindustry)",
        hypothesis="High cash taxes paid relative to pretax income reduce cash available to shareholders.",
        hint="PIT cash-flow tax paid versus pretax income.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_rd_reinvestment_quality",
        expression="group_rank(ts_delta(fnd7_ointfund_qdrx / (fnd7_ointfund_qelas + 0.000001), 252), subindustry)",
        hypothesis="R&D intensity rising versus sales can indicate reinvestment in future growth.",
        hint="Works best inside subindustry where R&D norms are comparable.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_acquisition_cash_drag",
        expression="-group_rank(ts_mean(fnd7_ointfund_qcqa / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="Persistent acquisition cash outflow can indicate integration and capital-allocation risk.",
        hint="PIT acquisition cash-flow item normalized by total assets.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_alert",
        expression="-group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120), sector)",
        hypothesis="Rising issuance of long-term debt relative to outstanding debt can flag leverage pressure.",
        hint="PIT issuance/outstanding long-term debt ratio.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_supported",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120) * ts_rank(fnd7_ointfund_qfcnao / (fnd7_ointfund_qta + 0.000001), 252), sector)",
        hypothesis="Long-term debt issuance backed by strong operating cash flow can signal productive financing capacity.",
        hint="Builds on RRrKVEp0: keep issuance signal, gate it by asset-scaled operating cash-flow quality.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_net_issuance_repair",
        expression="group_rank(ts_delta((fnd7_ointfund_qsitld - fnd7_ointfund_qrtld) / (fnd7_ointfund_qttld + 0.000001), 120), sector)",
        hypothesis="Net long-term debt issuance captures financing expansion after subtracting repayments.",
        hint="Separates gross issuance from simultaneous deleveraging to reduce noisy balance-sheet churn.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_assets_momentum",
        expression="hump(group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qta + 0.000001), 120), sector), 0.01)",
        hypothesis="Debt issuance scaled by total assets avoids overweighting firms with small existing debt bases.",
        hint="Uses assets instead of long-term debt denominator and hump to reduce drawdown/turnover.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_cash_coverage_combo",
        expression="group_rank(group_zscore(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120), sector) + group_zscore(fnd7_ointfund_qfcnao / (abs(fnd7_ointfund_qtnix) + abs(fnd7_ointfund_qcld) + 0.000001), sector), sector)",
        hypothesis="Debt issuance is more investable when cash flow covers interest expense and current debt.",
        hint="Aims to lift fitness and reduce drawdown by combining financing access with debt-service quality.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_sales_growth_finance",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120) * ts_delta(fnd7_ointfund_qelas / (fnd7_ointfund_qta + 0.000001), 120), sector)",
        hypothesis="Debt issuance paired with improving sales productivity can indicate growth financing rather than distress borrowing.",
        hint="Combines RRrKVEp0 issuance slope with asset-normalized sales improvement.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_regression_trend",
        expression="group_rank(ts_regression(fnd7_ointfund_qsitld / (fnd7_ointfund_qta + 0.000001), fnd7_ointfund_qelas / (fnd7_ointfund_qta + 0.000001), 252), sector)",
        hypothesis="Debt issuance that historically tracks sales productivity can be productive financing.",
        hint="Regression beta links asset-scaled debt issuance to asset-scaled sales over one year.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_base",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120), sector)",
        hypothesis="RRrKVEp0 showed the positive debt-issuance direction is the live signal; tune it directly.",
        hint="Positive version of the near-miss core with tighter truncation to reduce drawdown.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_hump",
        expression="hump(group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 120), sector), 0.005)",
        hypothesis="Hump smoothing may keep the strong issuance signal while reducing the near-miss drawdown.",
        hint="Same RRrKVEp0 core, with very light hump to dampen rebalance shocks.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_avdiff",
        expression="group_rank(ts_av_diff(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 252), sector)",
        hypothesis="Debt issuance above its one-year average may capture the same financing regime with less endpoint noise.",
        hint="Replaces ts_delta with ts_av_diff to reduce single-quarter jump sensitivity.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_window60",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 60), sector)",
        hypothesis="A shorter quarter-scale issuance acceleration may improve returns while preserving low turnover.",
        hint="Same denominator as RRrKVEp0 but with a 60-day change window.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_window252",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qttld + 0.000001), 252), sector)",
        hypothesis="A full-year issuance change may reduce drawdown by favoring persistent financing access.",
        hint="Same denominator as RRrKVEp0 but with a 252-day change window.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_long_debt_issuance_positive_assets",
        expression="group_rank(ts_delta(fnd7_ointfund_qsitld / (fnd7_ointfund_qta + 0.000001), 120), sector)",
        hypothesis="Scaling debt issuance by assets avoids denominator instability when existing long-term debt is small.",
        hint="Tests whether the near-miss improves when total assets replace long-term debt as denominator.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=8, truncation=0.04,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_debt_repayment_strength",
        expression="group_rank(ts_rank(fnd7_ointfund_qrtld / (fnd7_ointfund_qttld + 0.000001), 252), sector)",
        hypothesis="Long-term debt repayment relative to debt stock supports balance-sheet repair.",
        hint="PIT cash repayment of long-term debt over outstanding long-term debt.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_deferred_tax_income_quality",
        expression="-group_rank(ts_zscore(fnd7_ointfund_qidxt / (abs(fnd7_ointfund_qip) + 0.000001), 252), subindustry)",
        hypothesis="Deferred taxes high versus pretax income may indicate lower cash quality of earnings.",
        hint="PIT deferred income tax ratio.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_accrual_quality_cash_gap",
        expression="group_rank(winsorize(ts_zscore((fnd7_ointfund_qfcnao - fnd7_ointfund_qin) / (fnd7_ointfund_qta + 0.000001), 252), std=4), subindustry)",
        hypothesis="Operating cash flow exceeding reported net income indicates higher earnings quality and lower accrual risk.",
        hint="Uses PIT operating cash flow minus quarterly net income, normalized by assets and winsorized.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_free_cashflow_yield_quality",
        expression="hump(group_rank(ts_rank((fnd7_ointfund_qfcnao + fnd7_ointfund_qfcnvi) / (fnd7_ointfund_qta + 0.000001), 252), subindustry), 0.01)",
        hypothesis="Companies converting assets into free cash flow should have stronger forward returns than asset-heavy peers.",
        hint="Operating plus investing cash flow approximates free cash flow; hump limits low-frequency turnover jumps.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_cashflow_sales_regression_beta",
        expression="group_rank(ts_regression(fnd7_ointfund_qfcnao / (fnd7_ointfund_qta + 0.000001), fnd7_ointfund_qelas / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="A high cash-flow response to sales indicates sales are translating into real cash earnings.",
        hint="ts_regression(y, x, d) estimates cash-flow sensitivity to asset-normalized sales.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_working_capital_release",
        expression="group_rank(ts_av_diff((fnd7_ointfund_qhccer + fnd7_ointfund_qhclapa + fnd7_ointfund_qhcvni) / (fnd7_ointfund_qta + 0.000001), 252), subindustry)",
        hypothesis="Working-capital release from receivables, payables, and inventory supports cash conversion.",
        hint="Cash-flow statement working-capital items are scaled by assets and compared with their own history.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_receivable_inventory_risk",
        expression="-group_rank(ts_delta((fnd7_ointfund_qtcer + abs(fnd7_ointfund_qhcvni)) / (fnd7_ointfund_qelas + 0.000001), 120), subindustry)",
        hypothesis="Receivables and inventory pressure rising faster than sales often flags lower revenue quality.",
        hint="Combines balance-sheet receivables with cash-flow inventory change against PIT sales.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_margin_cost_discipline",
        expression="-group_rank(ts_delta((fnd7_ointfund_qsgoc + fnd7_ointfund_qagsx) / (fnd7_ointfund_qelas + 0.000001), 120), subindustry)",
        hypothesis="COGS plus SG&A falling relative to sales captures improving operating discipline.",
        hint="Industry-neutral cost intensity change is usually cleaner than raw income growth.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_shareholder_yield_cashback",
        expression="group_rank(ts_rank((fnd7_ointfund_qvd + fnd7_ointfund_qcktsrp - fnd7_ointfund_qktss) / (fnd7_ointfund_qqec + 0.000001), 252), sector)",
        hypothesis="Dividends plus buybacks net of equity issuance indicate shareholder-friendly capital allocation.",
        hint="Balances cash dividends and repurchases against common/preferred stock issuance.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_debt_service_coverage",
        expression="group_rank(ts_rank((fnd7_ointfund_qfcnao + fnd7_ointfund_qnptni) / (abs(fnd7_ointfund_qtnix) + abs(fnd7_ointfund_qcld) + 0.000001), 252), sector)",
        hypothesis="Cash flow covering interest expense and current debt improves balance-sheet resilience.",
        hint="Debt service coverage uses PIT cash flow, net interest paid, interest expense, and current debt.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SECTOR", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_rd_cash_productivity",
        expression="group_rank(ts_regression(fnd7_ointfund_qfcnao / (fnd7_ointfund_qta + 0.000001), fnd7_ointfund_qdrx / (fnd7_ointfund_qelas + 0.000001), 252), subindustry)",
        hypothesis="R&D that co-moves with cash-flow improvement is more valuable than raw R&D spending.",
        hint="Regression beta links R&D intensity to cash-flow generation within the firm's PIT history.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_balance_sheet_quality_combo",
        expression="group_rank(group_zscore(fnd7_ointfund_qehc / (fnd7_ointfund_qta + 0.000001), subindustry) - group_zscore(fnd7_ointfund_qtl / (fnd7_ointfund_qta + 0.000001), subindustry), subindustry)",
        hypothesis="Cash-rich, low-liability balance sheets provide a quality tilt inside each subindustry.",
        hint="Cross-sectional group z-scores combine liquidity strength and leverage penalty.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_clean_eps_momentum",
        expression="group_rank(ts_delta((fnd7_ointfund_21speo - fnd7_ointfund_21xspe) / (abs(fnd7_ointfund_21xspe) + 0.000001), 120), subindustry)",
        hypothesis="Operations EPS improving versus EPS excluding extraordinary items captures cleaner core earnings momentum.",
        hint="Uses trailing 12-month PIT EPS fields instead of noisier single-quarter EPS.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    templates.append(AlphaTemplate(
        name="fnd7_nonoperating_income_drag",
        expression="-group_rank(ts_zscore(fnd7_ointfund_qipon / (abs(fnd7_ointfund_qip) + 0.000001), 252), subindustry)",
        hypothesis="Pretax income relying on nonoperating income is lower quality than core operating profitability.",
        hint="Penalizes unusually high PIT nonoperating income relative to pretax income.",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=8, truncation=0.06,
    ))

    # ═══════════════════════════════════════════════════════════════════
    # IQC 2026 Tip #3: hump 操作符 + earnings4 数据集
    # hump(x, hump=threshold): 限制信号变化频率和幅度
    #   - 如果变化 < threshold，保持前值不变 → 降低换手
    #   - 如果变化 > threshold，只允许变化 threshold 幅度 → 降低回撤
    # ═══════════════════════════════════════════════════════════════════

    # --- Tip #3 官方示例模板 (直接复现) ---
    templates.append(AlphaTemplate(
        name="ern4_hump_90div_zscore",
        expression="hump(ts_zscore(ts_backfill(vec_avg(ern4_90div), 252), 5), hump=0.0005)",
        hypothesis="Official Tip #3 template: 90-day IV z-score stabilized by hump to reduce turnover and drawdown.",
        hint="Exact reproduction of IQC Tip #3 example. hump=0.0005 is the official recommendation.",
        dataset_category="earnings",
        level="custom",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + IV 系列: 隐含波动率信号稳定化 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_30div_zscore",
        expression="hump(ts_zscore(ts_backfill(vec_avg(ern4_30div), 252), 5), hump=0.0005)",
        hypothesis="30-day constant-maturity IV z-score with hump stabilization: low-turnover IV regime signal.",
        hint="Shorter IV tenor captures faster regime changes; hump prevents whipsawing.",
        dataset_category="earnings",
        level="custom",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_60div_zscore",
        expression="hump(ts_zscore(ts_backfill(vec_avg(ern4_60div), 252), 5), hump=0.0005)",
        hypothesis="60-day IV z-score with hump: medium-term volatility regime detection with stable portfolio turnover.",
        hint="60-day tenor balances speed and stability; hump smooths quarterly IV spikes.",
        dataset_category="earnings",
        level="custom",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_10div_rank",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_10div), 252), subindustry), hump=0.001)",
        hypothesis="10-day very short-term IV cross-sectional rank, hump-stabilized to prevent excessive turnover from daily noise.",
        hint="10div is noisier than 30/60/90div; hump is essential to prevent churn.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + IV Gap (隐含盈利效应): 核心 alpha ---
    templates.append(AlphaTemplate(
        name="ern4_hump_iv_gap",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_30div), 252) - ts_backfill(vec_avg(ern4_30dexerniv), 252), subindustry), hump=0.001)",
        hypothesis="Earnings IV premium (30div - 30dexerniv) is the core earnings4 alpha. hump stabilizes portfolio turnover.",
        hint="The IV gap is the single most effective earnings4 construction. hump adds stability.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_iv_gap_zscore",
        expression="hump(ts_zscore(ts_backfill(vec_avg(ern4_30div), 252) - ts_backfill(vec_avg(ern4_30dexerniv), 252), 60), hump=0.0005)",
        hypothesis="Z-scored IV gap detects when earnings premium is unusually high/low; hump prevents overtrading.",
        hint="60-day z-score window captures quarterly patterns; hump=0.0005 matches official recommendation.",
        dataset_category="earnings",
        level="custom",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + Forecast 系列: 低换手高边际 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_fcsterneffct",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_fcsterneffct), 5), subindustry), hump=0.001)",
        hypothesis="Forecast earnings effect is already slow-changing; hump further reduces turnover for near-zero churn.",
        hint="Forecast family (fcsterneffct) updates rarely; hump pushes turnover below 5%.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_forecast_gap",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_fcsterneffct), 5) - ts_backfill(vec_avg(ern4_erneffct1), 5), subindustry), hump=0.001)",
        hypothesis="Gap between forecasted and realized earnings effect; hump eliminates noise from infrequent updates.",
        hint="Forecast vs realized is a classic 'expectation surprise' signal; hump keeps turnover ultra-low.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + Fair Vol 系列: 模型公允价值偏差 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_fairvol_gap",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_fairvol90d), 252) - ts_backfill(vec_avg(ern4_90div), 252), subindustry), hump=0.001)",
        hypothesis="Fair value vol model vs actual 90-day IV: positive gap = market underpricing volatility.",
        hint="fairvol90d is model-based; gap to market IV is a mispricing signal. hump smooths.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_fairxiee_gap",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_fairxieevol90d), 252) - ts_backfill(vec_avg(ern4_90div), 252), subindustry), hump=0.001)",
        hypothesis="Fair vol excluding implied earnings effect vs actual IV: pure non-earnings mispricing signal.",
        hint="fairxieevol90d removes earnings component; cleaner structural mispricing.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + 盈利移动 (ernmv) 系列 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_ernmv1_drift",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_ernmv1), 60), subindustry), hump=0.001)",
        hypothesis="Post-earnings drift (PEAD) from last earnings move, stabilized by hump for lower churn.",
        hint="ernmv1 is the most-used field in earnings4. hump prevents turnover spikes around announcement.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_ernmv1_normalized",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_ernmv1), 5) / ts_backfill(vec_avg(ern4_absavgernmv), 252), subindustry), hump=0.001)",
        hypothesis="ernmv1 normalized by avg absolute move: captures 'surprise magnitude' relative to history.",
        hint="Division by absavgernmv normalizes for stock-specific earnings volatility.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + Implied Earnings Move ---
    templates.append(AlphaTemplate(
        name="ern4_hump_implied_vs_avg",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_impernmv90d), 252) - ts_backfill(vec_avg(ern4_absavgernmv), 252), subindustry), hump=0.001)",
        hypothesis="Implied move vs historical average: market overestimating/underestimating future earnings vol.",
        hint="Positive gap = market expects bigger move than usual → potential mean reversion.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + 期限结构: IV vs HV ---
    templates.append(AlphaTemplate(
        name="ern4_hump_iv_hv_spread",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_30div), 252) - ts_backfill(vec_avg(ern4_20dclshv), 252), subindustry), hump=0.001)",
        hypothesis="IV > HV = market overpricing vol (sell vol); IV < HV = underpricing (buy vol). hump stabilizes.",
        hint="Classic variance risk premium signal from earnings4; hump prevents whipsaw.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_iv_hv_spread_neg",
        expression="-hump(group_rank(ts_backfill(vec_avg(ern4_90div), 252) - ts_backfill(vec_avg(ern4_90dclshv), 252), subindustry), hump=0.001)",
        hypothesis="Negative of IV-HV spread: short overpriced vol stocks. 90-day tenor for medium-term view.",
        hint="Negative sign → buy stocks where vol is cheap relative to realized.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + Slope + 波动率曲面 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_slope",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_slope), 252), subindustry), hump=0.001)",
        hypothesis="Volatility term structure slope reflects market's forward vol expectations. hump reduces noise.",
        hint="slope is a derivative signal; hump is critical to avoid over-trading on daily fluctuations.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + HV xern (去盈利实现波动率) ---
    templates.append(AlphaTemplate(
        name="ern4_hump_hv_earnings_share",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_1000dclshv), 252) - ts_backfill(vec_avg(ern4_1000dclshvxern), 252), subindustry), hump=0.001)",
        hypothesis="Long-term HV minus HV-excluding-earnings: isolates historical earnings-day volatility contribution.",
        hint="Fundamental data cannot provide this; only earnings4 has HV/HVxern decomposition.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + ATM IV 月度展期 ---
    templates.append(AlphaTemplate(
        name="ern4_hump_atm_term_spread",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_m1atmiv), 252) - ts_backfill(vec_avg(ern4_m3atmiv), 252), subindustry), hump=0.001)",
        hypothesis="ATM IV month1 minus month3: steep contango = near-term event risk. hump stabilizes signal.",
        hint="m1atmiv-m3atmiv is the ATM calendar spread signal; positive = near-term fear.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    # --- Hump + Straddle Forecast ---
    templates.append(AlphaTemplate(
        name="ern4_hump_straddle_forecast",
        expression="hump(group_rank(ts_backfill(vec_avg(ern4_m1fcaststrapx), 5), subindustry), hump=0.001)",
        hypothesis="Month-1 forecast straddle price: high straddle = market expects large move. hump smooths updates.",
        hint="m1fcaststrapx updates around events; hump prevents position churn.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_hump_option_volume_change",
        expression="hump(group_rank(ts_delta(ts_backfill(vec_avg(ern4_avg20doptvolu), 252), 20), subindustry), hump=0.001)",
        hypothesis="20-day average option volume changes can flag rising pre-earnings attention and event-risk demand.",
        hint="Use vec_avg then backfill for the earnings4 event field; hump limits volume-spike churn.",
        dataset_category="earnings",
        level="custom",
        neutralization="SUBINDUSTRY", decay=0, truncation=0.08,
    ))

    return templates


# ──────────────────────────── MUTATION ENGINE ─────────────────────

# 按数据集类别推荐的 neutralization (来自文档27)
NEUT_RECOMMENDATIONS = {
    "fundamental": ["INDUSTRY", "SUBINDUSTRY"],
    "analyst": ["INDUSTRY"],
    "model": ["MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY"],
    "news": ["SUBINDUSTRY"],
    "option": ["MARKET", "SECTOR"],
    "pv": ["MARKET", "SECTOR"],
    "social_media": ["SUBINDUSTRY", "INDUSTRY"],
    "sentiment": ["INDUSTRY", "SUBINDUSTRY"],
    "earnings": ["INDUSTRY"],
    "institutions": ["SECTOR", "INDUSTRY"],
    "short_interest": ["INDUSTRY"],
    "insider": ["INDUSTRY", "SUBINDUSTRY"],
    "macro": ["SECTOR", "MARKET", "INDUSTRY"],
}


def apply_official_hint(tmpl: AlphaTemplate) -> List[ParamVariant]:
    """
    根据官方 hint 和 neutralization 推荐生成参数变体
    """
    variants = []
    expr = tmpl.expression

    # ── 基础变体: 原始模板 + 不同 decay ──
    for decay in [0, 2, 4, 6, 8, 10]:
        if decay == tmpl.decay:
            desc = "原始"
        else:
            desc = f"decay={decay}"
        variants.append(ParamVariant(
            expression=expr, decay=decay,
            neutralization=tmpl.neutralization,
            truncation=tmpl.truncation,
            universe=tmpl.universe,
            delay=tmpl.delay,
            mutation_desc=desc,
        ))

    flipped_expr = expr[1:] if expr.startswith("-") else f"-({expr})"
    variants.append(ParamVariant(
        expression=flipped_expr,
        decay=tmpl.decay,
        neutralization=tmpl.neutralization,
        truncation=tmpl.truncation,
        universe=tmpl.universe,
        delay=tmpl.delay,
        mutation_desc="polarity_flip",
    ))

    # ── neutralization 变体 (按官方推荐矩阵) ──
    rec_neuts = NEUT_RECOMMENDATIONS.get(tmpl.dataset_category, ["INDUSTRY"])
    for neut in rec_neuts:
        if neut != tmpl.neutralization:
            variants.append(ParamVariant(
                expression=expr,
                decay=tmpl.decay if tmpl.decay > 0 else 2,
                neutralization=neut,
                truncation=tmpl.truncation,
                universe=tmpl.universe,
                delay=tmpl.delay,
                mutation_desc=f"neut={neut}",
            ))

    # ── 表达式变异 (应用官方改进技巧) ──

    # 技巧1: 加 group_rank 压缩 (降 turnover)
    if "group_rank" not in expr and "rank" not in expr.split("(")[0]:
        wrapped = f"group_rank({expr}, subindustry)"
        variants.append(ParamVariant(
            expression=wrapped, decay=4,
            neutralization=tmpl.neutralization,
            truncation=tmpl.truncation,
            universe=tmpl.universe,
            delay=tmpl.delay,
            mutation_desc="group_rank包裹+d4",
        ))

    # 技巧2: ts_decay_linear 平滑 (降 turnover)
    if "ts_decay_linear" not in expr:
        wrapped = f"ts_decay_linear({expr}, 10)"
        variants.append(ParamVariant(
            expression=wrapped, decay=2,
            neutralization=tmpl.neutralization,
            truncation=tmpl.truncation,
            universe=tmpl.universe,
            delay=tmpl.delay,
            mutation_desc="ts_decay_linear(10)+d2",
        ))

    # 技巧3: ts_zscore 标准化
    if "ts_zscore" not in expr and "zscore" not in expr:
        wrapped = f"ts_zscore({expr}, 252)"
        variants.append(ParamVariant(
            expression=wrapped, decay=4,
            neutralization=tmpl.neutralization,
            truncation=tmpl.truncation,
            universe=tmpl.universe,
            delay=tmpl.delay,
            mutation_desc="ts_zscore(252)+d4",
        ))

    # 技巧4: rank 归一化 (通过 weight 测试)
    if "rank(" not in expr:
        wrapped = f"rank({expr})"
        variants.append(ParamVariant(
            expression=wrapped, decay=0,
            neutralization=tmpl.neutralization,
            truncation=0.1,
            universe=tmpl.universe,
            delay=tmpl.delay,
            mutation_desc="rank包裹+trunc0.1",
        ))

    # 技巧5: 不同 universe (sub-universe 测试)
    if tmpl.universe == "TOP3000":
        for univ in ["TOP2000", "TOP1000"]:
            variants.append(ParamVariant(
                expression=expr, decay=max(tmpl.decay, 2),
                neutralization=tmpl.neutralization,
                truncation=tmpl.truncation,
                universe=univ,
                delay=tmpl.delay,
                mutation_desc=f"universe={univ}",
            ))

    # 技巧6: D0 转 D1 / D1 转 D0 (文档28)
    alt_delay = 0 if tmpl.delay == 1 else 1
    variants.append(ParamVariant(
        expression=expr,
        decay=max(tmpl.decay, 2) if alt_delay == 1 else tmpl.decay,
        neutralization=tmpl.neutralization,
        truncation=tmpl.truncation,
        universe=tmpl.universe if alt_delay == 1 else ("TOP1000" if tmpl.universe == "TOP3000" else tmpl.universe),
        delay=alt_delay,
        mutation_desc=f"delay=D{alt_delay}",
    ))

    # 去重 (基于 expression+关键参数)
    seen = set()
    unique = []
    for v in variants:
        key = (v.expression.strip(), v.decay, v.neutralization, v.universe, v.delay)
        if key not in seen:
            seen.add(key)
            unique.append(v)

    return unique


def variant_priority(variant: ParamVariant) -> int:
    desc = variant.mutation_desc
    if desc == "原始":
        return 0
    if "polarity" in desc:
        return 1
    if any(key in desc for key in ("group_rank", "ts_decay", "ts_zscore", "rank包裹")):
        return 2
    if desc.startswith("neut="):
        return 3
    if desc.startswith("universe="):
        return 4
    if desc.startswith("delay="):
        return 5
    if desc.startswith("decay="):
        return 6
    return 7


# ──────────────────────────── POWER POOL FILTER ──────────────────

def is_power_pool_candidate(expr: str) -> bool:
    """检查是否符合 Power Pool 条件 (≤8 运算符, ≤3 数据字段)"""
    import re
    # 粗略计算: 按函数名计数
    operators = set(re.findall(r'([a-z_]+)\s*\(', expr))
    # 排除 grouping fields
    grouping = {'industry', 'subindustry', 'sector', 'market', 'exchange', 'country', 'currency'}
    operators -= grouping

    # 数据字段: 非运算符、非数字、非关键字的标识符
    all_tokens = set(re.findall(r'\b([a-z][a-z0-9_]*)\b', expr))
    keywords = {'rettype', 'std', 'range', 'nth', 'percentage', 'constant'}
    fields = all_tokens - operators - grouping - keywords

    return len(operators) <= 8 and len(fields) <= 3


# ──────────────────────────── API CLIENT ─────────────────────────

class WQClient:
    """WorldQuant API 客户端 (支持 Cookie JWT 认证)"""

    def __init__(self, credential_file: str):
        self.credential_file = Path(credential_file)
        self.sess = requests.Session()
        self.sess.headers['User-Agent'] = 'Mozilla/5.0 (OfficialDocMiner/1.0)'
        self.email = ""

    def authenticate(self) -> bool:
        """认证 (支持 密码 和 Cookie 两种方式)"""
        if not self.credential_file.exists():
            log.error(f"❌ 凭据文件不存在: {self.credential_file}")
            return False

        lines = self.credential_file.read_text().strip().split('\n')
        if len(lines) < 2:
            log.error("❌ 凭据文件格式错误 (需要2行: email + password/COOKIE:token)")
            return False

        self.email = lines[0].strip()
        secret = lines[1].strip()

        if secret.startswith("COOKIE:"):
            # JWT Cookie 认证 (Bearer header causes 403 on /simulations)
            jwt = secret[7:]
            self.sess.cookies.set("t", jwt, domain=".worldquantbrain.com")
            self.sess.auth = None
        else:
            # 密码认证
            from requests.auth import HTTPBasicAuth
            auth = HTTPBasicAuth(self.email, secret)
            resp = self.sess.post(f'{API_BASE}/authentication', auth=auth, timeout=15)
            if resp.status_code != 201:
                log.error(f"❌ 密码认证失败: {resp.status_code} {resp.text[:200]}")
                return False
            self.sess.auth = auth

        # 验证
        resp = self.sess.get(f'{API_BASE}/users/self', timeout=15)
        if resp.status_code != 200:
            log.error(f"❌ 认证验证失败: {resp.status_code}")
            return False

        user = resp.json()
        self.email = user.get('email', self.email)
        level = user.get('geniusLevel', '?')
        log.info(f"✅ 认证成功: {self.email} | Level={level}")
        return True

    def submit_simulation(self, expression: str, variant: ParamVariant) -> Optional[str]:
        """提交模拟, 返回 progress URL"""
        settings = {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": variant.universe,
            "delay": variant.delay,
            "decay": variant.decay,
            "neutralization": variant.neutralization,
            "truncation": variant.truncation,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
            "testPeriod": "P5Y0M0D",
        }
        data = {"type": "REGULAR", "settings": settings, "regular": expression}

        for retry in range(5):
            try:
                r = self.sess.post(f'{API_BASE}/simulations', json=data, timeout=20)
                if r.status_code == 201:
                    return r.headers.get('Location', '')
                elif r.status_code == 429:
                    wait = 10 * (retry + 1) + random.uniform(0, 5)
                    log.warning(f"⏳ 429 限流, 等待 {wait:.0f}s...")
                    time.sleep(wait)
                elif r.status_code == 401:
                    log.warning("🔄 401 认证过期, 重新认证...")
                    if self.authenticate():
                        continue
                    return None
                else:
                    log.error(f"❌ 提交失败: {r.status_code} {r.text[:200]}")
                    return None
            except Exception as e:
                log.error(f"❌ 提交异常: {e}")
                time.sleep(5)

        return None

    def poll_result(self, progress_url: str, max_wait: int = 300) -> Optional[dict]:
        """轮询模拟结果"""
        start = time.time()
        while time.time() - start < max_wait:
            try:
                r = self.sess.get(progress_url, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    if 'alpha' in data:
                        return data
                    elif data.get('status') == 'ERROR':
                        return {'error': data.get('message', str(data.get('error', 'unknown')))}
                    # Still running
                    time.sleep(10)
                elif r.status_code == 401:
                    self.authenticate()
                    time.sleep(5)
                else:
                    time.sleep(10)
            except Exception:
                time.sleep(10)

        return {'error': 'timeout'}

    def try_submit_alpha(self, alpha_id_or_url: str) -> Tuple[bool, str]:
        """尝试正式提交 Alpha (通过 OS 测试)"""
        try:
            submit_url = f"{API_BASE}/alphas/{alpha_id_or_url}/submit"
            r = self.sess.post(submit_url, timeout=15)
            if r.status_code in (200, 201):
                return True, "提交成功 ✅"
            elif r.status_code == 403:
                # 解析失败原因 (通常是 self-correlation)
                try:
                    data = r.json()
                    checks = data.get('is', {}).get('checks', [])
                    failed = [c for c in checks if c.get('result') == 'FAIL']
                    if failed:
                        reasons = []
                        for f in failed:
                            name = f.get('name', '?')
                            val = f.get('value', '?')
                            lim = f.get('limit', '?')
                            reasons.append(f"{name}={val}(limit={lim})")
                        return False, f"403 检查未通过: {', '.join(reasons)}"
                    return False, f"403: {r.text[:200]}"
                except Exception:
                    return False, f"403: {r.text[:200]}"
            else:
                return False, f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            return False, str(e)


# ──────────────────────────── RESULT TRACKER ─────────────────────

class ResultTracker:
    """记录和追踪所有模拟结果"""

    def __init__(self, save_path: Path):
        self.save_path = save_path
        self.results: List[SimResult] = []
        self._load()

    def _load(self):
        if self.save_path.exists():
            try:
                data = json.loads(self.save_path.read_text(encoding='utf-8'))
                self.results = [SimResult(**r) for r in data]
                log.info(f"📂 加载了 {len(self.results)} 条历史结果")
            except Exception:
                self.results = []

    def save(self):
        data = [asdict(r) for r in self.results]
        self.save_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

    def add(self, result: SimResult):
        self.results.append(result)
        self.save()

    def is_submitted(self, expression: str, decay: int, neut: str) -> bool:
        """检查是否已提交过相同配置"""
        for r in self.results:
            if r.expression.strip() == expression.strip() and r.variant_desc:
                if f"d={decay}" in r.variant_desc and neut in r.variant_desc:
                    return True
        return False

    def get_best(self, n: int = 20) -> List[SimResult]:
        """按 fitness 排序返回最佳结果"""
        valid = [r for r in self.results if r.sharpe != 0 and not r.error]
        return sorted(valid, key=lambda x: x.fitness, reverse=True)[:n]

    def print_summary(self):
        """打印汇总"""
        valid = [r for r in self.results if r.sharpe != 0 and not r.error]
        if not valid:
            log.info("📊 暂无有效结果")
            return

        # 统计
        passed = [r for r in valid if r.sharpe >= 1.25 and r.fitness >= 1.0
                  and r.turnover <= 0.15 and r.drawdown <= 0.05]
        d0_passed = [r for r in valid if r.sharpe >= 2.0 and r.fitness >= 1.3]

        log.info(f"\n{'='*100}")
        log.info(f"📊 结果汇总: 总计 {len(self.results)} 次提交, {len(valid)} 次有效")
        log.info(f"   D1 通过标准: {len(passed)} 个 (Sharpe≥1.25, Fitness≥1.0, TO≤15%, DD≤5%)")
        log.info(f"   D0 通过标准: {len(d0_passed)} 个 (Sharpe≥2.0, Fitness≥1.3)")
        log.info(f"{'='*100}")

        # Top 15
        top = self.get_best(15)
        log.info(f"{'Name':<30} {'Sharpe':>7} {'Fitness':>8} {'TO%':>7} {'Ret%':>7} {'DD%':>7} {'Variant':<30}")
        log.info("-" * 100)
        for r in top:
            to_pct = r.turnover * 100
            ret_pct = r.returns * 100
            dd_pct = r.drawdown * 100
            flag = ""
            if r.sharpe >= 2.0 and r.fitness >= 1.3:
                flag = " 🏆D0"
            elif r.sharpe >= 1.25 and r.fitness >= 1.0:
                flag = " ⭐D1"
            pp = " 🎯PP" if is_power_pool_candidate(r.expression) and r.sharpe >= 1.0 else ""
            log.info(f"{r.name:<30} {r.sharpe:>7.3f} {r.fitness:>8.3f} {to_pct:>6.1f}% {ret_pct:>6.2f}% {dd_pct:>6.2f}%{flag}{pp} {r.variant_desc[:30]}")


# ──────────────────────────── MAIN MINER ─────────────────────────

class OfficialDocsMiner:
    """官方文档 Alpha 挖掘器"""

    def __init__(self, credential_file: str, max_concurrent: int = 1):
        self.client = WQClient(credential_file)
        self.tracker = ResultTracker(BASE_DIR / "official_miner_results.json")
        self.max_concurrent = max_concurrent
        self.templates = get_official_templates()
        self.submission_delay = 15  # 秒, 每次提交间隔 (避免429)

    def run(self, rounds: int = 3, templates_per_round: int = 5,
            variants_per_template: int = 3, level_filter: str = None,
            category_filter: str = None,
            template_prefix: str = None):
        """
        主运行循环

        Args:
            rounds: 运行轮数
            templates_per_round: 每轮处理的模板数
            variants_per_template: 每个模板提交的变体数 (从所有变体中选最优)
            level_filter: 可选过滤: beginner/bronze/silver/custom
            category_filter: 可选过滤: fundamental/option/model/...
            template_prefix: 可选过滤: template name prefix, e.g. fnd7_
        """
        log.info(f"""
╔══════════════════════════════════════════════════════════╗
║     🧠 Official Documentation Alpha Miner v1.0          ║
║     基于 28 篇官方文档 | {len(self.templates)} 个模板               ║
╚══════════════════════════════════════════════════════════╝
        """)

        # 认证
        if not self.client.authenticate():
            log.error("❌ 认证失败, 退出")
            return False  # Signal auth failure to caller

        # 筛选模板
        active_templates = self.templates
        if level_filter:
            active_templates = [t for t in active_templates if t.level == level_filter]
            log.info(f"🔍 筛选 level={level_filter}: {len(active_templates)} 个模板")

        if category_filter:
            active_templates = [t for t in active_templates if t.dataset_category == category_filter]
            log.info(f"🔍 筛选 category={category_filter}: {len(active_templates)} 个模板")

        if template_prefix:
            active_templates = [t for t in active_templates if t.name.startswith(template_prefix)]
            log.info(f"🔍 筛选 template_prefix={template_prefix}: {len(active_templates)} 个模板")

        submitted_cache = _load_submitted_datafield_cache()
        if submitted_cache:
            before_cache_filter = len(active_templates)
            active_templates = [
                t for t in active_templates
                if not _template_hits_submitted_cache(t, submitted_cache)
            ]
            skipped = before_cache_filter - len(active_templates)
            if skipped:
                log.info(f"🧊 Submitted datafield cache skipped {skipped} already-submitted templates")

        log.info(f"📋 模板统计:")
        for cat in set(t.dataset_category for t in active_templates):
            count = len([t for t in active_templates if t.dataset_category == cat])
            log.info(f"   {cat}: {count} 个")

        # 按 round 轮转
        total_submitted = 0
        total_passed = 0

        for round_idx in range(rounds):
            log.info(f"\n{'='*60}")
            log.info(f"🔄 Round {round_idx+1}/{rounds}")
            log.info(f"{'='*60}")

            # 随机选模板 (避免每轮都重复)
            random.shuffle(active_templates)
            batch = active_templates[:templates_per_round]

            for tmpl in batch:
                log.info(f"\n📌 模板: {tmpl.name} [{tmpl.level}]")
                log.info(f"   假设: {tmpl.hypothesis}")
                log.info(f"   表达式: {tmpl.expression[:80]}...")

                # 生成变体
                all_variants = apply_official_hint(tmpl)
                log.info(f"   生成 {len(all_variants)} 个变体")

                # 选择 top N 变体 (优先未测试的)
                untested = []
                for v in all_variants:
                    key = f"d={v.decay},n={v.neutralization},u={v.universe}"
                    already = any(
                        r.name == tmpl.name and key in r.variant_desc and not r.error
                        for r in self.tracker.results
                    )
                    if not already:
                        untested.append(v)

                if not untested:
                    log.info(f"   ⏭️ 所有变体已测试过, 跳过")
                    continue

                random.shuffle(untested)
                untested.sort(key=variant_priority)
                selected = untested[:variants_per_template]
                log.info(f"   选择 {len(selected)} 个未测试变体")

                # Keep inst4 conservative: account-level concurrency can be lower than API docs.
                BATCH_SIZE = max(1, self.max_concurrent)
                for batch_start in range(0, len(selected), BATCH_SIZE):
                    batch_variants = selected[batch_start:batch_start + BATCH_SIZE]
                    log.info(f"\n   📦 批次 {batch_start//BATCH_SIZE + 1}: 提交 {len(batch_variants)} 个并发模拟")

                    # Step 1: 一次性提交本批次全部 (最多3个)
                    pending = []  # [(variant, progress_url)]
                    for variant in batch_variants:
                        log.info(f"     ➡️ {variant.mutation_desc} | D{variant.delay} decay={variant.decay} neut={variant.neutralization} univ={variant.universe}")
                        progress_url = self.client.submit_simulation(variant.expression, variant)
                        if progress_url:
                            pending.append((variant, progress_url))
                            total_submitted += 1
                        else:
                            log.warning(f"     ❌ 提交失败")
                            self.tracker.add(SimResult(
                                name=tmpl.name,
                                expression=variant.expression,
                                variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},{variant.mutation_desc}",
                                error="submit_failed",
                            ))
                        # Stagger submissions; simulations still overlap when max_concurrent > 1.
                        time.sleep(self.submission_delay)

                    if not pending:
                        continue

                    # Step 2: 并行轮询等待全部完成
                    log.info(f"     ⏳ 等待 {len(pending)} 个模拟完成...")
                    results_map = {}  # {progress_url: result_data}
                    poll_start = time.time()
                    max_poll = 300  # 5分钟超时

                    while len(results_map) < len(pending) and time.time() - poll_start < max_poll:
                        for variant, url in pending:
                            if url in results_map:
                                continue
                            try:
                                r = self.client.sess.get(url, timeout=15)
                                if r.status_code == 200:
                                    data = r.json()
                                    if 'alpha' in data:
                                        results_map[url] = data
                                        log.info(f"     ✅ {variant.mutation_desc} 完成")
                                    elif data.get('status') == 'ERROR':
                                        results_map[url] = {'error': data.get('message', str(data.get('error', 'unknown')))}
                                        log.warning(f"     ❌ {variant.mutation_desc} 错误: {data.get('message', '')[:80]}")
                                elif r.status_code == 401:
                                    self.client.authenticate()
                            except Exception:
                                pass
                        if len(results_map) < len(pending):
                            time.sleep(10)

                    # Step 3: 处理全部结果
                    for variant, url in pending:
                        result_data = results_map.get(url)
                        if not result_data or 'error' in result_data:
                            err = result_data.get('error', 'timeout') if result_data else 'timeout'
                            self.tracker.add(SimResult(
                                name=tmpl.name,
                                expression=variant.expression,
                                variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},{variant.mutation_desc}",
                                error=str(err)[:200],
                            ))
                        else:
                            try:
                                # WQ API 流程: progress URL 只返回 alpha ID
                                # 必须再请求 GET /alphas/{id} 才能拿到指标
                                alpha_id_raw = result_data.get('alpha', '')
                                if isinstance(alpha_id_raw, (list, tuple)):
                                    alpha_id = str(alpha_id_raw[0]) if alpha_id_raw else ''
                                else:
                                    alpha_id = str(alpha_id_raw) if alpha_id_raw else ''

                                if not alpha_id:
                                    log.warning(f"     ⚠️ {variant.mutation_desc}: 没有 alpha ID")
                                    self.tracker.add(SimResult(
                                        name=tmpl.name, expression=variant.expression,
                                        variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},{variant.mutation_desc}",
                                        error="no_alpha_id",
                                    ))
                                    continue

                                # 关键: 第二次请求获取 IS 指标
                                alpha_resp = self.client.sess.get(
                                    f'{API_BASE}/alphas/{alpha_id}', timeout=15
                                )
                                if alpha_resp.status_code != 200:
                                    log.warning(f"     ⚠️ 获取 alpha 详情失败: {alpha_resp.status_code}")
                                    self.tracker.add(SimResult(
                                        name=tmpl.name, expression=variant.expression,
                                        variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},{variant.mutation_desc}",
                                        error=f"alpha_fetch_{alpha_resp.status_code}",
                                        alpha_id=alpha_id,
                                    ))
                                    continue

                                alpha_data = alpha_resp.json()
                                is_data = alpha_data.get('is', {})

                                sharpe = float(is_data.get('sharpe') or 0)
                                fitness = float(is_data.get('fitness') or 0)
                                turnover = float(is_data.get('turnover') or 0)
                                returns_v = float(is_data.get('returns') or 0)
                                drawdown = float(is_data.get('drawdown') or 0)
                                margin = float(is_data.get('margin') or 0)
                                long_count = int(is_data.get('longCount') or 0)
                                short_count = int(is_data.get('shortCount') or 0)


                                # 判断是否通过 (用户标准: Sharpe>1.25, Fitness>1, TO<15%, DD<5%)
                                is_d0 = variant.delay == 0
                                sharpe_pass = sharpe >= (2.0 if is_d0 else 1.25)
                                fitness_pass = fitness >= (1.3 if is_d0 else 1.0)
                                to_pass = turnover <= 0.15  # 15% turnover 上限
                                dd_pass = drawdown <= 0.05  # 5% drawdown 上限
                                passed = sharpe_pass and fitness_pass and to_pass and dd_pass

                                if passed:
                                    total_passed += 1

                                # 标记
                                to_pct = turnover * 100
                                status = "🏆 PASS" if passed else "📊"
                                pp_flag = " [PowerPool候选]" if is_power_pool_candidate(variant.expression) and sharpe >= 1.0 and variant.delay == 1 else ""

                                log.info(f"     {status} {variant.mutation_desc}: S={sharpe:.3f} F={fitness:.3f} TO={to_pct:.1f}% R={returns_v:.4f}{pp_flag}")

                                sr = SimResult(
                                    name=tmpl.name,
                                    expression=variant.expression,
                                    variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},D{variant.delay},{variant.mutation_desc}",
                                    sharpe=sharpe, fitness=fitness, turnover=turnover,
                                    returns=returns_v, drawdown=drawdown, margin=margin,
                                    long_count=long_count, short_count=short_count,
                                    passed_checks=passed, alpha_id=alpha_id,
                                )
                                self.tracker.add(sr)

                                # 不自动提交，只记录好因子 (用户手动提交)
                                if passed and alpha_id:
                                    log.info(f"     🌟 好因子! Alpha={alpha_id} S={sharpe:.3f} F={fitness:.3f} TO={to_pct:.1f}% DD={drawdown*100:.1f}%")
                                    log.info(f"     🌟 表达式: {variant.expression[:120]}")

                            except Exception as e:
                                log.error(f"     ❌ 解析结果异常: {e} | raw={str(result_data)[:200]}")
                                self.tracker.add(SimResult(
                                    name=tmpl.name,
                                    expression=variant.expression,
                                    variant_desc=f"d={variant.decay},n={variant.neutralization},u={variant.universe},{variant.mutation_desc}",
                                    error=f"parse_error: {e}",
                                ))

                    # 批次间隔 (等前一批完全释放)
                    time.sleep(5)

            # Round 汇总
            log.info(f"\n📊 Round {round_idx+1} 完成: 本轮提交 {total_submitted} 个, 累计通过 {total_passed} 个")
            self.tracker.print_summary()

        # 最终汇总
        log.info(f"\n{'='*60}")
        log.info(f"🏁 全部 {rounds} 轮完成!")
        log.info(f"   总提交: {total_submitted} | 总通过: {total_passed}")
        log.info(f"{'='*60}")
        self.tracker.print_summary()
        return True


# ──────────────────────────── CLI ─────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Official Documentation Alpha Miner — 基于28篇WQ官方文档的Alpha挖掘器"
    )
    parser.add_argument(
        '--credential', '-c',
        default=str(BASE_DIR / 'credential_4.txt'),
        help='凭据文件路径 (default: credential_4.txt)'
    )
    parser.add_argument(
        '--rounds', '-r', type=int, default=5,
        help='运行轮数 (default: 5)'
    )
    parser.add_argument(
        '--templates-per-round', '-t', type=int, default=5,
        help='每轮处理模板数 (default: 5)'
    )
    parser.add_argument(
        '--variants', '-v', type=int, default=3,
        help='每模板提交变体数 (default: 3)'
    )
    parser.add_argument(
        '--max-concurrent', type=int, default=1,
        help='每批并发模拟数 (default: 1)'
    )
    parser.add_argument(
        '--level', '-l', choices=['beginner', 'bronze', 'silver', 'custom'],
        help='只运行特定级别的模板'
    )
    parser.add_argument(
        '--category',
        choices=['fundamental', 'option', 'model', 'sentiment', 'earnings', 'news', 'pv',
                 'analyst', 'institutions', 'short_interest', 'insider', 'macro',
                 'social_media'],
        help='只运行特定数据集类别的模板，例如 fundamental'
    )
    parser.add_argument(
        '--template-prefix',
        help='只运行名称以该前缀开头的模板，例如 fnd7_'
    )
    parser.add_argument(
        '--delay-between', '-d', type=int, default=15,
        help='提交间隔秒数 (default: 15, 避免429)'
    )
    parser.add_argument(
        '--summary-only', '-s', action='store_true',
        help='只显示结果汇总, 不提交'
    )
    parser.add_argument(
        '--infinite', action='store_true',
        help='无限循环模式 (cookie过期前持续运行)'
    )

    args = parser.parse_args()

    miner = OfficialDocsMiner(
        credential_file=args.credential,
        max_concurrent=args.max_concurrent,
    )
    miner.submission_delay = args.delay_between

    if args.summary_only:
        miner.tracker.print_summary()
        return

    if args.infinite:
        # 无限循环模式: 每轮结束后继续下一轮
        mega_round = 0
        auth_fail_count = 0
        while True:
            mega_round += 1
            log.info(f"\n{'🔥'*30}")
            log.info(f"🔥 INFINITE MODE — Mega Round {mega_round}")
            log.info(f"{'🔥'*30}")
            try:
                result = miner.run(
                    rounds=args.rounds,
                    templates_per_round=args.templates_per_round,
                    variants_per_template=args.variants,
                    level_filter=args.level,
                    category_filter=args.category,
                    template_prefix=args.template_prefix,
                )
                if result is False:
                    # 认证失败 — 指数退避等待
                    auth_fail_count += 1
                    wait = min(300, 30 * auth_fail_count)  # 30s, 60s, ... max 5min
                    log.warning(f"⏳ Cookie可能过期, 等待 {wait}s 后重试 (第{auth_fail_count}次)")
                    time.sleep(wait)
                else:
                    auth_fail_count = 0  # 重置
                    time.sleep(10)  # Mega Round间隔
            except KeyboardInterrupt:
                log.info("\n⏹️ 用户中断")
                break
            except Exception as e:
                log.error(f"❌ Mega Round {mega_round} 异常: {e}")
                time.sleep(30)
    else:
        miner.run(
            rounds=args.rounds,
            templates_per_round=args.templates_per_round,
            variants_per_template=args.variants,
            level_filter=args.level,
            category_filter=args.category,
            template_prefix=args.template_prefix,
        )


if __name__ == '__main__':
    main()
