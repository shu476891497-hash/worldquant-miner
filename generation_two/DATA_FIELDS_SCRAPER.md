# WQ Brain 数据字段爬虫文档

> 最后更新: 2026-05-13 | Scraper v7 (offset pagination + dedup)

## 📊 当前缓存数据

| 文件 | Delay | Universe | 字段数 | 大小 |
|------|-------|----------|--------|------|
| `constants/data_fields_cache_USA_1_TOP3000.json` | D1 | TOP3000 | **7,780** | ~4.2 MB |
| `constants/data_fields_cache_USA_0_TOP1000.json` | D0 | TOP1000 | **2,121** | ~1.1 MB |

### D1 字段分布
| Category | Count | 主要 Datasets |
|----------|-------|---------------|
| Model | 3,296 | model16(24), model51(16), model77(3256) |
| Analyst | 1,324 | analyst4(1324) |
| Fundamental | 1,758 | fundamental2(766), fundamental6(886+) |
| News | 1,021 | news12(875+), news18(121+) |
| Option | 138 | option8(64), option9(74) |
| PV | 202 | pv1(24), pv13(165+), univ1(6) |
| Sentiment | 19 | sentiment1(19) |
| SocialMedia | 22 | socialmedia12(18), socialmedia8(4) |

---

## 🚀 快速使用 (队友一键操作)

### 方法 1: 直接用缓存 (推荐)
```bash
git clone https://github.com/shu476891497-hash/worldquant-miner.git
# 缓存已在 generation_two/constants/ 目录下，直接可用
```

### 方法 2: 自己重新爬取 (更新数据)
```bash
cd generation_two

# 1. 准备 auth.json (需要有效的 JWT token)
# 从浏览器登录 https://platform.worldquantbrain.com 后，
# 在 DevTools > Application > Cookies 中找到 't' cookie
# 创建 auth.json:
cat > auth.json << 'EOF'
{
  "cookies": [
    {"name": "t", "value": "你的JWT_TOKEN"}
  ]
}
EOF

# 2. 运行爬虫 (约 30-45 分钟)
python fetch_all_datafields.py

# 3. 输出文件在 constants/ 目录下
```

### 方法 3: 检查 JWT 有效期
```bash
python check_token.py
# 输出示例: Token expires at 2026-05-13 03:59:18 UTC (1.8h remaining)
```

---

## ⚠️ API 踩坑记录 (重要！)

### 1. Rate Limiting (速率限制)

| 限制类型 | 值 | 来源 |
|---------|-----|------|
| 每秒请求数 | **1 req/sec** | `X-RateLimit-Limit: 1` header |
| 每分钟请求数 | **~30 req/min** | 实测，非官方文档 |
| 安全间隔 | **≥3 秒/请求** | 我们的最佳实践 |

**429 处理**: 收到 429 时，读 `Retry-After` header，等待 `Retry-After + 5` 秒

```python
if r.status_code == 429:
    wait = int(r.headers.get('Retry-After', 10))
    time.sleep(wait + 5)  # +5s 安全裕量
```

### 2. 分页方式: `offset` (不是 `page`!)

**这是最大的坑！**

- ❌ `page=2` → API 会忽略 page 参数，返回和 page=1 一样的数据（无限循环！）
- ✅ `offset=50` → 正确跳过前 50 条，返回下一批

```python
# 正确的分页方式
params = {
    'dataset.id': ds_id,
    'limit': 50,
    'offset': 0,      # 第一页: 0
    # 'offset': 50,    # 第二页: 50
    # 'offset': 100,   # 第三页: 100
}
```

**判断分页结束**:
- API 返回 `count` 字段 = 总数
- 当 `len(unique_fields) >= count` 时停止
- 额外安全: 如果一页没有新的 unique field，说明在循环

### 3. `/data-sets` 的 limit 限制

- ❌ `limit=100` → **400 Bad Request**: `"pagination limit too high"`
- ✅ `limit=20` → 正常返回
- `/data-fields` 的 limit 可以到 `50`

### 4. 认证方式

| 方式 | 说明 | 推荐 |
|------|------|------|
| JWT Bearer Token | `Authorization: Bearer <JWT>` | ✅ 推荐 |
| Email+Password (BasicAuth) | 会触发 Biometrics 验证 | ❌ 不推荐 |
| Cookie `t=<JWT>` | 等效于 Bearer，浏览器方式 | ⚠️ 可用 |

