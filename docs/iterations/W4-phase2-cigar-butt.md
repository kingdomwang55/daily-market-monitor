# W4 Phase 2 · 烟蒂股筛选器（Cigar-butt Screener）

**状态**：✅ 已交付（2026-07-10 收尾）
**动机**：Phase 1 只解决了"整体贵不贵"（指数分位），Phase 2 要解决"具体买啥"——从**已知低估值池**里挑深度价值股。
**依赖**：W4 Phase 1（指数估值分位）已完成

---

## 1. 背景与目标

**烟蒂股（Cigar-butt Stock）**：格雷厄姆经典策略，找那些"没人要但还能吸一口"的股票——市场极度低估、有安全边际、有稳定现金流。

Phase 1 输出了 **"A 股整体在 3 年高位区"** 的判断（沪深 300 PE 95.2%），但这不意味着**每一只**股票都贵。**结构性机会**恰恰在于：
- 大盘整体贵 → 但**红利/价值风格**（上证红利指数）本身 PE 仅 9.76、股息率 5.09%
- 从这个池子里逐只筛选，能找到"整体行情高热但被冷落的价值股"

### 目标产出

**每周日跑一次**，输出 **Top N 深度价值股清单**：

```
【🚬 烟蒂股筛选（2026-07-13）】
共 13 只符合条件（PB<0.7 + PE<10 + 分红次数≥5 + 3年ROE>0）

排名  代码    名称      PB    PE    分红次数  ROE(3Y均)  评分
 1   600015 华夏银行  0.34  3.98  25        7.6%       78.7
 2   601818 光大银行  0.36  4.78  16        7.5%       68.2
 ...
```

## 2. 需求与约束

| 项 | 要求 |
| --- | --- |
| 候选池 | 上证红利指数（000015）50 只成分股 |
| 数据源 | akshare（延续项目风格） |
| 频率 | 每周日跑一次（数据变动慢，无需高频） |
| 存储 | 独立 SQLite 表 `cigar_butt_screening`，历史可回溯 |
| 展示 | 独立 CLI 命令 + 周度报告推送 |
| 时区 | UTC naive 存 + Asia/Shanghai 展示（沿用规范） |

## 3. 数据源调研

### 3.1 候选池：`ak.index_stock_cons_csindex(symbol='000015')`

已验证：返回 50 行 × 9 列，含成分股代码、名称、交易所等。

### 3.2 个股估值：`ak.stock_value_em(symbol='...')`

已验证：返回 2000+ 行 × 13 列，含 `PE(TTM)`、`PE(静)`、`市净率`、`总市值`、`流通市值`、`市销率`。取最新一行即可。

### 3.3 财务指标：`ak.stock_financial_analysis_indicator(symbol='...', start_year='2022')`

已验证：返回 16 行 × 86 列。**ROE 列名 = `净资产收益率(%)`**。筛年报（12-31 结束）取近 3 年均值。

### 3.4 ⚠️ 股息率数据源踩坑记录（重要）

**尝试过的方案（均失败）**：

| 数据源 | 错误 |
| ------ | ---- |
| `ak.stock_individual_basic_info_xq(symbol='SH600015')` | 抛 `KeyError: 'data'` |
| `ak.stock_individual_info_em(symbol='600015')` | `http.client.RemoteDisconnected` |
| `ak.stock_history_dividend()` 的 `年均股息` 字段 | 单位不明。华夏银行 `年均股息=3.3` / 股价 6.78 = 48.67% → 明显不对 |

**降级方案（务实）**：
- **改用「累计分红次数 ≥ 5 + 近 1 年有过分红」作为分红能力代理指标**
- 逻辑：能稳定分红 5 次以上说明**有分红能力和意愿**，是价值股的必要（虽非充分）条件
- 缺点：不知道具体股息率数字（不能筛"> 5%"）
- 优点：数据源稳（`ak.stock_history_dividend()` 返回 5675 行全量），逻辑简单可解释

**未来 TODO**（DS-2 或后续迭代）：
- 尝试 zzshare 或雪球爬虫拿真实 TTM 股息率
- 或按 `(近 1 年分红总额 × 送转前股数) / 市值` 手工估算

