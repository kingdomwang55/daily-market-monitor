# Web API 使用说明

API 根路径为 `/api`，完整交互契约可在运行后的 `/docs` 查看。时间使用 UTC ISO 8601，分页接口返回 `items`、`total`、`limit` 和 `offset`。

## 查询

```bash
curl 'http://127.0.0.1:8000/api/signals?days=7&monitor=pulse&level=2&limit=50'
curl 'http://127.0.0.1:8000/api/signals/1'
curl 'http://127.0.0.1:8000/api/trades?status=open&strategy=manual'
curl 'http://127.0.0.1:8000/api/reviews?period_type=week'
curl 'http://127.0.0.1:8000/api/system/status'
```

信号详情聚合原始 signal、push、人工 action、note 和关联 paper trade。原始 signal 不提供更新或删除接口。

## 信号判断与笔记

```bash
curl -X POST 'http://127.0.0.1:8000/api/signals/1/actions' \
  -H 'Content-Type: application/json' \
  -d '{"decision":"watch","reason":"等待量价确认"}'

curl -X POST 'http://127.0.0.1:8000/api/signals/1/notes' \
  -H 'Content-Type: application/json' \
  -d '{"body":"午后继续观察成交量"}'
```

`decision` 仅允许 `act`、`skip`、`watch`、`noise`。重复提交完全相同的 action/note 会返回已有记录和 `created: false`。

## 纸面交易

```bash
curl -X POST 'http://127.0.0.1:8000/api/trades' \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id":"web-20260718-001",
    "symbol":"sh510300",
    "action":"long",
    "strategy":"signal-follow",
    "entry_price":4.20,
    "qty":1000,
    "stop_loss":4.05,
    "take_profit":4.50,
    "signal_event_id":1,
    "entry_reason":"信号确认"
  }'

curl -X PATCH 'http://127.0.0.1:8000/api/trades/1/close' \
  -H 'Content-Type: application/json' \
  -d '{"close_price":4.45,"close_reason":"目标区域止盈"}'
```

`request_id` 是客户端幂等键。同一键和同一载荷返回已有交易；同一键配不同载荷返回 `409`。已关闭交易再次关闭也返回 `409`。所有交易仅为研究记录，不连接券商。

## 复盘

```bash
curl -X POST 'http://127.0.0.1:8000/api/reviews/generate' \
  -H 'Content-Type: application/json' \
  -d '{"period_type":"week"}'

curl -OJ 'http://127.0.0.1:8000/api/reviews/week/2026-W29/markdown'
```

`period_type` 允许 `week` 或 `month`，也可提供对应的 `period_key` 重新生成历史复盘。

## 写入令牌

设置 `MARKET_WEB_TOKEN` 后，所有 POST/PATCH 请求需要以下任一请求头：

```text
X-Market-Token: <token>
Authorization: Bearer <token>
```

GET 接口保持可读。页面在 `/system` 将令牌保存到当前浏览器会话，不会把令牌写入数据库或返回给前端。
