"""
骨架工厂（Skeleton Factory）
用金融语义模块系统性组合，生成 2000+ 个结构唯一且有意义的 alpha 骨架。

核心理念：每个骨架 = 一个 alpha 假说
- 信号提取层(what): 动量、均值回归、波动率、信噪比…
- 截面处理层(how): group_rank / group_neutralize / zscore
- 组合层(structure): 价差、比率、加权混合
- 门控层(when): trade_when 择时条件

所有骨架使用 {F}/{F1}/{F2}/{W} 占位符，与现有模板系统完全兼容。
"""
import itertools
import logging

# ════════════════════════════════════════════════════════════
# 1. 信号提取器（每个都有明确的金融含义）
# ════════════════════════════════════════════════════════════

# 单字段信号 — 从一个数据字段提取特征
_SINGLE_SIGNALS = [
    # 标识符            表达式                                              金融含义
    ("raw",             "{F}"),                                             # 原始值
    ("momentum",        "ts_delta({F}, {W})"),                              # 动量/变化量
    ("pct_rank",        "ts_rank({F}, {W})"),                               # 时序百分位
    ("deviation",       "ts_zscore({F}, {W})"),                             # 标准化偏离
    ("smoothed",        "ts_mean({F}, {W})"),                               # 平滑均值
    ("risk_adj",        "ts_ir({F}, {W})"),                                 # 信息比率（风险调整）
    ("volatility",      "ts_std_dev({F}, {W})"),                            # 波动率
    ("recency",         "ts_decay_linear({F}, {W})"),                       # 近期加权衰减
    ("asymmetry",       "ts_skewness({F}, {W})"),                           # 分布偏度
    ("filled",          "ts_backfill({F}, {W})"),                           # 缺失值填充
    ("cumulative",      "ts_sum({F}, {W})"),                                # 累积量
    ("mean_diff",       "ts_av_diff({F}, {W})"),                            # 均值偏差
    ("tail_risk",       "ts_kurtosis({F}, {W})"),                           # 尾部风险/峰度
    ("disorder",        "ts_entropy({F}, {W})"),                            # 信息熵/无序度
    ("concentration",   "ts_herfindahl({F}, {W})"),                         # 集中度
    ("higher_moment",   "ts_moment({F}, {W}, 3)"),                          # 三阶矩
    ("peak_timing",     "ts_arg_max({F}, {W})"),                            # 峰值出现时机
    ("trough_timing",   "ts_arg_min({F}, {W})"),                            # 谷值出现时机
    ("compound",        "ts_product({F}, {W})"),                            # 复合增长
    ("data_quality",    "ts_count_nans({F}, {W})"),                         # 数据质量
    ("staleness",       "days_from_last_change({F})"),                      # 数据新鲜度
    ("last_change",     "last_diff_value({F}, {W})"),                       # 最近变化值
    ("ranked",          "rank({F})"),                                       # 截面排名
    ("quantile_low",    "ts_quantile({F}, 0.25, {W})"),                     # 下四分位
    ("quantile_high",   "ts_quantile({F}, 0.75, {W})"),                     # 上四分位
    # ═══ 冷门算子补充 ═══
    ("ts_max",          "ts_max({F}, {W})"),                                # 区间最大值
    ("ts_min",          "ts_min({F}, {W})"),                                # 区间最小值
    ("lagged",          "ts_delay({F}, {W})"),                              # 滞后值
    ("returns",         "ts_returns({F}, {W}, 1)"),                         # 收益率
    ("pct_position",    "ts_percentage({F}, {W})"),                         # 百分比位置
    ("scaled_ts",       "ts_scale({F}, {W})"),                              # 时序缩放
    ("kth_val",         "kth_element({F}, 3, {W})"),                        # 第k大值
    ("hump_decay",      "hump({F}, 0.3)"),                                  # 驼峰函数
    ("bucketed",        "bucket({F}, 5)"),                                  # 分桶离散化
    ("densified",       "densify({F})"),                                    # 密集化(填NaN)
    ("pasteurized",     "pasteurize({F})"),                                 # 巴氏消毒(去异常)
    ("purified",        "purify({F})"),                                     # 纯化(去噪声)
    ("vol_hedged",      "hedge_volatility({F})"),                           # 波动率对冲
    ("left_tail_r",     "left_tail({F}, 0.1)"),                             # 左尾(下行风险)
    ("right_tail_r",    "right_tail({F}, 0.9)"),                            # 右尾(上行潜力)
    ("fractional",      "fraction({F})"),                                   # 取小数部分
    ("inverted",        "inverse({F})"),                                    # 倒数
    ("log_transform",   "log(abs({F}) + 1e-6)"),                            # 对数变换
    ("sqrt_transform",  "sqrt(abs({F}))"),                                  # 平方根变换
    ("sign_of",         "sign({F})"),                                       # 符号函数
    ("decay_exp",       "ts_decay_exp({F}, {W})"),                          # 指数衰减(简版)
]

