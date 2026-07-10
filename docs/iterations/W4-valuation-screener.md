# W4 · 指数估值分位监控 & 价值筛选器

**状态**：✅ Phase 1 已完成（2026-07-10）
**动机**：判断 A 股/港股当前是不是“便宜”，最有效的锚是**核心宽基指数的估值分位**（PE / PB / 股息率），而不是逐只股票的绝对估值。

---

## 1. 背景与目标

Steven 的路线图(`MEMORY.md` 中"迭代路线图")原始 W4 是**烟蒂股筛选器**:

> **W4 烟蒂股筛选器 v1**
> 条件:PB<0.7 + PE<10 + 股息>5% + 现金/市值>50% + 3 年 ROE>0
> 每周日跑,输出 Top 20 深度价值股

**中途遇到的问题**:

- akshare 没有便捷的个股批量估值接口
- 东财 spot 接口(`stock_zh_a_spot_em`)持续 429/断连
- 逐个股票查(`stock_value_em`)太慢,5000+ 只不可接受

**调整后的 W4 目标**(分两阶段):

### Phase 1(本迭代先做):核心宽基指数估值分位监控

- 每日快照:核心宽基/风格指数的 PE / PB / 股息率
- 计算历史分位(滚动 3 年 / 5 年 / 全历史)
- 分位极端时(≤ P20 / ≥ P80)标注信号
- 接入 morning / evening 报告尾部

### Phase 2(下个迭代):小池烟蒂股筛选器

- 用 **红利指数成分股**(50 只)作为候选池
- 通过 `stock_zh_index_value_csindex` 拿指数级估值,再逐只查候选股(数量可控)
- 输出 Top 20 深度价值股

Phase 2 单独开 W4.5 或 W5 迭代。

## 2. 需求与约束

- **数据源必须稳定**:放弃东财 spot(有连接问题)
- **必须能算历史分位**:至少 3 年样本
- **UTC naive 存库 + Asia/Shanghai 展示**
- **独立表**(沿用 W2/W3 风格)
- **不做全市场估值**:只跟踪核心指数

## 3. 数据源调研(Phase 1)

| 数据源                              | 覆盖范围                            | 历史长度   | 采纳?                       |
| ----------------------------------- | ----------------------------------- | ---------- | ---------------------------- |
| `stock_index_pe_lg(symbol='上证50')`| **只有** 上证50 / 沪深300 / 上证380 | 5000+ 天   | ✅ 长期分位主源              |
| `stock_index_pb_lg(...)`            | 同上                                | 5000+ 天   | ✅ 长期分位主源              |
| `stock_zh_index_value_csindex(symbol='000015')` | 几乎所有中证/上证指数(红利/中证500/中证1000/创业板等)| **只有 20 个交易日**(滚动) | ✅ 覆盖广度补充源 |
| `stock_a_all_pb`                    | 全 A 中位数(非成分股级)           | 5000+ 天   | ✅ 全市场情绪辅助信号        |
| `stock_a_gxl_lg(choice='上证A股')`  | 板块股息率(上证/深证/创业板/科创板)| 3000+ 天   | ✅ 股息率主源                |
| `stock_buffett_index_lg()`          | 巴菲特指数(总市值/GDP)            | 长         | 🟡 二期加,先不接            |
| `stock_market_pe_lg()`              | 全市场 PE                           | 长         | 🟡 类似 all_pb,暂不接        |

**放弃的方案**:

- `stock_zh_a_spot_em`:3 次重试均 `RemoteDisconnected`
- `stock_value_em`:单股查询,5000+ 只 rate limit 上做不完
- `stock_zh_a_spot`(新浪):无 PE/PB 字段

## 4. 覆盖清单(Phase 1)

### 4.1 长期分位组(LG 源,5000+ 天,主力)

| 指数    | 代号          | 用途                             |
| ------- | ------------- | -------------------------------- |
| 上证 50 | `sh000016`    | 大盘蓝筹估值基准                 |
| 沪深 300| `sh000300`    | A 股整体估值基准(**最常用**)   |
| 上证 380| `sh000009`    | 中盘蓝筹                         |

