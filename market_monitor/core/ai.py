"""AI 分析"""
import json
import urllib.request
import sys
from typing import Optional

from .config import get_config


def _call_model(url: str, api_key: str, model: str, prompt: str,
                temperature: float, max_tokens: int, timeout: int) -> Optional[str]:
    """单次调用。返回 content 或 None。失败抛异常。

    针对推理模型（返回 reasoning_content + content）：如果 content 为空但
    finish_reason=length 且有 reasoning_content，说明 max_tokens 不够导致答案
    被截断在推理段。此时自动加大 max_tokens 重试一次。
    """
    def _post(mt: int):
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
                "max_tokens": mt,
            }).encode("utf-8"),
        )
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))

    result = _post(max_tokens)
    choice = result["choices"][0]
    content = (choice["message"].get("content") or "").strip()
    finish = choice.get("finish_reason")
    reasoning = (choice["message"].get("reasoning_content") or "").strip()

    if content:
        return content

    # 推理模型 max_tokens 不够被截断在思考段：加大重试一次
    if finish == "length" and reasoning and max_tokens < 6000:
        boosted = max(min(max_tokens * 2, 6000), 3000)
        print(f"[ai] {model} 推理占满 max_tokens={max_tokens}，加大到 {boosted} 重试", file=sys.stderr)
        result2 = _post(boosted)
        content2 = (result2["choices"][0]["message"].get("content") or "").strip()
        if content2:
            return content2

    return None


def ai_chat(prompt: str, temperature: float = 0.7, max_tokens: int = 2000,
            timeout: int = 60) -> Optional[str]:
    """调用 AI 生成回答。主模型失败自动 fallback 到备选模型；两者都失败返回 None。"""
    cfg = get_config()
    base_url = cfg.ai_base_url
    api_key = cfg.ai_api_key
    primary = cfg.ai_model
    fallbacks = cfg.ai_fallback_models or []

    if not (base_url and api_key):
        print("[ai] 缺少 AI 凭据", file=sys.stderr)
        return None

    # 兼容 base_url 是否带 /v1
    if not base_url.rstrip("/").endswith("/v1"):
        url = base_url.rstrip("/") + "/v1/chat/completions"
    else:
        url = base_url.rstrip("/") + "/chat/completions"

    # 主模型 -> fallback 链，去重且保序
    candidates = [primary]
    for m in fallbacks:
        if m and m not in candidates:
            candidates.append(m)

    for idx, model in enumerate(candidates):
        try:
            content = _call_model(url, api_key, model, prompt,
                                  temperature, max_tokens, timeout)
            if content:
                if idx > 0:
                    print(f"[ai] 主模型 {primary} 失败，已 fallback 到 {model}", file=sys.stderr)
                return content
            print(f"[ai] 模型 {model} 返回空内容", file=sys.stderr)
        except Exception as e:
            print(f"[ai] 模型 {model} 失败: {e}", file=sys.stderr)

    return None
