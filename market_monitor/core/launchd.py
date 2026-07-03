"""launchd plist 模板生成"""
from pathlib import Path
from typing import List, Dict, Optional


PLIST_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        {args}
    </array>
{schedule}
    <key>StandardOutPath</key><string>{stdout}</string>
    <key>StandardErrorPath</key><string>{stderr}</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
"""


def make_calendar_entry(weekday: Optional[int], hour: int, minute: int) -> str:
    lines = ["        <dict>"]
    if weekday is not None:
        lines.append(f"            <key>Weekday</key><integer>{weekday}</integer>")
    lines.append(f"            <key>Hour</key><integer>{hour}</integer>")
    lines.append(f"            <key>Minute</key><integer>{minute}</integer>")
    lines.append("        </dict>")
    return "\n".join(lines)


def make_calendar_schedule(entries: List[Dict]) -> str:
    """生成 StartCalendarInterval 段"""
    body = "\n".join(
        make_calendar_entry(e.get("weekday"), e["hour"], e["minute"])
        for e in entries
    )
    return f"    <key>StartCalendarInterval</key>\n    <array>\n{body}\n    </array>"


def make_interval_schedule(seconds: int) -> str:
    return f"    <key>StartInterval</key>\n    <integer>{seconds}</integer>"


def generate_plist(
    label: str,
    python: str,
    script_path: str,
    args: List[str],
    schedule: str,
    log_dir: str = "/tmp",
) -> str:
    """生成 plist 内容"""
    arg_lines = [f"        <string>{python}</string>"]
    arg_lines.append(f"        <string>{script_path}</string>")
    for a in args:
        arg_lines.append(f"        <string>{a}</string>")
    arg_str = "\n".join(arg_lines)

    return PLIST_HEADER.format(
        label=label,
        args=arg_str.strip(),
        schedule=schedule,
        stdout=f"{log_dir}/{label}.log",
        stderr=f"{log_dir}/{label}.err",
    )


def weekday_range(days: List[int], hour_min_list: List[tuple]) -> List[Dict]:
    """快捷：为多个工作日 + 多个时点生成 entries"""
    result = []
    for d in days:
        for h, m in hour_min_list:
            result.append({"weekday": d, "hour": h, "minute": m})
    return result
