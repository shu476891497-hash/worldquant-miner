# Power Pool 主题 & 提交机制 发现记录（2026-07-13）

> 通过 WQ API 实测搜集，用于修正提交策略。账号 XS20799（full consultant）。

## 1. 本月活跃主题（从因子的 MATCHES_THEMES 检查里读到）

每个 alpha 的 `is.checks` 里有 `MATCHES_THEMES`，列出它命中的主题 + 倍率：

| 主题 id | 主题名 | 倍率 | 说明 |
|---|---|---|---|
| `lyvRddy` | **USA/D1 Power Pool July'26** | **1.0** | 本月主力 Power Pool 主题（USA、delay1） |
| `myzqOo4` | **GLB High Turnover Theme** | **2.0** ⭐ | 奖励翻倍，面向 GLB + 高换手 |

- 主题 id 没有直接查询接口（`/themes/{id}`、`/competitions/{id}` 对这俩 id 都 404）。信息只能从 alpha 的 MATCHES_THEMES 里读。
- **规则没根本变**：本月仍是 `USA/D1 Power Pool`，我们一直用的 USA/TOP1000/delay1/特殊中性化设置依然对路。

## 2. 关键机制修正（实测推翻了之前的猜测）

### 2.1 MATCHES_THEMES 是"打分项"，不是"进池闸门"
- **已进池（ACTIVE）的因子（pwlXdkwb、xAk0nNdN、lelzLK28）的 USA 主题匹配也是 PENDING。**
- 即：主题匹配 PENDING **不阻止进池**。它是 WQ 慢慢算的，决定**竞赛得分（乘以倍率）**，和能否 ACTIVE 无关。
- GLB High Turnover 那条对我们的 USA 低换手因子是 WARNING（不完全匹配），USA 那条是 PENDING（在算）。

### 2.2 进池闸门 = `POWER_POOL_ELIGIBLE` 分类章（只读，WQ 算）
- `GET /alphas/{id}` → `classifications`。有 `POWER_POOL:POWER_POOL_ELIGIBLE` 才走快速通道进池。
- **实测不可写**：`PATCH classifications=[POWER_POOL_ELIGIBLE]` → **HTTP 400 "is not a valid choice"**。
- 加同名 tag 能加（200），但 `classifications` 不变 → **对进池无效**（闸门看 classifications，不看 tag）。
- 结论：进池资格只能等 WQ 定期批量计算，无法人为添加/加速（只能靠因子质量更高）。

### 2.3 提交通道对比（我们的弱因子只够 Power Pool）
| 通道 | 门槛 | 我们 Sharpe~1.0 的因子 |
|---|---|---|
| Power Pool | Sharpe≥1.0、≤8算子、≤3字段、换手1-70%、PP自相关<0.5、**免 fitness/prod-corr/IS Ladder** | ✅ 唯一够得着 |
| ATOM（单数据集） | 近2年 Sharpe≥1.59（D1）、prod-corr<0.7、免 IS Ladder | ❌ 太弱 |
| Regular | prod-corr<0.7 + IS Ladder | ❌ 太难 |

### 2.4 HTTP 201 ≠ 进池
- `POST /submit` 返回 201 只代表请求被接受，进入 PENDING 检查。
- **只有 `status==ACTIVE` 才是真进池。** 没资格章的因子提交后走"普通 Alpha"路径（PROD_CORRELATION/REGULAR_SUBMISSION 永远 PENDING），卡死不进池。

## 3. 竞赛背景
- `/users/self/competitions`：当前报名 **IQC2026S2**（International Quant Championship 2026 Stage 2）。
- PPAC2025（Power Pool Alphas Competition）是 2025-03~05 的旧赛事，已 EXCLUDED。
- 月度 Power Pool Alpha 组合的合并表现决定 Power Pool 排行奖励。

## 4. 战略含义 & 建议

### 4.1 现有 USA 低换手线（1.0倍）
- 方向没错，但进池靠等 WQ 盖 `POWER_POOL_ELIGIBLE`，节奏慢、不可控。
- 保持：挖高质量（Sharpe 1.3+、稳健、低相关）组合因子 → WQ 更可能盖章 → 守护进程自动交。

### 4.2 ⭐ 新机会：GLB High Turnover Theme（2.0倍）
- **奖励翻倍**，且**高换手因子容易冲高 Sharpe**（历史 ern4 高换手能到 1.8+）——双重利好。
- 需要的设置（待确认精确阈值）：**region=GLB、高换手**（可能 >某阈值，与低换手约束相反）。
- **建议开第二条线**：专挖 GLB 高换手因子打 2.0 主题，可能比 USA 低换手线更快见效且翻倍赚。

### 4.3 待确认（open questions）
- GLB High Turnover Theme 的**精确准入规则**（换手下限？universe？中性化范围？delay？）——API 无直接接口，需从命中该主题且 result≠WARNING 的因子反推，或查 WQ 文档/论坛。
- `POWER_POOL_ELIGIBLE` 分类的**触发条件与周期**（是否与"提交过一次"相关、多久算一批）——目前只能观察。

## 5. 给 codex 的行动项
1. 现有 USA 组合 miner 继续跑（1.0倍主力）。
2. **新增 GLB 高换手 miner**：region=GLB、放开换手上限（甚至偏好高换手）、冲高 Sharpe，打 2.0 主题。先小规模验证能否命中 `GLB High Turnover Theme` 且 result 变 PASS。
3. 提交守护 `pp_autosubmit.py`：只交有 `POWER_POOL_ELIGIBLE` 的，轮询到 ACTIVE 才算成功（已修）。

## 6. 2026-07-13 API 实测补充：GLB 高换手精确门槛

通过 `GET /users/self/alphas?settings.region=GLB` 和逐条
`GET /alphas/{id}`，账户共有 8 条 GLB 样本。平台直接暴露了以下检查：

- `HT_TURNOVER`: 换手下限 `0.20`。
- `HIGH_TURNOVER`: 普通上限 `0.70`。
- 因此主题目标换手区间为 **20% 到 70%**。
- `HT_HIGH_TURNOVER_RETURNS_RATIO`: 下限 `0.75`。
- GLB Regular 同时要求总 Sharpe `>=1.58`，且 Amer/EMEA/APAC 各自
  Sharpe `>=1.0`。

样本 `O0ZW6OmJ`（GLB/TOP3000/D1/COUNTRY/decay0）换手 28.56%，
`HT_TURNOVER=PASS`，但 returns ratio 只有 0.3043，因此主题仍 WARNING。
这证明“region=GLB + 高换手”仍不充分，ratio 是第二个硬门槛。

当前最值得优化的种子是 `KP9lkrE8`：总 Sharpe 1.95，Amer/EMEA/APAC
分别为 1.05/1.58/1.13，均已通过；换手 14.63%，ratio 0.3944。其表达式为：

```text
rank(ts_delta(mdl110_growth,120))
+ rank(ts_delta(mdl110_analyst_sentiment,120))
```

下一步只缩短两个趋势窗口到 90/60/40/20 日及非对称 60/120，保留
GLB/MINVOL1M/D1/INDUSTRY/decay0，目标是将换手推入 20%-70%，同时保持
三大区域 Sharpe 并把 returns ratio 提升至 0.75。
