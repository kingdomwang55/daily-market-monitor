# 信号模块抽象与智能市场研究库评估

| 字段 | 内容 |
|------|------|
| **文档类型** | 架构与产品评估（非执行计划） |
| **评估日期** | 2026-07-11 |
| **执行计划** | [RESEARCH_OS_UPGRADE_PLAN.md](./RESEARCH_OS_UPGRADE_PLAN.md) |
| **关联文档** | [DATA_LAYER_DESIGN.md](./DATA_LAYER_DESIGN.md)、[PROJECT_REVIEW_2026-07-11.md](./PROJECT_REVIEW_2026-07-11.md)、[ADD_MONITOR.md](./ADD_MONITOR.md) |
| **评估范围** | (1) 如何在当前项目抽象信号模块；(2) 如何以管理系统页面将系统从「信号推送」升级为个人智能市场研究库 |

---

## 0. 总评

两件事都**值得做**，而且和现有数据层设计方向一致；但顺序必须是：

> **先抽象信号（事件事实）→ 再做研究库页面（读侧）→ 最后才谈「智能」与量化。**

如果反过来先做漂亮管理页、信号仍埋在各 Monitor 的文案里，页面只会变成「推送日志浏览器」，升不成研究库。

当前仓库其实已经有 **约 30% 的信号抽象雏形**，缺的是统一契约与「识别必落库、推送可选」的主路径。

---

## 1. 现状：信号在哪里？

### 1.1 目标形态对比

```
现在（推送中心）:
  Monitor.run()
    → 拉行情
    → if 阈值: 拼中文消息
    → self.send(message, meta={signal_type?})
         → 飞书
         → 偶发写 signal_event（仅 meta 带 signal_type 时）
         → 同时 JSONL push_logger

目标（研究库）:
  Detector.evaluate(ctx) → List[Signal]
    → 一律落库 signal_event（识别即记）
    → Policy 决定是否推送 / 推什么文案
    → 异步/批处理写 signal_outcome
    → UI / 导出 / 纸面交易挂在 Signal 上
```

### 1.2 已有、可复用的积木

| 积木 | 状态 | 对抽象的意义 |
|------|------|----------------|
| `signal_type_registry` + seeds | 有，偏 hk_shock/shock/pulse/price | **Meta 层已有** |
| `SignalEvent` + `SignalEventRepository` | 有 create，查询弱 | Event 层壳子在 |
| `SignalOutcome` 表 | **只建表，无写入逻辑** | 研究库的「验真」空位 |
| `BaseMonitor.send` + `meta.signal_type` | 推送时顺带落库 | **识别与推送绑死** |
| shock / hk_shock / pulse / price_alert | 已写 `signal_type` | 最佳迁移样本 |
| morning/evening/macro 等 | 基本只推文，无结构化信号 | 需拆「报告」与「信号」 |
| ah_premium / etf_premium / cigar_butt / index_valuation | 分析模块，未统一成 Signal | 研究库核心矿源 |
| decision_tracker | 从文案反抽命题 → JSONL | 与 SQL 信号**双轨**，应收敛 |
| paper_trade / trade_signal_link | 表与 CLI 有 | 信号→决策→盈亏链路已预留 |
| 管理页面 | **无** | 需新增读侧 |

### 1.3 当前最大结构性问题

1. **信号不是一等公民**：多数逻辑是「拼消息」，不是「产出 Signal 对象」。
2. **只推才记**：`BaseMonitor` 仅在 `send` 且 `meta.signal_type` 存在时写库 → 大量「识别到但未推」丢失，无法做频率/命中率。
3. **一次推送 ≈ 一个主 signal_type**：pulse 实际可多触发，却压成单一类型。
4. **报告类 Monitor ≠ 信号源**：晚报是信息聚合，不应硬塞成一个 `evening_signal`。
5. **验证层空转**：`signal_outcome` 未用；decision 走另一套 JSONL。
6. **表字段偏港 A 联动**：`hk_avg_pct` / `a_avg_pct` 是特例冗余，通用指标应进 `metrics_json`。

