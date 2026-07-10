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
            if "market-monitor" in line:
                print(line)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)


def cmd_test_feishu(args):
    """测试飞书发送"""
    from .core.feishu import send_text
    msg = args.message or "🐉 market-monitor 测试消息"
    ok = send_text(msg, push_type="cli_test")
    print("✅ 发送成功" if ok else "❌ 发送失败")


def cmd_logs(args):
    """查看日志（按行 tail）"""
    log_paths = [
        Path(f"/tmp/{args.name}.log"),
        Path(f"/tmp/{args.name}.err"),
        Path(f"/tmp/{args.name}_alert.log"),
        Path(f"/tmp/{args.name}_alert.err"),
        Path.home() / "projects" / "market-monitor" / "logs" / f"{args.name}.log",
    ]
    found = False
    for p in log_paths:
        if not p.exists():
            continue
        found = True
        print(f"\n\u2550\u2550\u2550 {p} \u2550\u2550\u2550")
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"⚠️  读取失败: {e}")
            continue
        if args.tail:
            lines = text.splitlines()
            print("\n".join(lines[-args.tail:]))
        else:
            print(text)
    if not found:
        print(f"⚠️  未找到 {args.name} 相关的日志文件")
        print("尝试：market-monitor list  查看已注册的 monitor")


def cmd_query(args):
    """概念速查"""
    from .core.teaching import query_concept, list_concepts, CONCEPTS

    # 不传 term → 列出所有可查询的概念
    if not args.term:
        print("📚 可查询的概念（支持中英文与常见别名）\n")
        for group_title, keys in list_concepts():
            print(group_title)
            for k in keys:
                # 第一行作为摘要
                first_line = CONCEPTS[k].split("\n")[0]
                # 去掉开头可能的引号
                summary = first_line.strip('"').strip('“').strip('”')
                print(f"  • {k:24s} {summary[:40]}")
            print()
        print("用法：market-monitor query <词>  例如：market-monitor query 止损")
        print("       market-monitor query — 列出全部")
        print("\n添加 --push 可推送到飞书")
        return

    # 多个词拼接（支持带空格的查询）
    term = " ".join(args.term)
    result = query_concept(term)
    if not result:
        print(f"❌ 未找到与 '{term}' 相关的概念")
        print("\n💡 尝试：market-monitor query   (不带参数看全部可用概念)")
        sys.exit(1)

    key, body = result
    output = f"📚 概念解释: {key}\n\n{body}"
    print(output)

    if args.push:
        from .core.feishu import send_text
        ok = send_text(output, push_type="query", meta={"concept": key})
        print("\n✅ 已推送飞书" if ok else "\n❌ 推送失败")


def cmd_tip(args):
    """今日锦囊（可 --push）"""
    from .core.teaching import get_daily_tip
    tip = get_daily_tip()
    print(tip)
    if args.push:
        from .core.feishu import send_text
        ok = send_text(tip, push_type="daily_tip")
        print("\n✅ 已推送飞书" if ok else "\n❌ 推送失败")


