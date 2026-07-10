# W3 · ETF 折溢价监控

**状态**：✅ 已完成
**完成时间**：2026-07-10
**动机**：QDII / 跨境 / 商品 ETF 因额度限制、场外套利受限，价格常偏离 IOPV（净值估值），是短期均值回归的机会。

---

## 1. 背景与目标

**IOPV**（Indicative Optimized Portfolio Value）= 基金实时估值，即"这只 ETF 现在应该值多少钱"。

- **溢价率 = 市价 / IOPV - 1**
  - `>0`：市价比净值贵（追高危险）
  - `<0`：市价比净值便宜（潜在买点）
- QDII/跨境 ETF（如纳指、日经、恒生）常见溢价原因：**QDII 额度限制**、**海外市场闭市**、**T+0 套利受限**
- 商品 ETF（黄金、原油）：**期货移仓、跨境审批**

**要解决的问题**：

1. 每日/盘中扫一遍核心 ETF，标注哪些溢价异常
2. 罕见信号（|溢价率| > 5%）时**交叉核实**：是标的性因素（合理）还是数据脏（不可信）
3. 累积历史分位数，动态判定"当下溢价率在自己历史里位于什么位置"

## 2. 需求与约束

- **只跟踪核心白名单**：21 只 QDII / 跨境 / 商品 ETF（全市场 1543 只 ETF 会淹没在噪声里）
- **数据源**：东财 `akshare.fund_etf_spot_em`（含 IOPV 实时估值）
- **符号翻转**：东财原字段叫「基金折价率 = (IOPV - 价) / IOPV」，改成「溢价率 = 价/IOPV - 1」，正数=贵，直观
- **交叉核实策略特殊**：不是二次数据源，而是**同板块 peers 均值比对**——因为东财 IOPV 本身已是权威源，问题在于"这只是不是与同类一致"

## 3. 数据源调研

| 数据源                        | 结果                                                  |
| ----------------------------- | ----------------------------------------------------- |
| `akshare.fund_etf_spot_em`    | ✅ 采用。1543 只 ETF 一次拉全，含最新价 + IOPV + 折价率 |
| `fund_etf_hist_em`            | 只用于历史行情，非当前 IOPV                           |
| `fund_etf_category_sina/ths`  | 无 IOPV                                               |
| 自建 NAV 计算                 | ❌ 太复杂，且实盘 IOPV 已由东财提供                    |

`df.shape = (1543, 37)`，字段含「代码」「名称」「最新价」「IOPV实时估值」「基金折价率」等。

## 4. 数据模型

### 独立表 `etf_premium_snapshot`

`market_monitor/core/etf_premium.py::_init_snapshot_table()`：

```sql
CREATE TABLE IF NOT EXISTS etf_premium_snapshot (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         DATETIME NOT NULL,
    trade_date DATE NOT NULL,
    code       TEXT NOT NULL,
    name       TEXT,
    sector     TEXT,          -- us_tech / hk_hs / jp_nk / gold / oil / soybean / metal ...
    price      REAL,
    iopv       REAL,
    premium    REAL,          -- 百分比 e.g. 15.95
    UNIQUE(trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_etf_code_date
    ON etf_premium_snapshot(code, trade_date);
```

## 5. 算法 / 阈值

### 5.1 CORE_ETFS 白名单（21 只）

按板块（`sector`）分组，覆盖：

- **美股**：纳指（多只）、标普 500、美国 50
- **港股**：恒生、恒生科技、恒生医疗
- **日股**：日经 225
- **欧股**：德国 30 / 法国 CAC
- **商品**：黄金 ETF、豆粕 ETF、有色 ETF、原油 LOF
- **主题**：中概互联、纳指科技华夏

具体清单见 `CORE_ETFS` 常量。

### 5.2 分级阈值（固定基线）

| 状态             | 溢价率区间 | 说明                          |
| ---------------- | ---------- | ----------------------------- |
| 🔴 拒追高        | `>= +3%`   | 场内价明显偏贵，等回归        |
| 🟡 观察          | `>= +1%`   | 温和溢价，别急着上车          |
| 🟢 折价买入      | `<= -1%`   | 场内比 IOPV 便宜，均值回归买入 |
| ⚪ 正常          | 其它       | 无操作                        |

常量：`_HIGH_PREMIUM=3.0`, `_WARN_PREMIUM=1.0`, `_DISCOUNT_BUY=-1.0`

### 5.3 分位数阈值（同 W2）

