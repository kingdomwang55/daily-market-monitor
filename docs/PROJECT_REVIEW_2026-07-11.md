# daily-market-monitor 项目评估与审查报告

| 字段 | 内容 |
|------|------|
| **审查日期** | 2026-07-11 |
| **审查范围** | 整仓静态审查（`main` 分支，工作区干净，`HEAD` = 最近 30 次提交） |
| **审查方式** | 架构/文档对照、源码通读抽样、依赖与运维脚本检查、测试覆盖统计 |
| **审查对象** | `market_monitor/`、`scripts/`、`config/`、`launchd/`、`docs/`、`tests/`、`pyproject.toml` |
| **不在范围** | 生产运行日志回放、真实行情/飞书联调、性能压测、安全渗透 |

---

## 1. 执行摘要

**market-monitor** 是一套面向个人的多市场智能监控系统：覆盖 A 股 / 港股 / 美股 / 大宗与宏观，通过 launchd 定时运行、飞书推送、可选 AI 解读，并已演进到「推送落库 + 纸面交易 + 估值/溢价筛选」阶段。

**总体评价：作为个人量化辅助工具，架构清晰、功能迭代快、文档意识强，已具备日常可用骨架；作为可长期维护的工程资产，测试与可移植性明显欠账，部分基础设施与依赖声明尚未闭环。**

| 维度 | 评分 (1–5) | 一句话 |
|------|------------|--------|
| 产品完整度 | **4.0** | 监控矩阵 + CLI + 交易日志 + 筛选器，功能面宽 |
| 架构清晰度 | **3.5** | 分层意图明确，部分双轨实现与文档滞后 |
| 代码质量 | **3.5** | 可读性好，容错偏「吞异常」，大文件膨胀 |
| 测试与质量门禁 | **1.5** | 仅 1 个解析单测文件，无 CI |
| 安全与凭据 | **3.5** | 敏感配置已 gitignore；飞书用 curl 子进程；依赖 HTTP 数据源 |
| 可运维 / 可移植 | **2.5** | launchd 硬编码旧机器路径；路径假设强 |
| 文档 | **4.0** | 架构、迭代、数据源文档丰富；入口 README 漂移 |
| **综合** | **3.3 / 5** | **可日常使用，建议优先补测试、可移植与依赖/迁移闭环** |

### 优先处理（P0）

1. **修复 launchd / `gen_launchd.py` 中硬编码的旧用户路径**（当前指向 `$HOME/...`），否则本机安装会静默跑错或跑不起来。
2. **补齐运行时依赖声明**：`us_treasury.py` 使用 `requests`，但 `pyproject.toml` 未声明；`alembic` 已声明却无迁移工程。
3. **README / 架构文档与真实 REGISTRY 对齐**（14 个 monitor 中仅约一半出现在 README）。

### 优先处理（P1）

4. 测试从「仅解析器」扩展到：config、state 去重、monitor 阈值、repository、CLI 烟雾测试。
5. 推送双写（JSONL `push_logger` + SQL `push_log`）明确主从与迁移路径。
6. 状态落盘失败静默吞掉（`State.save`）应至少打日志。
7. 硬编码 `~/projects/market-monitor` 改为基于 `PROJECT_ROOT` / 配置。

---

## 2. 项目画像

### 2.1 规模

| 指标 | 数值 |
|------|------|
| 源码规模 | 约 **14,867** 行 Python（`market_monitor/`，不含 `__pycache__`） |
| Python 模块数 | **63** |
| 注册 Monitor | **14**（stabilize / us_market / hk_market / shock / hk_shock / price_alert / morning / evening / voice / macro / review / monthly / midday / pulse） |
| launchd 模板 | **11** 个 plist |
| 测试文件 | **1**（`tests/test_data_source.py`，约 59 行） |
| 文档 | `docs/` 约 **3,100+** 行 Markdown（含迭代与数据源目录） |
| Git 历史 | **30** commits，单作者 `kingdomwang55` |
| 版本 | `0.1.0`（`pyproject.toml`） |