def cmd_note(args):
    """市场笔记本。自动创建/追加/列出 notes/YYYY-MM-DD.md"""
    from datetime import datetime

    notes_dir = Path.home() / "projects" / "market-monitor" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    note_file = notes_dir / f"{today}.md"

    if args.list:
        files = sorted(notes_dir.glob("*.md"), reverse=True)
        if not files:
            print("📋 还没有任何笔记，输入 market-monitor note 创建今日笔记")
            return
        print(f"📋 共 {len(files)} 份笔记：\n")
        for f in files[:20]:
            size = f.stat().st_size
            print(f"  {f.stem}   ({size} bytes)  {f}")
        return

    if args.show:
        target = notes_dir / f"{args.show}.md"
        if not target.exists():
            print(f"❌ 未找到 {args.show} 的笔记")
            sys.exit(1)
        body = target.read_text(encoding="utf-8")
        print(body)
        if args.push:
            from .core.feishu import send_text
            ok = send_text(body, push_type="note", meta={"date": args.show})
            print("\n✅ 已推送飞书" if ok else "\n❌ 推送失败")
        return

    # 默认：创建/打开今日笔记
    if not note_file.exists():
        template = f"""# 市场笔记 · {today}

## 🔍 今日观察
<!-- 大盘/板块/持仓/异动：你看到了什么？ -->
- 

## 🧠 我的判断
<!-- 你对今日行情的解读（不看新闻、先写自己的想法） -->
- 

## ⚖️ 关键信号
<!-- 今天跟踪的信号是否触发？VIX / 北向 / 港股 / 金银比… -->
- 

## 🎯 明日预期
<!-- 你为自己定下什么规则？什么情况不动？什么情况需重新审视？ -->
- 

## 💡 学到了什么
<!-- 今天或 monitor 推送里学到的新概念/新规律 -->
- 

---
_创建于 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 用 `market-monitor note --show {today}` 查看_
"""
        note_file.write_text(template, encoding="utf-8")
        print(f"✅ 创建今日笔记：{note_file}")
    else:
        print(f"📝 今日笔记已存在：{note_file}")

    if args.append:
        # 将 --append 内容插入到“今日观察”区（插在 ‘- ’ 占位行之前，避免顶贴标题）
        text = " ".join(args.append)
        ts = datetime.now().strftime("%H:%M")
        existing = note_file.read_text(encoding="utf-8")
        marker = "## \U0001F50D 今日观察"
        insertion_line = f"- [{ts}] {text}"
        if marker in existing:
            # 定位到该小节内的第一个 `- ` 行（空占位），在它前面插入
            start = existing.index(marker)
            # 下一个 `## ` 标题前为本小节范围
            next_section = existing.find("\n## ", start + len(marker))
            section_end = next_section if next_section != -1 else len(existing)
            section = existing[start:section_end]
            # 找第一个“- ”占位行（只有“- ”或“- \n”）
            placeholder_idx = section.find("\n- \n")
            if placeholder_idx != -1:
                # 替换占位行
                abs_idx = start + placeholder_idx + 1  # +1 skip leading \n
                head = existing[:abs_idx]
                rest = existing[abs_idx + 2:]  # skip "- "
                note_file.write_text(head + insertion_line + rest, encoding="utf-8")
            else:
                # 无占位行，就插在本小节末尾
                head = existing[:section_end]
                rest = existing[section_end:]
                # 确保前后换行干净
                sep = "" if head.endswith("\n") else "\n"
                note_file.write_text(head + sep + insertion_line + "\n" + rest, encoding="utf-8")
            print(f"➕ 已追加到今日笔记：[{ts}] {text}")
        else:
            with open(note_file, "a", encoding="utf-8") as f:
                f.write(f"\n{insertion_line}\n")
            print(f"➕ 已追加到末尾：[{ts}] {text}")

    if args.edit:
        # 尝试用 $EDITOR 或 open
        import os
        editor = os.environ.get("EDITOR")
        if editor:
            subprocess.run([editor, str(note_file)])
        else:
            subprocess.run(["open", str(note_file)])


def cmd_sync_log(args):
    """生成今日推送日志的 Markdown（入口包装，方便手动查看）"""
    from .core import push_logger
    from datetime import datetime as _dt
    date_str = args.date or _dt.now().strftime("%Y-%m-%d")
    markdown = push_logger.format_daily_markdown(date_str)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"✅ 已写入：{args.out}")
    else:
        print(markdown)


def cmd_decision_extract(args):
    """从推送日志中提取可检验命题"""
    from .core import decision_tracker as dt
    from datetime import datetime as _dt
    date_str = args.date or _dt.now().strftime("%Y-%m-%d")
    decisions = dt.extract_decisions(date_str)
    if not decisions:
        print(f"📭 {date_str} 未提取到可检验命题")
        return
    print(f"📋 {date_str} 提取 {len(decisions)} 条命题：\n")
    for d in decisions:
        dir_icon = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}.get(d.get("direction", ""), "❓")
        print(f"  [{d['id']}] {dir_icon} {d['claim']}")
        print(f"         来源: {d.get('source_type','?')} | 时限: {d.get('timeframe','?')} | 置信度: {d.get('confidence','?')}")


