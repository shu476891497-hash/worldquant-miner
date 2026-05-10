# WorldQuant Miner — 交接文档（给下一个 Conversation 用）

## 项目概况

| 项 | 值 |
|---|---|
| 项目路径（本地） | `c:\Users\22637\OneDrive\Desktop\antigravity\worldquant_iqc\worldquant-miner` |
| GitHub 仓库 | `https://github.com/shu476891497-hash/worldquant-miner` |
| 核心文件 | `generation_two\continuous_evolution.py`（2947 行，Python，UTF-8） |
| 目标 | IQC Stage 2 — 24/7 云服务器自动挖矿 |
| 挖矿模式 | `--mode both`（D0 + D1 双引擎并发） |

---

## 项目目录结构（本地）

```
worldquant-miner/
├── generation_two/               ← 主引擎目录（~101 个 .py，约 3 万行）
│   ├── continuous_evolution.py   ← 核心挖矿引擎（2947 行）
│   ├── watchdog.py               ← 云端进程监控
│   ├── core/
│   │   ├── auto_token_refresh.py ← Token 自动刷新（云端必需）
│   │   ├── credential_manager.py
│   │   └── simulator_tester.py
│   ├── intelligence/             ← 论坛情报爬虫模块
│   │   ├── factor_spider.py
│   │   ├── intel_to_template.py
│   │   └── wq_forum_spider.py
│   ├── ollama/
│   │   ├── ollama_manager.py
│   │   └── deepseek_manager.py
│   ├── auth.json                 ← JWT Token（已在 .gitignore，不入库）
│   └── credential.txt            ← 账号密码（已在 .gitignore，不入库）
└── generation_two_alt/           ← 旧版备份（可忽略）
```

---

## GitHub 当前状态

> [!IMPORTANT]
> GitHub 仓库的目录结构是**展平的**——没有 `generation_two/` 前缀，所有文件都在根目录。这是上一个 commit 留下的结构，不要尝试改变它。

- **最新 commit**: `34ff898` — "feat: IQC Stage 2 prep"
- **包含 101 个 .py 文件，共约 30,787 行**
- `continuous_evolution.py` 在 GitHub 上是 2484 行（旧版，本地有 2947 行最新版**未推送**）

### ⚠️ 未推送的最新内容

本地 `generation_two/continuous_evolution.py`（2947 行）比 GitHub 上的版本（2484 行）多出约 463 行最新修改，**尚未推送到 GitHub**。

### 为什么没推成功？

GitHub Personal Access Token 缺少 `workflow` scope，历史 commit 中有 `.github/workflows/release.yml`，每次 push 都被 GitHub 拒绝。上一个 session 绕过了这个问题完成了 push，但是 `continuous_evolution.py` 的最新版没有被正确提取进去。

---

## 下一个 Conversation 的任务清单

### 任务一：把最新的 `continuous_evolution.py` 推到 GitHub

**正确的推送方法（避免 PowerShell 编码问题）：**

```python
# 用 Python 脚本来做 git add + commit + push，不要用 PowerShell 管道
# 或者直接在 cmd 里运行（不是 PowerShell）
```

**步骤：**
1. 确认本地文件行数正确：
   ```python
   python -c "print(len(open('generation_two/continuous_evolution.py', encoding='utf-8').readlines()))"
   # 期望输出: 2947
   ```
2. Git add 和 commit（**只 add 这一个文件**，避免触碰 `.github/` 目录）：
   ```bash
   git add continuous_evolution.py
   git commit -m "feat: update continuous_evolution to latest 2947-line version"
   git push origin master
   ```
   注意：因为 GitHub 上是展平结构，`continuous_evolution.py` 在根目录，不是 `generation_two/continuous_evolution.py`。

> [!CAUTION]
> **绝对不要用 PowerShell 的 `>` 或 `Out-File` 操作 Python 文件！** 会把文件变成 UTF-16 乱码。只能用 Python `subprocess` 或 `git checkout`。

### 任务二：购买云服务器并部署

**推荐配置：**
- 提供商：Vultr 或 DigitalOcean
- 规格：2 vCPU，4GB RAM，80GB SSD
- 地区：美国（New York 或 San Jose，离 WQ API 近）
- 费用：约 $24/月，按小时计费

**部署步骤（在云服务器上）：**

```bash
# 1. 安装依赖
sudo apt update && sudo apt install python3-pip python3-venv git -y

# 2. 克隆仓库
git clone https://github.com/shu476891497-hash/worldquant-miner.git
cd worldquant-miner

# 3. 安装 Python 依赖
pip3 install -r requirements.txt

# 4. 创建 auth.json（手动，不在 git 里）
cat > auth.json << 'EOF'
{
  "cookies": [
    {
      "name": "t",
      "value": "你的JWT_TOKEN",
      "domain": ".worldquantbrain.com",
      "path": "/",
      "httpOnly": false,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
EOF

# 5. 创建 credential.txt
echo "你的邮箱:你的密码" > generation_two/credential.txt

# 6. 启动 24/7 挖矿（使用 nohup 保持后台运行）
nohup python3 continuous_evolution.py --mode both > mining.log 2>&1 &

# 7. 启动看门狗（防止程序崩溃）
nohup python3 watchdog.py > watchdog.log 2>&1 &
```

**查看运行状态：**
```bash
tail -f mining.log      # 实时查看挖矿日志
ps aux | grep python    # 确认进程在跑
```

---

## 重要注意事项

1. **auth.json 的 JWT Token 有过期时间**，需要定期从 WorldQuant Brain 网页更新。`auto_token_refresh.py` 可以自动刷新，需要配置好 `credential.txt`。

2. **Ollama 在云端**：云服务器上如果没有 Ollama，`continuous_evolution.py` 会降级到模板生成模式，仍然可以运行，只是 AI 增强功能失效。

3. **查看 GitHub 上的 Brain URL**：终端日志里会打印 `https://api.worldquantbrain.com/simulations/XXX`，把 `api.` 换成 `brain.`，然后 `/simulations/` 换成 `/alphas/` 就是可以在浏览器里看的链接。

4. **本地开发路径**：本地继续在 `generation_two/` 下开发，云端 `git pull` 同步。GitHub 上是展平结构，本地是有 `generation_two/` 子目录的结构，这个不一致性目前只能接受。

---

## 本次 Session 做了什么

| 操作 | 结果 |
|---|---|
| 更新 `.gitignore` 保护 auth.json 等敏感文件 | ✅ 完成 |
| 推送核心引擎 + intelligence 模块 + watchdog 等到 GitHub | ✅ 完成（`34ff898`） |
| 恢复被 git reset --hard 删掉的 generation_two/ 目录 | ✅ 完成 |
| 修复 PowerShell 编码破坏导致的乱码 | ✅ 完成（用 Python subprocess） |
| 把 2947 行最新版 continuous_evolution.py 推到 GitHub | ❌ 未完成（留给下一个 session） |
