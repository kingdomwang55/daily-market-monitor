# 本地 Web 研究库与 Docker 部署实施计划

| 字段 | 内容 |
|------|------|
| 文档类型 | Web UI 与部署实施计划 |
| 当前结论 | 本地 Web 页面需要做；主线采用 FastAPI API + Vue + SQLite + Docker Compose |
| 不采用 | Streamlit 作为正式主线、macOS/Windows/iOS 原生客户端作为当前主线 |
| 主事实源 | SQLite + SQLAlchemy + Alembic |
| 目标用户 | 个人投资者本地使用；OpenClaw/Codex 继续通过 CLI/JSON 调用 |

---

## 1. 背景与目标

当前系统已经从 OpenClaw 调用的命令集合，演进为个人 Market Research OS：

```text
行情采集
  -> 规则信号识别
  -> 信号分级与去重
  -> 飞书推送
  -> 信号与推送落库
  -> 纸面交易/人工动作记录
  -> outcome 验证
  -> 周/月复盘
  -> 研究库查询与沉淀
```

继续只依赖命令行和与 OpenClaw 对话，会在这些场景变得低效：

- 回看历史信号和推送，需要反复拼 CLI 参数。
- 信号详情中的 metrics、关联推送、交易动作不够直观。
- 纸面交易、act/skip、批注等人工轻写操作不适合长期只靠命令。
- 周/月复盘需要更稳定的浏览和筛选界面。

因此需要新增本地 Web 页面。但 Web 页面应定位为：

> 个人市场研究库的人机界面，而不是替代 monitor/CLI 的核心判断系统。

---

## 2. 架构决策

### 2.1 Web 主线

采用：

```text
FastAPI
  -> 只读/轻写 JSON API
  -> Vue 单页应用
  -> SQLite/SQLAlchemy repositories
  -> Docker Compose 部署
```

理由：

- 前后端边界清楚，避免先用模板页后期迁移到 SPA 的返工。
- API 可同时服务浏览器页面、OpenClaw/Codex、未来移动浏览器。
- Vue 适合逐步承载更复杂的筛选、图表、状态管理和研究工作流。
- Docker 部署边界清楚。
- 不破坏现有 CLI 一等接口。
- 可以从很薄的前端开始，随着页面变重自然演进。

前端主线建议：

```text
Vue 3 + TypeScript + Vite
  -> Vue Router
  -> Pinia（等页面状态复杂后再引入）
  -> fetch/axios API client
  -> CSS Modules 或普通 CSS 起步
```

首版不引入重型组件库，避免页面气质变成通用后台。图表需求出现后再评估 ECharts 或 lightweight-charts。

### 2.2 不以 Streamlit 为主线

Streamlit 适合快速数据看板原型，但不适合作为本项目正式主线：

- 页面和路由形态更像脚本看板，不像长期使用的研究库。
- API、鉴权、部署和前后端边界不如 FastAPI 清楚。
- 后续迁移到正式 Web 服务时大概率需要重写。

结论：

> 不采用 Streamlit 作为正式主线；如需极短期验证某个数据视图，可作为一次性实验，不沉淀为主架构。

### 2.3 不优先做原生客户端

当前不做 macOS / Windows / iOS 原生页面：

- 浏览器页面天然跨平台。
- Docker 部署要求更适合 HTTP 服务。
- 飞书已承担移动端提醒入口。
- 原生客户端会提前引入打包、权限、更新和平台差异成本。

未来若 Web 已稳定，可考虑：

- Tauri/Electron 包一层桌面壳。
- 手机浏览器只读入口。
- 局域网部署 + 简单认证。

---

## 3. 存储方案

### 3.1 当前主库

继续使用 SQLite 作为主事实源：

```text
data/market.db
```

Docker 内建议路径：

```text
/app/data/market.db
```

环境变量：

```bash
MARKET_DB_URL=sqlite:////app/data/market.db
```

