# 架构说明

## 分层设计

```
┌───────────────────────────────────────┐
│  CLI (market_monitor/cli.py)          │  ← 命令行入口
├───────────────────────────────────────┤
│  Monitors (market_monitor/monitors/)  │  ← 各监控实现
│  ├── StabilizeMonitor                 │
│  ├── UsMarketMonitor                  │
│  ├── HkMarketMonitor                  │
│  ├── ShockMonitor                     │
│  └── PriceAlertMonitor                │
├───────────────────────────────────────┤
│  Core (market_monitor/core/)          │  ← 公共基础设施
│  ├── config.py    - 配置加载          │
│  ├── feishu.py    - 飞书推送          │
│  ├── data_source.py - 行情数据源      │
│  ├── state.py     - 状态存储          │
│  ├── base.py      - Monitor 基类       │
│  └── launchd.py   - plist 生成器       │
├───────────────────────────────────────┤
│  External                             │
│  ├── sinajs (新浪财经)                │
│  ├── eastmoney (东方财富)             │
│  ├── 飞书 Open API                    │
│  └── AI (custom / deepseek)         │
└───────────────────────────────────────┘
```

## 数据流

```
launchd → python -m market_monitor.cli run <name>
                    ↓
              MonitorClass()
                    ↓
     ┌──────────────┼──────────────┐
     ↓              ↓              ↓
  Config       DataSource       State
     ↓              ↓              ↓
     └──────────► run() ◄──────────┘
                    ↓
                  Feishu
                    ↓
                  用户飞书
```

## 关键设计决策

### 1. 状态文件路径统一
所有 monitor 的 state 都在 `/tmp/{name}_state.json`，`State` 类统一管理。

### 2. 配置分离
- 结构化配置：`config/config.yaml` (本地，不入 git，含凭据)
- 模板：`config/config.example.yaml` (git tracked，占位符)
- 凭据也可通过环境变量覆盖: `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `AI_BASE_URL` / `AI_API_KEY`

### 3. 触发-静默模式
默认静默运行，只在满足以下条件才推送：
- 命中预警阈值（首次）
- `--force` 强制
- `--snapshot` 快照模式
- 每日首次（如企稳信号的防御性资产快照）

### 4. Monitor 独立
每个 monitor 是独立类，继承 `BaseMonitor`。新增只需：
1. 在 `monitors/` 建新文件
2. 在 `registry.py` 注册
3. 在 `config.yaml` 加配置

### 5. launchd plist 自动生成
不手写 XML。修改 `scripts/gen_launchd.py` 后重新生成，保持一致性。