### 2.2 技术栈

- **语言 / 运行时**：Python ≥ 3.9，标准库 HTTP 为主
- **配置**：YAML（`pyyaml`）
- **持久化**：SQLAlchemy 2.0 + SQLite（WAL），设计兼容 PostgreSQL
- **调度**：macOS `launchd`
- **通知**：飞书 Open API（通过 `curl` 子进程）
- **AI**：可配置 OpenAI 兼容接口（custom / deepseek）
- **数据源**：新浪、东方财富、美国财政部 CSV、RSS/网页抓取等

### 2.3 设计原则（项目自述，审查确认）

| 原则 | 落地情况 |
|------|----------|
| 触发才推 | 多数 shock/alert 类 monitor 有 state 去重与阈值；force/snapshot 覆盖合理 |
| 分级预警 | shock 等模块阈值清晰 |
| 配置驱动 | 标的与阈值多在 YAML；部分逻辑仍硬编码在模块内 |
| 可插拔 Monitor | `BaseMonitor` + `REGISTRY` 模式清晰，扩展路径文档化 |
| 可测试 | **原则写了，实践远未跟上** |

---

## 3. 架构评估

### 3.1 分层（优点）

```
CLI → Monitors → Core (config / data_source / feishu / state / AI / …)
                → Data (SQLAlchemy models + repositories)
                → External (Sina / Eastmoney / Feishu / AI / Treasury)
```

- **Monitor 插件化**：`registry.py` 集中注册，CLI `run <name>` 统一入口。
- **BaseMonitor 横切**：推送、落库、时间字段、日志格式一致。
- **数据层设计意识强**：Meta / Raw / Event / Derived 分层、Repository 封装、`MARKET_DB_URL` 可切换库——见 `docs/DATA_LAYER_DESIGN.md`。
- **容错主路径优先**：行情落库、推送落库失败一般不阻断飞书发送（对个人工具合理）。

### 3.2 架构风险与债务

#### (1) 文档与实现双轨 / 漂移

| 文档声称 | 实际 |
|----------|------|
| ARCHITECTURE 列出 5 个 monitor | REGISTRY 有 **14** 个 |
| README「可用监控名称」约 7 个 | 缺 hk_shock / voice / macro / review / monthly / midday / pulse |
| DATA_LAYER「正式流程用 Alembic」 | 仓库内 **无** `alembic.ini` / versions；依赖仍声明 `alembic` |
| AlertDedup「替代 JSON state」 | 运行时仍主要依赖 `/tmp/*_state.json` |
| 数据层「Phase 1 落地中」 | models/repos 已较完整，但 Derived（outcome 回填、daily_summary 物化）与种子使用深度不一 |

#### (2) 推送与状态「双轨存储」

- **去重**：JSON `State`（文件）
- **推送日志**：`push_logger` JSONL + SQL `push_log`（BaseMonitor._log_push）
- 成功路径上可能 **双写**（feishu 成功 → JSONL；BaseMonitor.send → SQL），增加一致性心智负担，长期应定主库。

#### (3) 路径与机器绑定

- `scripts/gen_launchd.py`：`PYTHON = "$PROJECT_ROOT/.venv/bin/python"`
- 已生成的 `launchd/*.plist`：`WorkingDirectory` / `PYTHONPATH` / Python 解释器均绑定该路径
- `cli.py` logs/notes：`Path.home() / "projects" / "market-monitor" / ...`
- `position_tracker` 文档/默认路径：`~/projects/market-monitor/positions.json`
- 当前仓库位于 `/Users/yehlv/idea-project/daily-market-monitor` —— **与模板路径不一致**

对个人单机可跑，但换机/换用户/换目录即失败，可移植性评分被显著拉低。

#### (4) CLI 上帝模块

`market_monitor/cli.py` 约 **928** 行，集中了 run/list/status/logs/query/note/decision/db/trade/screen 等。功能完整，但：

- 难以单测
- 职责过多，后续建议按子命令拆到 `cli/` 包