### 3.2 SQLite 使用原则

- 使用 SQLAlchemy repository 访问数据库，页面和 API 不直接拼业务 SQL。
- 使用 Alembic 管理 schema 迁移。
- 启用 SQLite pragma：
  - `foreign_keys=ON`
  - `journal_mode=WAL`
  - `busy_timeout`
- 所有 JSON 字段继续使用 SQLAlchemy `JSON` 类型，保留未来迁移 PostgreSQL 的空间。
- 数据库文件通过 Docker volume 持久化，不打进镜像。

### 3.3 备份与迁移

已提供基于 SQLite online backup API 的一致性备份与校验恢复，支持 WAL 模式：

```bash
python scripts/backup_db.py
python scripts/restore_db.py --from data/backups/<backup>.db --yes
```

恢复前必须停止应用；脚本会校验源文件、自动备份当前库并原子替换目标文件。不得用普通 `cp` 复制运行中的数据库。

### 3.4 何时迁移 PostgreSQL

只有出现以下需求时，再迁移 PostgreSQL：

- 多机器同时访问同一个研究库。
- Web 与 monitor 并发读写明显触发 SQLite 锁等待。
- 需要更强权限、全文搜索、物化视图或 BI 接入。
- 行情快照从辅助上下文升级为大量历史时序数据。

当前阶段不引入 MongoDB、ClickHouse、向量库或 TimescaleDB 作为主库。

---

## 4. Docker 部署边界

### 4.1 容器内容

容器内包含：

```text
market-monitor CLI
FastAPI Web/API
Vue 静态构建产物
Alembic migration
运行时依赖
```

容器外通过 volume 持久化：

```text
./data      -> /app/data
./config    -> /app/config
./logs      -> /app/logs
./reports   -> /app/reports
```

### 4.2 Compose 目标形态

```yaml
services:
  app:
    build: .
    command: market-monitor-web
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      MARKET_DB_URL: sqlite:////app/data/market.db
    volumes:
      - ./data:/app/data
      - ./config:/app/config:ro
      - ./logs:/app/logs
      - ./reports:/app/reports
```

生产容器建议使用多阶段构建：

```text
Node stage
  -> 构建 frontend/dist

Python stage
  -> 安装 market-monitor
  -> 复制 frontend/dist 到 /app/frontend/dist
  -> FastAPI 挂载静态文件并回退到 index.html
```

本地开发可以拆成两个服务：

```text
backend  FastAPI on :8000
frontend Vite dev server on :5173
```

Docker 正式部署则只需要一个 `app` 服务即可。

### 4.3 安全边界

- 默认只绑定 `127.0.0.1`。
- 配置文件只读挂载。
- 密钥不进入前端，不在页面展示完整值。
- 写操作先限定为研究库轻写：批注、act/skip、纸面交易。
- 不在 Web 首版提供实盘下单能力。

---

## 5. 实施阶段

### Phase W0：Web 基础设施

目标：建立可运行的本地 Web 服务和 Docker 部署骨架。

任务：

1. 新增 `market_monitor/api/server.py`。
2. 新增 `market_monitor/api/routes/`：
   - `health.py`
   - `signals.py`
   - `pushes.py`
   - `trades.py`
3. 新增 `frontend/`：
   - `package.json`
   - `vite.config.ts`
   - `src/main.ts`
   - `src/App.vue`
   - `src/router.ts`
   - `src/api/client.ts`
4. FastAPI 增加静态文件挂载：
   - `/assets/*` 服务 Vue 构建资源
   - 非 `/api/*` 路由回退到 `index.html`
5. `pyproject.toml` 增加可选依赖：
   - `fastapi`
   - `uvicorn`
6. 增加 console script：
   - `market-monitor-web = market_monitor.api.server:main`
7. 新增 `Dockerfile`、`.dockerignore`、`docker-compose.yml`。
8. 容器启动前执行：
   - `alembic upgrade head`
   - `market-monitor db init`（幂等）

