# 因子质量提升设计文档（交给 codex 实现）

> 目标：让 miner 挖出的因子能被 WQ 认定 `POWER_POOL_ELIGIBLE` 并真正进池、赚钱。
> 现状：单信号因子 Sharpe 卡在 1.0-1.1，WQ 不给资格；且有高换手、爆仓年、自相关等质量问题。
> 本文档 = 背景硬事实 + 质量提升策略 + 给 codex 的具体实现任务。

---

## 0. 背景硬事实（codex 必读，这些是踩坑换来的）

### 0.1 本周 Power Pool 主题（硬性提交门槛）
```
region=USA & delay=1 & universe=TOP1000
& neutralization ∈ {STATISTICAL, CROWDING, FAST, SLOW, SLOW_AND_FAST}
& datasets NOT in [pv1]
```
不符合主题 = 提交直接 FAIL（"does not match any Power Pool Theme"）。主题每周轮换，可能变 GLB。**当前所有挖矿必须用上面这套设置。**

### 0.2 真正的 Power Pool 资格标准（不是常规 Alpha 标准）
- Sharpe ≥ 1.0（**不是** 1.58）
- 唯一算子数 ≤ 8
- 唯一数据字段数 ≤ 3（不含 group 字段 country/industry/subindustry/currency/market/sector/exchange）
- 换手 1%-70%
- 和自己**已在 Power Pool 里**的 alpha 自相关 < 0.5
- **不适用**：Fitness 门槛、Prod Correlation、IS Ladder、与非-PP alpha 的自相关

### 0.3 真正的进池闸门 = WQ 的 classification（最关键的发现）
- 光满足 0.2 的数值标准**不够**。WQ 会给合格的 alpha 打分类 `POWER_POOL:POWER_POOL_ELIGIBLE`。
- **只有带这个分类的才能真正提交进池（status 变 ACTIVE）。** 没有这个分类的，提交后会走"普通 Alpha"路径，卡在 PROD_CORRELATION PENDING 永不结束。
- 判断方法：`GET /alphas/{id}` → `classifications` 里有没有 `POWER_POOL:POWER_POOL_ELIGIBLE`；列表接口 `/users/self/alphas` 的每条也带 `classifications` 字段。
- 观察：Sharpe 1.07/1.11/1.49 的进了池（有资格分类）；Sharpe 1.00-1.03 的**没有**资格分类。**推测 WQ 的实际资格 Sharpe 门槛比 1.0 高（约 ≥1.05~1.1），且分类是 WQ 定期批量计算、非即时。**
- **实现要点：submit 前先查 classification，只提交带 `POWER_POOL_ELIGIBLE` 的。**

### 0.4 什么数据集能用（信号在风险中性化下能不能活）
- **死矿**：fundamental / analyst（est_eps 等）。在 statistical/crowding 等风险模型中性化下 Sharpe 从 1.4 掉到 0.3-0.7。earnings4/option6 也是死矿（高换手、扣费后亏）。
- **活矿**：model / 预测 / CNN / technical 数据集（天生和风险因子正交）。已验证能出 Sharpe≥1 主题合规因子的字段：`img_cnn_feature1_us_ibes_1_b2_d1`、`img30d_return_bisection`、`atm_call_option_delta_maximum`、`mdl313_ick`、`mdl141_qes_fleir_irr` 等。
- **优先数据集**（预测/收益预测类，信号最强）：`multifactor_return_pred`、`predictive_starmine`、`ai_equity_alpha`、`analyst_revision_horizons`、`global_seasonal_model`、`tech_chart_model`、以及 `model*` 系列。

### 0.5 已知质量问题（都要在 miner 里过滤掉）
1. **高换手**：`ts_zscore(field,60)` 结构换手 22-68%，`rank(ts_delta(field,120))` 结构换手 8-16%。→ **只留换手 ≤30%，优先慢动量结构。**
2. **爆仓年（过拟合）**：整体 Sharpe 1.10 但某个样本外年份收益 -83%、Sharpe -1.64（如 WjGqVP6k）。用 `GET /alphas/{id}/recordsets/yearly-stats` 拿逐年数据（含 TRAIN/TEST 划分）。→ **任何 TEST 年份 returns<-15% 或 sharpe<-1 直接毙。**
3. **重复字段/自相关**：miner 反复挖同一个字段的不同参数变体，互相自相关，第二个交不进去。→ **每个字段/数据集只留一个最好的。**
4. **边缘 Sharpe**：Sharpe 刚过 1.0 的拿不到资格分类。→ **把留存门槛提到 Sharpe≥1.3。**

### 0.6 字段池
- 位置：`generation_two/constants/consultant_fields/consultant_expression_fields.jsonl`（231MB，36万字段，每行一个 JSON）。
- 每行字段：`id, type(MATRIX/VECTOR), region, delay, universe, dataset_id, category_name` 等。
- **流式读**（不要 json.load 整包，会 1.5GB 内存爆）。只取 region=USA & delay=1 & type=MATRIX & dataset 非 pv1 的 model/预测类。

