# OpenClaw 使用手册

本文说明 OpenClaw 如何稳定使用 `market-monitor`。

核心原则：

> OpenClaw 负责研究、解释、总结和辅助改造；`market-monitor` 负责定时运行、规则判断、去重、推送和数据沉淀。

---

## 1. 角色边界

### OpenClaw 适合做

- 调用 CLI 查看今日/近期市场状态。
- 读取推送历史和纸面交易，生成复盘。
- 根据结构化输出解释某个信号。
- 辅助修改 monitor、detector、测试和配置。
- 根据你的新想法设计规则草案。

### OpenClaw 不应做

- 作为定时任务执行器。
- 每次临场重新判断是否触发信号。
- 替代规则代码进行去重。
- 作为唯一数据存储。
- 直接承担实盘交易决策。

---

## 2. 环境假设

推荐 OpenClaw 在项目根目录调用命令：

```bash
cd /path/to/daily-market-monitor
source .venv/bin/activate
```

如果没有激活虚拟环境，应显式使用：

```bash
.venv/bin/python -m market_monitor.cli <command>
```

或使用已安装的 console script：

```bash
market-monitor <command>
```

---

## 3. 当前稳定可用命令

### 3.1 查看系统健康

```bash
market-monitor doctor --ci
```

用途：

- 检查 Python、monitor 注册表、launchd 模板、数据库路径和示例配置。
- 不要求真实飞书凭据，适合 OpenClaw 快速判断项目是否可运行。

本机完整检查：

```bash
market-monitor doctor
```

用途：

- 检查真实 `config/config.yaml` 和凭据占位符。

### 3.2 查看可用 monitor

```bash
market-monitor list
```

OpenClaw 应以该命令输出为准，不要硬编码 monitor 列表。

### 3.3 手动运行 monitor

快照模式：

```bash
market-monitor run pulse --snapshot
market-monitor run price_alert --snapshot
market-monitor run shanghai_watch --snapshot
```

强制推送：

```bash
market-monitor run price_alert --force
```

注意：

- `--snapshot` 更适合查询当前状态。
- `--force` 可能触发真实推送，OpenClaw 不应随意使用。

### 3.4 查看推送历史

```bash
market-monitor db query --days 7
market-monitor db query --monitor pulse --days 7
market-monitor db query --level 2 --days 30
```

统计：

```bash
market-monitor db stats --days 30
```

数据库信息：

```bash
market-monitor db info
```

### 3.5 纸面交易

查看持仓和交易：

```bash
market-monitor trade list --all
market-monitor trade pnl --days 30
market-monitor trade review --period week
```

新增纸面交易：

```bash
market-monitor trade add sh510300 4.20 1000 --strategy manual --reason "规则信号后测试开仓"
```

关联已有 `signal_event`：

```bash
market-monitor trade add sh510300 4.20 1000 --signal-id 123 --reason "跟随信号"
```

### 3.6 决策复盘

从推送日志中抽取可检验命题：

```bash
market-monitor decision extract --date 2026-07-17
```

校验某天命题：

```bash
market-monitor decision verify --date 2026-07-17
```

生成周报：

```bash
market-monitor decision review --start 2026-07-10 --end 2026-07-17
```

注意：当前 `decision_tracker` 仍使用 JSONL 作为主存储。后续会逐步收敛到 SQL 信号体系。

### 3.7 日志

```bash
market-monitor logs pulse --tail 100
market-monitor logs price_alert --tail 100
```

---

## 4. 推荐调用范式

### 4.1 今日市场状态

```bash
market-monitor run pulse --snapshot
market-monitor db query --days 1 --limit 20
```

OpenClaw 读取结果后再做中文总结。

### 4.2 最近一周复盘

```bash
market-monitor db stats --days 7
market-monitor db query --days 7 --limit 50
market-monitor trade pnl --days 7
market-monitor trade review --period week
```

OpenClaw 的任务是总结：

- 哪些 monitor 最活跃。
- 哪些信号等级最高。
- 哪些交易有行动偏差。
- 下周应重点观察什么。

### 4.3 检查系统是否能运行

```bash
market-monitor doctor --ci
bash scripts/verify.sh
```

如果要避免运行完整测试：

```bash
market-monitor list
market-monitor db info
```

---

## 5. 当前限制

当前 CLI 主要输出面向人类阅读的文本，还没有全局 `--json` 契约。因此 OpenClaw 现在应优先：

1. 调用 CLI 获取文本结果。
2. 必要时读取 SQLite。
3. 避免依赖中文文案中的脆弱格式。

Phase 1 将补充稳定机器接口：

```bash
market-monitor signal list --days 7 --json
market-monitor signal show <id> --json
market-monitor signal types --json
market-monitor db stats --json
market-monitor trade list --json
market-monitor review weekly --json
```

---

## 6. 数据库入口

默认数据库：

```text
data/market.db
```

路径可由环境变量覆盖：

```bash
MARKET_DB_URL="sqlite:////absolute/path/to/market.db"
```

OpenClaw 可以直接查询 SQLite，但推荐优先使用 CLI。直接查询时应只读，不要绕过 repository 修改数据。

---

## 7. 生成或修改规则的流程

当用户要求 OpenClaw 新增或修改监控规则时，推荐流程：

1. 先读相关 monitor 和配置。
2. 明确触发条件、等级、去重键和建议动作。
3. 补 fixture 或 mock 数据测试。
4. 修改 monitor 或 detector。
5. 运行：

```bash
python -m pytest
bash scripts/verify.sh
```

6. 再手动跑：

```bash
market-monitor run <monitor> --snapshot
```

---

## 8. 安全边界

OpenClaw 不应主动输出或提交：

- `config/config.yaml` 中的真实凭据。
- 飞书 app secret。
- AI API key。
- 个人持仓隐私文件。
- 本地数据库中的敏感备注。

涉及真实推送的命令，例如 `--force`、`test-feishu`，应明确告知用户。

---

## 9. 升级后的目标体验

目标不是让 OpenClaw 每次重新回答“市场怎么样”，而是让它基于事实源回答：

- 今天系统识别了哪些信号？
- 哪些信号被推送，哪些被静默？
- 我有没有采取行动？
- 历史上类似信号结果如何？
- 本周我最大的判断偏差是什么？

也就是：

> OpenClaw 调用事实，解释事实；market-monitor 生产事实，沉淀事实。