def cmd_decision_list(args):
    """列出某天的决策（含校验结果）"""
    from .core import decision_tracker as dt
    from datetime import datetime as _dt
    date_str = args.date or _dt.now().strftime("%Y-%m-%d")
    decisions = dt.list_decisions(date_str)
    if not decisions:
        print(f"📭 {date_str} 暂无决策记录，先运行 market-monitor decision extract")
        return

    verdict_icon = {"hit": "✅", "miss": "❌", "partial": "⚠️", "n_a": "➖", None: "◻️"}
    print(f"📋 {date_str} 共 {len(decisions)} 条决策：\n")
    for d in decisions:
        vi = verdict_icon.get(d.get("verdict"), "◻️")
        print(f"  {vi} [{d['id']}] {d['claim']}")
        if d.get("verdict_note"):
            print(f"     ↳ {d['verdict_note']}")
        if d.get("user_note"):
            print(f"     💬 {d['user_note']}")
        if d.get("user_action"):
            print(f"     🎮 {'已执行' if d['user_action'] == 'did_i_act' else '未执行'}")


def cmd_decision_mark(args):
    """手动标记某条决策"""
    from .core import decision_tracker as dt
    ok = dt.mark_decision(
        args.id,
        verdict=args.verdict,
        user_action=args.action,
        user_note=args.note,
    )
    print(f"{'✅ 已标记' if ok else '❌ 未找到决策'} {args.id}")


def cmd_decision_verify(args):
    """校验某天的决策（拉市场实际数据比对）"""
    from .core import decision_tracker as dt
    from datetime import datetime as _dt
    date_str = args.date or _dt.now().strftime("%Y-%m-%d")
    decisions = dt.verify_decisions(date_str, reference_date=args.ref)
    if not decisions:
        print(f"📭 {date_str} 无决策可校验")
        return
    cmd_decision_list(args)  # 复用列表展示


