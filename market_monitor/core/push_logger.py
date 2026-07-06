"""推送日志：所有飞书推送落 jsonl，供后续同步到飞书日报。

设计原则：
- 永不失败：任何异常吞掉，不影响主推送链路
- 结构化：一行一 JSON，方便脚本消费
- 按日切分：logs/push_YYYY-MM-DD.jsonl
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# 日志根目录：项目根 logs/
_LOG_ROOT = Path(__file__).resolve().parent.parent.parent / "logs"


def _today_path() -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    return _LOG_ROOT / f"push_{day}.jsonl"


def append(message: str, push_type: str = "unknown", meta: Optional[dict] = None) -> None:
    """追加一条推送日志。

    Args:
        message: 完整推送内容
        push_type: 推送类型（morning/evening/price_alert/shock/stabilize/hk/us/health/manual...）
        meta: 附加信息（触发原因、锦囊 id 等）
    """
    try:
        _LOG_ROOT.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z") or datetime.now().isoformat(),
            "type": push_type,
            "summary": _extract_summary(message),
            "length": len(message),
            "message": message,
        }
        # 加时区（isoformat 不带 tz）
        if not record["ts"].endswith(("+0800", "-0000")) and "+" not in record["ts"][-6:]:
            record["ts"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        if meta:
            record["meta"] = meta

        with _today_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        # 永不影响主推送
        print(f"[push_logger] 记录失败（已忽略）: {e}", file=sys.stderr)


def _extract_summary(message: str, max_len: int = 80) -> str:
    """从推送消息中提取一行摘要（首个非空行）"""
    for line in message.split("\n"):
        line = line.strip()
        if line:
            if len(line) > max_len:
                return line[: max_len - 1] + "…"
            return line
    return ""


def read_day(date_str: Optional[str] = None) -> list:
    """读取某天的所有推送记录。

    Args:
        date_str: YYYY-MM-DD，默认今天

    Returns:
        list[dict] 按时间顺序
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    path = _LOG_ROOT / f"push_{date_str}.jsonl"
    if not path.exists():
        return []

    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def format_daily_markdown(date_str: Optional[str] = None) -> str:
    """把某天的推送日志格式化成飞书文档 Markdown。"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    records = read_day(date_str)
    if not records:
        return f"# 📊 推送日志 · {date_str}\n\n> _今日暂无推送记录_\n"

    # 按类型分组统计
    type_count = {}
    for r in records:
        t = r.get("type", "unknown")
        type_count[t] = type_count.get(t, 0) + 1

    lines = [
        f"# 📊 推送日志 · {date_str}",
        "",
        f"**共 {len(records)} 条推送**，按类型分布：",
        "",
    ]
    for t, c in sorted(type_count.items(), key=lambda x: -x[1]):
        lines.append(f"- `{t}` × {c}")
    lines.extend(["", "---", "", "## 时间线", ""])

    for r in records:
        ts = r.get("ts", "")
        # 只取 HH:MM
        try:
            hhmm = ts.split("T", 1)[1][:5] if "T" in ts else ts[:5]
        except Exception:
            hhmm = "??:??"

        t = r.get("type", "unknown")
        summary = r.get("summary", "")
        length = r.get("length", 0)
        meta = r.get("meta", {})

        lines.append(f"### [{hhmm}] `{t}` · {summary}")
        lines.append("")
        if meta:
            for k, v in meta.items():
                lines.append(f"- **{k}**：{v}")
        lines.append(f"- **字数**：{length}")
        lines.append("")

        # 折叠原文
        msg = r.get("message", "")
        if msg:
            lines.append("<details><summary>📄 原文</summary>")
            lines.append("")
            lines.append("```")
            lines.append(msg)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.extend([
        "",
        "## 📝 复盘区",
        "",
        "> 明天回填：哪些推送有效？哪些冗余？教学锦囊有共鸣吗？",
        "",
        "- **有效推送**：",
        "- **冗余推送**：",
        "- **今日心得**：",
        "",
    ])

    return "\n".join(lines)
