# W2 · AH 溢价套利监控

**状态**：✅ 已完成
**完成时间**：2026-07 上旬
**动机**：同一家公司 A/H 两地上市，价差反映情绪极端。历史上溢价率处于历史 P20 / P80 分位是均值回归的高概率时点。

---

## 1. 背景与目标

- A 股与 H 股同一家公司的股价差异叫 **AH 溢价率**：`(A股价 × 汇率) / H股价 - 1`
- **正值 = A 股比 H 股贵**（正常，因为内地流动性溢价 + 资本管制）
- 极端情况：
  - **> +40%（或 P80）** → A 股严重贵，H 股相对低估 → 若看好公司则买 H 股
  - **< 0%（或 P20，甚至负数）** → 罕见，A 股比 H 股便宜，可能是市场情绪极度悲观（内地不能做空 → 只做多 A 股）
- 内地投资者能操作的方向：
  - **A 股低估 → 买 A 股**（普通账户可交易）
  - **H 股低估 → 买 H 股 / 港股 ETF**（需港股通）
- 目标：每日盘中/盘后落库 20 只核心蓝筹 AH 对的溢价，罕见分位时推送。

## 2. 需求与约束

- **20 只核心蓝筹**：金融、能源、通信等大盘股（噪声小、成交活跃、汇率影响小）
- **实时数据**：新浪 hq.sinajs.cn（A股 + 港股 + USDCNH）
- **罕见信号必须交叉验证**：接一个二次数据源（akshare 腾讯的 `stock_zh_ah_spot`）
- **独立 SQLite 表**：不污染 `MarketSnapshot`，减少迁移风险
- **历史分位**：≥30 天样本切换到 P20/P80 动态阈值，否则用固定 40% / 0%

## 3. 数据源调研

| 数据源                           | 用途                    | 备注                             |
| -------------------------------- | ----------------------- | -------------------------------- |
| `hq.sinajs.cn`（新浪实时）       | A股 + H股 + USDCNH 汇率 | 主源，一次拉 20 只 + 汇率        |
| `akshare.stock_zh_ah_spot`（腾讯）| 交叉验证                | 只在**罕见信号**触发（A 股折价） |

**放弃的方案**：

- 东财 AH 接口 `stock_zh_ah_spot_em`：字段口径不稳，且部分标的名称不匹配
- 只用新浪单源：罕见分位（A 股折价）需要防止数据脏

## 4. 数据模型

### 独立表 `ah_premium_snapshot`

在 `market_monitor/core/ah_premium.py::_init_snapshot_table()` 中幂等创建：

```sql
CREATE TABLE IF NOT EXISTS ah_premium_snapshot (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         DATETIME NOT NULL,           -- UTC naive
    trade_date DATE NOT NULL,               -- Asia/Shanghai date
    a_code     TEXT NOT NULL,
    hk_code    TEXT NOT NULL,
    name       TEXT,
    sector     TEXT,
    a_price    REAL,
    h_price    REAL,
    hkd_cny    REAL,
    premium    REAL,                        -- 百分比 e.g. 42.3
    UNIQUE(trade_date, a_code)
);
CREATE INDEX IF NOT EXISTS idx_ah_a_code_date
    ON ah_premium_snapshot(a_code, trade_date);
```

**UNIQUE(trade_date, a_code)** 保证一天一只一条，重复写自动 IGNORE。

## 5. 算法 / 阈值

### 5.1 溢价率计算

```python
hkd_cny = get_usdcnh() / usd_hkd            # 约 0.93 附近
premium = (a_price / (h_price * hkd_cny) - 1) * 100
```

汇率拿不到时降级到 `_DEFAULT_HKD_CNY = 0.93`。

### 5.2 分位数阈值

- 常量：`_HIST_MIN_SAMPLES=30`, `_HIST_WINDOW_DAYS=250`, `_PERCENTILE_LOW=20`, `_PERCENTILE_HIGH=80`
- 样本不够 30 天 → 用固定阈值：`>40%` H 股低估、`<0%` A 股低估
- 样本足 → 用 P20 / P80 动态阈值（每个 A 股独立算自己的分布）

