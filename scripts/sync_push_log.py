"""同步推送日志到飞书文档。

用法：
    python -m scripts.sync_push_log                # 生成今日 markdown 到 stdout
    python -m scripts.sync_push_log --date 2026-07-05
    python -m scripts.sync_push_log --out /tmp/push_log.md

飞书写入部分由 OpenClaw agent 完成（读取 stdout / 文件后调用 feishu_create_doc）。
本脚本只负责：读 jsonl → 生成 markdown → 输出。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

# 允许从项目根直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_monitor.core import push_logger  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="生成飞书推送日志 Markdown")
    p.add_argument("--date", help="日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--out", help="输出文件路径（默认 stdout）")
    p.add_argument("--title-only", action="store_true", help="只输出建议的文档标题")
    args = p.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    title = f"📊 推送日志 · {date_str}"

    if args.title_only:
        print(title)
        return

    markdown = push_logger.format_daily_markdown(date_str)

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"✅ 已写入：{args.out}", file=sys.stderr)
        print(f"📄 建议文档标题：{title}", file=sys.stderr)
    else:
        print(markdown)


if __name__ == "__main__":
    main()