## 4. 筛选逻辑

### 4.1 硬门槛（同时满足）

| 条件 | 数值 | 含义 |
| --- | --- | --- |
| **PB < 0.7** | 市净率极低 | 破净，账面价值大于市值 |
| **PE > 0 AND PE < 10** | 市盈率低且盈利 | 排除亏损股（PE≤0） |
| **累计分红次数 ≥ 5** | 长期分红能力 | 代理指标（见 3.4） |
| **3 年 ROE 均值 > 0** | 稳定盈利 | 不是垃圾股（避免"低估值陷阱"） |

**PE > 0 硬门槛**：修 bug 后加入。旧版会漏进 3 只负 PE 的煤炭/建材（如兰花科创、开滦股份、建发股份），负 PE 本身就等于亏损，与烟蒂股定义相悖。

### 4.2 排名评分（加权 0-100）

```python
score = 0.30 × norm(分红次数, 5-20)         # 分红意愿越强越好
      + 0.25 × norm(1/PB, 1.5-3)            # PB 越低越好
      + 0.20 × norm(ROE均值, 0-20%)         # ROE 越高越好
      + 0.15 × norm(1/PE, 0.1-0.3)          # PE 越低越好
      + 0.10 × norm(市值, 100亿-2000亿)     # 大市值加分（稳定）
```

其中 `norm(x, a, b) = clip((x-a)/(b-a), 0, 1)` × 100。

**权重设计说明**：
- 分红次数占 30%（最高）：稳定分红是烟蒂股核心特征
- PB 占 25%：低估值是硬指标
- ROE + PE + 市值 依次递减，防止单一指标失真

### 4.3 罕见 / 特殊情况

- **PB < 0.4**：极端破净警示。**区分行业**：
  - 银行股（`_BANK_SYMBOLS` 白名单 40 只）：文案 = `ℹ️ 银行股深度破净（行业常态）`
  - 一般行业：文案 = `⚠️ 非银行股极端破净 - 复核暂停上市/退市风险`
- **累计分红次数 > 30**：老牌蓝筹加分（评分逻辑自然处理，无需特殊标记）

## 5. 表结构

### 5.1 `cigar_butt_screening` 主表

```sql
CREATE TABLE IF NOT EXISTS cigar_butt_screening (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_ts      DATETIME NOT NULL,           -- UTC naive
    run_date    DATE     NOT NULL,           -- Asia/Shanghai
    pool        TEXT     NOT NULL,           -- 'sse_dividend' 等
    symbol      TEXT     NOT NULL,           -- '600519' 等
    name        TEXT,
    pb          REAL,
    pe          REAL,
    dividend_count INTEGER,                  -- 累计分红次数（代理股息率）
    roe_3y_avg  REAL,
    market_cap  REAL,                        -- 亿元
    passed      BOOLEAN NOT NULL,            -- 是否通过硬门槛
    score       REAL,                        -- 未通过为 NULL
    reason      TEXT,                        -- 未通过时的原因
    UNIQUE(run_date, pool, symbol)
);
CREATE INDEX idx_screening_run_date ON cigar_butt_screening(run_date);
CREATE INDEX idx_screening_symbol   ON cigar_butt_screening(symbol);
```

**写入策略**：**`INSERT OR REPLACE`**（同一天重跑覆盖旧数据，保证一致性）。

**注意**：把**所有**候选股（含未通过）都写入，方便回看"哪些一直卡在门槛边缘"。

## 6. 文件清单

| 文件 | 作用 | 状态 |
| --- | --- | --- |
| `market_monitor/core/cigar_butt.py` | 主模块（12528 bytes） | ✅ |
| `market_monitor/cli.py` | 加 `screen` 子命令（`cmd_screen`） | ✅ |
| `market_monitor/monitors/weekly_screener.py` | 周度独立 monitor | ⏸️ 视效果决定 |
| `~/Library/LaunchAgents/com.market-monitor.weekly-screener.plist` | 每周日 08:00 触发 | ⏸️ 视效果决定 |

