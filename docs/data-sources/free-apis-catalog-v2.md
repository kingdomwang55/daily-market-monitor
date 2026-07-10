# 免费金融数据接口清单 v2

**来源**：Steven 于 2026-07-10 16:01 GMT+8 提供（第二批）
**用途**：market-monitor 数据源选型参考补充

## 完整清单

| 接口名称 | 主要覆盖资产 | 免费额度/限制 | 协议与特点 | 适合场景 |
| :--- | :--- | :--- | :--- | :--- |
| **AllTick** | 全球股票、外汇、加密货币、贵金属等全品类 | **永久免费**基础调用，无每日上限；注册有7天全功能试用 | REST + WebSocket，延迟<180ms | **实时行情监控**、量化交易、多资产 |
| **Alpha Vantage** | 全球股票、外汇、加密货币、技术指标 | 每日 500 次或每分钟 5 次 | 仅 REST，**数分钟延迟** | 学术研究、低频回测 |
| **Finnhub** | 美股为主，覆盖全球股票、外汇、加密货币 | 每分钟 60 次，WS 限 50 标的 | REST + 基础 WS，延迟 2-5s | 欧美市场分析、基本面数据 |
| **Yahoo Finance (yfinance)** | 全球股票、外汇、期权、期货、基金 | **完全免费**，非官方（爬虫） | Python 库，延迟 10-30s，不稳定 | 历史数据回测、个人学习 |
| **Tushare** | 国内**最全面**：A股/港股/美股/期货/基金/宏观 | 免费但需积分，高级数据付费 | Python 包，数据规范 | 国内量化投资、丰富财经数据 |
| **iTick** | 全球股票（含 A/H/美）、外汇、加密货币、期货 | 永久免费基础行情 | REST + WebSocket，延迟<50ms | 跨市场、低延迟开发者 |
| **Polygon.io** | 美股、加密货币为主 | **免费版额度极低**，WS 需付费 | REST + 高性能 WS，延迟<20ms | 专业美股高频（免费版限制大） |
| **新浪财经 API** | A股、港股实时行情（**15 分钟延迟**） | 完全免费 | HTTP 接口简单 | 个人投资者、教育项目 |
| **BaoStock** | 中国 A 股：历史行情、财务、宏观 | 完全免费开源 | Python 库，返回 DataFrame | A 股历史数据 |
| **AKShare** | 覆盖**国内最广**：股票、期货、基金、宏观、数字货币 | 完全免费开源 | Python 库，数据源多样 | 需丰富数据源的量化研究 |
| **Ashare** | 中国 A 股实时行情 | 完全免费 | Python 库，**双源自动切换**（新浪、腾讯） | 极简 A 股实时行情 |
| **zzshare** | **A 股量化数据**：行情、龙虎榜、情绪 40+ 接口 | 免费，注册 Token 提频 | Python SDK | A 股量化策略、特色数据 |
| **FRED** | **宏观经济数据**（GDP、CPI、利率等） | 完全免费 | API | 宏观分析 |
| **Fixer** | 外汇汇率，160+ 货币 | 每日 500 次 | API | 跨境电商、汇率换算 |

## Gap 分析

**当前 market-monitor 使用中**：akshare、新浪、东财、Yahoo Finance、U.S. Treasury（今日新增）

### 与第一批（v1）对比重叠

以下已在 v1 清单中分析：Alpha Vantage、Finnhub、Polygon、Tushare、BaoStock、AKShare、FRED、Frankfurter

### 新出现的接口

| 接口 | 独特价值 | 我的评估 |
| ---- | -------- | -------- |
| **AllTick** | 全品类 + 永久免费 + WebSocket + <180ms | ⚠️ 需注册，但**无每日上限**很吸引 |
| **iTick** | 跨市场（A+H+美）+ <50ms + WebSocket | ⚠️ 需注册，覆盖广 |
| **yfinance** | Python 库封装 Yahoo，已隐式在用（bonds.py 里 `ds.yahoo_quote` 就是这个方向） | ✅ 已用 |
| **Ashare** | **A 股新浪+腾讯双源自动切换** | ⭐ 有意思，可以借鉴思路 |
| **zzshare** | **龙虎榜 + 情绪指标 40+** | ⭐⭐ 有价值补充 |
| **Fixer** | 500/天，160+ 货币 | 与 Frankfurter 重叠且更弱 |

