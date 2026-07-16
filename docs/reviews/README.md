# 市场评估报告目录 (docs/reviews/)

存放临时性/事件驱动的市场评估报告，与推送脚本 (`market_monitor/monitors/`) 和迭代文档 (`docs/iterations/`) 分开。

## 命名约定

`YYYY-MM-DD-<主题>-<结论标签>.md`

例：
- `2026-07-16-shanghai-3800-not-entry.md` — 上证 3800 附近入场评估
- `2026-XX-XX-<event>-<verdict>.md` — 其他事件评估

## 内容要求

必须包含：
1. **报告生成时间**（精确到分钟 + 时区）
2. **市场快照**（关键指数收盘价 + 涨跌幅 + 快照时间戳）
3. **核心结论**（一句话）
4. **数据来源**（数据库表 / API / 手工核验）

## 与 iterations 的区别

- `docs/iterations/` = 系统建设过程（写代码 + 建表 + 修 bug）
- `docs/reviews/` = 市场评估结果（回答"现在该不该买"这类问题）