验收：

- `market-monitor-web` 本机可启动。
- `frontend` 本地可通过 Vite 开发服务器访问。
- `docker compose up --build` 可启动。
- 访问 `http://127.0.0.1:8000/api/health` 返回健康状态。
- 访问 `http://127.0.0.1:8000/` 返回 Vue 页面。
- 现有 `market-monitor` CLI 不受影响。

W0-W1 实施状态（2026-07-18）：已完成。基础 API、Vue 工程、Docker 多阶段构建、SQLite volume、启动迁移、健康检查和全部只读接口已落地。

### Phase W1：只读 API

目标：先稳定数据契约，让页面只是 API 的一个消费者。

接口：

```text
GET /api/health
GET /api/monitors
GET /api/signals?days=&monitor=&level=&type=&limit=&offset=
GET /api/signals/{id}
GET /api/pushes?days=&monitor=&level=&limit=&offset=
GET /api/pushes/{id}
GET /api/trades?status=&symbol=&limit=&offset=
GET /api/stats/summary?days=
```

原则：

- API 使用 repository 或已有 CLI JSON 序列化逻辑。
- 不在 API 层复制复杂业务判断。
- 返回字段尽量与 CLI `--json` 契约一致。

验收：

- OpenAPI 文档可访问。
- 7 天信号、推送、交易可稳定返回。
- 测试覆盖 API smoke test。

### Phase W2：Today + Signals 页面

目标：做出每天真正会打开的最小研究库页面。

页面：

```text
/              Today
/signals       信号列表
/signals/{id}  信号详情
```

Today 内容：

- 今日最高信号等级。
- 今日信号数量。
- 最近推送。
- 待验证信号。
- 最近纸面交易动作。

Signals 内容：

- 日期范围筛选。
- monitor 筛选。
- level 筛选。
- signal_type 筛选。
- 信号详情展示：
  - title
  - summary
  - metrics_json
  - evidence/context
  - 关联 push
  - 关联 trade/action

验收：

- 通过浏览器可完成“回看最近 7 天信号并打开详情”。
- 页面不要求 AI 即时生成解释。
- 页面不承担信号检测逻辑。
- 前端路由刷新不 404。
- API client 有统一错误展示。

W2 实施状态（2026-07-18）：已完成 Today、Signals、Signal Detail 的研究流程；筛选项来自 registry，列表支持服务端分页，详情展示关联 push、人工判断和 paper trade。Today 已接入 stats、signals、pushes、trades 聚合数据。

### Phase W3：轻写操作

目标：把研究过程中的人工动作沉淀到库里。

功能：

- 在信号详情页标记：
  - `act`
  - `skip`
  - `watch`
  - `noise`
- 为信号添加简短批注。
- 从信号详情创建纸面交易。
- 关联已有纸面交易。

原则：

- 写操作必须复用现有 trade / signal action repository。
- 不直接修改不可变的原始 signal fact。
- 人工判断写入独立 action/note 字段或关联表。

验收：

- 信号详情页可以完成 act/skip 标记。
- 标记后 CLI 查询仍能看到同一事实。
- 测试覆盖幂等和错误输入。

W3 实施状态（2026-07-18）：已完成。支持 act/skip/watch/noise、信号笔记、关联已有交易、从信号创建交易；新增数据独立存储，CLI `signal show --json` 可见，写接口有校验、幂等键和可选 token。

### Phase W4：Reviews 页面

目标：把周/月复盘变成可浏览、可追溯的研究工作流。

页面：

```text
/reviews/weekly
/reviews/monthly
```

内容：

- 最近一周信号统计。
- 高等级信号回顾。
- 纸面交易 PnL 与行动偏差。
- 命中/未命中 outcome 摘要。
- 可导出 Markdown。

验收：