**结论：** 数据层设计已经按研究库画了图，业务层仍停在推送脚本。抽象信号模块，就是把设计图真正接到运行时。

---

## 2. 如何抽象「信号模块」

### 2.1 建议的领域模型（最小够用）

```text
Signal（一次识别结果，不可变事实）
├── signal_id / ts / trade_date
├── signal_type     # 注册表主键，如 shock_index_down_L2
├── monitor         # 来源编排器（可空：纯 detector 也可）
├── symbols[]       # 主标的 + 相关标的
├── direction       # -1 / 0 / +1
├── level           # 0–3 强度
├── title           # 短标题（给人看）
├── metrics         # 结构化指标 dict（pct, premium, zscore…）
├── evidence        # 可选：关键快照引用 / 原文片段
├── dedup_key       # 去重键
└── status          # detected | suppressed | pushed | acted | expired
```

和现有表对齐方式：

- **写入** → `signal_event`（一行一个 Signal；多信号就多行）
- **字典** → `signal_type_registry`
- **推送** → `push_log`（1 条 push 可关联 N 条 signal）
- **事后** → `signal_outcome`
- **人工** → `trade_signal_link` / `paper_trade` / 笔记

不必一上来拆很多表；先把 **「永远先有 Signal，再决定推不推」** 立住。

### 2.2 运行时分层（推荐）

```text
┌─────────────────────────────────────────────┐
│  Orchestrator（现 Monitor，改职责）            │
│  定时 / CLI / 手动触发                         │
└───────────────┬─────────────────────────────┘
                │ context: 行情、配置、时段、持仓
                ▼
┌─────────────────────────────────────────────┐
│  Signal Module（新建 market_monitor/signals/） │
│  ├── types.py        Signal / SignalContext   │
│  ├── registry.py     Detector 注册            │
│  ├── detectors/      各规则实现               │
│  ├── dedupe.py       去重（替/并 JSON State）  │
│  ├── persist.py      落库 signal_event        │
│  ├── outcome.py      T+1/T+5 回填（Phase 2）  │
│  └── render.py       Signal → 飞书文案        │
└───────────────┬─────────────────────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
   Delivery(飞书)    Research API / UI
```

**关键原则：**

| 原则 | 含义 |
|------|------|
| Detect ≠ Deliver | 识别失败/成功与推不推送解耦 |
| Detect always persists | 识别到即写 `signal_event`（含未推送） |
| One detector, one concern | 例：指数阈值、AH 溢价、ETF 折价、企稳条件各一个 |
| Monitor = 编排 | 负责调度、组上下文、调 delivery，不内嵌巨型 if |
| 文案后置 | `render(signals) → str`，AI 解读挂在 render/enrich 层 |

### 2.3 Detector 契约（示意）

```python
# 概念接口，非要求立刻落代码
class SignalDetector(Protocol):
    signal_types: list[str]          # 必须在 registry/seeds 声明

    def evaluate(self, ctx: SignalContext) -> list[Signal]:
        ...
```

`SignalContext` 建议包含：`now`、`config`、已拉好的 quotes/snapshots、可选 positions、market stage（A live/closed 等）。

**取数尽量在 Orchestrator 做一次**，多个 detector 共享，避免每个规则各打一遍新浪。

### 2.4 从现有代码迁什么（优先级）

| 优先级 | 来源 | 抽成 Detector 的理由 |
|--------|------|----------------------|
| **P0** | `shock` 分级 + 板块阈值 | 逻辑纯、已有 signal_type |
| **P0** | `hk_shock` 场景（独跌/共振…） | seeds 最完整，研究价值高 |
| **P0** | `price_alert` 止损/加仓 | 与个人交易直接相关 |
| **P1** | `pulse` 内多条件 | 示范「一次 run → 多 Signal」 |
| **P1** | `ah_premium` / `etf_premium` | 真正「可检验」的研究信号 |
| **P1** | `index_valuation` 分位 | 中低频研究信号 |
| **P2** | `cigar_butt` 筛选结果 | 批次信号，适合研究库列表 |
| **P2** | stabilize 条件集合 | 可拆多原子信号再组合 |
| **P3** | morning/evening | 不整页当信号；从中抽「可检验命题」或只当 Document |

