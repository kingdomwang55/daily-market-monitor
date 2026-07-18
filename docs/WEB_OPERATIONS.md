# Web 与 Docker 运行手册

## 启动与升级

```bash
docker compose up --build -d
docker compose ps
curl -f http://127.0.0.1:8000/api/health
```

容器启动时会先执行 `alembic upgrade head` 和幂等 registry 初始化。数据库位于宿主机 `data/market.db`，配置目录以只读方式挂载。

拉取代码后重复执行 `docker compose up --build -d` 即可升级。迁移应向前兼容；升级前建议先备份。

## 本地访问与安全

Compose 默认发布到 `127.0.0.1:8000`，不会监听局域网地址。Web 不提供实盘交易或敏感配置编辑。

本机单用户可以不设置写入令牌。需要额外保护写接口时：

```yaml
services:
  app:
    environment:
      MARKET_WEB_TOKEN: "replace-with-a-long-random-value"
```

重启容器后，在 `/system` 的“写入令牌”中输入同一值。令牌仅保存在浏览器 `sessionStorage`，关闭会话后清除；读接口始终可用。不要把真实令牌提交到仓库。

## 备份

运行中的 WAL 数据库必须通过 SQLite online backup API 备份：

```bash
python scripts/backup_db.py
python scripts/backup_db.py --output /absolute/path/market-backup.db
```

默认输出到 `data/backups/`。命令完成前会执行 `PRAGMA integrity_check`，再原子发布备份文件。

Docker 环境也可在宿主机执行以上命令，因为 `data/` 是 bind volume。建议在版本升级前和定期任务中执行。

## 恢复

恢复时必须停止所有可能写库的进程，包括 Docker app 和本机 monitor：

```bash
docker compose stop app
python scripts/restore_db.py --from data/backups/market-20260718-120000.db --yes
docker compose up -d app
curl -f http://127.0.0.1:8000/api/health
```

恢复脚本会先校验源文件，在 `data/backups/` 保存 `pre-restore` 版本，再通过临时文件原子替换数据库。`--yes` 表示已确认应用停止。

## 验证

```bash
.venv/bin/pytest -q
cd frontend && npm test && npm run build
cd ..
.venv/bin/python -m market_monitor.cli doctor --ci
docker compose run --rm app market-monitor doctor --ci
```

浏览器检查：

- `/` 今日概览有数据或明确空状态。
- `/signals` 可筛选、打开详情并记录判断/笔记。
- `/trades` 可创建、筛选、打开和关闭纸面交易。
- `/reviews/weekly` 与 `/reviews/monthly` 可生成并导出 Markdown。
- `/system` 不展示 API key、secret 或完整连接凭据。

## 排障

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose exec app market-monitor db info
docker compose exec app market-monitor doctor --ci
```

若写操作返回 `401`，检查容器的 `MARKET_WEB_TOKEN` 与系统页当前会话令牌是否一致。若迁移失败，不要手工改 `alembic_version`；先保留日志和数据库备份，再修复迁移或回退应用镜像。
