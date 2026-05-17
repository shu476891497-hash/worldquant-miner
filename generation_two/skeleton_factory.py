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
]

# ════════════════════════════════════════════════════════════
# 3. 组合模式（两个信号如何交互）
# ════════════════════════════════════════════════════════════
_COMBINERS = [
    ("sum",      "rank({A}) + rank({B})"),                    # 等权叠加
    ("diff",     "rank({A}) - rank({B})"),                    # 多空价差
    ("product",  "rank({A}) * rank({B})"),                    # 交互增强
    ("weighted", "0.6 * rank({A}) + 0.4 * rank({B})"),        # 加权混合
]

# ════════════════════════════════════════════════════════════
# 4. 条件门控（择时 + 信号）
# ════════════════════════════════════════════════════════════
_CONDITIONS = [
    ("high_rank",    "trade_when(ts_rank({C}, {W}) > 0.8, {S}, 0)"),          # 高分位才交易
    ("low_rank",     "trade_when(ts_rank({C}, {W}) < 0.2, {S}, 0)"),          # 低分位才交易
    ("extreme_z",    "trade_when(abs(ts_zscore({C}, {W})) > 1.5, {S}, 0)"),   # 极端偏离才交易
    ("trend_up",     "trade_when(ts_delta({C}, {W}) > 0, {S}, -1)"),          # 趋势向上才交易
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


# 缓存：只在首次调用时生成
_CACHED_POOL = None

def get_skeleton_pool() -> list:
    """获取骨架池（带缓存）。"""
    global _CACHED_POOL
    if _CACHED_POOL is None:
        _CACHED_POOL = build_skeleton_pool()
    return _CACHED_POOL


if __name__ == "__main__":
    # 测试：打印统计和样例
    pool = build_skeleton_pool()
    print(f"\n总骨架数: {len(pool)}")
    print(f"\n前20个样例:")
    for i, sk in enumerate(pool[:20]):
        print(f"  {i+1}. {sk}")
    
    # 统计骨架类型分布
    trade_when_count = sum(1 for s in pool if "trade_when" in s)
    group_rank_count = sum(1 for s in pool if s.startswith("group_rank"))
    group_neut_count = sum(1 for s in pool if s.startswith("group_neutralize"))
    decay_count = sum(1 for s in pool if "ts_decay" in s)
    print(f"\n类型分布:")
    print(f"  trade_when 门控: {trade_when_count}")
    print(f"  group_rank 起始: {group_rank_count}")
    print(f"  group_neutralize: {group_neut_count}")
    print(f"  含衰减: {decay_count}")