### 4.2 广度组(csindex 源,20 天滚动)

| 指数        | 代号     | 用途                        |
| ----------- | -------- | --------------------------- |
| 上证红利    | `000015` | 高股息 / 价值风格           |
| 上证 50     | `000016` | 与 LG 交叉验证              |
| 沪深 300    | `000300` | 同上                        |
| 中证 500    | `000905` | 中盘成长                    |
| 中证 1000   | `000852` | 小盘成长                    |

### 4.3 全市场辅助信号

| 指标          | 接口                            | 用途                     |
| ------------- | ------------------------------- | ------------------------ |
| 全 A 中位数 PB| `stock_a_all_pb`                | 极端情绪判断(<1.5 便宜)|
| 板块股息率    | `stock_a_gxl_lg(choice=...)`    | 上证/深证/创业板/科创板 |

## 5. 数据模型

### 独立表 `index_valuation_snapshot`

```sql
CREATE TABLE IF NOT EXISTS index_valuation_snapshot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            DATETIME NOT NULL,           -- UTC naive
    trade_date    DATE     NOT NULL,           -- Asia/Shanghai date
    symbol        TEXT     NOT NULL,           -- '000300' / 'sh000016' etc.
    name          TEXT,                        -- '沪深300'
    pe            REAL,                        -- 滚动市盈率
    pb            REAL,                        -- 市净率
    dividend_yield REAL,                       -- 股息率 %
    source        TEXT,                        -- 'lg' / 'csindex'
    UNIQUE(trade_date, symbol, source)
);
CREATE INDEX IF NOT EXISTS idx_index_val_symbol_date
    ON index_valuation_snapshot(symbol, trade_date);
```

**为什么 `source` 也进 UNIQUE**:同一天同一指数 LG 和 csindex 都会各写一份(口径略有差异),可交叉验证。

## 6. 算法 / 阈值

### 6.1 历史分位(核心)

对每个指数每个指标:

```
current_percentile = 当前值在历史里的排位百分比

percentile ≤ 20  → 🟢 极便宜(历史底部区)
percentile ≤ 40  → 🟢 便宜
percentile 40~60 → ⚪ 中性
percentile 60~80 → 🟡 贵
percentile ≥ 80  → 🔴 极贵(历史顶部区)
```

### 6.2 分位窗口

- **长窗口**:全历史(LG 源)
- **短窗口**:3 年 / 5 年(可选)

先都算,展示时优先 3 年(更贴近当前市场状态)。

### 6.3 交叉核实

同一天同一指数(如沪深 300)LG 与 csindex 都有数据 → 差异 > 10% 时告警(数据脏)。

### 6.4 罕见信号定义

- **极端便宜**:3 年分位 ≤ 10% 的指数(`_EXTREME_LOW = 10`)
- **极端贵**:3 年分位 ≥ 90% 的指数(`_EXTREME_HIGH = 90`)

## 7. 文件清单(计划)

| 文件                                                      | 作用                                  |
| --------------------------------------------------------- | ------------------------------------- |
| `market_monitor/core/index_valuation.py` (新增)           | 主模块                                |
| `market_monitor/monitors/evening.py` (改)                 | W3 后追加 W4 段                       |
| `market_monitor/monitors/morning.py` (改)                 | W3 后追加 W4 段                       |
| `docs/iterations/W4-valuation-screener.md`(本文档)      | 迭代设计                              |
| `market_monitor/cli.py`(可能改)                         | 可加 `valuation` 子命令,手动跑一次   |

## 8. 接入位置

同 W2 / W3,独立 try/except 包裹:

```
morning.py:
... 教学锦囊 ...
+ AH 溢价段(W2)
+ ETF 折溢价段(W3)
+ 指数估值分位段(W4)    ← 新增

evening.py:
... 地缘事件 ...
+ AH 溢价段(W2)
+ ETF 折溢价段(W3)
+ 指数估值分位段(W4)    ← 新增
... AI 分析 ...
```