#### (5) 数据源层耦合

`data_source.sina_realtime` 在拉取时同步尝试写 `MarketSnapshot`，解析器与持久化耦合。测试解析时若 DB 可用会产生副作用；文档也写了「Mock 数据源」，但生产路径侧写库使 mock 成本升高。

---

## 4. 功能模块审查

### 4.1 监控矩阵

| Monitor | 角色 | 备注 |
|---------|------|------|
| stabilize | A 股企稳信号 | 核心告警类 |
| shock / hk_shock | A/港异动 | 分级 + 板块联动思路清晰 |
| price_alert | 关键点位 | 配置驱动止损/加仓位 |
| us_market / hk_market | 外盘/港股快照与阈值 | 时段依赖 launchd |
| morning / evening / midday / pulse | 定时报告节奏 | 功能面大，evening/morning 行数高，维护成本高 |
| voice / macro / review / monthly | 舆情/宏观/复盘/月度 | README 未列全 |
| 另有 CLI screen | 烟蒂股筛选 | 不在 REGISTRY 也可独立入口 |

**优点**：产品迭代节奏快（W1–W4、DS-1 均有迭代文档），功能贴合「个人盯盘 + 学习」场景（teaching / tip / query）。

**风险**：模块数量增长快于测试与架构文档；morning/evening 聚合过多分析模块，单点失败策略依赖大量 `try/except`。

### 4.2 分析与扩展模块（core/）

较大模块（行数）：`teaching`、`decision_tracker`、`position_tracker`、`ah_premium`、`index_valuation`、`cigar_butt`、`etf_premium` 等。

- **优点**：领域边界按文件拆分；迭代文档（`docs/iterations/`）记录动机与已知坑，利于个人回顾。
- **风险**：无统一接口约束（除 Monitor）；异常多为宽捕获；部分依赖外部页面结构，易碎。

### 4.3 数据层

**优点：**

- SQLAlchemy 2.0 `Mapped` 类型注解现代
- 索引与 FK 设计认真
- `get_session()` 事务边界正确
- SQLite WAL + foreign_keys 合理
- 纸面交易表（PaperTrade / TradeSignalLink / TradeReview）与信号链路设计有产品远见

**问题：**

- `alembic` 依赖悬空：无迁移脚本，schema 演进靠 `create_all`，生产数据升级路径缺失
- `datetime.utcnow` 全库使用：Python 3.12+ 已弃用，建议 `datetime.now(timezone.utc).replace(tzinfo=None)` 或 aware UTC
- `MarketSnapshot.trade_date` 注解为 `Mapped[datetime]` 却列类型为 `Date`——类型标注不准确
- 快照写入对 symbol FK 依赖：若种子未写入 `symbol_registry`，落库可能失败（虽被吞掉）

### 4.4 飞书与 AI

- 凭据优先级：**环境变量 > YAML**，设计正确；`config.yaml` / `positions.json` 已 gitignore。
- 实现用 **subprocess + curl**，不依赖 `requests`（与 treasury 模块不一致），在沙箱/无 curl 环境会失败；token 每次发送都申请，无缓存，高频推送时多一次 RTT。
- AI 模块标准库 urllib，超时可配，方向正确。

---

## 5. 代码质量细节

### 5.1 做得好的地方

1. **Monitor 契约简单**：`name` / `display_name` / `run() -> bool`
2. **配置点路径** `config.get("a.b.c")` 使用方便
3. **解析器与测试**：`test_data_source.py` 覆盖了主要 sina 解析边界（含空字段）
4. **敏感文件策略**：`.gitignore` 覆盖 config、positions、sqlite、logs
5. **「推送优先」错误处理哲学** 一致，适合告警系统

### 5.2 问题清单（按严重度）

