"""Static local research library export."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from sqlalchemy import desc, select

from ..data.models import PaperTrade, PushLog, SignalEvent, TradeSignalLink
from ..signals.types import signal_event_to_dict


def export_research_html(session, out_path: Path, *, days: int = 30) -> dict:
    """Export a self-contained HTML snapshot of recent research records."""

    since = datetime.utcnow() - timedelta(days=days)
    signals = list(
        session.execute(
            select(SignalEvent)
            .where(SignalEvent.ts >= since)
            .order_by(desc(SignalEvent.ts))
            .limit(200)
        ).scalars().all()
    )
    pushes = list(
        session.execute(
            select(PushLog)
            .where(PushLog.ts >= since)
            .order_by(desc(PushLog.ts))
            .limit(120)
        ).scalars().all()
    )
    links = list(
        session.execute(
            select(TradeSignalLink)
            .where(TradeSignalLink.created_at >= since)
            .order_by(desc(TradeSignalLink.created_at))
            .limit(120)
        ).scalars().all()
    )
    trades = list(
        session.execute(
            select(PaperTrade)
            .order_by(desc(PaperTrade.entry_at))
            .limit(120)
        ).scalars().all()
    )

    html = _render(days=days, signals=signals, pushes=pushes, links=links, trades=trades)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return {
        "out": str(out_path),
        "days": days,
        "signals": len(signals),
        "pushes": len(pushes),
        "signal_actions": len(links),
        "trades": len(trades),
    }


def _render(*, days: int, signals, pushes, links, trades) -> str:
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    signal_rows = "\n".join(_signal_row(s) for s in signals) or _empty_row(6)
    push_rows = "\n".join(_push_row(p) for p in pushes) or _empty_row(4)
    action_rows = "\n".join(_link_row(link) for link in links) or _empty_row(5)
    trade_rows = "\n".join(_trade_row(t) for t in trades) or _empty_row(7)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Research OS</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #1c2430; background: #f7f8fa; }}
    header {{ padding: 24px 32px 12px; background: #ffffff; border-bottom: 1px solid #d9dee7; }}
    main {{ padding: 24px 32px 40px; display: grid; gap: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    .meta {{ color: #596579; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ background: #ffffff; border: 1px solid #d9dee7; border-radius: 8px; padding: 14px 16px; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    section {{ background: #ffffff; border: 1px solid #d9dee7; border-radius: 8px; padding: 16px; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid #edf0f4; text-align: left; vertical-align: top; }}
    th {{ color: #465267; font-weight: 600; background: #fafbfc; }}
    .muted {{ color: #6c7789; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} main, header {{ padding-left: 16px; padding-right: 16px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Market Research OS</h1>
    <div class="meta">最近 {days} 天 · 生成于 {generated_at}</div>
  </header>
  <main>
    <div class="grid">
      <div class="metric"><span>Signals</span><strong>{len(signals)}</strong></div>
      <div class="metric"><span>Pushes</span><strong>{len(pushes)}</strong></div>
      <div class="metric"><span>Actions</span><strong>{len(links)}</strong></div>
      <div class="metric"><span>Trades</span><strong>{len(trades)}</strong></div>
    </div>
    <section>
      <h2>Recent Signals</h2>
      <table><thead><tr><th>ID</th><th>Time</th><th>Monitor</th><th>Type</th><th>Symbol</th><th>Title</th></tr></thead><tbody>{signal_rows}</tbody></table>
    </section>
    <section>
      <h2>Push Log</h2>
      <table><thead><tr><th>ID</th><th>Time</th><th>Monitor</th><th>Title</th></tr></thead><tbody>{push_rows}</tbody></table>
    </section>
    <section>
      <h2>Signal Actions</h2>
      <table><thead><tr><th>ID</th><th>Signal</th><th>Trade</th><th>Decision</th><th>Reason</th></tr></thead><tbody>{action_rows}</tbody></table>
    </section>
    <section>
      <h2>Paper Trades</h2>
      <table><thead><tr><th>ID</th><th>Symbol</th><th>Status</th><th>Entry</th><th>Close</th><th>PnL</th><th>Signal</th></tr></thead><tbody>{trade_rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def _signal_row(row) -> str:
    data = signal_event_to_dict(row)
    return (
        "<tr>"
        f"<td>#{data['id']}</td><td>{escape(str(data['ts'])[:19])}</td>"
        f"<td>{escape(data['monitor'])}</td><td>{escape(data['signal_type'])}</td>"
        f"<td>{escape(data.get('symbol') or '-')}</td><td>{escape(data.get('title') or '')}</td>"
        "</tr>"
    )


def _push_row(row) -> str:
    return (
        "<tr>"
        f"<td>#{row.id}</td><td>{escape(row.ts.isoformat()[:19])}</td>"
        f"<td>{escape(row.monitor)}</td><td>{escape(row.title or row.message[:80])}</td>"
        "</tr>"
    )


def _link_row(row) -> str:
    return (
        "<tr>"
        f"<td>#{row.id}</td><td>#{row.signal_event_id}</td>"
        f"<td>{'#' + str(row.paper_trade_id) if row.paper_trade_id else '-'}</td>"
        f"<td>{escape(row.decision)}</td><td>{escape(row.reason or '')}</td>"
        "</tr>"
    )


def _trade_row(row) -> str:
    return (
        "<tr>"
        f"<td>#{row.id}</td><td>{escape(row.symbol)}</td><td>{escape(row.status)}</td>"
        f"<td>{row.entry_price}</td><td>{row.close_price if row.close_price is not None else '-'}</td>"
        f"<td>{row.pnl if row.pnl is not None else '-'}</td>"
        f"<td>{'#' + str(row.signal_event_id) if row.signal_event_id else '-'}</td>"
        "</tr>"
    )


def _empty_row(cols: int) -> str:
    return f"<tr><td colspan=\"{cols}\" class=\"muted\">暂无记录</td></tr>"
