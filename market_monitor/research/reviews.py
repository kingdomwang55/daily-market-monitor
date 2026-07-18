"""Shared review read model and Markdown export."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..data.repositories import PaperTradeRepository, TradeReviewRepository
from ..data.serializers import paper_trade_to_dict, trade_review_to_dict


def review_detail(session: Session, row) -> dict:
    repository = TradeReviewRepository(session)
    analytics = repository.analytics(row.period_type, row.period_key) or {
        "signal_frequency": [],
        "decision_distribution": {},
        "outcomes": {
            "verified": 0,
            "pending": 0,
            "t1_hits": 0,
            "t1_misses": 0,
            "t1_hit_rate": None,
        },
    }
    trades = PaperTradeRepository(session)
    best = trades.by_id(row.best_trade_id) if row.best_trade_id else None
    worst = trades.by_id(row.worst_trade_id) if row.worst_trade_id else None
    return {
        **trade_review_to_dict(row),
        **analytics,
        "best_trade": paper_trade_to_dict(best) if best else None,
        "worst_trade": paper_trade_to_dict(worst) if worst else None,
    }


def review_markdown(payload: dict) -> str:
    period_label = "周度" if payload["period_type"] == "week" else "月度"
    win_rate = payload.get("win_rate")
    outcome_rate = payload["outcomes"].get("t1_hit_rate")
    lines = [
        f"# {period_label}复盘 {payload['period_key']}",
        "",
        "## 交易摘要",
        "",
        f"- 交易笔数：{payload['trade_count']}",
        f"- 胜 / 负：{payload['win_count']} / {payload['loss_count']}",
        f"- 胜率：{win_rate * 100:.1f}%" if win_rate is not None else "- 胜率：-",
        f"- 总盈亏：{payload.get('total_pnl') or 0:+.2f}",
        "",
        "## 信号与判断",
        "",
    ]
    frequency = payload.get("signal_frequency") or []
    lines.extend(
        [f"- {item['signal_type']}：{item['count']}" for item in frequency]
        or ["- 本期无信号记录"]
    )
    lines.extend(["", "判断分布："])
    distribution = payload.get("decision_distribution") or {}
    lines.extend(
        [f"- {decision}：{count}" for decision, count in sorted(distribution.items())]
        or ["- 本期无人工判断"]
    )
    outcomes = payload["outcomes"]
    lines.extend([
        "",
        "## 信号验证",
        "",
        f"- 已验证：{outcomes['verified']}",
        f"- 待验证：{outcomes['pending']}",
        (
            f"- T+1 命中率：{outcome_rate * 100:.1f}%"
            if outcome_rate is not None else "- T+1 命中率：-"
        ),
    ])
    for label, key in (("最佳交易", "best_trade"), ("最差交易", "worst_trade")):
        trade = payload.get(key)
        if trade:
            lines.extend([
                "",
                f"## {label}",
                "",
                f"- #{trade['id']} {trade['name'] or trade['symbol']}",
                f"- 盈亏：{trade.get('pnl') or 0:+.2f}",
            ])
    return "\n".join(lines) + "\n"