- 周报页面可替代常用 CLI review 查看流程。
- 仍保留 CLI 复盘命令作为一等接口。

W4 实施状态（2026-07-18）：已完成。周/月复盘支持生成、历史浏览、交易统计、判断分布、信号验证、最佳/最差交易和 Markdown 导出。

### Phase W5：System 页面

目标：提供本地运维可视化，但不让它喧宾夺主。

页面：

```text
/system
```

内容：

- monitor 注册表。
- 最近运行/推送时间。
- 数据库路径和表行数。
- `doctor --ci` 状态。
- 配置项存在性检查，不展示完整密钥。

验收：

- 能判断系统是否健康。
- 不允许在首版页面直接编辑敏感配置。

W5 实施状态（2026-07-18）：已完成。系统页展示脱敏数据库信息、doctor 检查、monitor 推送状态、表行数和浏览器会话级写入 token；不提供配置编辑。

---

## 6. 文件清单

预计新增：

```text
market_monitor/
  api/
    __init__.py
    server.py
    deps.py
    routes/
      __init__.py
      health.py
      signals.py
      pushes.py
      trades.py
      stats.py

frontend/
  package.json
  package-lock.json
  index.html
  vite.config.ts
  tsconfig.json
  src/
    main.ts
    App.vue
    router.ts
    api/
      client.ts
      types.ts
    views/
      TodayView.vue
      SignalsView.vue
      SignalDetailView.vue
      TradesView.vue
      ReviewsView.vue
      SystemView.vue
    components/
      AppShell.vue
      SignalTable.vue
      LevelBadge.vue
    styles/
      app.css

Dockerfile
.dockerignore
docker-compose.yml
scripts/docker_entrypoint.sh
tests/test_web_api.py
frontend Vitest tests
```

预计修改：

```text
pyproject.toml
README.md
docs/OPENCLAW_USAGE.md
docs/RESEARCH_OS_UPGRADE_PLAN.md
```

---

## 7. 测试策略

### 7.1 单元与集成测试

- API 使用临时 SQLite 数据库。
- 使用现有 seeds 初始化 registry。
- 覆盖：
  - `/api/health`
  - `/api/signals`
  - `/api/signals/{id}`
  - `/api/pushes`
  - `/api/trades`

### 7.2 Docker 验证

每次 Web 基础设施变更后运行：

```bash
docker compose build
docker compose run --rm app market-monitor doctor --ci
docker compose up
```

前端本地验证：

```bash
cd frontend
npm install
npm test
npm run build
```

手动访问：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/api/health
```

### 7.3 现有回归

Web 改造不应破坏现有质量门禁：

```bash
bash scripts/verify.sh
python -m pytest
python -m market_monitor.cli doctor --ci
```

---

## 8. 非目标

首版不做：

- 实盘交易。
- 多用户权限系统。
- 过早引入复杂前端工程化和重型组件库。
- Streamlit 正式页面。
- macOS/Windows/iOS 原生客户端。
- PostgreSQL/TimescaleDB 迁移。
- 向量库作为主事实源。

这些都可以后置，避免 Web 首版范围膨胀。

---

## 9. 里程碑建议

```text
M1  Docker 可启动 Web skeleton
M2  API 可读 signals/pushes/trades/stats
M3  Vue Today + Signals 页面可日常使用
M4  信号详情轻写 act/skip/note
M5  Reviews + System 页面补齐
```

项目进入 Web 阶段后的核心验收句：

> 浏览器页面能稳定回看、筛选、解释和标记市场信号；CLI、OpenClaw 和 Docker 部署仍然同等可靠。

## 10. v1 收口状态

截至 2026-07-18，W0-W5 已进入最终验收。v1 保持以下边界：本机单用户、SQLite 主库、无实盘交易、无敏感配置编辑、无原生客户端。后续需求按实际并发和使用频率决定，不预先引入 PostgreSQL、桌面壳或重型状态管理。
