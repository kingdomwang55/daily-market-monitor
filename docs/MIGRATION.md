# 迁移日志

## 2026-07-03 - 项目初始化 + 从 workspace/scripts/ 迁移

### 起因
散落在 `~/.openclaw/workspace/scripts/` 的多个监控脚本存在以下问题：
- 代码重复（每个脚本都自己写飞书发送、状态管理、数据获取）
- 凭据硬编码/写死 USER_ID
- 阈值、监控标的写死在代码里
- 无版本管理、无测试、无文档
- launchd plist 手写几十行 XML

### 方案
建立独立项目 `~/projects/market-monitor/`：
- Python 包结构 + CLI 入口
- YAML 配置驱动
- 私有 GitHub 仓库版本管理
- launchd plist 自动生成

### 迁移映射

| 老脚本 | 新位置 |
|---|---|
| `scripts/stabilize_alert.py` | `market_monitor/monitors/stabilize.py` |
| `scripts/us_market_alert.py` | `market_monitor/monitors/us_market.py` |
| `scripts/hk_market_alert.py` | `market_monitor/monitors/hk_market.py` |
| `scripts/market_shock_alert.py` | `market_monitor/monitors/shock.py` |
| `scripts/price_alert.py` | `market_monitor/monitors/price_alert.py` |
| （复用飞书） | `market_monitor/core/feishu.py` |
| （复用数据源） | `market_monitor/core/data_source.py` |
| （复用状态） | `market_monitor/core/state.py` |
| （复用配置） | `market_monitor/core/config.py` |
| `~/Library/LaunchAgents/com.openclaw.*.plist` | `launchd/com.market-monitor.*.plist` |

### 未迁移（暂保留在 workspace）
- `stock_morning_report.py` - 晨报（AI 集成较复杂，Phase 2 迁移）
- `stock_evening_report.py` - 盘后报告（同上）
- `beijing_housing_daily.sh` - 与市场监控无关
- `camera_capture.py` - 与市场监控无关
- `voice-*.sh` - 与市场监控无关
- `health-check.sh` - 系统级

### 采用 A 方案（稳妥式）
新老版本并行运行一段时间，观察无异常后再执行 `scripts/migrate.sh` 移除旧任务。

### 验证清单
- [x] 5 个 monitor 手动跑通（`cli run <name>`）
- [x] YAML 配置加载正确
- [x] 飞书凭据从 openclaw.json 自动加载
- [x] launchd plist 自动生成
- [ ] 老任务并行运行观察 3 天（切换前）
- [ ] git init + push 到 GitHub
- [ ] `scripts/install.sh` 完整执行
- [ ] 单元测试 (Phase 2)