**不要**把整个 `EveningMonitor` 变成一个 Detector——晚报是 **Research Document**，里面可以挂当天 Signal 摘要。

### 2.5 与 decision_tracker 的关系

现在是：

> 推送原文 → AI 反抽 claim → JSONL

抽象后应演进为：

> **规则 Signal（主）** + **可选 AI 命题（辅）** → 统一进 `signal_event`（可 `source=rule|ai`）→ `signal_outcome` 统一验证

初学者阶段：**规则信号优先**（可复现、可统计）；AI 只做解释与「从报告抽命题」，不要当唯一信号源。

### 2.6 信号模块落地的最小 API（CLI 先于 UI）

在有页面之前，先有这些能力，研究库才算「活」：

```bash
# 概念命令
market-monitor signal list --days 7
market-monitor signal types
market-monitor signal show <id>
market-monitor signal run shock --dry-run   # 只检测落库/打印，不飞书
market-monitor signal outcome --backfill 5  # 回填 T+1..T+5
```

有了 CLI，页面只是查询壳；没有这些，页面只能展示 push 文本。

### 2.7 抽象时的坑（结合本项目）

1. **FK 与种子**：`signal_type` / `symbol` 必须先在 registry；新 detector 要同步 seeds。
2. **去重双轨**：JSON `State` 与未来 `alert_dedup` 并存时，dedupe 应进 signal 模块，Monitor 不再各写一套 key。
3. **多信号推送**：一次飞书可汇总多条 Signal，但库中仍是多行 event。
4. **报告噪音**：heartbeat / neutral 是否入库要产品决策——建议 **入库但默认 UI 过滤**，否则频率统计被稀释。
5. **测试**：Detector 必须纯函数化 + fixture 行情，这是项目变「可进化」的关键。

### 2.8 对初学者路径的评价

| 问题 | 判断 |
|------|------|
| 现在抽象信号模块，方向对吗？ | **对，且应作为升级研究库的前提** |
| 工作量？ | 中等：P0 四类 1–2 周可做出骨架；全量迁移要滚动多周 |
| 会不会过度设计？ | 若一上来微服务/复杂事件总线 → 过度；**单包 `signals/` + 表复用** 刚好 |
| 对入门学习有帮助吗？ | **很大**：强迫分清「事实信号 / 解读 / 交易动作」 |

---

## 3. 管理系统页面：从「信号推送」到「智能市场研究库」

### 3.1 产品定义（避免做成普通后台）

**不是：** Monitor 开关面板 + 日志 tail。  
**是：** 个人 **Market Research OS**——以「信号与证据」为中心的第二大脑。

建议一句话定位：

> **把每日市场事实、结构化信号、我的判断与纸面结果，沉淀成可检索、可验证、可导出的个人研究库。**

推送降级为：**研究库的通知渠道之一**。

### 3.2 信息架构（页面怎么切）

按学习路径，建议 **5 个一级模块**（先做 3 个就够用）：

```text
1. 今日看板 Today
   - 今日推送摘要 / 信号条数 / 最高 level
   - 全球-A-H 一句话状态（可来自 morning/pulse 落库）
   - 待验证信号、待复盘纸面

2. 信号中心 Signals          ← 核心
   - 筛选：市场、类型、方向、level、日期
   - 详情：metrics、关联推送、后续 outcome、我的批注
   - 「类似历史信号」列表（同 type 近 90 天）

3. 研究笔记 Research
   - 日记 notes、概念库、AI 解读归档
   - 主题页：如「AH 溢价」「美债曲线」时间线

4. 实验与交易 Lab
   - 纸面持仓、信号→act/skip/noise
   - 胜率不是 KPI；逻辑分类与错误类型才是

5. 系统 System（可最后做）
   - monitor 启用、最近运行、健康检查
   - 配置只读/简单编辑（谨慎暴露密钥）
```