#### Bug / 高优先级

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| B1 | `scripts/gen_launchd.py` + `launchd/*.plist` | Python / WorkingDirectory 硬编码为 `$PROJECT_ROOT` | 用 `PROJECT_ROOT` + `sys.executable` 或 env 生成；重新 `gen_launchd` 并安装 |
| B2 | `core/us_treasury.py` | `import requests` 未列入 `pyproject.toml` dependencies | 加入 `requests`，或改为 `urllib` 与全库一致 |
| B3 | `State.save` | 写盘失败 `except: pass`，去重可能失效导致 **重复轰炸** | 至少 stderr 打错误；可选失败时返回 bool |
| B4 | 依赖环境 | 审查机上 `yaml` 未安装，`pip install -e .` 未作为默认闭环验证 | 安装脚本检查依赖；README 写清必须依赖（非「可选」） |

#### 设计 / 中优先级

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| D1 | README / ARCHITECTURE | 与 REGISTRY、CLI 能力严重漂移 | 生成式文档或单测断言 README 列表 ⊆ REGISTRY |
| D2 | 推送双写 | JSONL + SQL 两套历史 | 以 SQL 为主；JSONL 作兼容或弃用时间表 |
| D3 | `cli.py` / 超大 monitor | 上帝模块 | 拆分 CLI；morning/evening 拆 section builder |
| D4 | 无 Alembic 工程 | schema 变更无版本 | 补 alembic 或从依赖中移除并文档化 create_all-only |
| D5 | `sina_realtime` 侧写库 | 解析/IO/持久化耦合 | 可选参数 `persist=False`；默认由 monitor 显式调用 |
| D6 | 路径硬编码 | notes/logs/positions | 全部走 `common.*` 配置或 `PROJECT_ROOT` |
| D7 | HTTP 明文行情 | `http://hq.sinajs.cn` 等 | 能升 HTTPS 则升；否则文档标明中间人风险（个人工具可接受） |

#### 低优先级 / Nit

| # | 问题 | 建议 |
|---|------|------|
| N1 | 大量 `print(..., file=sys.stderr)`，无统一 logging | 核心路径用 `logging`，launchd 更易过滤 |
| N2 | `datetime.utcnow` 弃用 | 统一 timeutil |
| N3 | emoji 与中文日志混用 | 个人工具可接受；若自动化解析日志建议加纯文本 level |
| N4 | `pyproject` 无 optional dev deps（pytest、ruff） | 增加 `[project.optional-dependencies] dev` |
| N5 | bare/`except Exception` 过宽 | 至少记录 stack 或分类网络错误 |

---

## 6. 测试与质量门禁

| 项 | 现状 | 目标建议 |
|----|------|----------|
| 单元测试 | 1 文件，约 5 个解析用例 | 解析全覆盖 + state 去重 + 阈值 level_of |
| Monitor 测试 | 无 | 注入 mock data_source，断言是否 send |
| Repository 测试 | 无 | sqlite `:memory:` 测 trade/push |
| CLI 烟雾 | 无 | `list` / `db info` 子进程测试 |
| 类型检查 | 未配置 mypy/pyright | 可选逐步启用 |
| Lint | 无 ruff/flake8 配置 | 加 ruff 基础规则 |
| CI | 无 | GitHub Actions：install + pytest |
| 覆盖率 | ≪ 5% 估算 | 先到 30% 核心路径 |

**结论**：设计原则写了「可测试 / Mock 数据源」，但工程上几乎只有解析器回归。这是当前最大工程短板——任何重构（尤其 cigar_butt、数据层、CLI）都缺乏安全网。近期 git 历史中已有「P0 崩溃修复」类提交，侧面印证缺少回归测试。

---

## 7. 安全与隐私

| 项 | 评估 |
|----|------|
| 凭据入库 | 示例配置用占位符；真实 config/positions 已忽略 — **良好** |
| 飞书 token | 内存/curl 参数，未写日志 — **可接受**；子进程参数列表可能被 `ps` 窥见 — 个人机风险低 |
| 持仓/月薪 | `positions.json` 敏感且已 gitignore — **良好**；注意备份别进公开云 |
| 外部数据 | 非官方 scrape/免费接口，可用性与 ToS 风险需自负 |
| 供应链 | 依赖少，攻击面小；`requests` 未声明导致环境不一致 |
| SQL | 走 ORM，注入风险低 |