# 复合单字段信号 — 二层嵌套，每个都有独立金融含义
_COMPOUND_SIGNALS = [
    ("t_stat",          "ts_delta({F}, {W}) / (ts_std_dev({F}, {W}) + 1e-6)"),     # t统计量/信噪比
    ("mom_rank",        "ts_rank(ts_delta({F}, {W}), {W})"),                        # 动量排名
    ("mom_zscore",      "ts_zscore(ts_delta({F}, {W}), {W})"),                      # 标准化动量
    ("fading",          "ts_decay_linear(ts_zscore({F}, {W}), {W})"),               # 衰减中的信号
    ("acceleration",    "ts_mean(ts_delta({F}, {W}), {W})"),                        # 加速度
    ("mom_vol",         "ts_std_dev(ts_delta({F}, {W}), {W})"),                     # 动量波动
    ("vol_regime",      "ts_rank(ts_std_dev({F}, {W}), {W})"),                      # 波动率区间
    ("clipped",         "winsorize(ts_zscore({F}, {W}), std=3)"),                   # 截尾信号
    ("filled_mom",      "ts_backfill(ts_delta({F}, {W}), 5)"),                      # 填充后动量
    ("mom_quality",     "ts_ir(ts_delta({F}, {W}), {W})"),                          # 动量质量
    ("reversal",        "-ts_rank({F}, {W})"),                                      # 反转信号
    ("2nd_deriv",       "ts_delta(ts_delta({F}, 5), 5)"),                           # 二阶导/加速度
    ("time_from_peak",  "({W} - ts_arg_max({F}, {W})) / {W}"),                     # 距峰值相对时间
    ("iqr",             "ts_quantile({F}, 0.75, {W}) - ts_quantile({F}, 0.25, {W})"), # 四分位距
    ("cv",              "ts_std_dev({F}, {W}) / (ts_mean(abs({F}), {W}) + 1e-6)"), # 变异系数
    ("decay_ir",        "ts_decay_exp_window(ts_ir({F}, {W}), {W}, 2)"),           # 衰减信息比率
    ("trend_strength",  "ts_theilsen({F}, ts_step(1), {W})"),                      # 趋势强度(稳健)
    ("jump_signal",     "jump_decay({F}, {W}, 0.5, 252)"),                         # 跳跃衰减信号
    ("sqrt_zscore",     "signed_power(ts_zscore({F}, {W}), 0.5)"),                 # 压缩极值的z分数
    ("neg_skew_adj",    "ts_skewness({F}, {W}) * ts_ir({F}, {W})"),                # 偏度调整收益
    # ═══ 冷门复合信号补充 ═══
    ("purified_mom",    "ts_delta(pasteurize({F}), {W})"),                         # 纯化后动量
    ("dense_zscore",    "ts_zscore(densify({F}), {W})"),                           # 密集化z分数
    ("hedged_rank",     "ts_rank(hedge_volatility({F}), {W})"),                   # 对冲后排名
    ("max_min_ratio",   "ts_max({F}, {W}) / (ts_min({F}, {W}) + 1e-6)"),          # 极值比率
    ("range_pct",       "({F} - ts_min({F}, {W})) / (ts_max({F}, {W}) - ts_min({F}, {W}) + 1e-6)"), # 区间位置
    ("delayed_diff",    "ts_delta({F}, {W}) - ts_delta(ts_delay({F}, {W}), {W})"), # 延迟差分
    ("tail_asym",       "right_tail({F}, 0.9) - left_tail({F}, 0.1)"),             # 尾部不对称
    ("bucket_rank",     "ts_rank(bucket({F}, 5), {W})"),                          # 分桶后排名
    ("log_momentum",    "ts_delta(log(abs({F}) + 1e-6), {W})"),                   # 对数动量
    ("inv_vol",         "inverse(ts_std_dev({F}, {W}) + 1e-6)"),                  # 波动率倒数(低波优先)
    ("sign_momentum",   "sign(ts_delta({F}, {W})) * ts_ir({F}, {W})"),            # direction x quality
    ("kth_spread",      "kth_element({F}, 1, {W}) - kth_element({F}, 5, {W})"),   # extreme spread
]

