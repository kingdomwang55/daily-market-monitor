"""命令行入口"""
import argparse
import subprocess
import sys
from pathlib import Path

from .monitors.registry import get_monitor, list_monitors, REGISTRY


def cmd_run(args):
    """运行单个 monitor"""
    Cls = get_monitor(args.name)
    m = Cls(force=args.force, snapshot=args.snapshot)
    ok = m.run()
    sys.exit(0 if ok else 1)


def cmd_list(args):
    """列出所有 monitor"""
    print(f"{'Name':<15} {'Display':<20}")
    print("-" * 40)
    for m in list_monitors():
        print(f"{m['name']:<15} {m['display']:<20}")


def cmd_status(args):
    """查看 launchd 任务状态"""
    try:
        out = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True
        ).stdout
        print(f"{'PID':<8} {'Status':<8} {'Label':<40}")
        print("-" * 60)
        for line in out.splitlines():
            if "openclaw.market" in line or "openclaw.stock" in line \
               or "openclaw.price" in line or "openclaw.stabilize" in line \
               or "openclaw.us-market" in line or "openclaw.hk-market" in line:
                print(line)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)


def cmd_test_feishu(args):
    """测试飞书发送"""
    from .core.feishu import send_text
    msg = args.message or "🐉 market-monitor 测试消息"
    ok = send_text(msg)
    print("✅ 发送成功" if ok else "❌ 发送失败")


def cmd_logs(args):
    """查看日志"""
    log_paths = [
        Path(f"/tmp/{args.name}.log"),
        Path(f"/tmp/{args.name}.err"),
        Path(f"/tmp/{args.name}_alert.log"),
        Path(f"/tmp/{args.name}_alert.err"),
        Path.home() / ".openclaw" / "workspace" / "logs" / f"{args.name}.log",
    ]
    for p in log_paths:
        if p.exists():
            print(f"\n═══ {p} ═══")
            print(p.read_text()[-args.tail * 100:] if args.tail else p.read_text())
    else:
        pass  # for/else


def main():
    parser = argparse.ArgumentParser(
        prog="market-monitor",
        description="🐉 Global market monitor",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run
    p_run = sub.add_parser("run", help="运行单个 monitor")
    p_run.add_argument("name", help=f"monitor 名称 ({', '.join(REGISTRY.keys())})")
    p_run.add_argument("--force", action="store_true", help="强制发送（忽略状态）")
    p_run.add_argument("--snapshot", action="store_true", help="快照模式（发送当前状态）")
    p_run.set_defaults(func=cmd_run)

    # list
    p_list = sub.add_parser("list", help="列出所有 monitor")
    p_list.set_defaults(func=cmd_list)

    # status
    p_status = sub.add_parser("status", help="查看 launchd 任务")
    p_status.set_defaults(func=cmd_status)

    # test-feishu
    p_test = sub.add_parser("test-feishu", help="测试飞书发送")
    p_test.add_argument("message", nargs="?", help="消息内容")
    p_test.set_defaults(func=cmd_test_feishu)

    # logs
    p_logs = sub.add_parser("logs", help="查看日志")
    p_logs.add_argument("name", help="日志名称")
    p_logs.add_argument("--tail", type=int, default=50, help="末尾行数")
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