「智能」放在哪里（务实）：

- **检索**：按标的/主题/信号类型找历史
- **对照**：该信号历史 T+1/T+5 分布（outcome 表）
- **辅助**：详情页「用 AI 解释这条信号」——**解释已有结构，不替代结构**
- **不要一上来**：全自动荐股、无人交易台

### 3.3 技术路线评价（个人项目）

| 方案 | 优点 | 缺点 | 建议 |
|------|------|------|------|
| **FastAPI + 简单前端（HTMX/Jinja 或轻量 Vue）** | 与现有 Python 同栈；API 可给未来 App；贴合 SQL repo | 要写一点前端 | **首选（中长期）** |
| Streamlit / Gradio | 极快出页面 | 难做成「库」感、权限/路由弱 | 适合 1 周原型验证 |
| 纯静态读 SQLite 导出 | 简单 | 交互差 | 仅过渡 |
| 重型 React 独立仓库 | 炫 | 对初学者成本过高 | 暂缓 |

数据访问：**禁止页面直连业务拼 SQL**；统一：

`signals/persist + repositories` → **`api/` 只读服务** → UI

写操作谨慎：批注、纸面交易、skip 决策可以写；改阈值配置要鉴权/本地 only。

### 3.4 与现有数据层如何对齐

数据层文档已写「可视化前置」——页面应 **优先读**：

| UI 模块 | 主表 |
|---------|------|
| 今日看板 | `push_log` + `daily_summary`（需物化任务） |
| 信号列表/详情 | `signal_event` + registry + `push_log` |
| 命中率 | `signal_outcome`（必须先实现回填） |
| 交易实验 | `paper_trade` + `trade_signal_link` |
| 行情上下文 | `market_snapshot` / 未来 ohlc |
| 概念/笔记 | 文件 notes + 可选 DB |

没有 **outcome 回填 Job**，信号中心只是列表，谈不上研究库。

### 3.5 分阶段（强烈建议）

| 阶段 | 目标 | 完成标准 |
|------|------|----------|
| **S0 信号骨架** | `signals/` 包 + P0 detector 迁入 + 识别必落库 | CLI `signal list` 有真实数据 |
| **S1 只读研究页 MVP** | 本地 Web：今日 + 信号列表/详情 | 能回看 7 天信号并点开 metrics |
| **S2 验证闭环** | outcome 回填 + 类型维度命中率 | 每个主信号有 T+1/T+5 粗统计 |
| **S3 实验台** | 纸面与 act/skip 在 UI 完成 | 信号详情一键记「做了/跳过」 |
| **S4 智能增强** | 语义检索、AI 旁注、主题时间线 | 仍以结构化信号为轴 |
| **S5 导出量化** | CSV/Parquet 信号流给外平台 | 与「稳定盈利」解耦，只做数据出口 |

对初学者：**S0→S1→S2** 就是最有学习杠杆的路径；S4 以前不要堆模型。

### 3.6 风险与边界

| 风险 | 说明 |
|------|------|
| 做成推送 CMS | 只展示 message 文本 → 失败 |
| 先 UI 后信号 | 返工成本高 |
| 智能幻觉 | AI 当结论而非注释 → 学坏习惯 |
| 范围膨胀 | 持仓券商同步、实盘下单、社区… 全是另一产品 |
| 安全 | 本地绑定 `127.0.0.1`；密钥永不进前端 |

---

## 4. 两者关系：一张图

```text
                    ┌──────────────────┐
  行情/宏观/筛选 ──►│  Signal Module   │──► signal_event（事实）
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         飞书推送        研究库 Web      导出/外平台
         (可选渠道)     (主界面)        (未来量化)
              │              │
              └──────┬───────┘
                     ▼
              signal_outcome + paper_trade
              （学习与验证，不是承诺盈利）
```

- **信号模块** = 系统的「语义操作系统」
- **管理页 / 研究库** = 系统的「人机研究界面」