**⏸️ 未做说明**：`weekly_screener.py` + launchd 暂缓。原因：CLI (`python -m market_monitor.cli screen --send`) 已能满足周度手动跑的需求，Steven 先手工用一段时间再决定是否需要自动化。

## 7. 接入位置

- **独立 monitor**：**不接入** morning/evening（数据变动慢，插进去会稀释注意力）
- **CLI 手动**：`python -m market_monitor.cli screen [--pool sse_dividend] [--top 20] [--send]`
- **未来自动化**：若手动使用 4-8 周后觉得有价值，再补 `weekly_screener.py` + launchd 每周日 08:00

## 8. 决策记录

| 决策 | 理由 |
| --- | --- |
| 只跟踪上证红利池，不跑全 A | 全 A 5000+ 只逐个查不现实，红利池已经是"官方精选低估值" |
| 未通过股也写库 | 便于回看临界股，未来可挖掘"接近通过"的候选 |
| 加权评分不是简单排序 | 单一指标（如分红次数）容易被特殊情况误导 |
| 周度而非日度 | 财务数据季度更新，日频跑没意义 |
| 独立 monitor 不塞报告 | 内容偏静态，塞进 morning/evening 增加噪音 |
| **股息率降级为分红次数** | 3 个精确数据源均失败，务实选择可靠代理指标 |
| **PE > 0 硬门槛** | 负 PE = 亏损，与烟蒂股定义相悖 |
| **INSERT OR REPLACE** | 同日重跑覆盖旧数据，保证 DB 与最新 in-memory 结果一致 |
| **银行股 PB<0.4 警示分行业** | 40 只 A 股主要银行内置白名单，避免误报 |
| `weekly_screener.py` + launchd 暂缓 | CLI 已够用，先手动跑观察效果 |

## 9. 已知风险与限制

- ✅ `stock_value_em` 单只 2000+ 行 × 50 只：稍慢但可承受（sleep 0.4s 避限流）
- ✅ `stock_financial_analysis_indicator` 拉 3 年数据比较慢，全跑 5-6 分钟
- ⚠️ **股息率是"代理指标"而非精确值**：分红次数≥5 不代表股息率一定 >5%（见 3.4）
- ⚠️ **50 只全银行的极端结果**：当前市场周期使然，如果全 A 都不便宜，"红利池 + 深度价值"必然聚焦到银行
- ⚠️ **未加港股/美股**：Phase 2 仅 A 股，港股银行（工行 H）估值更低但没纳入

## 10. 测试计划与结果

### 10.1 测试计划

- [x] `ak.index_stock_cons_csindex('000015')` 返回 50 只成分股
- [x] `ak.stock_value_em` 单只 API 稳定性（重试 2 次容错）
- [x] `ak.stock_financial_analysis_indicator` 拉 3 年 ROE 均值
- [x] 50 只完整跑通耗时（目标 < 8 分钟）
- [x] 至少 1 只通过硬门槛（如全不通过说明门槛太严或市场无烟蒂）
- [x] 快照落库 + UNIQUE 去重
- [x] INSERT OR REPLACE 幂等验证
- [x] CLI 端到端 `python -m market_monitor.cli screen`

### 10.2 实盘结果（2026-07-10 跑，基准日 2026-07-09）

**共 13/50 通过硬门槛**（PE 修复前是 16，修 bug 后过滤掉 3 只负 PE）：

| 排名 | 代码 | 名称 | PB | PE | 分红次数 | ROE(3Y) | 评分 |
| --- | ---- | ---- | --- | --- | --- | --- | --- |
| 1 | 600015 | 华夏银行 | 0.34 | 3.98 | 25 | 7.6% | 78.7 |
| 2 | 601818 | 光大银行 | 0.36 | 4.78 | 16 | 7.5% | 68.2 |
| 3 | 601166 | 兴业银行 | 0.44 | 4.73 | 19 | 9.0% | 68.1 |
| 4 | 601169 | 北京银行 | 0.37 | 5.05 | 19 | 6.8% | 67.7 |
| 5 | 601328 | 交通银行 | 0.50 | 6.06 | 22 | 8.1% | 61.2 |
| 6 | 601998 | 中信银行 | 0.54 | 5.59 | 18 | 8.8% | 56.9 |
| 7 | 601398 | 工商银行 | 0.66 | 7.04 | 20 | 9.2% | 52.5 |
| 8 | 601988 | 中国银行 | 0.68 | 7.61 | 20 | 8.4% | 50.8 |
| 9 | 601009 | 南京银行 | 0.70 | 5.90 | 19 | 10.7% | 50.3 |
| 10 | 601229 | 上海银行 | 0.50 | 5.22 | 10 | 9.4% | 40.6 |
| 11 | 601916 | 浙商银行 | 0.41 | 5.82 | 5 | 7.4% | 31.7 |
| 12 | 601077 | 渝农商行 | 0.53 | 5.81 | 7 | 8.8% | 28.2 |
| 13 | 601825 | 沪农商行 | 0.56 | 5.99 | 7 | 10.1% | 27.2 |