**未发现**仓库内明文 app_secret / api_key 提交（基于示例与 gitignore 策略；未做完整 git history 密钥扫描）。

---

## 8. 运维与部署

### 8.1 安装链路

- `scripts/install.sh` / `uninstall.sh` / `gen_launchd.py` / `health_check.py` 形成闭环意图清晰。
- **阻塞点**：plist 内 Python 与项目路径绑定旧机器；当前 workspace 路径不同，直接 load 旧 plist 会失败。

### 8.2 调度

- 交易日日历调度（weekday 1–5）合理。
- 日志打到 `/tmp/com.market-monitor.*.{log,err}`，重启/清理 /tmp 可能丢日志；macOS 上 /tmp 也非永久。

### 8.3 可观测性

- `cli status` 过滤 launchctl
- `cli logs` 多路径猜测
- `health_check.py` 有状态文件
- 缺：结构化 metrics、失败告警（监控自身挂了谁来告警？）

---

## 9. 文档评估

| 文档 | 评价 |
|------|------|
| `docs/iterations/*` | **优秀**：动机、接口、已知问题模板化 |
| `docs/DATA_LAYER_DESIGN.md` | **优秀**：分层与演进路径清楚 |
| `docs/data-sources/*` | **良好**：缺口分析有产品价值 |
| `docs/ADD_MONITOR.md` / `ALERTS.md` | 实用 |
| `docs/ARCHITECTURE.md` | **过时**（monitor 列表、数据层表述） |
| `README.md` | **入口不足**：功能与命令列表落后；「纯标准库也能跑」与 sqlalchemy/pyyaml/requests 现实冲突 |

---

## 10. 依赖与工程卫生

```toml
# pyproject.toml 声明
pyyaml>=6.0
sqlalchemy>=2.0
alembic>=1.13
```

| 依赖 | 使用情况 | 问题 |
|------|----------|------|
| pyyaml | 必需 | README 写「可选」易误导 |
| sqlalchemy | 数据层 | 模块 import 时可能触发 DB 目录创建 |
| alembic | **未落地** | 应补齐或移除 |
| requests | us_treasury **使用但未声明** | 安装不完整会 ImportError |
| curl | feishu 运行时依赖 | 未文档化为系统依赖 |

其他：

- 无 `requirements.lock` / uv.lock
- 无 pre-commit
- `data/` 目录由 runtime mkdir，git 中可不存在（合理）

---

## 11. 优势总结（应保留）

1. **清晰的个人产品定位**：盯盘 + 教学 + 复盘 + 纸面交易，不是空壳脚手架。
2. **Monitor 插件模型** 扩展成本低，有 ADD_MONITOR 文档。
3. **数据层前瞻设计**（分层表、Repository、可切 PG）超出典型脚本项目。
4. **迭代文档文化** 强，利于单人长期维护记忆。
5. **触发才推 + 分级阈值** 产品原则贯彻较好。
6. **敏感配置隔离** 正确。

---

## 12. 改进路线图（建议）

### 第 0 周（立刻，阻塞可用性）

- [ ] 修正 `gen_launchd.py` 使用本机 `PROJECT_ROOT` 与 venv/`sys.executable`
- [ ] 重新生成并安装 launchd plist
- [ ] `pyproject.toml` 加入 `requests`；明确 alembic 去留
- [ ] 验证 `pip install -e .` + `python -m market_monitor.cli list` 在干净环境可跑

### 第 1–2 周（质量底座）

- [ ] 核心单测：data_source 全解析、State 去重、shock level、trade_repo 内存库
- [ ] `State.save` 失败可见
- [ ] README 用脚本或手写同步 REGISTRY + 主要 CLI
- [ ] 路径统一到 PROJECT_ROOT / config

### 第 3–4 周（架构收敛）

- [ ] 推送日志以 SQL 为准；JSONL 兼容层标 deprecated
- [ ] Alembic 初始化或文档改为 create_all-only 并删依赖
- [ ] CLI 拆包；feishu 改为 urllib/requests + token 缓存
- [ ] 可选：最简 CI（pytest）

