# 数据源 Gap 分析（2026-07-10）

**当前主用数据源**：akshare / 新浪实时 / 东财 spot（3 个）

**分析目标**：从新提供的 22 个免费接口清单里，挖掘可直接补进现有监控模块的高价值增量。

## 现有痛点 → 候选补救

| 现有模块 | 痛点 | 候选补救 API | 优先级 |
| -------- | ---- | ------------ | ------ |
| `bonds.py` / `bond_curve.py` | 美债收益率依赖 akshare（`bond_zh_us_rate`），稳定性一般 | **U.S. Treasury Data API**（官方，无 Key，日频） | ⭐⭐⭐ |
| `econ_calendar.py` | ForexFactory JSON 偶发 403；手工日历需人工维护 | **FRED API**（美国宏观全套时序，含 CPI/GDP/失业率） | ⭐⭐⭐ |
| `forex.py` / `fx_monitor.py` | 新浪 fx_susdcnh 偶发挂 | **Frankfurter**（无 Key，ECB 官方汇率聚合，日频） | ⭐⭐ |
| `sentiment.py` | VIX 从 akshare / 新浪，SKEW 从 akshare | **FRED**（VIXCLS/DGS10 等，长历史稳定） | ⭐⭐ |
| `bonds.py` | 中美利差监控，中国国债收益率也来自 akshare | 短期无好替代（TuShare Pro 需 Token） | ⭐ |
| `cigar_butt.py` | 美股/港股尚未支持烟蒂股筛选 | **FMP** 250 次/天可跑港股/美股基本面 | ⭐ |
| `geopolitics.py` | 依赖新闻聚合 | **Finnhub** 有 news + earnings 日历 | 观察 |
| `news_sources.py` | 目前仅 RSS/网页抓 | 同上 | 观察 |
| 加密货币 | 目前**没有**监控加密货币 | Steven 不做加密 → 暂缓 | - |

## 高价值增量：3 个即插即用的候选

### 🥇 U.S. Treasury Data（无 Key，日频）
- **接口**：`https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve`
- **提供**：美债 1M/3M/6M/1Y/2Y/5Y/10Y/20Y/30Y 完整曲线
- **接入位置**：`bonds.py` 里 `fetch_us_yields()` 加 fallback；akshare 挂时自动降级
- **成本**：0 Key，日更，官方源
- **价值**：**曲线倒挂检测**（当前 bonds.py 核心信号）稳定性 ⬆⬆

### 🥈 FRED API（需 Key，免费，30 秒申请）
- **接口**：`https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key=...`
- **提供**：
  - 通胀：CPIAUCSL、PCEPI、CPILFESL（核心 CPI）
  - 就业：UNRATE、PAYEMS
  - 增长：GDP、GDPC1
  - 利率：DFF（联邦基金利率）、DGS10
  - 情绪：**VIXCLS**（长历史 VIX 官方源）、UMCSENT（密歇根消费者信心）
  - 汇率：DEXCHUS、DEXUSEU
- **接入位置**：新建 `market_monitor/core/fred.py`，被 `econ_calendar.py`、`sentiment.py` 复用
- **价值**：宏观日历不再靠爬网页，长历史因子回测有权威源

### 🥉 Frankfurter（无 Key，即刻可用）
- **接口**：`https://api.frankfurter.dev/v1/latest?from=USD&to=CNY`
- **提供**：ECB 官方汇率（USD/EUR/CNY/JPY/GBP/HKD 等 30+ 对）
- **接入位置**：`forex.py` 主/备切换：Frankfurter 主，新浪备
- **价值**：ECB 官方源，比新浪 fx_susdcnh 更权威稳定

## 不推荐 / 已覆盖

- **AKShare/BaoStock/TuShare Pro**：AKShare 已用；BaoStock/TuShare 覆盖面重叠且 TuShare 要 Token
- **Alpha Vantage/Twelve Data/Finnhub/Polygon/FMP/Marketstack**：全球市场行情类，A 股当前场景覆盖不到，价值有限
- **CoinGecko/CoinPaprika/Binance/Kraken**：不做加密货币
- **SEC EDGAR**：美股财报解析，本地场景暂无美股基本面需求
- **World Bank / IMF / OECD / DBnomics / ECB**：SDMX 或 JSON-stat 结构复杂，短期收益低

## 落地建议

**本轮先做**：🥇 U.S. Treasury Data —— 无 Key、日频、结构清晰，直接给 `bonds.py` 加 fallback，最小改动最大价值。

**后续做**：
- FRED（需 Key 30 秒申请，Steven 决策后动）
- Frankfurter（bonds/treasury 落地稳定后接）

## 决策记录

- 2026-07-10：优先 U.S. Treasury，其余观察
