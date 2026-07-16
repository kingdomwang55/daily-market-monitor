#!/usr/bin/env python3
"""生成 launchd plist 文件到 launchd/ 目录"""
import os
import sys
from pathlib import Path

# 允许脚本独立运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_monitor.core.launchd import (
    generate_plist, make_calendar_schedule, make_interval_schedule,
    weekday_range,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHD_DIR = Path(os.environ.get("MARKET_MONITOR_LAUNCHD_DIR", PROJECT_ROOT / "launchd"))
PYTHON = os.environ.get("MARKET_MONITOR_PYTHON", sys.executable)

# python -m market_monitor.cli run <name>
def make_cli_args(monitor_name: str, extra_args=None) -> tuple:
    """返回 (script_path, args)"""
    # 用 -c 方式统一入口
    args = ["-m", "market_monitor.cli", "run", monitor_name]
    if extra_args:
        args.extend(extra_args)
    # script_path 用 -m 时留空占位
    return args


def build_plist_via_module(label: str, monitor_name: str, schedule: str,
                          extra_args=None) -> str:
    """构造使用 python -m market_monitor.cli 的 plist"""
    arg_lines = [f"        <string>{PYTHON}</string>",
                 f"        <string>-m</string>",
                 f"        <string>market_monitor.cli</string>",
                 f"        <string>run</string>",
                 f"        <string>{monitor_name}</string>"]
    if extra_args:
        for a in extra_args:
            arg_lines.append(f"        <string>{a}</string>")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{chr(10).join(arg_lines)}
    </array>
    <key>WorkingDirectory</key>
    <string>{PROJECT_ROOT}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{PROJECT_ROOT}</string>
    </dict>
{schedule}
    <key>StandardOutPath</key><string>/tmp/{label}.log</string>
    <key>StandardErrorPath</key><string>/tmp/{label}.err</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
"""


def main():
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    # 交易日 = 周一~周五 = weekday 1~5
    weekdays = [1, 2, 3, 4, 5]

    # ===== 1. stabilize-alert（A 股企稳信号） =====
    schedule = make_calendar_schedule(weekday_range(
        weekdays,
        [(9, 35), (10, 0), (10, 30), (11, 0), (11, 25),
         (13, 15), (13, 45), (14, 15), (14, 45), (15, 5)]
    ))
    (LAUNCHD_DIR / "com.market-monitor.stabilize.plist").write_text(
        build_plist_via_module("com.market-monitor.stabilize", "stabilize", schedule)
    )

    # ===== 2. us-market-alert（美股夜盘） =====
    # 21:32 / 22:00 / 22:30 / 23:00 / 23:30 / 00:00 / 00:30 ... 03:30 / 04:05
    # 周二~周六（对应美股周一~周五）
    us_days = [2, 3, 4, 5, 6]
    entries = []
    for d in us_days:
        # 当天晚上时段（21:32 - 23:30）
        for h, m in [(21, 32), (22, 0), (22, 30), (23, 0), (23, 30)]:
            entries.append({"weekday": d, "hour": h, "minute": m})
        # 次日凌晨时段（00:00 - 04:05）
        next_d = d + 1 if d < 7 else 1
        for h, m in [(0, 0), (0, 30), (1, 0), (1, 30), (2, 0),
                     (2, 30), (3, 0), (3, 30), (4, 5)]:
            entries.append({"weekday": next_d, "hour": h, "minute": m})
    schedule = make_calendar_schedule(entries)
    (LAUNCHD_DIR / "com.market-monitor.us-market.plist").write_text(
        build_plist_via_module("com.market-monitor.us-market", "us_market", schedule)
    )

    # ===== 3. hk-market-alert（港股） =====
    hk_times = [
        (9, 32), (10, 0), (10, 30), (11, 0), (11, 30),
        (12, 0), (13, 30), (14, 0), (14, 30),
        (15, 0), (15, 30), (16, 5),
    ]
    schedule = make_calendar_schedule(weekday_range(weekdays, hk_times))
    (LAUNCHD_DIR / "com.market-monitor.hk-market.plist").write_text(
        build_plist_via_module("com.market-monitor.hk-market", "hk_market", schedule)
    )

    # ===== 4. market-shock-alert（A 股异动，每 10 分钟） =====
    schedule = make_interval_schedule(600)
    (LAUNCHD_DIR / "com.market-monitor.shock.plist").write_text(
        build_plist_via_module("com.market-monitor.shock", "shock", schedule)
    )

    # ===== 4b. hk-shock（港股异动，每 10 分钟） =====
    schedule = make_interval_schedule(600)
    (LAUNCHD_DIR / "com.market-monitor.hk-shock.plist").write_text(
        build_plist_via_module("com.market-monitor.hk-shock", "hk_shock", schedule)
    )

    # ===== 5. price-alert（关键点位，每 30 分钟） =====
    schedule = make_interval_schedule(1800)
    (LAUNCHD_DIR / "com.market-monitor.price-alert.plist").write_text(
        build_plist_via_module("com.market-monitor.price-alert", "price_alert", schedule)
    )

    # ===== 6. morning（晨报，每工作日 07:00） =====
    schedule = make_calendar_schedule(weekday_range(weekdays, [(7, 0)]))
    (LAUNCHD_DIR / "com.market-monitor.morning.plist").write_text(
        build_plist_via_module("com.market-monitor.morning", "morning", schedule)
    )

    # ===== 7. evening（盘后报告，每工作日 17:00） =====
    schedule = make_calendar_schedule(weekday_range(weekdays, [(17, 0)]))
    (LAUNCHD_DIR / "com.market-monitor.evening.plist").write_text(
        build_plist_via_module("com.market-monitor.evening", "evening", schedule)
    )

    # ===== 8. voice（意见领袖发言日报，每工作日 07:30） =====
    schedule = make_calendar_schedule(weekday_range(weekdays, [(7, 30)]))
    (LAUNCHD_DIR / "com.market-monitor.voice.plist").write_text(
        build_plist_via_module("com.market-monitor.voice", "voice", schedule)
    )

    # ===== 9. review（周度复盘，周日 20:00） =====
    schedule = make_calendar_schedule([{"weekday": 7, "hour": 20, "minute": 0}])
    (LAUNCHD_DIR / "com.market-monitor.review.plist").write_text(
        build_plist_via_module("com.market-monitor.review", "review", schedule)
    )

    # ===== 10. monthly（月度复盘，每月 1 日 09:00） =====
    schedule = make_calendar_schedule([{"day": 1, "hour": 9, "minute": 0}])
    (LAUNCHD_DIR / "com.market-monitor.monthly.plist").write_text(
        build_plist_via_module("com.market-monitor.monthly", "monthly", schedule)
    )

    print("✅ plist 已生成到:", LAUNCHD_DIR)
    for f in sorted(LAUNCHD_DIR.glob("*.plist")):
        print(f"   {f.name}")


if __name__ == "__main__":
    main()