**极端破净警示**（`ℹ️ 银行股深度破净，行业常态`）：
- 600015 (PB 0.34)、601818 (0.36)、601169 (0.37)

**发现**：
- ✅ **13/50 = 26%**：门槛严格度合理（既不空手也不过多）
- ✅ **全部银行**：真实市场画像。当前 A 股 3 年高位区间，红利池深度价值集中在银行
- ⚠️ **PE 修复前混入的 3 只**（兰花科创、开滦股份、建发股份）：负 PE 意味亏损，与烟蒂股定义相悖，应排除

### 10.3 修复的 bug

- **BUG-1**：PE ≤ 0 未排除 → 3 只负 PE 混入 → 加硬门槛 `PE > 0`
- **BUG-2**：INSERT OR IGNORE 导致同日重跑旧数据不覆盖 → 改 INSERT OR REPLACE
- **BUG-3**：银行股 PB<0.4 全部报警 → 加银行白名单分行业文案

## 11. Review 建议路径

**给外部 code reviewer（Claude Code / Codex / Cursor）**：

### 优先审查

1. **`market_monitor/core/cigar_butt.py`**（主模块 12528 bytes）
   - `_check_hard_gate()` 硬门槛逻辑是否完备
   - `_compute_score()` 评分权重是否合理
   - `fetch_dividend_info()` 分红次数代理指标是否合理（见 §3.4）
   - `_BANK_SYMBOLS` 白名单是否覆盖当前上证红利成分（40 只是否够用）

2. **数据源健壮性**
   - `_retry()` 重试 2 次是否够（akshare 网络抖动概率）
   - `_SLEEP_BETWEEN_STOCKS = 0.4s` 是否会被 API 限流
   - `stock_history_dividend` 全量拉一次 5675 行的内存占用

3. **SQL 表设计**
   - UNIQUE(run_date, pool, symbol) + INSERT OR REPLACE 语义是否正确
   - `passed BOOLEAN` vs `passed INTEGER` 在 SQLite 下等价，但读代码时需知道

### 关注点

- ✅ 时区：UTC naive 存 + Shanghai 展示（沿用项目规范）
- ✅ 幂等：同一天多次跑结果一致（REPLACE 覆盖）
- ✅ 独立表：不污染 `MarketSnapshot` 主表
- ⚠️ **股息率是代理指标**：不要误以为拿到的是真实股息率数字
- ⚠️ **50 只全银行的结果**是市场周期使然，不是 bug

### 建议改进方向（Phase 3 或后续）

- [ ] 引入雪球或 zzshare 拿真实 TTM 股息率
- [ ] 扩展候选池：中证红利（000922）、深证红利（399324）
- [ ] 加入港股：恒生 H 股金融指数（HSCEIF）成分
- [ ] `weekly_screener.py` 独立 monitor + launchd 周日 08:00 触发（视手动使用效果决定）
- [ ] 加入更多可解释信号：连续分红年数、最近 3 年 EPS 增速、货币资金/市值比

### 测试建议

- 单元测试：`_norm()`、`_compute_score()`、`_check_hard_gate()` 纯函数易测
- 集成测试：mock `ak.stock_value_em` 等 akshare 接口，跑一遍全流程
- 数据回归：将来跑几周后做纵向对比（分红次数应递增，PB/PE 应有波动）
