"""AI 分析"""
import json
import urllib.request
import sys
from typing import Optional

from .config import get_config


def ai_chat(prompt: str, temperature: float = 0.7, max_tokens: int = 1000,
            timeout: int = 60) -> Optional[str]:
    """调用 AI 生成回答，失败返回 None"""
    cfg = get_config()
    base_url = cfg.ai_base_url
    api_key = cfg.ai_api_key
    model = cfg.ai_model

    if not (base_url and api_key):
        print("[ai] 缺少 AI 凭据", file=sys.stderr)
        return None

    # 兼容 base_url 是否带 /v1
    if not base_url.rstrip("/").endswith("/v1"):
        url = base_url.rstrip("/") + "/v1/chat/completions"
    else:
        url = base_url.rstrip("/") + "/chat/completions"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }).encode("utf-8"),
        )
        resp = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        result = json.loads(resp)
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[ai] 失败: {e}", file=sys.stderr)
        return None
