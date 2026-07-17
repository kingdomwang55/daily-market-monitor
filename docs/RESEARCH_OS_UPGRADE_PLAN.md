# Market Research OS 升级改造方案

| 字段 | 内容 |
|------|------|
| 文档类型 | 全量升级改造方案与验收计划 |
| 当前定位 | 从 OpenClaw 使用的市场监控工具沉淀为独立本地系统 |
| 目标定位 | 面向个人投资者的市场信号监控与研究沉淀系统 |
| 核心约束 | 保持 OpenClaw 继续高质量调用当前项目 |
| 关联文档 | [SIGNAL_AND_RESEARCH_OS_EVAL.md](./SIGNAL_AND_RESEARCH_OS_EVAL.md)、[DATA_LAYER_DESIGN.md](./DATA_LAYER_DESIGN.md)、[PROJECT_REVIEW_2026-07-11.md](./PROJECT_REVIEW_2026-07-11.md) |

---

## 1. 背景与判断

项目最初的真实痛点不是“缺一个行情脚本”，而是：

1. OpenClaw 每次临场问答的回复速度、稳定性和一致性不可控。
2. OpenClaw 不能天然做主动定时监控、状态去重、持续推送和长期复盘。
3. 市场判断需要规则、数据、历史记录和行动结果沉淀，而不是每次重新问一遍。

因此，项目应从“OpenClaw 临时调用的工具集合”升级为一个独立运行的本地系统。OpenClaw 不再承担主执行职责，而是作为研究助手、解释器和高级调用方继续使用本项目。

一句话方向：

> 让 OpenClaw 从司机变成副驾；方向盘交给稳定、可运行、可验证的 market-monitor。

---

## 2. 产品目标

最终系统应能完成一条完整链路：

```text
行情采集
  -> 规则信号识别
  -> 信号分级与去重
  -> 推送提醒
  -> 信号与推送落库
  -> 纸面交易/人工动作记录
  -> T+1/T+3/T+5 验证
  -> 周/月复盘
  -> 研究库查询与沉淀
```

目标产品定义：

> 一个面向个人投资者的市场信号监控与研究沉淀系统。它将行情监控、规则信号、推送提醒、纸面交易和复盘记录沉淀为可运行、可验证、可扩展的本地工具。

### 2.1 必须解决的痛点

| 痛点 | 系统目标 |
|------|----------|
| 不想反复问 AI 当前市场怎样 | 定时监控，主动识别信号 |
| AI 回答慢且不稳定 | 规则信号由确定性代码产生 |
| 消息太多容易疲劳 | 分级、去重、触发才推 |
| 看到了信号但没有沉淀 | 所有信号结构化落库 |
| 不知道信号历史效果 | outcome 回填与复盘 |
| 交易纪律难坚持 | 信号、行动、纸面交易关联 |
| 仍希望 OpenClaw 帮忙研究 | 提供稳定 CLI/JSON/SQLite 接口 |

---

## 3. 设计原则

1. **独立运行优先**：系统关闭 AI 后仍应能完成监控、信号、推送和落库。
2. **OpenClaw 兼容优先**：所有关键能力必须能被 OpenClaw 稳定调用。
3. **规则信号优先**：规则检测是主事实源，AI 只做解释、总结和辅助研究。
4. **先 CLI 后页面**：先把命令行和数据模型做稳，页面只是读侧。
5. **先 Signal 后 Push**：先产生结构化 Signal，再决定是否推送。
6. **识别必落库**：检测到的信号都应写入 `signal_event`，推送只是可选后续动作。
7. **可验证优先**：每个核心信号都应具备 fixture、测试和 outcome 口径。
8. **兼容渐进迁移**：现有 monitor、配置和命令尽量不破坏；必要变更提供 alias 或迁移提示。

---

## 4. OpenClaw 兼容方案

OpenClaw 是本项目的重要使用方。升级不是把它踢出去，而是让它使用更稳定的底层能力。

### 4.1 OpenClaw 的新角色

OpenClaw 适合做：

- 查询今日/近期信号并解释。
- 根据历史信号辅助生成复盘。
- 读取纸面交易和 outcome，帮助发现错误模式。
- 根据你的新想法生成 detector 草案。
- 辅助改代码、补测试、调配置。

OpenClaw 不应负责：

- 定时调度。
- 主信号判断。
- 状态去重。
- 主数据存储。
- 推送是否触发的最终规则。

### 4.2 面向 OpenClaw 的稳定接口