没有信号模块，管理页只是日志站；没有管理页，信号模块只对 CLI 友好、难形成每日研究习惯。

---

## 5. 综合可行性判断

| 维度 | 评分 | 说明 |
|------|------|------|
| 与现有架构契合度 | **高** | 表、seeds、部分 monitor 已按信号语义演进 |
| 技术可行性 | **高** | 个人本地 FastAPI + SQLite 足够 |
| 对入门学习价值 | **很高** | 强迫结构化思维与复盘 |
| 工作量（做到能用） | **中** | S0+S1 大约数周业余时间级 |
| 直接带来盈利 | **低/无关** | 研究库提高认知质量，不保证 edge |
| 过度设计风险 | **中** | 用「薄信号层 + 薄只读 API」可控 |

### 结论

1. **抽象信号模块：靠谱，且应优先于大而全管理后台。** 以 P0 四类 detector 为切口，统一 `Signal` + 识别落库 + CLI。
2. **管理系统页面：靠谱，但定位必须是「个人智能研究库」而非运维台。** 在信号可查询、outcome 可回填之后，价值会陡增。
3. **两者一起，正好是从「推送订阅者」升级为「有证据的研究者」的工程路径**；量化与外平台是 S5 的自然出口，而不是现在的第一枪。

---

## 6. 最小开工包（建议）

1. 新建 `market_monitor/signals/`：`Signal` 数据类、`Detector` 协议、`persist_signals()`。
2. 把 `shock` 改成：detect → persist →（可选）render → send。
3. CLI：`signal list/show`。
4. 极简 Web：信号表 + 详情（Streamlit 原型或 FastAPI+Jinja 二选一）。
5. 一个定时任务：对昨日信号回填 `signal_outcome.t1_pct`。

做完这五步，系统性质就变了：从报警器变成**研究库雏形**。

---

## 7. 建议的包与目录草图（供后续设计细化）

```text
market_monitor/
├── signals/                 # 新增：信号一等公民
│   ├── __init__.py
│   ├── types.py             # Signal, SignalContext
│   ├── protocol.py          # SignalDetector Protocol
│   ├── registry.py          # detector 注册表
│   ├── dedupe.py
│   ├── persist.py           # → signal_event
│   ├── outcome.py           # → signal_outcome 回填
│   ├── render.py            # → 飞书/文案
│   └── detectors/
│       ├── shock.py
│       ├── hk_shock.py
│       ├── price_alert.py
│       └── ...
├── monitors/                # 编排层：调度 + 取数 + 调 signals + delivery
├── data/                    # 既有 models / repositories
└── api/                     # 后续：研究库 HTTP（S1）
    ├── app.py
    └── routes/
        ├── today.py
        ├── signals.py
        └── lab.py
```

---

## 8. 与「稳定盈利 / 量化」的边界声明

- 本评估中的信号模块与研究库，目标是 **可检索、可验证、可导出的个人研究底座**。
- **不承诺、也不应以「稳定盈利」作为本阶段验收标准。**
- 外平台量化、实盘执行属于 S5 及以后；当前成功标准是：结构化信号流水线 + 回看/复盘习惯 + 命中率粗统计。

---

## 附录 A：当前会写 `signal_type` 的 Monitor（审查时点）

根据代码检索，以下路径会向 `meta` 写入 `signal_type` 从而可能触发 `signal_event` 落库：

- `monitors/shock.py`
- `monitors/hk_shock.py`
- `monitors/pulse.py`
- `monitors/price_alert.py`

其余 Monitor 多数仅推送文案，不产生结构化信号行。

## 附录 B：seeds 中已登记的部分 signal_type 族

- `hk_*`（港 A 联动场景）
- `shock_*`（A 股异动分级）
- `price_*`（关键点位）
- `pulse_*`（盘中脉搏）

AH / ETF / 估值 / 烟蒂等研究信号尚未系统进入 `signal_type_registry`。

---

*文档保存日期：2026-07-11。*
