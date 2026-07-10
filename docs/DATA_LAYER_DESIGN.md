# market-monitor 数据层架构设计

> **状态**：设计已确认，Phase 1 落地中
> **作者**：小龙 + Steven
> **创建时间**：2026-07-09
> **最后更新**：2026-07-09

## 背景与目标

当前系统有 15+ 个 monitor，全部"打完就忘"（JSON state 只做去重）。为支撑后续可视化页面和更强大的分析能力，引入 SQLite 存储层，并做好未来切换 PostgreSQL/TimescaleDB 的兼容性设计。

---

## 一、核心设计原则

1. **零数据库锁定** —— SQLite 起步，任何时候能一键切 PostgreSQL/TimescaleDB
2. **业务代码不写 SQL** —— 所有 DB 操作走 Repository 层，切库不改业务
3. **时间序列为一等公民** —— 所有数据都带 UTC 时间戳，为时序库预留
4. **分层数据模型** —— Raw / Event / Derived / Meta 各司其职
5. **可视化前置设计** —— 表结构按"前端易查"设计，不是按"我方便写"

---

## 二、数据分层模型

```
┌─────────────────────────────────────────────────┐
│  Meta Layer  (维度表：不常变)                     │
│  ├─ monitor_registry   (推送模块字典)             │
│  ├─ symbol_registry    (标的字典)                 │
│  └─ signal_type_registry (信号类型字典)           │
└─────────────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────────────┐
│  Raw Layer  (原始事实：追加写，不改)              │
│  ├─ market_snapshot    (行情快照，时序主表)       │
│  ├─ api_call_log       (API 调用记录，可选)       │
│  └─ south_flow_daily   (南下资金历史)             │
└─────────────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────────────┐
│  Event Layer  (业务事件)                          │
│  ├─ push_log           (所有推送)                 │
│  ├─ signal_event       (信号识别记录)             │
│  └─ alert_dedup        (告警去重键，替代 JSON)    │
└─────────────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────────────┐
│  Derived Layer  (派生/物化视图)                   │
│  ├─ daily_summary      (每日汇总)                 │
│  ├─ signal_outcome     (信号验证结果)             │
│  ├─ monitor_stats      (推送统计)                 │
│  └─ symbol_ohlc_daily  (日 K 冗余，前端专用)      │
└─────────────────────────────────────────────────┘
```

**分层原则**：
- **Raw** 永久保留（可选归档），是所有分析的源头
- **Event** 永久保留，可视化主查询源
- **Derived** 可重建（跑批脚本重新计算），前端优先查这层（性能）
- **Meta** 稳定，前端 dropdown / 分类用

---

## 三、核心表 schema（SQLite 起步，兼容 PG）

### 3.1 Meta Layer

```sql
-- 推送模块字典
CREATE TABLE monitor_registry (
    name         TEXT PRIMARY KEY,              -- 'hk_shock'
    display_name TEXT NOT NULL,                 -- '港股异动'
    category     TEXT NOT NULL,                 -- 'shock'|'periodic'|'alert'|'report'
    enabled      BOOLEAN DEFAULT TRUE,
    description  TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 标的字典（统一 symbol 命名空间）
CREATE TABLE symbol_registry (
    symbol       TEXT PRIMARY KEY,              -- 's_sh000001', 'hkHSI', 'nf_AU0'
    display_name TEXT NOT NULL,                 -- '上证指数'
    market       TEXT NOT NULL,                 -- 'CN'|'HK'|'US'|'GOLD'|'FX'|'BOND'
    asset_class  TEXT NOT NULL,                 -- 'index'|'stock'|'etf'|'commodity'|'fx'|'bond'
    currency     TEXT,                          -- 'CNY'|'HKD'|'USD'
    data_source  TEXT,                          -- 'sina'|'eastmoney'|...
    meta_json    TEXT,                          -- 灵活扩展字段
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 信号类型字典
CREATE TABLE signal_type_registry (
    signal_type  TEXT PRIMARY KEY,              -- 'hk_only_down', 'stabilize_bullish'
    monitor      TEXT NOT NULL,                 -- 'hk_shock'
    display_name TEXT NOT NULL,                 -- '港股独跌'
    direction    INTEGER,                       -- -1/0/+1（跌/中性/涨）
    description  TEXT,
    FOREIGN KEY (monitor) REFERENCES monitor_registry(name)
);
```