# Three-layer nested compound signals (deeper alpha hypotheses)
_TRIPLE_SIGNALS = [
    ("regime_switch",   "ts_rank(ts_zscore(ts_delta({F}, {W}), {W}), {W})"),       # regime-adjusted momentum
    ("vol_adjusted_mom","ts_delta({F}, {W}) / (ts_std_dev({F}, {W}) + 1e-6) * sign(ts_delta({F}, 5))"), # vol-adj signed momentum
    ("fading_reversal", "ts_decay_linear(-ts_zscore(ts_delta({F}, {W}), {W}), {W})"), # mean-reversion with recency
    ("momentum_of_ir",  "ts_delta(ts_ir({F}, {W}), {W})"),                          # acceleration of risk-adj return
    ("volatility_breakout", "ts_rank(ts_std_dev({F}, {W}), {W}) * sign(ts_delta({F}, 5))"), # vol breakout direction
    ("ranked_entropy",  "ts_rank(ts_entropy({F}, {W}), {W})"),                      # info disorder regime
    ("persistent_shock","ts_mean(ts_delta({F}, 5), {W}) / (ts_std_dev(ts_delta({F}, 5), {W}) + 1e-6)"), # sustained shock
    ("cross_sectional_ir", "rank(ts_ir({F}, {W})) * rank(ts_delta({F}, 5))"),       # cross-sect quality x direction
    ("decay_of_surprise","ts_decay_exp({F} - ts_mean({F}, {W}), {W})"),             # surprise with exponential decay
    ("anchoring_bias",  "({F} - ts_quantile({F}, 0.5, {W})) / (ts_std_dev({F}, {W}) + 1e-6)"), # distance from median
    ("jump_detection",  "ts_delta({F}, 1) / (ts_std_dev({F}, {W}) + 1e-6)"),        # standardized daily change
    ("range_breakout",  "({F} - ts_min({F}, {W})) / (ts_max({F}, {W}) - ts_min({F}, {W}) + 1e-6) - 0.5"), # centered range position
    ("herfindahl_change","ts_delta(ts_herfindahl({F}, {W}), 5)"),                   # concentration shift
    ("kurtosis_regime", "ts_rank(ts_kurtosis({F}, {W}), {W})"),                     # tail risk regime rank
]

# 双字段信号 — 捕捉两个字段之间的关系
_DUAL_SIGNALS = [
    ("ratio",           "{F1} / ({F2} + 1e-6)"),                                    # 比率
    ("spread",          "{F1} - {F2}"),                                             # 价差
    ("correlation",     "ts_corr({F1}, {F2}, {W})"),                                # 相关性
    ("robust_beta",     "ts_theilsen({F1}, {F2}, {W})"),                            # 稳健回归斜率
    ("interaction",     "rank({F1}) * rank({F2})"),                                 # 交互效应
    ("rank_spread",     "rank({F1}) - rank({F2})"),                                 # 排名差
    ("mom_spread",      "ts_delta({F1}, {W}) - ts_delta({F2}, {W})"),               # 动量差
    ("zscore_spread",   "ts_zscore({F1}, {W}) - ts_zscore({F2}, {W})"),             # Z分数差
    ("nonlinear_sprd",  "signed_power(rank({F1}) - rank({F2}), 3)"),                # 非线性排名差
    ("residual",        "ts_regression({F1}, {F2}, {W}, 0, 2)"),                    # 回归残差
    ("cov_ratio",       "ts_covariance({F1}, {F2}, {W}) / (ts_std_dev({F1}, {W}) + 1e-6)"), # 协方差比
    ("ir_spread",       "ts_ir({F1}, {W}) - ts_ir({F2}, {W})"),                    # 信息比率差
    ("moment_diff",     "ts_moment({F1}, {W}, 3) - ts_moment({F2}, {W}, 3)"),      # 高阶矩差
    ("ratio_momentum",  "ts_delta({F1} / ({F2} + 1e-6), {W})"),                    # 比率动量
    ("rel_strength",    "ts_rank({F1}, {W}) - ts_rank({F2}, {W})"),                # 相对强度
    # ═══ 冷门双字段补充 ═══
    ("log_ratio",       "log(divide({F1}, {F2}))"),                                 # 对数比率
    ("peak_diff",       "ts_arg_max({F1}, {W}) - ts_arg_max({F2}, {W})"),           # 峰值时差
    ("vol_ratio",       "ts_std_dev({F1}, {W}) / (ts_std_dev({F2}, {W}) + 1e-6)"), # 波动率比
    ("purified_spread", "pasteurize({F1}) - pasteurize({F2})"),                     # 纯化价差
    ("skew_diff",       "ts_skewness({F1}, {W}) - ts_skewness({F2}, {W})"),        # 偏度差
    ("tail_corr",       "ts_corr(left_tail({F1}, 0.2), left_tail({F2}, 0.2), {W})"), # 尾部相关性
]

