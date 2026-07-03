# market-monitor

**多市场智能监控系统** - A股/港股/美股/大宗商品全球联动监控与预警

> 🚀 从 A 股企稳信号到美股夜盘异动，从港股开盘预警到板块黑天鹅，一站式全球市场监控。

## ✨ 功能

- 🇨🇳 **A 股监控**：晨报、盘后总结、关键点位、企稳信号、异常波动预警
- 🇭🇰 **港股监控**：开盘/午盘/尾盘快照 + 盘中异动
- 🌍 **美股夜盘**：中概股 + 科技龙头 + 三大指数
- 💰 **防御性资产**：黄金 / 红利 / 消费 / 海外 ETF 实时快照
- 🤖 **AI 分析**：deepseek-v4-flash 智能解读市场信号
- 📱 **飞书推送**：触发才推，避免打扰

## 📦 项目结构

```
market-monitor/
├── market_monitor/          # Python 包
│   ├── core/                # 公共模块（飞书/数据源/状态/配置）
│   ├── monitors/            # 各监控实现
│   └── cli.py               # 命令行入口
├── config/                  # YAML 配置
├── launchd/                 # macOS 定时任务模板
├── scripts/                 # 安装/卸载/状态脚本
├── tests/                   # 单元测试
└── docs/                    # 文档
```

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone <your-repo> ~/projects/market-monitor
cd ~/projects/market-monitor

# 2. 复制配置模板
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml，填入飞书 user_id 等

# 3. 安装依赖（可选，纯标准库也能跑）
pip install -e .

# 4. 手动测试单个监控
python -m market_monitor.cli run stabilize --force

# 5. 查看所有监控状态
python -m market_monitor.cli status

# 6. 安装到 launchd（macOS）
bash scripts/install.sh
```

## 📚 文档

- [架构说明](docs/ARCHITECTURE.md)
- [如何添加新监控](docs/ADD_MONITOR.md)
- [预警规则详解](docs/ALERTS.md)
- [迁移日志](docs/MIGRATION.md)

## 🛠️ 常用命令

```bash
# 手动运行监控
python -m market_monitor.cli run <monitor_name> [--force] [--snapshot]

# 可用监控名称
#   stabilize     - 企稳信号
#   us_market     - 美股夜盘
#   hk_market     - 港股
#   shock         - A 股异动
#   price_alert   - 关键点位
#   morning       - 晨报
#   evening       - 盘后

# 查看日志
python -m market_monitor.cli logs <monitor_name>

# 查看当前 launchd 任务
python -m market_monitor.cli status

# 测试飞书发送
python -m market_monitor.cli test-feishu "Hello 🐉"
```

## 🎯 设计原则

1. **触发才推** - 只在异动/信号命中时发送，避免噪音
2. **分级预警** - 1.5% 注意 / 2.5% 警戒 / 3.5% 严重
3. **配置驱动** - YAML 改配置，不动代码
4. **可插拔** - 每个监控独立，新增/关闭都简单
5. **可测试** - Mock 数据源，逻辑单测覆盖

## 📄 License

Private - Personal use only