## 高价值增量分析（按优先级）

### 🥇 zzshare —— A 股情绪 + 龙虎榜（真正的新增量）

**为什么值得**：
- 当前 monitor 缺**龙虎榜/大单**监控（游资动向）
- `sentiment.py` 只有 VIX/SKEW（美股情绪），A 股情绪空白
- zzshare 号称有情绪指标 40+ 接口

**风险**：
- 需查项目活跃度和接口稳定性
- 需要注册 Token（提频用，基础免费）

**评估**：先查 GitHub 是否活跃再定

**2026-07-10 调研结果**：
- PyPI 存在：0.4.8（Beta），作者 `zzquant`，MIT 协议
- GitHub：https://github.com/zzquant/zzshare
- 官方站：https://quant.zizizaizai.com/
- 匿名模式免费可用，Token 只是提高频率上限
- **确认的高价值接口**：
  - `market_sentiment` / `sentiment_trend`：A 股市场情绪 + 趋势 ✅ 正好补 sentiment.py 空白
  - `lhb_list` / `lhb_detail` / `lhb_stock_history`：龙虎榜 3 接口
  - `ths_hot_top`：同花顺热度 Top 100（散户情绪）
  - `uplimit_hot` / `uplimit_stocks` / `stock_uplimit_reason`：涨停梯队 + 热门板块
  - `plates_list` / `plates_rank`：行业/概念板块热度
- **兼容 tushare 接口规范**（stock_basic、daily 等），迁移成本低

**结论**：**技术评估通过，是候选 DS-2 主力**。但今日先不落地，理由：
1. 今日已交付 W1-W4 + DS-1（工作面够宽）
2. us_treasury 需要跑几天看稳定性
3. zzshare 是 β 版（0.4.8），观察 GitHub 活跃度和 issue 响应后再押注

### 🥈 Ashare 双源思路借鉴（不用装库，学思路）

Ashare 库本身只有一个功能：新浪挂时切腾讯拿实时行情。

**我已经用 akshare + 新浪 + 东财 三源**，但**新浪单独挂时没有自动切腾讯的机制**。

**行动**：`data_source.py` 补 A 股实时行情的 sinajs → 腾讯 qt 自动 fallback 逻辑。**不需要装 Ashare 库**，抄思路即可。

### 🥉 AllTick / iTick —— 观察

- 全品类免费 + WebSocket 听着好，但：
  - 我的场景**日频足够**，不需要 <180ms
  - 加个第三方 API 依赖（Key + 服务稳定性）性价比低
- 除非将来做实时高频（例：盘中乌龙指检测），否则不动

### ❌ Fixer

- 与 Frankfurter 重叠，且 Frankfurter 无 Key 更优。跳过。

## 决策记录（2026-07-10）

**本轮不落地任何新接口**——刚接入 U.S. Treasury 完成 DS-1，先跑几天看稳定性。

**后续动手顺序**：
1. **调研 zzshare**（GitHub 活跃度 + 接口列表）→ 潜在 DS-2「A 股情绪 + 龙虎榜」
2. **data_source.py 加 A 股行情源 fallback**（Ashare 思路，无新依赖）→ 潜在 DS-3
3. FRED（v1 已列，需 Key 30 秒申请）→ DS-4 econ_calendar / sentiment

**已完成调研**：
- ✅ zzshare 技术评估通过（见上方 🥇 段），待观察 β 版稳定性后落地为 DS-2

**长期忽略**：AllTick、iTick、Fixer、Alpha Vantage、Finnhub、Polygon、yfinance 直装（当前 akshare/新浪已覆盖 A 股，us_treasury 覆盖美债 2Y-30Y）

## 引用

Steven 提供，无原始链接。