# ════════════════════════════════════════════════════════════
# 2. 截面处理器（外层包裹）
# ════════════════════════════════════════════════════════════
_WRAPPERS = [
    ("grk_sub",  "group_rank({S}, subindustry)"),
    ("grk_sec",  "group_rank({S}, sector)"),
    ("grk_ind",  "group_rank({S}, industry)"),
    ("gn_sub",   "group_neutralize({S}, subindustry)"),
    ("gn_sec",   "group_neutralize({S}, sector)"),
    ("gn_ind",   "group_neutralize({S}, industry)"),
    ("gz_sub",   "group_zscore({S}, subindustry)"),
    ("raw_rank", "rank({S})"),
    # ═══ 冷门截面算子 ═══
    ("gnorm_sub","group_normalize({S}, subindustry)"),
    ("gscale",   "group_scale({S}, subindustry)"),
    ("gpct_sub", "group_percentage({S}, subindustry)"),
    ("gq_sub",   "group_quantile({S}, 0.1, subindustry)"),
]

# ════════════════════════════════════════════════════════════
# 3. 组合模式（两个信号如何交互）
# ════════════════════════════════════════════════════════════
_COMBINERS = [
    ("sum",      "rank({A}) + rank({B})"),                    # equal weight
    ("diff",     "rank({A}) - rank({B})"),                    # long-short spread
    ("product",  "rank({A}) * rank({B})"),                    # interaction
    ("weighted", "0.6 * rank({A}) + 0.4 * rank({B})"),        # weighted blend
    # Anti-pattern combiners (structurally unique for low self-correlation)
    ("conditional_blend", "trade_when(rank({A}) > 0.5, {B}, -1 * {B})"),  # A gates B direction
    ("residual_alpha",    "ts_regression({A}, {B}, 20, 0, 2)"),            # alpha after removing B's effect
    ("regime_switch",     "trade_when(ts_rank({A}, 60) > 0.7, {B}, -1 * {A})"),  # regime-based switching
    ("ratio_rank",        "rank({A} / ({B} + 1e-6))"),                      # cross-sectional ratio
    ("divergence",        "ts_delta(rank({A}), 10) - ts_delta(rank({B}), 10)"),  # ranking divergence
]

# ════════════════════════════════════════════════════════════
# 4. 条件门控（择时 + 信号）
# ════════════════════════════════════════════════════════════
_CONDITIONS = [
    ("high_rank",    "trade_when(ts_rank({C}, {W}) > 0.8, {S}, 0)"),          # high quantile only
    ("low_rank",     "trade_when(ts_rank({C}, {W}) < 0.2, {S}, 0)"),          # low quantile only
    ("extreme_z",    "trade_when(abs(ts_zscore({C}, {W})) > 1.5, {S}, 0)"),   # extreme deviation only
    ("trend_up",     "trade_when(ts_delta({C}, {W}) > 0, {S}, -1)"),          # trend-up only
    # New conditions for diverse gating
    ("vol_regime",   "trade_when(ts_rank(ts_std_dev({C}, {W}), {W}) > 0.6, {S}, 0)"),  # high-vol regime
    ("mean_revert",  "trade_when(ts_zscore({C}, {W}) < -1, {S}, 0)"),         # oversold condition
    ("quality_gate", "trade_when(rank({C}) > 0.6, {S}, -1)"),                 # quality threshold
]

# ════════════════════════════════════════════════════════════
# 5. 后处理修饰符（数据清洗 / 衰减）
# ════════════════════════════════════════════════════════════
_POST_PROCESSORS = [
    ("none",     "{X}"),                                       # 不处理
    ("decay_l",  "ts_decay_linear({X}, {W})"),                 # 线性衰减
    ("decay_e",  "ts_decay_exp_window({X}, {W}, 2)"),          # 指数衰减
]