`_HIST_MIN_SAMPLES=30`, `_HIST_WINDOW_DAYS=250`, `_PERCENTILE_LOW=20`, `_PERCENTILE_HIGH=80`

≥30 天样本 → 切换 P20/P80。

### 5.4 罕见信号交叉核实（`|premium| > 5%`）

**特殊设计**：不接二次数据源，而是**同板块 peers 均值比对**。

```
异常 ETF premium = X%
同 sector 其它 ETF premium 均值 = Y%
|X - Y| < 2%  → ✅ 标的性因素（比如整个板块都被限购）
|X - Y| >= 2% → ⚠️ 个别异常，建议人工复核
```

常量：`_RARE_THRESHOLD=5.0`

**实盘举例**（2026-07-10）：

- 纳指科技华夏 (159509) **+15.95%** vs 同板块 peers 均值 **+5.41%**
  → 差异 10.5%，**⚠️ 个别异常**（该 ETF 长期限购，普通投资者只能场内买 → 溢价高企）
- 纳指 ETF **+7.4~7.8%** vs peers 均值一致 → ✅ 标的性因素（QDII 额度整体紧张）
- 日经 225 ETF **+7.05%** vs peers 一致 → ✅ 同上

## 6. 文件清单

| 文件                                                     | 作用                                     |
| -------------------------------------------------------- | ---------------------------------------- |
| `market_monitor/core/etf_premium.py`（386 行）           | 主模块                                   |
| `market_monitor/monitors/evening.py`（改）               | W2 (AH) 后追加 W3 (ETF) 段，独立 try/except |
| `market_monitor/monitors/morning.py`（改）               | 教学锦囊后，W2 后追加 W3 段              |

### `etf_premium.py` 关键函数

- `fetch_etf_premium()` —— 主入口
- `CORE_ETFS` —— 21 只 ETF 白名单
- `get_signals(df)` —— 判定信号（拒追高/观察/折价/正常）
- `format_summary(df)` / `format_signals(signals, df)`
- `_save_snapshot(df)`
- `_get_hist_percentiles(code)`
- `_cross_check_sector_peers(df, code, sector)` —— peers 均值对比
- `_init_snapshot_table()`

## 7. 接入位置

### evening.py

```
... 地缘事件 ...
+ AH 溢价段（W2）
+ ETF 折溢价段（W3）    ← 新增
... AI 分析 ...
```

### morning.py

```
... 教学锦囊 ...
+ AH 溢价段（W2）
+ ETF 折溢价段（W3）    ← 新增
```

两处都用独立 `try/except` 包裹，任何一个模块崩不影响其它段。

## 8. 测试与验证

### 端到端跑通

```bash
cd $PROJECT_ROOT
source .venv/bin/activate
python -c "from market_monitor.core import etf_premium as etf; df=etf.fetch_etf_premium(); print(etf.format_signals(etf.get_signals(df), df))"
```

### 语法检查

`morning + evening OK`（AST 通过）

### 2026-07-10 输出摘要

- **🔴 拒追高**：纳指科技华夏 (159509) +15.95% ⚠️ 个别异常
- **🔴 拒追高**：纳指 ETF 系列 +7.4~7.8%（peers 一致，标的性因素）
- **🔴 拒追高**：日经 225 +7.05%（peers 一致）

## 9. 已知问题 / 后续

- [ ] LOF 品种（162411 华宝油气LOF、161129 南方原油LOF）已在清单但 IOPV 字段可能为空 —— 需运行几天验证
- [ ] 历史分位需要 30 天样本才能生效
- [ ] 21 只清单较小，后续可根据实盘信号频次动态扩展
- [ ] `_cross_check_sector_peers` 目前用简单均值，可以升级为中位数（更抗单个异常值）
- [ ] 可考虑加入"折价买入"事件驱动推送（当前仅在早晚报告出现）

## 10. Review 建议路径

1. `market_monitor/core/etf_premium.py`：
   - `CORE_ETFS` 白名单 →
   - `fetch_etf_premium()`（拉数据 + 落库） →
   - `get_signals()`（阈值 + 分位） →
   - `_cross_check_sector_peers()`（peers 比对，这里是本 W3 最"新"的设计） →
   - `format_*()`（面向报告的展示层）
2. `evening.py` / `morning.py` 中的 `import etf_premium as etf` 附近段
3. `etf_premium_snapshot` 表 schema：`sqlite3 data/market.db ".schema etf_premium_snapshot"`
