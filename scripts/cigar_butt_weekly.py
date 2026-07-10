#!/usr/bin/env python3
"""烟蒂股筛选 - 每周日 10:00 触发"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_monitor.core.cigar_butt import screen, format_report
from market_monitor.core.feishu import send_text


def main():
    try:
        results = screen(pool="sse_dividend")
        report = format_report(results, pool="sse_dividend")

        # 加日期头
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"📅 {date_str} · 周报\n\n{report}"

        send_text(message, push_type="cigar_butt_weekly")
        print(f"✅ 烟蒂股筛选完成，通过 {sum(1 for r in results if r['passed'])} 只")
    except Exception as e:
        import traceback
        err = f"❌ 烟蒂股筛选失败：{e}\n{traceback.format_exc()}"
        print(err)
        try:
            send_text(err[:1000], push_type="cigar_butt_weekly_err")
        except:
            pass


if __name__ == "__main__":
    main()
