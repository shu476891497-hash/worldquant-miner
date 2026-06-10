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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"official_miner_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("official_miner")


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
        expression="ts_regression(ts_sum(ts_backfill(fnd6_newqv1300_ivltq, 60), 252), ts_step(1), 756, 0, 2)",
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
        expression="ts_backfill(ern4_fcsterneffct, 5) - ts_backfill(ern4_erneffct1, 5)",
        hypothesis="预测效应 - 实现效应 = 市场预期偏差",
        hint="预测家族是低turnover高margin的宝地",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_implied_move",
        expression="ts_backfill(ern4_impernmv90d, 5)",
        hypothesis="市场隐含的下次盈利移动百分比",
        hint="信号在forecast vs implied的差距中",
        dataset_category="earnings",
        level="silver",
        neutralization="INDUSTRY", decay=0, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="ern4_ernmv1_drift",
        expression="ts_backfill(ern4_ernmv1, 60)",
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
        expression="group_rank(ts_ir(operating_income / (assets + 0.000001), 120), subindustry)",
        hypothesis="经营收入/资产的信息比率高 → 稳定改善 → 买入",
        hint="ts_ir = mean/std = 信号稳定性指标",
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
        expression="group_rank(ts_regression(equity / (assets + 0.000001), ts_step(1), 252, 0, 2), subindustry)",
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
        expression="group_rank(ts_regression(sales_ps, ts_step(1), 252, 0, 2), subindustry)",
        hypothesis="每股销售长期趋势斜率为正 → 收入稳步增长 → 买入",
        hint="ts_regression rettype=2返回斜率, ts_step(1)是时间序列",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_ebitda_trend_slope",
        expression="group_rank(ts_regression(ebitda, ts_step(1), 252, 0, 2), subindustry)",
        hypothesis="EBITDA趋势斜率为正 → 盈利能力持续提升 → 买入",
        hint="长窗口(252天)捕捉年度趋势",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    templates.append(AlphaTemplate(
        name="fn_eps_trend_slope",
        expression="group_rank(ts_regression(eps, ts_step(1), 120, 0, 2), subindustry)",
        hypothesis="EPS半年趋势为正 → 盈利改善 → 买入",
        hint="120天窗口更敏感, 适合捕捉季报变化",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # rettype=0: residual (偏离趋势的异常值)
    templates.append(AlphaTemplate(
        name="fn_sales_resid_reversal",
        expression="-1 * group_rank(ts_regression(sales_ps, ts_step(1), 252, 0, 0), subindustry)",
        hypothesis="残差为正=高于趋势→均值回归做空; 残差为负→反弹做多",
        hint="rettype=0返回残差, 捕捉偏离长期趋势的异常",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # rettype=1: R² (拟合度 → 趋势可靠性)
    templates.append(AlphaTemplate(
        name="fn_operating_income_r2",
        expression="group_rank(ts_regression(operating_income, ts_step(1), 252, 0, 1), subindustry)",
        hypothesis="经营收入趋势R²高→走势可预测→市场定价准确→动量有效",
        hint="rettype=1返回R², 高R²意味着线性趋势强",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
    ))

    # 双因子回归: 用一个因子解释另一个
    templates.append(AlphaTemplate(
        name="fn_eps_vs_sales_beta",
        expression="group_rank(ts_regression(eps, sales_ps, 252, 0, 2), subindustry)",
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
            "resid = ts_regression(equity, ts_step(1), 252, 0, 0);\n"
            "slope = ts_regression(equity, ts_step(1), 252, 0, 2);\n"
            "trade_when(slope > 0, -group_rank(resid, subindustry), nan)"
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
        expression="group_rank(ts_regression(fnd7_ointfund_qxspeo, fnd7_ointhstfund_hqxspeo, 252, 0, 2), subindustry)",
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
        expression="group_rank(ts_regression(fnd7_ointfund_qbi, ts_step(1), 252, 0, 2), subindustry)",
        hypothesis="税前经常性收入趋势上升→核心盈利改善→买入",
        hint="qbi = income before extraordinary items, 排除非经常性",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=10, truncation=0.08,
    ))

    # --- Cash Flow ---
    templates.append(AlphaTemplate(
        name="fnd7_operating_cashflow_trend",
        expression="group_rank(ts_regression(fnd7_ointfund_qfcnif, ts_step(1), 252, 0, 2), subindustry)",
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
        expression="group_rank(ts_regression(fnd7_ointfund_qer, ts_step(1), 252, 0, 2), subindustry)",
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
        expression="group_rank(ts_regression(fnd7_ointfund_21speo, ts_step(1), 252, 0, 2), subindustry)",
        hypothesis="12个月移动EPS趋势上升→持续盈利改善→买入",
        hint="21speo = EPS from operations, trailing 12 months",
        dataset_category="fundamental",
        level="custom",
        neutralization="SUBINDUSTRY", decay=5, truncation=0.08,
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
            # JWT Bearer 认证
            jwt = secret[7:]
            self.sess.headers['Authorization'] = f'Bearer {jwt}'
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
            variants_per_template: int = 3, level_filter: str = None):
        """
        主运行循环

        Args:
            rounds: 运行轮数
            templates_per_round: 每轮处理的模板数
            variants_per_template: 每个模板提交的变体数 (从所有变体中选最优)
            level_filter: 可选过滤: beginner/bronze/silver/custom
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
                        r.name == tmpl.name and key in r.variant_desc
                        for r in self.tracker.results
                    )
                    if not already:
                        untested.append(v)

                if not untested:
                    log.info(f"   ⏭️ 所有变体已测试过, 跳过")
                    continue

                selected = untested[:variants_per_template]
                log.info(f"   选择 {len(selected)} 个未测试变体")

                # ── 批量提交: 每次最多 3 个并发 ──
                BATCH_SIZE = 3  # API 并发上限
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
                        # 短间隔避免瞬间并发触发 429
                        time.sleep(2)

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
        '--level', '-l', choices=['beginner', 'bronze', 'silver', 'custom'],
        help='只运行特定级别的模板'
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
        max_concurrent=1,
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
        )


if __name__ == '__main__':
    main()