所有关键能力都应提供 CLI，并支持 `--json`：

```bash
market-monitor list --json
market-monitor run <monitor> --snapshot --json
market-monitor signal list --days 7 --json
market-monitor signal show <id> --json
market-monitor signal types --json
market-monitor db stats --json
market-monitor trade list --json
market-monitor review weekly --json
```

文本输出继续面向人类阅读，JSON 输出面向 OpenClaw 和自动化调用。

### 4.3 JSON 输出契约

信号列表的最小字段：

```json
{
  "id": 123,
  "ts": "2026-07-17T09:45:00Z",
  "trade_date": "2026-07-17",
  "monitor": "pulse",
  "signal_type": "pulse_index_down",
  "symbol": "sh000001",
  "symbols": ["sh000001", "sz399006"],
  "direction": -1,
  "level": 2,
  "title": "创业板指跌幅扩大",
  "status": "pushed",
  "metrics": {
    "pct": -1.6
  },
  "push_log_id": 456,
  "outcome": null
}
```

### 4.4 专用文档

新增或补充：

```text
docs/OPENCLAW_USAGE.md
```

内容包括：

- OpenClaw 推荐调用命令。
- JSON 字段说明。
- 常见任务范式：看今日信号、生成复盘、分析交易、创建 detector。
- 不建议让 OpenClaw 承担的职责。

---

## 5. 目标架构

```text
market_monitor/
  core/                 # 配置、时间、飞书、AI、通用工具
  data/                 # SQLAlchemy models/repositories/migrations
  sources/              # 可逐步从 core.data_source 拆出的数据源适配器
  signals/              # 新增：Signal 一等公民
    types.py
    context.py
    registry.py
    policy.py
    dedupe.py
    persist.py
    render.py
    outcome.py
    detectors/
  monitors/             # 调度与编排，逐步变薄
  research/             # 研究库查询、复盘、报告聚合
  cli/                  # 后续从大 cli.py 拆分
```

运行时目标：

```text
Monitor / CLI
  -> collect data once
  -> build SignalContext
  -> detectors.evaluate(ctx)
  -> persist signal_event
  -> policy decide push/suppress
  -> render human message
  -> delivery send
  -> link push_log <-> signal_event
  -> later outcome/review/trade
```

---

## 6. 核心领域模型

### 6.1 Signal

`Signal` 是一次不可变的市场事实识别结果。

```text
Signal
├── id / ts / trade_date
├── monitor
├── detector
├── signal_type
├── symbols
├── primary_symbol
├── direction          # -1 / 0 / +1
├── level              # 0-3
├── title
├── summary
├── metrics
├── evidence
├── dedup_key
└── status             # detected / suppressed / pushed / acted / expired
```

### 6.2 SignalContext

```text
SignalContext
├── now
├── config
├── market_stage
├── quotes
├── klines
├── positions
├── recent_signals
└── raw_payloads
```

### 6.3 Detector

```python
class SignalDetector(Protocol):
    name: str
    signal_types: list[str]

    def evaluate(self, ctx: SignalContext) -> list[Signal]:
        ...
```

Detector 应尽量是纯逻辑：输入 fixture 数据，输出稳定 Signal。

### 6.4 Policy

Policy 负责决定：

- 是否推送。
- 推送等级。
- 是否静默落库。
- 是否去重。
- 是否 heartbeat 默认过滤。

### 6.5 Outcome

`SignalOutcome` 负责回答：

- 该信号 T+1/T+3/T+5 后方向是否正确？
- 最大回撤/最大涨幅如何？
- 这类信号历史命中率如何？
- 我是否行动，行动结果是否优于不行动？

---

## 7. 分期计划

### Phase 0：环境、文档与基线收口

目标：让项目在干净环境中可安装、可测试、可运行。

任务：

- 更新 README 定位：从“AI 智能监控”调整为“个人市场信号监控与研究沉淀系统”。
- 明确安装命令：`python3 -m venv`、`pip install -e '.[dev,analytics]'`。
- 修复或确认 `pyproject.toml` 依赖闭环。
- 保证 `python3 -m pytest` 可以运行。
- 保证 `market-monitor doctor --ci` 在干净环境通过。
- 对现有未跟踪评估文档决定是否纳入版本库。
- 新增 `docs/OPENCLAW_USAGE.md`。

验收：

```bash
python3 -m pip install -e '.[dev,analytics]'
python3 -m pytest
market-monitor doctor --ci
market-monitor list
```

全部通过。

### Phase 1：Signal 骨架落地

