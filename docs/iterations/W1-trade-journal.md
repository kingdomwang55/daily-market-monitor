# W1 · 交易日志 & 复盘系统（Trade Journal）

**状态**：✅ 已完成
**完成时间**：2026-07 上旬
**核心动机**：让"推送信号"和"实盘决策"能对得上，三个月后能算清"推的信号哪些赚哪些亏"。

---

## 1. 背景与目标

之前的 monitor 系统只是**推送**（早/中/晚 + 事件驱动），Steven 反馈：

> 一知半解，需要通过代码 + 实践互相验证。

要解决的问题：

1. 推送的信号里，**哪些真的转化成了下单动作？** —— 之前完全无法回溯
2. 那些下过的单，**最后是赚了还是亏了？** —— 全靠脑子记
3. 每周/每月能不能出一份**归因复盘**？ —— 之前没有

目标是搭一个"纸面交易日志 + 信号回溯 + 定期复盘"的最小闭环。

## 2. 需求与约束

- **不接真实券商**：纸面交易（paper trading）优先，不做真钱撮合
- **必须能关联到推送信号**：从 `signal_event`（monitor 层已有）反查
- **UTC naive 存库，Asia/Shanghai 展示**（继承项目一贯规范）
- **不写原生 DDL**：走 SQLAlchemy ORM
- **CLI 优先**：Steven 更习惯命令行，暂不做 UI

## 3. 数据模型（三张表）

### `paper_trade` —— 纸面持仓明细

一笔记录 = 一个完整持仓（开仓 + 可选平仓），字段见 `market_monitor/data/models.py:267`。

关键点：

| 字段              | 说明                                              |
| ----------------- | ------------------------------------------------- |
| `symbol`          | 标的代码（`sh600519` / `hk00700` / `159509` 都行）|
| `action`          | `long` / `short`（内地暂时只用 long）             |
| `strategy`        | `ah_arb` / `etf_disc` / `tobacco` / `manual`      |
| `entry_at/price/qty/reason` | 开仓四件套                              |
| `close_at/price/reason`     | 平仓（可空）                            |
| `stop_loss / take_profit`   | 主动风控位（可空）                      |
| `pnl / pnl_pct / hold_days` | 平仓后自动计算                          |
| `status`          | `open` / `closed`                                 |
| `signal_event_id` | 关联到触发这笔单的推送信号（可空）                |

索引：`status`, `strategy`, `entry_at`

### `trade_signal_link` —— 信号 ↔ 决策映射

```
signal_event ─┬─► trade_signal_link(decision=act,   paper_trade_id=1) ─► paper_trade(1)
              ├─► trade_signal_link(decision=skip)                     （看了但没动）
              └─► trade_signal_link(decision=noise)                    （判定为噪声）
```

一个信号可能触发多笔交易，也可能一笔都没有。**统计链路"信号→决策→盈亏"必须用它**。

### `trade_review` —— 周/月复盘归因

复合主键 `(period_type, period_key)`：

- `period_type ∈ {"week", "month"}`
- `period_key`  = `"2026-W27"` 或 `"2026-07"`

字段：`trade_count / win_count / loss_count / win_rate / total_pnl / avg_win / avg_loss / max_drawdown / best_trade_id / worst_trade_id / notes / generated_at`

## 4. 关键实现细节

### 4.1 UTC / Shanghai 转换

`market_monitor/data/repositories/trade_repo.py:1-22`

```python
SHANGHAI = timezone(timedelta(hours=8))

def _now_utc() -> datetime:
    return datetime.utcnow()          # naive UTC，直接存

def _to_shanghai(ts_utc: datetime) -> datetime:
    return ts_utc.replace(tzinfo=timezone.utc)\
                 .astimezone(SHANGHAI).replace(tzinfo=None)
```

**只在展示层转，DB 层永远 UTC naive**。

### 4.2 平仓自动算 P&L

`PaperTradeRepository.close_trade` 里，平仓时：

```python
pnl        = (close_price - entry_price) * qty       # long 方向
pnl_pct    = (close_price / entry_price - 1) * 100
hold_days  = (close_at.date() - entry_at.date()).days
status     = "closed"
```

Short 方向未启用（内地无融券细分）。

### 4.3 三个 Repository

`market_monitor/data/repositories/trade_repo.py`:

- `PaperTradeRepository`（line 23）—— 开仓 / 平仓 / 列表 / 更新止损
- `TradeSignalLinkRepository`（line 196）—— 信号回溯
- `TradeReviewRepository`（line 240）—— 复盘统计

所有 repo 都吃一个 `Session`，业务代码通过 `get_session()` 拿。

## 5. 接入位置

### CLI

```
market-monitor trade add    ── 开仓
market-monitor trade close  ── 平仓
market-monitor trade list   ── 列出当前持仓
market-monitor trade pnl    ── 总盈亏 / 胜率
market-monitor trade review ── 周/月复盘
```

（具体命令定义见 `market_monitor/cli.py` 中 `trade` 子命令）

### 报告尾部

`morning.py` / `evening.py` 尾部有轻量纸面持仓 P&L 摘要（不是复盘详情，只显示 open positions 数量 + 当日浮动盈亏）。

## 6. 已知问题 / 后续

- [ ] 尚未实现"信号 → 自动 skip 记录"，目前 `trade_signal_link.decision=skip` 需要人工输入
- [ ] `max_drawdown` 计算逻辑简化，只用日线最低点，未做 tick 级回撤
- [ ] W1 的复盘输出目前是纯文本，后续可考虑饼图/时间线图（依赖 W4 数据积累）

## 7. Review 建议路径

1. `market_monitor/data/models.py:267-380` —— 三张表模型
2. `market_monitor/data/repositories/trade_repo.py` —— CRUD + P&L 计算
3. `market_monitor/cli.py` —— trade 子命令实现
4. `market_monitor/monitors/morning.py` 和 `evening.py` —— 尾部 P&L 附注区块
