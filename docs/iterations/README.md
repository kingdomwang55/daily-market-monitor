# 迭代文档索引

本目录留存每次功能迭代的**设计文档 + 实现记录 + 决策依据**，方便使用 Claude Code / Codex / Cursor 等工具对代码做 code review 时能快速理解背景。

## 命名规范

`W{阶段编号}-{英文短名}.md`，例如：

- `W1-trade-journal.md` —— 交易日志与复盘系统
- `W2-ah-premium.md` —— AH 溢价套利监控
- `W3-etf-premium.md` —— ETF 折溢价监控
- `W4-valuation-screener.md` —— 估值/烟蒂股筛选器

## 每份文档的固定结构

1. **背景与目标** —— 为什么要做，解决什么问题
2. **需求与约束** —— Steven 给的偏好、技术限制
3. **数据源调研** —— 试过哪些接口、放弃原因、最终选型
4. **表结构与字段** —— DDL 说明（用 SQLAlchemy 模型 or 独立表）
5. **算法/阈值** —— 分位数、罕见信号交叉核实、状态判定
6. **文件清单** —— 新增/修改了哪些代码文件
7. **接入位置** —— 在 morning/evening/其它 monitor 的哪一段
8. **测试与验证** —— 端到端跑一遍的输出、边界情况
9. **已知问题与后续** —— TODO、待观察的坑

## 当前状态（2026-07-10）

| 阶段 | 名称                     | 状态       | 文档                          |
| ---- | ------------------------ | ---------- | ----------------------------- |
| W1   | 交易日志 & 复盘系统      | ✅ 已完成  | [W1-trade-journal.md](./W1-trade-journal.md) |
| W2   | AH 溢价套利监控          | ✅ 已完成  | [W2-ah-premium.md](./W2-ah-premium.md) |
| W3   | ETF 折溢价监控           | ✅ 已完成  | [W3-etf-premium.md](./W3-etf-premium.md) |
| W4   | 估值/烟蒂股筛选器        | ✅ Phase 1 完成 / Phase 2 待做 | [W4-valuation-screener.md](./W4-valuation-screener.md) |

## Review 使用指南

外部工具（Claude Code / Codex）review 代码时，建议先按顺序读：

1. `docs/ARCHITECTURE.md` —— 项目分层
2. `docs/DATA_LAYER_DESIGN.md` —— 数据层规范
3. `docs/iterations/W{N}-*.md` —— 具体迭代的动机与设计
4. 对应源码：`market_monitor/core/{feature}.py`