### 0.7 提交 API 流程
1. `PATCH /alphas/{id}` json=`{"tags":["PowerPoolSelected"], "regular":{"description": <至少100字符, Idea/Rationale 模板>}}`
2. `POST /alphas/{id}/submit`
3. 轮询 `GET /alphas/{id}` 直到 `status=="ACTIVE"`（=进池）。
- **每日进池上限约 1-2 个**，且检查慢（几十分钟~几小时）。**不要反复 re-trigger submit（会重置检查）**，提交一次后耐心等。
- **认证**：cookie 模式，`credential_4.txt` 第2行 `COOKIE:<jwt>`，代码里 `session.cookies.set("t", jwt, domain=".worldquantbrain.com")`（**不是** Authorization Bearer，Bearer 会 403）。

### 0.8 multi-simulation（吞吐 10x，官方 ACE 方式）
- `POST /simulations` 传 **list[dict]**（最多10个，同 region/delay/language/instrument）→ 返回 Location → 轮询父任务 → 完成后 `children` 是子模拟 id 列表 → 每个 `GET /simulations/{child}` 拿 `alpha` id → 再 `GET /alphas/{alpha_id}` 拿指标。
- 并发上限：8 个 multi-sim 同时 = 最多 80 模拟在飞。
- 参考现有实现：`generation_two/pp_usa_optimize.py`、`pp_usa_combo.py` 的 `run_multi()`。

---

## 1. 核心质量提升策略（按影响力排序）

### 策略 A：双信号组合（最重要，数学上确定有效）⭐⭐⭐
- **原理**：两个各 Sharpe≈1.0、互不相关的信号等权相加 → 组合 Sharpe ≈ 1.0×√2 ≈ **1.4**。这是官方 mdl110 推荐因子（growth + analyst_sentiment）的思路。
- **结构**（保持 ≤3 字段 ≤8 算子）：
  - `rank(ts_delta(A, 120)) + rank(ts_delta(B, 120))`
  - `group_rank(ts_zscore(A,60),industry) + group_rank(ts_zscore(B,60),industry)`
- **关键：A、B 必须来自不同数据集、低相关**，否则组合不涨 Sharpe。
- 已有骨架：`pp_usa_combo.py`（两阶段：先测单信号→挑好的→两两组合）。**codex 在此基础上加"相关性感知配对"（见任务 3）。**

### 策略 B：只挖强数据集 ⭐⭐
- 优先 0.4 里的预测/收益预测数据集（本身就是收益预测，Sharpe 天生高）。
- 每个数据集覆盖 1-2 个代表字段，横扫多数据集找多样信号。

### 策略 C：三重质量闸门 ⭐⭐
留存条件（全部满足才算 winner）：
1. 主题合规（USA/TOP1000/delay1/特殊中性化）
2. Sharpe ≥ 1.3（而不是 1.0，冲资格分类）
3. 换手 1%-30%
4. 无爆仓年（TEST 年份无 returns<-15% 或 sharpe<-1）
5. 每字段/数据集只留 returns 最高的一个（去自相关）

### 策略 D：相关性感知（进阶）⭐
- 组合配对前，先算候选信号两两相关性（用 alpha 的 pnl recordset 或 WQ 的 correlation 接口），**只组合相关性 <0.3 的对**，最大化 Sharpe 提升。
- 提交前，算和已在池因子的相关性，>0.5 的跳过（否则 POWER_POOL_CORRELATION 拒）。

### 策略 E：只提交 WQ 已认证够格的 ⭐⭐⭐
- 见 0.3。提交前必查 `classifications` 含 `POWER_POOL_ELIGIBLE`。
- 挖矿产出先攒着，等 WQ 打上资格分类后再由自动提交守护进程提交。参考 `/tmp/autosubmit.py` 逻辑（本地已有，见任务 5）。

---

## 2. 目标产出定义（什么叫"好因子"）

一个可提交的高质量 Power Pool 因子必须**同时**满足：
| 维度 | 标准 |
|---|---|
| 主题合规 | USA / TOP1000 / delay1 / {statistical,crowding,fast,slow,slow_and_fast} / 非pv1 |
| Sharpe | ≥ 1.3（冲资格分类，实测 1.0 边缘拿不到资格） |
| 换手 | 1%–30%（低成本） |
| 稳健性 | 所有样本外(TEST)年份 returns ≥ -15% 且 sharpe ≥ -1 |
| 简洁性 | 算子 ≤ 8，字段 ≤ 3 |
| 多样性 | 和已提交因子不同字段/低相关 |
| WQ 资格 | classifications 含 POWER_POOL_ELIGIBLE |
| 收益 | returns 越高越好（同等条件下选 returns 最高） |

---

## 3. 给 codex 的具体实现任务