def cmd_decision_review(args):
    """生成周报复盘"""
    from .core import decision_tracker as dt
    from datetime import datetime as _dt

    if args.week:
        start, end = dt.week_date_range()
    else:
        start = args.start or (_dt.now() - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
        end = args.end or _dt.now().strftime("%Y-%m-%d")

    report = dt.format_weekly_review(start, end)

    if args.push:
        from .core.feishu import send_text
        ok = send_text(report, push_type="weekly_review", meta={"start": start, "end": end})
        print("✅ 已推送飞书" if ok else "❌ 推送失败")
    else:
        print(report)


def cmd_decision_monthly(args):
    """生成月报复盘"""
    from .core import decision_tracker as dt
    from datetime import datetime as _dt

    if args.month:
        year, month = map(int, args.month.split("-"))
    else:
        # 默认：上个月
        now = _dt.now()
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1

    report = dt.format_monthly_review(year, month)

    if args.push:
        from .core.feishu import send_text
        ok = send_text(report, push_type="monthly_review", meta={"month": f"{year}-{month:02d}"})
        print("✅ 已推送飞书" if ok else "❌ 推送失败")
    else:
        print(report)


def cmd_calendar(args):
    """查看宏观事件日历"""
    from .core import calendar_events as cal

    if args.month:
        year, month = map(int, args.month.split("-"))
        events = cal.in_month(year, month)
        title = f"🗓️ {year}-{month:02d} 宏观日历"
        show_days = False
    else:
        events = cal.upcoming(days=args.days)
        title = f"🗓️ 未来 {args.days} 天宏观日历"
        show_days = True

    output = f"{title}\n\n{cal.format_events(events, show_days_from_now=show_days)}"
    print(output)

    if args.push:
        from .core.feishu import send_text
        ok = send_text(output, push_type="calendar", meta={"scope": args.month or f"{args.days}d"})
        print("\n✅ 已推送飞书" if ok else "\n❌ 推送失败")


def cmd_db_init(args):
    """初始化 DB + 种子数据"""
    from .data import init_db
    from .data.seeds import seed_all
    from .data.database import db_info

    print(f"🗄️  DB: {db_info()}")
    print("🔨 建表...")
    init_db()
    print("🌱 写入种子数据...")
    seed_all()
    print("✅ DB 就绪")


def cmd_db_info(args):
    """查看表行数"""
    from .data import get_session
    from .data.database import db_info
    from .data import (
        MonitorRegistry, SymbolRegistry, SignalTypeRegistry,
        MarketSnapshot, PushLog, SignalEvent, AlertDedup,
    )
    from sqlalchemy import select, func

    print(f"🗄️  DB: {db_info()}\n")
    with get_session() as s:
        print(f"{'Table':<24} {'Rows':>10}")
        print("-" * 36)
        for tbl, name in [
            (MonitorRegistry, "monitor_registry"),
            (SymbolRegistry, "symbol_registry"),
            (SignalTypeRegistry, "signal_type_registry"),
            (MarketSnapshot, "market_snapshot"),
            (PushLog, "push_log"),
            (SignalEvent, "signal_event"),
            (AlertDedup, "alert_dedup"),
        ]:
            n = s.execute(select(func.count()).select_from(tbl)).scalar()
            print(f"{name:<24} {n:>10}")


def cmd_db_query(args):
    """查推送历史"""
    from .data import get_session
    from .data.repositories import PushLogRepository

    with get_session() as s:
        rows = PushLogRepository(s).recent(
            monitor=args.monitor,
            days=args.days,
            min_level=args.level,
            limit=args.limit,
        )
        if not rows:
            print(f"💭 没找到符合条件的推送")
            return
        print(f"📋 共 {len(rows)} 条推送:\n")
        for r in rows:
            lvl_icon = ["⚪", "🟡", "🟠", "🔴"][min(r.max_level, 3)]
            ts_local = r.ts.strftime("%Y-%m-%d %H:%M")
            scen = f" [{r.scenario}]" if r.scenario else ""
            print(f"  {lvl_icon} L{r.max_level} {ts_local} {r.monitor}{scen}")
            print(f"     {(r.title or '')[:60]}")


def cmd_db_stats(args):
    """推送统计"""
    from .data import get_session
    from .data.repositories import StatsRepository

    with get_session() as s:
        repo = StatsRepository(s)

        print(f"📊 最近 {args.days} 天 monitor 推送统计:\n")
        print(f"  {'Monitor':<20} {'Count':>8} {'AvgL':>6} {'MaxL':>6}")
        print("  " + "-" * 42)
        for row in repo.monitor_stats(args.days):
            print(f"  {row['monitor']:<20} {row['count']:>8} "
                  f"{row['avg_level']:>6} {row['max_level']:>6}")

        sig_stats = repo.signal_frequency(args.days)
        if sig_stats:
            print(f"\n🎯 信号类型频次:\n")
            print(f"  {'Signal Type':<24} {'Count':>8}")
            print("  " + "-" * 34)
            for row in sig_stats:
                print(f"  {row['signal_type']:<24} {row['count']:>8}")


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

    # tip
    p_tip = sub.add_parser("tip", help="今日锦囊（教学轮换）")
    p_tip.add_argument("--push", action="store_true", help="推送到飞书")
    p_tip.set_defaults(func=cmd_tip)

    # query
    p_query = sub.add_parser("query", help="概念速查（中英文均可）")
    p_query.add_argument("term", nargs="*", help="要查询的概念名称，不传则列出全部")
    p_query.add_argument("--push", action="store_true", help="推送到飞书")
    p_query.set_defaults(func=cmd_query)

    # note
    p_note = sub.add_parser("note", help="市场笔记本")
    p_note.add_argument("--append", nargs="+", help="追加一条观察到今日笔记")
    p_note.add_argument("--edit", action="store_true", help="用编辑器打开")
    p_note.add_argument("--list", action="store_true", help="列出所有笔记")
    p_note.add_argument("--show", help="查看指定日期的笔记 (YYYY-MM-DD)")
    p_note.add_argument("--push", action="store_true", help="配合 --show 推送到飞书")
    p_note.set_defaults(func=cmd_note)

    # sync-log
    p_sync = sub.add_parser("sync-log", help="生成今日推送日志 Markdown（供飞书同步）")
    p_sync.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    p_sync.add_argument("--out", help="输出到文件而非 stdout")
    p_sync.set_defaults(func=cmd_sync_log)

    # decision
    p_decision = sub.add_parser("decision", help="决策闭环追踪")
    d_sub = p_decision.add_subparsers(dest="action", required=True)

    d_extract = d_sub.add_parser("extract", help="从推送日志提取可检验命题")
    d_extract.add_argument("--date", help="日期 YYYY-MM-DD（默认今天）")
    d_extract.set_defaults(func=cmd_decision_extract)

    d_list = d_sub.add_parser("list", help="列出决策（含校验结果）")
    d_list.add_argument("--date", help="日期 YYYY-MM-DD（默认今天）")
    d_list.set_defaults(func=cmd_decision_list)

    d_mark = d_sub.add_parser("mark", help="手动标记某条决策")
    d_mark.add_argument("id", help="决策 ID（如 2026-07-06-003）")
    d_mark.add_argument("--verdict", choices=["hit", "miss", "partial", "n_a"], help="手动覆写裁决")
    d_mark.add_argument("--action", choices=["did_i_act", "did_i_not_act", "n_a"], help="是否执行了操作")
    d_mark.add_argument("--note", help="自由备注")
    d_mark.set_defaults(func=cmd_decision_mark)

    d_verify = d_sub.add_parser("verify", help="校验决策（拉市场实际数据比对）")
    d_verify.add_argument("--date", help="决策日期 YYYY-MM-DD（默认今天）")
    d_verify.add_argument("--ref", help="参考市场数据日期（默认今天）")
    d_verify.set_defaults(func=cmd_decision_verify)

    d_review = d_sub.add_parser("review", help="生成周报复盘")
    d_review.add_argument("--week", action="store_true", help="本周复盘（默认）")
    d_review.add_argument("--start", help="起始日期 YYYY-MM-DD")
    d_review.add_argument("--end", help="结束日期 YYYY-MM-DD")
    d_review.add_argument("--push", action="store_true", help="推送到飞书")
    d_review.set_defaults(func=cmd_decision_review)

    d_monthly = d_sub.add_parser("monthly", help="生成月报复盘")
    d_monthly.add_argument("--month", help="月份 YYYY-MM（默认上个月）")
    d_monthly.add_argument("--push", action="store_true", help="推送到飞书")
    d_monthly.set_defaults(func=cmd_decision_monthly)

    # calendar
    p_calendar = sub.add_parser("calendar", help="宏观事件日历")
    p_calendar.add_argument("--days", type=int, default=7, help="未来多少天（默认 7）")
    p_calendar.add_argument("--month", help="查某月完整日历 YYYY-MM")
    p_calendar.add_argument("--push", action="store_true", help="推送到飞书")
    p_calendar.set_defaults(func=cmd_calendar)

    # db（Phase 1 新增）
    p_db = sub.add_parser("db", help="数据库相关命令")
    db_sub = p_db.add_subparsers(dest="action", required=True)

    p_db_init = db_sub.add_parser("init", help="初始化 DB + 写入种子数据")
    p_db_init.set_defaults(func=cmd_db_init)

    p_db_info = db_sub.add_parser("info", help="查看当前 DB 信息 + 表行数统计")
    p_db_info.set_defaults(func=cmd_db_info)

    p_db_query = db_sub.add_parser("query", help="查推送历史")
    p_db_query.add_argument("--monitor", help="筛选 monitor")
    p_db_query.add_argument("--days", type=int, default=7, help="最近多少天（默认 7）")
    p_db_query.add_argument("--level", type=int, default=0, help="最低 level（默认 0）")
    p_db_query.add_argument("--limit", type=int, default=20, help="最多多少条（默认 20）")
    p_db_query.set_defaults(func=cmd_db_query)

    p_db_stats = db_sub.add_parser("stats", help="推送统计")
    p_db_stats.add_argument("--days", type=int, default=30, help="最近多少天")
    p_db_stats.set_defaults(func=cmd_db_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