### 中期（产品）

- [ ] signal_outcome 自动回填（设计已预留）
- [ ] 自身健康失败时的飞书/本地告警
- [ ] 数据源失败降级策略统一（缓存上次快照）

---

## 13. 风险登记册（摘要）

| ID | 风险 | 可能性 | 影响 | 缓解 |
|----|------|--------|------|------|
| R1 | launchd 路径错误导致定时全挂 | 高（换机后） | 高 | 动态生成 plist |
| R2 | 免费 API/页面改版 | 中高 | 中 | 多源 + 健康检查 + 测试夹具 |
| R3 | 无测试下重构引入回归 | 高 | 中高 | 补测再重构 |
| R4 | schema 变更打坏本地 DB | 中 | 中 | Alembic 或备份脚本 |
| R5 | State 写失败导致重复推送 | 低 | 中 | 显式错误日志 + 磁盘检查 |
| R6 | 依赖声明不全导致间歇 ImportError | 中 | 中 | 锁依赖 + install 校验 |

---

## 14. 结论

**daily-market-monitor 是一个完成度高于平均水平的个人市场监控系统**：功能纵深（多市场监控、AI、教学、纸面交易、估值/溢价/烟蒂筛选）与文档纵深（迭代笔记、数据层设计、数据源目录）都值得肯定。

当前主要短板不在「会不会做功能」，而在 **工程化底座**：

1. **可移植运维**（硬编码路径）  
2. **测试与 CI 几乎空白**  
3. **依赖与迁移声明未闭环**  
4. **入口文档滞后于真实能力**

建议将下一阶段迭代重心从「继续加监控模块」暂时切到 **P0 可运行性 + 最小测试网 + 文档/配置收敛**，再推进 Phase 2 信号验证与可视化。以当前代码体量（~15k LOC）与模块数，若不补安全网，维护成本会非线性上升。

---

## 附录 A：审查方法说明

- 静态阅读：`README`、`ARCHITECTURE`、`DATA_LAYER_DESIGN`、`pyproject.toml`、`config.example.yaml`、核心 base/config/feishu/data_source/database/models、registry、cli 结构、launchd 样例、gen_launchd、测试目录。
- 自动化辅助：LOC 统计、语法 `ast.parse` 全量通过、依赖与硬编码路径检索、REGISTRY vs README 对照、`datetime.utcnow` / HTTP / except 模式扫描。
- **未做**：真实 `pip install` 全链路联调、飞书/行情 live 调用、pytest 执行（审查环境缺 pyyaml）。

## 附录 B：关键路径速查

| 路径 | 说明 |
|------|------|
| `market_monitor/cli.py` | CLI 入口（~928 行） |
| `market_monitor/monitors/registry.py` | Monitor 注册表 |
| `market_monitor/core/base.py` | 基类与推送落库 |
| `market_monitor/core/data_source.py` | 行情获取与解析 |
| `market_monitor/data/models.py` | ORM 模型 |
| `scripts/gen_launchd.py` | plist 生成（含硬编码路径） |
| `tests/test_data_source.py` | 唯一成体系单测 |
| `docs/iterations/` | 功能迭代记录 |

## 附录 C：REGISTRY 完整列表（审查时点）

1. stabilize — StabilizeMonitor  
2. us_market — UsMarketMonitor  
3. hk_market — HkMarketMonitor  
4. shock — ShockMonitor  
5. hk_shock — HkShockMonitor  
6. price_alert — PriceAlertMonitor  
7. morning — MorningMonitor  
8. evening — EveningMonitor  
9. voice — VoiceMonitor  
10. macro — MacroMonitor  
11. review — ReviewMonitor  
12. monthly — MonthlyMonitor  
13. midday — MiddayMonitor  
14. pulse — PulseMonitor  

---

*本报告为静态代码评估，不构成投资建议。报告生成日期：2026-07-11。*