def build_skeleton_pool() -> list:
    """生成有金融意义的骨架模板池。
    
    组合规则（非随机，每个都有 alpha 假说）:
    - 层级1: 单信号 × 包裹器 = 基础骨架
    - 层级2: 双字段信号 × 包裹器 = 关系骨架
    - 层级3: 复合信号 × 包裹器 = 深层骨架  
    - 层级4: 信号组合(A±B) × 包裹器 = 多因子骨架
    - 层级5: 条件门控 × 信号 = 择时骨架
    - 层级6: 后处理衰减 = 加工骨架
    
    返回: list[str] 骨架模板列表，使用 {F}/{F1}/{F2}/{W} 占位符
    """
    skeletons = set()
    
    # ── 层级1: 单字段信号 × 包裹器 ──
    for _, sig in _SINGLE_SIGNALS:
        for _, wrap in _WRAPPERS:
            skeletons.add(wrap.replace("{S}", sig))
    
    # ── 层级2: 复合单字段信号 × 包裹器 ──
    for _, sig in _COMPOUND_SIGNALS:
        for _, wrap in _WRAPPERS:
            skeletons.add(wrap.replace("{S}", sig))
    
    # ── 层级2.5: 三层嵌套信号 × 包裹器（深层alpha假说）──
    for _, sig in _TRIPLE_SIGNALS:
        for _, wrap in _WRAPPERS:
            skeletons.add(wrap.replace("{S}", sig))
    
    # ── 层级3: 双字段信号 × 包裹器 ──
    for _, sig in _DUAL_SIGNALS:
        for _, wrap in _WRAPPERS:
            skeletons.add(wrap.replace("{S}", sig))
    
    # ── 层级4: 信号组合 — 取 top-12 单信号两两配对 ──
    combo_sigs = _SINGLE_SIGNALS[:12]
    for (_, sig_a), (_, sig_b) in itertools.combinations(combo_sigs, 2):
        # 用 F1/F2 区分两个字段
        sa = sig_a.replace("{F}", "{F1}")
        sb = sig_b.replace("{F}", "{F2}")
        for _, comb in _COMBINERS:
            combined = comb.replace("{A}", sa).replace("{B}", sb)
            # 只用 top-3 包裹器（避免爆炸）
            for _, wrap in _WRAPPERS[:3]:
                skeletons.add(wrap.replace("{S}", combined))
    
    # ── 层级5: 条件门控 — 条件用一个信号，交易用另一个 ──
    cond_sigs = _SINGLE_SIGNALS[:8]   # 条件信号
    action_sigs = _SINGLE_SIGNALS[:10]  # 执行信号
    for _, cond_sig in cond_sigs:
        for _, act_sig in action_sigs:
            if cond_sig == act_sig:
                continue
            cond_expr = cond_sig.replace("{F}", "{F1}")
            act_expr = act_sig.replace("{F}", "{F2}")
            # 用 group_rank 包裹执行信号
            act_wrapped = f"group_rank({act_expr}, subindustry)"
            for _, cond_tmpl in _CONDITIONS[:2]:  # 只取2种条件
                skeleton = cond_tmpl.replace("{C}", cond_expr).replace("{S}", act_wrapped)
                skeletons.add(skeleton)
    
    # ── 层级6: 后处理衰减 — 对层级1的子集加衰减 ──
    # 取 top-15 单信号 × top-3 包裹 × 2 衰减方式
    decay_sigs = _SINGLE_SIGNALS[:15]
    for _, sig in decay_sigs:
        for _, wrap in _WRAPPERS[:3]:
            inner = wrap.replace("{S}", sig)
            for _, post in _POST_PROCESSORS[1:]:  # 跳过 "none"
                skeleton = post.replace("{X}", inner)
                skeletons.add(skeleton)
    
    result = list(skeletons)
    logging.info(f"🏭 骨架工厂: 生成 {len(result)} 个有金融意义的唯一骨架")
    return result

# ════════════════════════════════════════════════════════════
# 6. 冷门/热门算子分级系统
# ════════════════════════════════════════════════════════════

# 热门算子 — WQ上烂大街的、几乎所有人都用的
_HOT_OPS = frozenset({
    'rank', 'ts_rank', 'ts_delta', 'ts_mean', 'ts_zscore',
    'ts_std_dev', 'ts_backfill', 'ts_decay_linear',
    'group_rank', 'group_neutralize', 'ts_sum', 'ts_ir',
    'ts_corr', 'ts_decay_exp_window', 'ts_skewness',
})