目标：建立统一信号模块，但先不大规模迁移。

任务：

- 新增 `market_monitor/signals/`。
- 定义 `Signal`、`SignalContext`、`SignalDetector`。
- 实现 `persist_signals()`。
- 实现 `render_signals()` 的最小版本。
- 实现 `SignalPolicy` 和 dedup 基础能力。
- 新增 CLI：

```bash
market-monitor signal types
market-monitor signal list --days 7
market-monitor signal show <id>
```

验收：

- 可以手动创建/持久化一条 Signal。
- CLI 能查询 Signal。
- JSON 输出可被 OpenClaw 使用。
- 单元测试覆盖 Signal 类型、序列化、持久化。

### Phase 2：核心 Monitor Signal 化

目标：迁移最重要、最像规则系统的 monitor。

优先级：

| 优先级 | 模块 | 改造目标 |
|--------|------|----------|
| P0 | `price_alert` | 止损/加仓点位输出结构化 Signal |
| P0 | `shock` | 指数/板块分级异动输出 Signal |
| P0 | `hk_shock` | 港股独跌/共振/个股异动输出 Signal |
| P1 | `pulse` | 一次运行可输出多条 Signal |
| P1 | `shanghai_watch` | 3800 剧本各触发条件输出 Signal |

验收：

- 上述模块保持原 CLI 命令兼容。
- 原有推送文案不明显退化。
- 每个模块有 fixture 测试。
- 每个模块能 dry-run 输出 JSON Signal。
- 一次 push 可关联多条 Signal。

### Phase 3：推送、去重、日志主路径统一

目标：从双轨/多轨状态逐步收敛到 SQL 主事实源。

任务：

- 明确 SQL 为主数据源。
- `push_log` 与 `signal_event` 建立稳定关联。
- `AlertDedupRepository` 替代分散 JSON state 的核心去重职责。
- JSONL `push_logger` 降级为兼容日志或调试日志。
- 保留旧 state 的读取迁移策略，避免突然重复推送。

验收：

- 触发同一信号不会重复推送。
- 即使不推送，识别到的信号也能在 `signal list` 查到。
- `db stats` 能统计推送与信号。
- 断网/飞书失败时，信号事实仍可落库，推送状态可追踪。

### Phase 4：纸面交易与复盘闭环

目标：把“信号是否出现”推进到“我是否行动、结果如何”。

任务：

- 支持 `trade add --signal-id ... --json`，并自动写入 `trade_signal_link(decision=act)`。
- 支持 signal 标记：`market-monitor signal mark <id> --decision act|skip|noise|watch --json`。
- 支持 `market-monitor signal outcome backfill --days N --json`。
- 支持交易列表、详情、盈亏、复盘的 JSON 输出。
- 逐步收敛 `decision_tracker` JSONL 到 SQL 主路径。

验收：

```bash
market-monitor signal mark 123 --decision skip --reason "等待确认" --json
market-monitor trade add sh000001 3800 1 --signal-id 123 --json
market-monitor signal outcome backfill --days 30 --json
market-monitor trade review --period week --json
```

能够形成一条完整链路：Signal -> Push -> Action/Trade -> Outcome -> Review。

### Phase 5：AI 增强层重定位

目标：AI 只增强，不接管主判断。

任务：

- AI 解读挂在 `render/enrich` 或 `research` 层。
- 关闭 AI 时，系统仍能完成核心流程。
- AI 可从 SQL 信号生成解释、复盘和策略建议。
- `decision_tracker` 演进为“AI 命题提取器”，可通过 `market-monitor decision import-sql --date YYYY-MM-DD --json` 输出进入统一 `signal_event`。

验收：

- `ai.enabled=false` 时所有核心 monitor 可运行。
- `ai.enabled=true` 时报告更丰富，但不改变规则 Signal 的事实判断。
- AI 失败不会阻断推送和落库。
- 已提取的 decision JSONL 可幂等导入 SQL，并作为 `decision_bullish` / `decision_bearish` / `decision_neutral` 信号查询。

### Phase 6：本地研究库页面

目标：在 CLI 稳定后提供读侧页面。

优先模块：

```text
Today      今日信号和最高风险等级
Signals    信号中心、筛选、详情、历史相似信号
Trades     纸面交易与信号关联
Reviews    周/月复盘
System     monitor 健康、最近运行、配置状态
```

验收：

- 页面只读取稳定 API/SQL，不承载核心业务判断。
- 没有页面时 CLI 仍完整可用。
- OpenClaw 仍优先通过 CLI/JSON 使用项目。
- `market-monitor research export --out reports/research.html --json` 可生成本地静态研究页。