**JWT 获取方式**:
1. 浏览器登录 platform.worldquantbrain.com
2. DevTools → Application → Cookies → 复制 `t` 的值
3. Token 有效期约 **2 小时**

### 5. 必需的请求参数

```python
# /data-sets 必需参数
{
    'category': 'model',           # model|analyst|fundamental|news|option|pv|sentiment|socialmedia
    'delay': 1,                    # 0 或 1
    'instrumentType': 'EQUITY',    # 固定
    'region': 'USA',               # USA|EUR|ASI 等
    'universe': 'TOP3000',         # D1=TOP3000, D0=TOP1000
    'limit': 20,                   # ≤20!
}

# /data-fields 必需参数
{
    'dataset.id': 'model77',       # 从 /data-sets 获取
    'delay': 1,
    'instrumentType': 'EQUITY',
    'region': 'USA',
    'universe': 'TOP3000',
    'limit': 50,                   # ≤50 安全
    'offset': 0,                   # 分页偏移
}
```

### 6. Python `requests` 的 falsy 陷阱

```python
# ❌ 错误写法 — HTTP 400/404 的 Response 对象是 falsy!
r = sess.get(url)
if not r:    # 400 状态码的 r 也是 False!
    break

# ✅ 正确写法
if r is None or r.status_code != 200:
    break
```

### 7. GitHub 在中国服务器被墙

- 腾讯云服务器无法 `git pull` GitHub
- 解决方案: 本地 `tar -czf` 打包，`scp` 传到服务器解压

---

## 🏗️ 架构说明

```
fetch_all_datafields.py     # 爬虫主程序
├── jwt_auth()              # JWT 认证
├── throttle()              # 3s 间隔限流
├── api_get()               # 带重试的 GET (429/timeout 自动处理)
├── get_datasets()          # Step 1: 获取 dataset IDs
├── get_fields()            # Step 2: offset 分页拉取字段
└── main()                  # 遍历 8 个 category × 2 个 delay

constants/
├── data_fields_cache_USA_1_TOP3000.json    # D1 缓存 (7,780 fields)
├── data_fields_cache_USA_0_TOP1000.json    # D0 缓存 (2,121 fields)
└── *.json.bak                               # 上一次的备份

auth.json                   # JWT token (不要提交到 Git!)
check_token.py              # JWT 过期时间检查工具
```

---

## 🌊 蓝海策略说明

引擎会自动从缓存中筛选「蓝海字段」:
- `users < 30` (使用人数少)
- `alphas < 50` (已发现的 alpha 少)
- `coverage >= 0.3` (数据覆盖率合格)

当前蓝海字段: **~2,608 个** (主要在 Model 类别)

---

## 📝 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1-v3 | 2026-05-12 | BasicAuth → JWT 认证迁移 |
| v4 | 2026-05-12 | JWT-only 模式，去掉密码登录 |
| v5 | 2026-05-13 | 超慢模式 (5s interval)，调试 400 错误 |
| v6 | 2026-05-13 | 修复 `limit` 参数 (100→20)，添加 dedup |
| v7 | 2026-05-13 | **`page` → `offset` 分页**，修复无限循环，成功拉取 7,780 fields |

---

## 🔧 云服务器部署

```bash
# 1. 本地打包
tar -czf gen2_deploy.tar.gz --exclude=__pycache__ --exclude=*.pyc \
    --exclude=*.db --exclude=*.log --exclude=auth.json \
    --exclude=credential.txt -C /path/to/worldquant-miner generation_two

# 2. SCP 传到服务器
scp gen2_deploy.tar.gz root@124.220.69.2:/root/

# 3. 服务器解压
ssh root@124.220.69.2
cd /root/worldquant-miner && tar -xzf /root/gen2_deploy.tar.gz

# 4. 配置凭据
echo 'your_email@gmail.com' > generation_two/credential.txt
echo 'your_password' >> generation_two/credential.txt

# 5. 启动 24/7 引擎
cd generation_two
export PYTHONPATH=/root/worldquant-miner:$PYTHONPATH
nohup python3 continuous_evolution.py --mode d1 > mining.log 2>&1 &

# 6. 查看日志
tail -f mining.log
```