# 冷门算子 — 很少人用、加分的
_COLD_OPS = frozenset({
    'pasteurize', 'purify', 'densify', 'hedge_volatility',
    'bucket', 'kth_element', 'hump', 'jump_decay',
    'ts_entropy', 'ts_herfindahl', 'ts_kurtosis', 'ts_moment',
    'ts_arg_max', 'ts_arg_min', 'ts_product', 'ts_count_nans',
    'ts_theilsen', 'ts_quantile', 'ts_percentage', 'ts_scale',
    'ts_returns', 'ts_decay_exp',
    'left_tail', 'right_tail', 'fraction', 'inverse',
    'signed_power', 'sign', 'days_from_last_change', 'last_diff_value',
    'group_normalize', 'group_scale', 'group_percentage', 'group_quantile',
    'group_zscore', 'ts_regression', 'ts_covariance',
    'winsorize', 'ts_av_diff', 'log', 'sqrt',
})


def _classify_skeleton(skeleton: str) -> str:
    """将骨架分为 'cold'(含冷门算子) / 'hot'(只含热门算子) / 'mixed'"""
    import re
    ops = set(re.findall(r'[a-z_]+(?=\()', skeleton))
    has_cold = bool(ops & _COLD_OPS)
    # 只要含有任何冷门算子就算冷门骨架
    if has_cold:
        return 'cold'
    # 全是热门算子
    if ops and ops <= _HOT_OPS:
        return 'hot'
    return 'mixed'


# 缓存：分级后的骨架池
_CACHED_POOL = None
_CACHED_COLD = None
_CACHED_HOT = None

def get_skeleton_pool() -> list:
    """获取骨架池（带缓存）。"""
    global _CACHED_POOL
    if _CACHED_POOL is None:
        _CACHED_POOL = build_skeleton_pool()
    return _CACHED_POOL


def get_classified_pools() -> tuple:
    """获取分级后的骨架池: (cold_skeletons, hot_skeletons)
    
    cold = 含有至少一个冷门算子的骨架
    hot  = 只含热门算子的骨架 + mixed
    """
    global _CACHED_COLD, _CACHED_HOT
    if _CACHED_COLD is None:
        pool = get_skeleton_pool()
        cold, hot = [], []
        for sk in pool:
            cls = _classify_skeleton(sk)
            if cls == 'cold':
                cold.append(sk)
            else:
                hot.append(sk)
        _CACHED_COLD = cold
        _CACHED_HOT = hot
        logging.info(f"🧊 骨架分级: 冷门={len(cold)} ({100*len(cold)/len(pool):.0f}%) | 热门={len(hot)} ({100*len(hot)/len(pool):.0f}%)")
    return _CACHED_COLD, _CACHED_HOT


def sample_skeleton(cold_ratio: float = 0.90) -> str:
    """按冷门优先策略抽样一个骨架。
    
    cold_ratio: 从冷门池抽样的概率（默认90%）
    """
    import random
    cold_pool, hot_pool = get_classified_pools()
    if cold_pool and random.random() < cold_ratio:
        return random.choice(cold_pool)
    elif hot_pool:
        return random.choice(hot_pool)
    else:
        return random.choice(get_skeleton_pool())


if __name__ == "__main__":
    import re
    # 测试：打印统计和样例
    pool = build_skeleton_pool()
    print(f"\n总骨架数: {len(pool)}")
    
    cold_pool, hot_pool = get_classified_pools()
    print(f"\n冷门骨架: {len(cold_pool)} ({100*len(cold_pool)/len(pool):.0f}%)")
    print(f"热门骨架: {len(hot_pool)} ({100*len(hot_pool)/len(pool):.0f}%)")
    
    print(f"\n冷门骨架样例 (前15个):")
    for i, sk in enumerate(cold_pool[:15]):
        ops = set(re.findall(r'[a-z_]+(?=\()', sk))
        cold_ops = ops & _COLD_OPS
        print(f"  {i+1}. [冷门算子: {','.join(cold_ops)}]")
        print(f"     {sk}")
    
    print(f"\n热门骨架样例 (前5个):")
    for i, sk in enumerate(hot_pool[:5]):
        print(f"  {i+1}. {sk}")
    
    # 模拟抽样分布
    from collections import Counter
    samples = Counter()
    for _ in range(1000):
        sk = sample_skeleton(0.90)
        samples[_classify_skeleton(sk)] += 1
    print(f"\n1000次抽样分布 (90%冷门):")
    for k, v in sorted(samples.items()):
        print(f"  {k}: {v} ({100*v/1000:.0f}%)")