### 3.2 Raw Layer

```sql
-- 行情快照（时序主表）
-- 未来切 TimescaleDB 时这张表升级为 hypertable，SELECT * 无感
CREATE TABLE market_snapshot (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TIMESTAMP NOT NULL,            -- UTC，写入时间
    trade_date   DATE NOT NULL,                 -- 交易日（Asia/Shanghai）
    symbol       TEXT NOT NULL,
    price        REAL,                          -- 现价/收盘价
    prev_close   REAL,
    pct          REAL,                          -- 涨跌幅
    amount       REAL,                          -- 成交额
    volume       REAL,                          -- 成交量
    stage        TEXT,                          -- 'live'|'lunch'|'closed'|'pre'
    source       TEXT,                          -- 'sina'|'eastmoney'
    raw_json     TEXT,                          -- 原始数据留档
    FOREIGN KEY (symbol) REFERENCES symbol_registry(symbol)
);
CREATE INDEX idx_snapshot_symbol_ts ON market_snapshot(symbol, ts DESC);
CREATE INDEX idx_snapshot_trade_date ON market_snapshot(trade_date, symbol);
```

**关键设计**：
- `ts` 存 UTC，`trade_date` 存交易日（Asia/Shanghai）→ 时区问题彻底解决
- `raw_json` 兜底：即使 schema 演进，原始数据永远能回填新字段
- `symbol` 是唯一 join key，不用 code/name 混着来

### 3.3 Event Layer（重头戏）

```sql
-- 所有推送落库
CREATE TABLE push_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TIMESTAMP NOT NULL,            -- UTC
    trade_date   DATE NOT NULL,
    monitor      TEXT NOT NULL,                 -- 'hk_shock'
    scenario     TEXT,                          -- 'hk_only_down'|'neutral'|...
    max_level    INTEGER DEFAULT 0,             -- 0/1/2/3
    title        TEXT,                          -- '港股异动预警'（前端列表用）
    message      TEXT NOT NULL,                 -- 完整推送内容
    context_json TEXT,                          -- {"hk_avg":-2.3,"a_avg":-0.4,...}
    sent_ok      BOOLEAN,
    error        TEXT,
    FOREIGN KEY (monitor) REFERENCES monitor_registry(name)
);
CREATE INDEX idx_push_monitor_ts ON push_log(monitor, ts DESC);
CREATE INDEX idx_push_trade_date ON push_log(trade_date, monitor);
CREATE INDEX idx_push_level ON push_log(max_level, ts DESC);

-- 信号识别记录（每次识别出信号都记录，不管是否推送）
CREATE TABLE signal_event (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TIMESTAMP NOT NULL,
    trade_date   DATE NOT NULL,
    monitor      TEXT NOT NULL,
    signal_type  TEXT NOT NULL,                 -- 'hk_only_down'
    symbol       TEXT,                          -- 触发标的（可选）
    level        INTEGER,
    hk_avg_pct   REAL,                          -- 场景关键指标（冗余便于查询）
    a_avg_pct    REAL,
    metrics_json TEXT,                          -- 所有相关指标
    push_log_id  INTEGER,                       -- 关联的推送（可能没有）
    FOREIGN KEY (monitor) REFERENCES monitor_registry(name),
    FOREIGN KEY (signal_type) REFERENCES signal_type_registry(signal_type),
    FOREIGN KEY (push_log_id) REFERENCES push_log(id)
);
CREATE INDEX idx_signal_monitor_ts ON signal_event(monitor, ts DESC);
CREATE INDEX idx_signal_type_ts ON signal_event(signal_type, ts DESC);

-- 告警去重（替代当前 JSON state 文件）
CREATE TABLE alert_dedup (
    monitor      TEXT NOT NULL,
    dedup_key    TEXT NOT NULL,                 -- e.g. '恒生指数_2026-07-09_L2'
    first_seen   TIMESTAMP NOT NULL,
    trade_date   DATE NOT NULL,
    PRIMARY KEY (monitor, dedup_key)
);
CREATE INDEX idx_dedup_trade_date ON alert_dedup(trade_date);
```