---

## 8. 测试方案

### 8.1 单元测试

覆盖：

- 数据解析器。
- Detector 规则。
- Signal 序列化。
- Policy 推送决策。
- Dedup key。
- Render 文案。

要求：

- Detector 测试不访问网络。
- 输入 fixture 固定，输出 Signal 稳定。

### 8.2 Repository 测试

使用临时 SQLite，覆盖：

- `signal_event` 写入/查询。
- `push_log` 关联。
- `alert_dedup` 去重。
- `paper_trade` 开/平仓。
- `signal_outcome` 回填。

### 8.3 Monitor 集成测试

通过 mock data source 覆盖：

- 有信号。
- 无信号。
- 重复信号。
- force。
- snapshot。
- 飞书失败。
- DB 失败。

### 8.4 CLI 烟雾测试

覆盖：

```bash
market-monitor list
market-monitor doctor --ci
market-monitor run price_alert --snapshot
market-monitor signal list --json
market-monitor db info
market-monitor trade list --json
market-monitor review weekly --json
```

### 8.5 回归 Fixture

建立固定行情样本：

| fixture | 场景 |
|---------|------|
| `a_index_drop_l2` | A 股指数警戒下跌 |
| `hk_only_down` | 港股独跌 |
| `near_stop_loss` | 逼近止损位 |
| `stabilize_reversal` | 企稳反转 |
| `pulse_no_signal` | 心跳无异动 |
| `shanghai_3800_v_reversal` | 3800 V 型收回 |
| `shanghai_3800_break_stop` | 跌破 3700 止损 |

每个 fixture 应断言：

- Signal 数量。
- `signal_type`。
- `level`。
- `direction`。
- `dedup_key`。
- 推送策略结果。

---

## 9. 验收条件

### 9.1 项目级验收

全量升级完成时，必须满足：

1. README 能准确说明定位、安装、配置、运行和 OpenClaw 调用方式。
2. `python3 -m pytest` 在干净环境通过。
3. `market-monitor doctor --ci` 通过。
4. 核心告警类 monitor 已 Signal 化。
5. Signal 识别与推送解耦。
6. SQL 是主事实源。
7. 推送、信号、纸面交易、复盘可以串起来。
8. 关闭 AI 后系统仍可正常监控和推送。
9. JSON CLI 输出稳定，OpenClaw 可直接消费。
10. 新增一个 detector 不需要改核心框架。

### 9.2 业务级验收

系统必须能回答这些问题：

- 今天出现了哪些信号？
- 哪些信号推送了，哪些被静默？
- 某类信号过去 30 天出现过几次？
- 我对哪些信号采取了行动？
- 哪些行动赚钱/亏钱？
- 哪些信号 T+1/T+5 方向有效？
- 本周我最大的判断偏差是什么？
- OpenClaw 能否基于结构化数据生成复盘？

### 9.3 OpenClaw 验收

OpenClaw 应能稳定完成：

```text
1. 调用 signal list --json 获取近 7 天信号。
2. 调用 signal show --json 查看某个信号详情。
3. 调用 review weekly --json 获取复盘素材。
4. 基于 JSON 输出生成中文解释。
5. 不依赖重新临场判断即可回答“今天发生了什么”。
```

---

## 10. 不做或后做

短期不做：

- 多用户 SaaS。
- 复杂 Web 后台优先。
- 实盘自动交易。
- 高频行情服务化。
- 微服务/消息队列。
- 完全依赖 AI 的交易判断。

后续可做：

- 本地 Web UI。
- SQLite 到 PostgreSQL/TimescaleDB 的迁移。
- 更权威的数据源适配。
- Signal 历史相似案例检索。
- 策略实验与简单回测。

---

## 11. 推荐执行顺序

```text
P0  环境、README、测试基线、OpenClaw 使用文档
P1  Signal 类型、持久化、CLI JSON
P2  price_alert / shock / hk_shock / pulse Signal 化
P3  SQL 主路径、dedup、push-signal 关联
P4  trade / outcome / weekly review 闭环
P5  AI enrich 与 decision_tracker 收敛
P6  本地研究库页面
```

项目真正收口的标志不是 monitor 数量更多，而是：

> 每一个重要市场观察都能被结构化记录、被推送、被查询、被行动、被验证、被复盘，并且 OpenClaw 可以稳定地调用这些事实，而不是重新猜一遍。