### 任务 1：升级组合 miner `pp_usa_combo.py`
- 现状：两阶段（单信号→两两组合），阶段2硬编码 `rank(ts_delta(A,120))+rank(ts_delta(B,120))`。
- 要加：
  - (a) **相关性感知配对**：阶段1拿到每个好单信号的 pnl（`GET /alphas/{id}/recordsets/pnl` 或用日收益序列），算两两 Pearson 相关，**只组合 |corr|<0.3 的对**。
  - (b) 组合结构多试几种：`rank(ts_delta A)+rank(ts_delta B)`、`group_rank(ts_zscore A)+group_rank(ts_zscore B)`、加权 `0.6*rank(A)+0.4*rank(B)` 扫权重。
  - (c) winner 门槛：Sharpe≥1.3 + 换手≤30% + 无爆仓年（复用 `robust()`）+ ≤3字段≤8算子。
  - (d) 输出 winner 到 json 文件 `pp_combo_winners.json`（含 id/expr/sharpe/returns/turnover），供提交守护进程读。

### 任务 2：字段多样性 + 强数据集优先
- 从 jsonl 流式读，按 0.4 的优先数据集排序，每数据集取 1-2 个 MATRIX 字段，覆盖尽量多数据集（目标 ≥100 个不同数据集）。
- 跳过已在账号里用过的字段（读 `/users/self/alphas` 的现有表达式提取字段名，建 used 集合）。

### 任务 3：稳健性 + 换手过滤（复用现有）
- `robust(aid)`：`GET /alphas/{id}/recordsets/yearly-stats`，TEST 年份任一 returns<-15% 或 sharpe<-1 → 淘汰。（`pp_usa_optimize.py` 已有，抽成公共函数。）
- 换手 ≤0.30 硬过滤。

### 任务 4：只挑 WQ 认证够格的提交
- 扫 `/users/self/alphas`，筛 `classifications` 含 `POWER_POOL:POWER_POOL_ELIGIBLE` && status==UNSUBMITTED && 主题合规 && 换手≤30% && 无爆仓年 && 字段不撞已在池的。
- 对选中的：PATCH 标签+描述 → POST submit → 轮询到 ACTIVE。**提交一次不重复戳。**

### 任务 5：自动提交守护进程（长驻）
- 每 5 分钟循环任务4，发现新的够格因子自动提交，日志记 `AUTO-SUBMITTED`。
- 401 时干净退出（cookie 死）。每日进池到上限后自然停（后续因子会 pending，别硬戳）。
- 参考现有 `/tmp/autosubmit.py`（可整理进仓库 `generation_two/pp_autosubmit.py`）。

### 任务 6（可选，进阶）：ATOM / 单数据集因子
- Power Pool 因子若只用 1 个数据集的字段 = 同时也是 ATOM（单数据集 alpha），双重价值。
- 组合时若 A、B 同数据集不同字段，仍是单数据集 → 优先这种（既组合提 Sharpe 又保持 ATOM 资格）。但注意同数据集字段可能相关，需相关性过滤。

---

## 4. 关键陷阱（别踩）
- **cookie 每 1-2 小时死**：用户每次网页登录会顶掉 cookie；JWT 也短命。守护进程/挖矿要在一个 cookie 窗口内跑完，**用户发 cookie 后别再开 WQ 网页**。
- **别把大 JSON 整包读进内存**（1.5GB 爆）。流式读 jsonl。
- **别反复 re-trigger submit**（重置检查，永不完成）。
- **别提交没有 `POWER_POOL_ELIGIBLE` 分类的**（走普通路径卡死）。
- **Bearer 认证会 403**，必须用 cookie `t`。
- **GitHub 从上海 VPS 不稳**：`git config --global url."https://ghfast.top/https://github.com/".insteadOf "https://github.com/"` 走代理。
- **VNC/WebShell 粘贴长 cookie 会变圆点**：用 base64 传 `echo '<b64>' | base64 -d > credential_4.txt`。

---

## 5. 现有可复用代码
- `generation_two/pp_usa_optimize.py` — 单信号优化版（多样性+每字段最优+稳健性）。有 `run_multi()`、`robust()`、字段发现。
- `generation_two/pp_usa_combo.py` — 组合版骨架（任务1在此升级）。
- `generation_two/consultant_auto_miner.py` — `expression_operators()`、`expression_fields()` 工具函数（数算子/字段用）。
- `/tmp/autosubmit.py` — 自动提交守护进程逻辑（任务5整理进仓库）。

---

## 6. 成功标准
1. miner 产出的因子里，**被 WQ 打 `POWER_POOL_ELIGIBLE` 的比例显著上升**（现在≈0）。
2. 组合因子 Sharpe 稳定在 1.3+，换手 ≤30%，无爆仓年。
3. 自动提交守护进程能持续把够格因子送进池（status→ACTIVE）。
4. Power Pool 组合里信号多样、互相低相关（提升合并表现，这才是主题竞赛赚钱的关键）。