### 5.3 罕见信号交叉核实

只在 **A 股折价（premium < 0，也就是 A 股比 H 股便宜的极端情况）** 时触发：

```python
sina_premium ↔ akshare_tencent_premium
差异 < 2%   → 一致，信号可信
差异 ≥ 2%   → 数据源冲突，标注 ⚠️ 待复核
```

（正常 H 股低估不做交叉，因为常态出现，数据源基本一致）

## 6. 文件清单

| 文件                                                             | 作用                                    |
| ---------------------------------------------------------------- | --------------------------------------- |
| `market_monitor/core/ah_premium.py`（544 行）                    | 主模块                                  |
| `market_monitor/monitors/evening.py`（改）                       | 地缘事件后、AI 分析前插入 AH 溢价段     |
| `market_monitor/monitors/morning.py`（改）                       | 教学锦囊后插入 AH 溢价段                |

### `ah_premium.py` 关键函数

- `fetch_ah_premium()` —— 主入口：拉数据 + 落库 + 分位判定 → 返回 dataframe
- `CORE_AH_PAIRS` —— 20 只精选蓝筹清单（写死）
- `get_signals(df)` —— 判定 H 股低估 / A 股低估 / 无信号
- `format_summary(df)` —— 完整表格文本
- `format_signals(signals, df)` —— 只输出有信号的行 + 分位依据
- `_save_snapshot(df)` —— 写入 `ah_premium_snapshot`
- `_get_hist_percentiles(a_code)` —— 取该股 P20/P80
- `_cross_check_akshare(a_code, sina_premium)` —— 罕见信号交叉核实
- `_calc_current_percentile(a_code, current)` —— 当前值在历史里的百分位

## 7. 接入位置

### evening.py（盘后 17:00）

```
... 地缘事件段 ...
+ AH 溢价段（W2）      ← 独立 try/except
... AI 分析 ...
```

### morning.py（早盘 07:00）

```
... 教学锦囊 ...
+ AH 溢价段（W2）      ← 独立 try/except
+ ETF 折溢价段（W3）
```

## 8. 测试与验证

### 2026-07-10 实盘信号（12:50 抓取）

**H 股低估 4 只**（应看好则买 H 股）：

| 名称     | A股     | H股     | 溢价率 |
| -------- | ------- | ------- | ------ |
| 中国人寿 | ...     | ...     | +51%   |
| 中国电信 | ...     | ...     | +44%   |
| 建设银行 | ...     | ...     | +42%   |
| 华泰证券 | ...     | ...     | +42%   |

**A 股低估 2 只**（罕见！已触发交叉核实）：

| 名称     | 溢价率 | 交叉核实   |
| -------- | ------ | ---------- |
| 中国联通 | -23%   | ✅ 一致    |
| 招商银行 | -7%    | ✅ 一致    |

**快照落库**：20 条 → `ah_premium_snapshot`，UNIQUE 去重生效

## 9. 已知问题 / 后续

- [ ] `CORE_AH_PAIRS` 目前只覆盖 20 只，可后续扩到 50 只
- [ ] 汇率降级到 `0.93` 时应打日志（当前只是静默 fallback）
- [ ] 历史分位需要 30 天样本才能生效 —— 目前跑了 1-2 天，仍在用固定阈值
- [ ] 未来可加"分位 + 环比"复合判定，减少震荡分位区的噪声

## 10. Review 建议路径

1. `market_monitor/core/ah_premium.py`（自顶向下）：
   - `CORE_AH_PAIRS` → `fetch_ah_premium()` → `_save_snapshot()` → `get_signals()` → `format_*()`
2. `market_monitor/monitors/evening.py` —— 找 `import ah_premium as ah` 附近
3. `market_monitor/monitors/morning.py` —— 找教学锦囊后的 `try: ah.fetch_ah_premium()`
4. `ah_premium_snapshot` 表：可 `sqlite3 data/market.db ".schema ah_premium_snapshot"`
