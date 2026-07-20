"""飞书推送"""
import http.client
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

from .config import get_config
from .text_utils import strip_markdown
from . import push_logger

# 允许自动重试的瞬时网络错误
_RETRIABLE_EXC = (
    ssl.SSLError,
    socket.timeout,
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    http.client.BadStatusLine,
    urllib.error.URLError,
)


def _post_json(url: str, payload: dict, headers: Optional[dict] = None,
               timeout: int = 10, retries: int = 3,
               backoff: tuple = (1.0, 3.0, 7.0)) -> dict:
    """POST JSON，支持瞬时网络错误自动重试。

    macOS 系统 Python 3.9 用 LibreSSL 2.8.3，偶发 EOF SSL 瞬断，
    因此对所有网络类异常（SSL/超时/RemoteDisconnected/URLError）做指数退避重试。
    """
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except _RETRIABLE_EXC as e:
            last_exc = e
            # urllib.error.HTTPError 是 4xx/5xx，不属于瞬时错误，直接抛出
            if isinstance(e, urllib.error.HTTPError):
                raise
            if attempt >= retries - 1:
                break
            wait = backoff[min(attempt, len(backoff) - 1)]
            print(f"[feishu] 网络异常重试 {attempt + 1}/{retries - 1}: {e}（{wait}s 后重试）",
                  file=sys.stderr)
            time.sleep(wait)
    # 全部重试失败
    assert last_exc is not None
    raise last_exc


def send_text(message: str, user_id: Optional[str] = None, push_type: str = "manual", meta: Optional[dict] = None) -> bool:
    """发送纯文本消息到飞书

    Args:
        message: 消息内容
        user_id: 接收者 open_id（不传用 config 默认）
        push_type: 推送类型标签（morning/evening/price_alert/shock/stabilize/hk/us/health/manual...）
        meta: 附加元信息（会写入日志）

    适配飞书 text 消息，自动清洗 markdown 符号（**加粗**、## 标题、
    | 表格 | 、--- 分割线等）。
    """
    cfg = get_config()
    app_id = cfg.feishu_app_id
    app_secret = cfg.feishu_app_secret
    receive_id = user_id or cfg.feishu_user_id

    if not (app_id and app_secret and receive_id):
        print("[feishu] 缺少飞书凭据或 user_id", file=sys.stderr)
        return False

    # 上钩前统一清洗 markdown 符号
    message = strip_markdown(message)

    try:
        # 获取 tenant_access_token
        td = _post_json(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": app_id, "app_secret": app_secret},
        )
        if td.get("code") != 0:
            print(f"[feishu] 获取 token 失败: {td}", file=sys.stderr)
            return False
        token = td["tenant_access_token"]

        # 发送消息
        result = _post_json(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            {
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": message}, ensure_ascii=False),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if result.get("code") == 0:
            # 推送成功后同步写日志（失败不影响主链路）
            push_logger.append(message, push_type=push_type, meta=meta)
            return True
        print(f"[feishu] 发送失败: {result}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[feishu] 异常: {e}", file=sys.stderr)
        return False