### 3.4 Derived Layer（前端主查）

```sql
-- 每日推送汇总（前端 dashboard 主视图）
CREATE TABLE daily_summary (
    trade_date       DATE PRIMARY KEY,
    total_pushes     INTEGER,
    l3_count         INTEGER,
    l2_count         INTEGER,
    l1_count         INTEGER,
    monitors_active  TEXT,                      -- JSON: ["hk_shock",...]
    key_events       TEXT,                      -- JSON: [{"monitor":...,"summary":...}]
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 信号验证（Phase 2 核心）
CREATE TABLE signal_outcome (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_event_id       INTEGER NOT NULL,
    signal_type           TEXT NOT NULL,
    trade_date            DATE NOT NULL,
    predicted_direction   INTEGER,
    t1_pct                REAL,
    t3_pct                REAL,
    t5_pct                REAL,
    t1_hit                BOOLEAN,
    t3_hit                BOOLEAN,
    verified_at           TIMESTAMP,
    FOREIGN KEY (signal_event_id) REFERENCES signal_event(id),
    FOREIGN KEY (signal_type) REFERENCES signal_type_registry(signal_type)
);
CREATE INDEX idx_outcome_signal_type ON signal_outcome(signal_type);

-- 前端专用日 K 表（冗余，防止实时算）
CREATE TABLE symbol_ohlc_daily (
    symbol       TEXT NOT NULL,
    trade_date   DATE NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       REAL,
    amount       REAL,
    pct          REAL,
    PRIMARY KEY (symbol, trade_date),
    FOREIGN KEY (symbol) REFERENCES symbol_registry(symbol)
);
```

---

## 四、代码架构

```
market_monitor/
├── data/                          # 新增：数据层
│   ├── __init__.py
│   ├── database.py                # 连接管理（SQLite/PG 切换点）
│   ├── models.py                  # SQLAlchemy 表定义（唯一 schema 源）
│   ├── migrations/                # Alembic 迁移
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py
│   ├── repositories/              # 业务操作（业务代码只调这层）
│   │   ├── push_repo.py
│   │   ├── snapshot_repo.py
│   │   ├── signal_repo.py
│   │   ├── dedup_repo.py
│   │   └── stats_repo.py
│   ├── seeds.py                   # 种子数据（monitor_registry 等）
│   └── config.py                  # DB URL / 连接池配置
├── api/                           # 新增：前端 API（Phase 1.5）
│   ├── __init__.py
│   ├── server.py                  # FastAPI app
│   ├── routes/
│   └── schemas.py
├── core/                          # 已有：不变
├── monitors/                      # 已有：微改（用 repo 替代 state）
└── cli.py                         # 已有：加子命令 `query`
```

---

## 五、DB 抽象层（切库不改业务的关键）

**技术选型**：**SQLAlchemy Core + SQLModel**

```python
# data/database.py
DB_URL = os.getenv(
    "MARKET_DB_URL",
    "sqlite:///./data/market.db"
)
# 未来切 PG：postgresql+psycopg2://user:pass@host/market
# 未来切 Timescale：同上（Timescale 是 PG 扩展）

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {},
    pool_pre_ping=True,
)
```

**业务改造点**（只改 base.py）：

```python
# core/base.py 里 send() 方法
def send(self, message: str, meta: dict = None) -> bool:
    ok = send_text(message, push_type=self.name, meta=meta)
    with get_session() as s:
        PushLogRepository(s).create(
            monitor=self.name,
            message=message,
            context_json=json.dumps(meta or {}),
            sent_ok=ok,
        )
    return ok
```

---

## 六、跨库兼容注意点

