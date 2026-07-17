# market-monitor

面向个人投资者的市场信号监控与研究沉淀系统。

它把行情监控、规则信号、推送提醒、纸面交易和复盘记录沉淀为可运行、可验证、可扩展的本地工具。OpenClaw / LLM 仍然可以作为研究助手和高级调用方使用本项目，但定时监控、状态去重、信号判断和数据沉淀由本项目稳定执行。

## 当前能力

- A 股、港股、美股、大宗商品和宏观事件的定时监控
- 关键点位、异常波动、企稳、盘中脉搏、上证 3800 剧本等规则提醒
- 飞书推送，支持触发才推、强制推送和快照模式
- SQLite 数据层，沉淀行情快照、推送日志、信号事件和纸面交易
- 晨报、午间、盘后、周度、月度节奏化报告
- 纸面交易记录、盈亏统计、交易复盘
- 可选 AI 解读，支持 OpenAI-compatible 接口

## 项目方向

本项目正在从“OpenClaw 使用的监控工具集合”升级为独立的 Market Research OS：

```text
行情采集
  -> 规则信号识别
  -> 信号分级与去重
  -> 推送提醒
  -> 信号与推送落库
  -> 纸面交易/人工动作记录
  -> T+1/T+3/T+5 验证
  -> 周/月复盘
  -> 研究库查询与沉淀
```

升级总纲见 [docs/RESEARCH_OS_UPGRADE_PLAN.md](docs/RESEARCH_OS_UPGRADE_PLAN.md)。

OpenClaw 使用方式见 [docs/OPENCLAW_USAGE.md](docs/OPENCLAW_USAGE.md)。

## 项目结构

```text
market-monitor/
├── market_monitor/
│   ├── core/          # 配置、飞书、AI、行情源、状态等公共能力
│   ├── data/          # SQLAlchemy models、repositories、数据库入口
│   ├── monitors/      # 各监控实现
│   └── cli.py         # 命令行入口
├── alembic/           # 数据库迁移
├── config/            # YAML 配置模板
├── launchd/           # macOS 定时任务模板
├── scripts/           # 安装、验证、健康检查脚本
├── tests/             # 回归测试
└── docs/              # 架构、计划、迭代和复盘文档
```

## 快速开始

建议始终使用项目本地虚拟环境，不要直接安装到系统 Python。

```bash
git clone <your-repo> ~/projects/market-monitor
cd ~/projects/market-monitor

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

如果需要 AH 溢价、ETF 溢价、估值筛选、烟蒂股等 AkShare 扩展：

```bash
python -m pip install -e '.[dev,analytics]'
```

复制本地配置：

```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`，填入飞书、AI 等本机配置。凭据也可以通过环境变量覆盖：

```bash
export FEISHU_APP_ID="..."
export FEISHU_APP_SECRET="..."
export FEISHU_USER_ID="..."
export AI_BASE_URL="..."
export AI_API_KEY="..."
```

初始化数据库：

```bash
python -m alembic -c alembic.ini upgrade head
python -m market_monitor.cli db init
```

## 验证

本地质量门禁：

```bash
bash scripts/verify.sh
python -m pytest
python -m market_monitor.cli doctor --ci
```

本机完整健康检查：

```bash
python -m market_monitor.cli doctor
```

`doctor --ci` 不要求真实凭据；`doctor` 会检查本机 `config/config.yaml` 和飞书凭据占位符。

## 常用命令

列出 monitor：

```bash
market-monitor list
```

手动运行单个 monitor：

```bash
market-monitor run pulse --snapshot
market-monitor run price_alert --force
market-monitor run shanghai_watch --snapshot
```

查看日志：

```bash
market-monitor logs pulse --tail 100
```

查看数据库：

```bash
market-monitor db info
market-monitor db query --days 7 --level 1
market-monitor db stats --days 30
market-monitor db query --days 7 --json
market-monitor db stats --days 30 --json
```

结构化信号：

```bash
market-monitor signal types --json
market-monitor signal list --days 7 --json
market-monitor signal list --push-id <push_log_id> --json
market-monitor signal show <id> --json
```

纸面交易：

```bash
market-monitor trade add sh510300 4.20 1000 --strategy manual --reason "测试记录"
market-monitor trade list --all
market-monitor trade pnl --days 30
market-monitor trade review --period week
```

决策闭环：

```bash
market-monitor decision extract --date 2026-07-17
market-monitor decision verify --date 2026-07-17
market-monitor decision review --start 2026-07-10 --end 2026-07-17
```

## 可用 Monitor

以当前注册表为准：

```bash
market-monitor list
```

当前核心 monitor 包括：

- `stabilize`：A 股企稳信号
- `price_alert`：关键点位
- `shock`：A 股异动
- `hk_shock`：港股异动
- `pulse`：盘中脉搏
- `shanghai_watch`：上证 3800 剧本
- `morning` / `midday` / `evening`：定时报告
- `us_market` / `hk_market`：海外和港股市场快照
- `macro` / `voice`：宏观与意见领袖
- `review` / `monthly`：周度和月度复盘

## 定时运行

macOS 使用 `launchd`：

```bash
bash scripts/install.sh
```

安装脚本会先重新生成 plist，并运行 `doctor --ci`。当前任务状态：

```bash
market-monitor status
```

卸载：

```bash
bash scripts/uninstall.sh
```

## 数据库

默认 SQLite 数据库：

```text
data/market.db
```

可用环境变量覆盖：

```bash
export MARKET_DB_URL="sqlite:////absolute/path/to/market.db"
python -m alembic -c alembic.ini upgrade head
market-monitor db info
```

## 设计原则

1. 触发才推，避免噪音。
2. 规则信号优先，AI 只做增强。
3. 先产生结构化事实，再生成推送文案。
4. 运行、推送、落库、复盘必须可验证。
5. CLI 是一等接口，OpenClaw 和人都应能稳定调用。
6. 新增监控应尽量配置化、可测试、可回放。
7. SQL 是研究库主事实源；JSONL 推送日志保留为兼容与人工同步材料。

## 文档

- [架构说明](docs/ARCHITECTURE.md)
- [升级改造方案](docs/RESEARCH_OS_UPGRADE_PLAN.md)
- [OpenClaw 使用手册](docs/OPENCLAW_USAGE.md)
- [信号模块与研究库评估](docs/SIGNAL_AND_RESEARCH_OS_EVAL.md)
- [数据层设计](docs/DATA_LAYER_DESIGN.md)
- [如何添加新监控](docs/ADD_MONITOR.md)
- [预警规则详解](docs/ALERTS.md)
- [迁移说明](docs/MIGRATION.md)

## License

Private - Personal use only