## 9. 验证计划 & 实盘结果（2026-07-10）

### 端到端跑通

```bash
cd $PROJECT_ROOT
source .venv/bin/activate
python -c "from market_monitor.core import index_valuation as iv; \
  r = iv.fetch_and_snapshot(); print(iv.format_summary(r))"
```

输出：

```
【📊 指数估值分位快照】
───────────────────────────────────────────────────────────────
指数              PE      PE分位(3Y)      PB      PB分位(3Y)
上证50         11.39      🟡  83.3%    1.22      ⚪  63.5%
沪深300        13.78      🔴  95.2%    1.45      🟡  83.7%
上证380        27.14      🔴  97.7%    2.32      🔴  95.2%

─── 广度补充（无历史分位）───
  上证红利       PE=  9.76  股息率=5.09%
  上证50       PE= 14.55  股息率=3.48%
  沪深300      PE= 18.05  股息率=2.61%
  中证500      PE= 34.47  股息率=1.21%
  中证1000     PE= 37.08  股息率=0.99%

【⚠️ 指数估值极端信号（3 年分位）】
  · 沪深300 PE=13.78 PB=1.45 → pe_high=95.2%
  · 上证380 PE=27.14 PB=2.32 → pe_high=97.7% / pb_high=95.2%
```

### 快照落库验证

```sql
SELECT symbol, name, pe, pb, dividend_yield, source, trade_date
  FROM index_valuation_snapshot
  ORDER BY id DESC
  LIMIT 10;
```

→ 8 行，UNIQUE(trade_date, symbol, source) 去重生效。

### 已知 flaky 与处理

- **LG PE/PB 接口偶发 `NoneType.attrs`** → 已加 `_retry`（3 次递增退避）
- **上证50 双源 PE 差异 21.7%**（LG 11.39 vs csindex 14.55）→ 口径差异属于常态，阈值调为 30% + 日期同天才告警，免误报

## 10. 已知问题 / 后续（Phase 2 预告）

- [x] ✅ LG 接口重试封装
- [x] ✅ 交叉验证阈值从 10% 调到 30% 并限定同日
- [ ] LG 只覆盖 3 个指数是核心限制 —— Phase 2 可以考虑接雪球 API 补齐
- [ ] csindex 只有 20 天数据 → 每天写一次积累历史，跑够 250 天再启用分位（自动生效）
- [ ] 全 A PB（`stock_a_all_pb`）有 5000+ 天，可以接入全市场情绪信号（本迭代暂未接入，下一步 P2）
- [ ] Phase 2 烟蒂股筛选：
  - 候选池 = 上证红利成分股（50 只，`index_stock_cons_csindex(symbol='000015')`）
  - 对 50 只逐只查 `stock_value_em`（可承受）
  - 筛条件：PB<0.7 + PE<10 + 股息>5%
  - 加上「财报稳定性」（3 年 ROE > 0）需要 `stock_financial_analysis_indicator`

## 11. Review 建议路径

1. 本文档(背景 / 数据源调研 / 表结构 / 阈值)
2. `market_monitor/core/index_valuation.py`
3. `morning.py` / `evening.py` 中的 W4 段
4. 数据库:`sqlite3 data/market.db ".schema index_valuation_snapshot"`

## 12. 决策记录

| 决策                                                    | 理由                              |
| ------------------------------------------------------- | --------------------------------- |
| Phase 1 只做指数分位,不做个股筛选                      | akshare 无稳定批量个股估值接口    |
| LG 源 + csindex 源双源冗余                              | LG 覆盖窄但历史长,csindex 反之   |
| `source` 字段进 UNIQUE                                  | 允许双源同日共存 → 便于交叉验证   |
| 3 年分位为主展示                                        | 更贴近当前市场结构,减少久远失真  |
| 罕见信号阈值 P10 / P90(非 P20/P80)                    | 分位监控本身天然带梯度,罕见要更极端 |