| 陷阱 | SQLite 会过 | PG 会挂 | 我的处理 |
|---|---|---|---|
| `AUTOINCREMENT` 语法 | 需要 | 用 `SERIAL` | **让 SQLAlchemy 处理**，自己不写原生 DDL |
| 时间戳时区 | 无时区 | `TIMESTAMPTZ` | **统一存 UTC naive**，应用层处理时区 |
| JSON 字段 | TEXT | `JSONB` | **用 SQLAlchemy 的 `JSON` 类型**，自动适配 |
| Boolean | 存 0/1 | 存 t/f | SQLAlchemy 抽象 |
| `IF NOT EXISTS` | 支持 | 支持 | 用 Alembic 迁移，不裸写 |
| 并发写 | 单写者锁全库 | 行级锁 | SQLite 阶段用 `WAL` 模式 |
| 全文检索 | FTS5 | GIN | **暂不用**，前端搜索走 API 过滤 |

**具体做法**：
1. 表定义只用 SQLAlchemy Type，不写原生 SQL DDL
2. 所有 datetime 字段：应用层 `datetime.utcnow()`，展示时才转 Asia/Shanghai
3. JSON 字段用 `sqlalchemy.JSON` 类型（SQLite 存 TEXT，PG 自动 JSONB）
4. 用 Alembic 管理 schema 迁移，跨库脚本兼容

---

## 七、前端可视化预留

### 7.1 API 设计（RESTful，前端友好）

```
GET  /api/monitors                          # 所有 monitor 列表
GET  /api/symbols?market=HK                 # 标的列表
GET  /api/pushes?monitor=&from=&to=&level=&limit=&offset=
GET  /api/pushes/:id                        # 单条推送详情
GET  /api/signals?type=&from=&to=
GET  /api/signals/:id/outcome               # 信号验证结果

# 时序数据（前端画图）
GET  /api/snapshots?symbol=&from=&to=&interval=5m
GET  /api/ohlc/daily?symbol=&days=30

# 统计（前端 dashboard）
GET  /api/stats/daily?from=&to=
GET  /api/stats/monitor/:name?days=30
GET  /api/stats/signal-accuracy?type=

# 快速查询（对话式）
GET  /api/search?q=&days=90
```

### 7.2 响应格式约定

```json
{
  "data": [...],
  "meta": {
    "total": 42,
    "page": 1,
    "page_size": 20
  },
  "generated_at": "2026-07-09T09:47:00+08:00"
}
```

---

## 八、实施 Roadmap

### 🟢 Phase 1（本次实施，1-2 天）

**目标**：所有推送和市场快照落库，为可视化打基础

- [x] 设计文档
- [ ] 依赖：sqlalchemy + alembic 加入 pyproject.toml
- [ ] `data/` 模块：database / models / repositories
- [ ] Alembic migration `001_initial.py`
- [ ] seed 脚本：monitor_registry / symbol_registry / signal_type_registry
- [ ] `base.py` 的 `send()` 加落库（所有 monitor 零改动）
- [ ] `data_source.py` 的 `sina_realtime()` 加快照落库
- [ ] `hk_shock.py` 加 signal_event 记录（示范）
- [ ] CLI 子命令 `market-monitor query`
- [ ] 历史 push_log JSONL 回填脚本
- [ ] 验证：跑一次 hk_shock，看数据是否入库

### 🟡 Phase 2（Phase 1 跑 2-4 周后）

- 信号验证器 `outcome_verifier`
- 各 monitor 的信号识别改造（不只 push，signal_event 独立记录）
- 教学模块引用真实历史数据

### 🔴 Phase 3（可选，很后期）

- FastAPI 层 + 前端 dashboard
- 动态阈值 / 用户操作日志
- 切 PostgreSQL/TimescaleDB（DB_URL 一改即可）

---

## 九、备份 & 运维

- **备份**：daily 任务 `cp market.db backups/market-$(date +%F).db`（保留 30 天）
- **位置**：`~/projects/market-monitor/data/market.db`（加 .gitignore）
- **SQLite 模式**：启用 WAL（并发读写）
- **迁移**：`alembic upgrade head`

---

## 十、演进决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-07-09 | 采用 SQLAlchemy + Alembic，不用原生 sqlite3 | 未来切 PG 无痛 |
| 2026-07-09 | 时间统一存 UTC | 跨库兼容 + 时区问题彻底解决 |
| 2026-07-09 | 分 4 层（Meta/Raw/Event/Derived） | 前端查询性能 + 数据清晰度 |
| 2026-07-09 | signal_event 与 push_log 分离 | 支持"识别到但未推送"的信号也可分析 |
