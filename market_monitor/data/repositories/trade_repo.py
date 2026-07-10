"""交易日志相关操作（W1 - Trade Journal）"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, desc, func, and_
from sqlalchemy.orm import Session

from ..models import PaperTrade, TradeSignalLink, TradeReview


SHANGHAI = timezone(timedelta(hours=8))


def _now_utc() -> datetime:
    return datetime.utcnow()


def _to_shanghai(ts_utc: datetime) -> datetime:
    """UTC naive → Asia/Shanghai naive（用于展示）"""
    return ts_utc.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).replace(tzinfo=None)


class PaperTradeRepository:
    """纸面交易 CRUD + 盈亏统计"""

    def __init__(self, session: Session):
        self.s = session

    # ── 开仓 ────────────────────────────────────
    def open_trade(
        self,
        symbol: str,
        entry_price: float,
        qty: float,
        *,
        name: Optional[str] = None,
        action: str = "long",
        strategy: Optional[str] = None,
        tag: Optional[str] = None,
        entry_reason: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        signal_event_id: Optional[int] = None,
        notes: Optional[str] = None,
        entry_at: Optional[datetime] = None,
    ) -> PaperTrade:
        row = PaperTrade(
            symbol=symbol,
            name=name,
            action=action,
            strategy=strategy,
            tag=tag,
            entry_at=entry_at or _now_utc(),
            entry_price=entry_price,
            qty=qty,
            entry_reason=entry_reason,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_event_id=signal_event_id,
            notes=notes,
            status="open",
        )
        self.s.add(row)
        self.s.flush()
        return row

    # ── 平仓 ────────────────────────────────────
    def close_trade(
        self,
        trade_id: int,
        close_price: float,
        *,
        close_reason: Optional[str] = None,
        close_at: Optional[datetime] = None,
    ) -> Optional[PaperTrade]:
        row = self.s.get(PaperTrade, trade_id)
        if row is None or row.status == "closed":
            return None

        row.close_at = close_at or _now_utc()
        row.close_price = close_price
        row.close_reason = close_reason
        row.status = "closed"

        # 自动计算盈亏
        pnl, pnl_pct = self._calc_pnl(row.action, row.entry_price, close_price, row.qty)
        row.pnl = pnl
        row.pnl_pct = pnl_pct

        # 持仓天数
        delta = row.close_at - row.entry_at
        row.hold_days = max(int(delta.total_seconds() // 86400), 0)

        self.s.flush()
        return row

    @staticmethod
    def _calc_pnl(action: str, entry: float, close: float, qty: float):
        if action == "long":
            pnl = (close - entry) * qty
        else:  # short（暂不支持，但预留）
            pnl = (entry - close) * qty
        pnl_pct = ((close - entry) / entry) if entry else None
        if action == "short" and pnl_pct is not None:
            pnl_pct = -pnl_pct
        return pnl, pnl_pct

    # ── 查询 ────────────────────────────────────
    def by_id(self, trade_id: int) -> Optional[PaperTrade]:
        return self.s.get(PaperTrade, trade_id)

    def list_open(self, strategy: Optional[str] = None) -> List[PaperTrade]:
        q = select(PaperTrade).where(PaperTrade.status == "open")
        if strategy:
            q = q.where(PaperTrade.strategy == strategy)
        q = q.order_by(desc(PaperTrade.entry_at))
        return list(self.s.execute(q).scalars().all())

    def list_closed(
        self,
        strategy: Optional[str] = None,
        days: Optional[int] = None,
        limit: int = 100,
    ) -> List[PaperTrade]:
        q = select(PaperTrade).where(PaperTrade.status == "closed")
        if strategy:
            q = q.where(PaperTrade.strategy == strategy)
        if days:
            since = _now_utc() - timedelta(days=days)
            q = q.where(PaperTrade.close_at >= since)
        q = q.order_by(desc(PaperTrade.close_at)).limit(limit)
        return list(self.s.execute(q).scalars().all())

    def list_all(self, limit: int = 100) -> List[PaperTrade]:
        q = select(PaperTrade).order_by(desc(PaperTrade.entry_at)).limit(limit)
        return list(self.s.execute(q).scalars().all())

    # ── 盈亏统计 ────────────────────────────────
    def pnl_summary(self, days: Optional[int] = None,
                    strategy: Optional[str] = None) -> Dict[str, Any]:
        """当前浮盈 + 已实现盈亏 + 胜率"""
        # 已平仓
        closed = self.list_closed(strategy=strategy, days=days, limit=10000)
        wins = [t for t in closed if (t.pnl or 0) > 0]
        losses = [t for t in closed if (t.pnl or 0) < 0]

        total_realized = sum(t.pnl or 0 for t in closed)
        win_rate = (len(wins) / len(closed)) if closed else None
        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else None
        avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else None

        # 未平仓（浮盈需外部传入当前价，不在此计算）
        open_trades = self.list_open(strategy=strategy)

        return {
            "closed_count": len(closed),
            "open_count": len(open_trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": win_rate,
            "total_realized_pnl": total_realized,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": (
                abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses))
                if losses and sum(t.pnl for t in losses) != 0
                else None
            ),
        }

    def by_strategy_stats(self, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """按策略分组的盈亏统计"""
        q = select(
            PaperTrade.strategy,
            func.count(PaperTrade.id).label("cnt"),
            func.sum(PaperTrade.pnl).label("total_pnl"),
            func.avg(PaperTrade.pnl_pct).label("avg_pct"),
        ).where(PaperTrade.status == "closed")
        if days:
            since = _now_utc() - timedelta(days=days)
            q = q.where(PaperTrade.close_at >= since)
        q = q.group_by(PaperTrade.strategy).order_by(desc("total_pnl"))

        rows = self.s.execute(q).all()
        return [
            {
                "strategy": r.strategy or "(manual)",
                "count": r.cnt,
                "total_pnl": float(r.total_pnl or 0),
                "avg_pct": float(r.avg_pct) if r.avg_pct is not None else None,
            }
            for r in rows
        ]


class TradeSignalLinkRepository:
    """推送信号 → 交易决策关联"""

    def __init__(self, session: Session):
        self.s = session

    def create(
        self,
        signal_event_id: int,
        decision: str,
        *,
        paper_trade_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> TradeSignalLink:
        row = TradeSignalLink(
            signal_event_id=signal_event_id,
            paper_trade_id=paper_trade_id,
            decision=decision,
            reason=reason,
        )
        self.s.add(row)
        self.s.flush()
        return row

    def by_signal(self, signal_event_id: int) -> List[TradeSignalLink]:
        q = select(TradeSignalLink).where(
            TradeSignalLink.signal_event_id == signal_event_id
        )
        return list(self.s.execute(q).scalars().all())

    def decision_stats(self, days: Optional[int] = None) -> Dict[str, int]:
        """近 N 天 act / skip / noise 计数"""
        q = select(
            TradeSignalLink.decision,
            func.count(TradeSignalLink.id).label("cnt"),
        )
        if days:
            since = _now_utc() - timedelta(days=days)
            q = q.where(TradeSignalLink.created_at >= since)
        q = q.group_by(TradeSignalLink.decision)

        return {r.decision: r.cnt for r in self.s.execute(q).all()}


class TradeReviewRepository:
    """周/月复盘"""

    def __init__(self, session: Session):
        self.s = session

    @staticmethod
    def week_key(dt: datetime) -> str:
        """UTC datetime → 'YYYY-Www'（ISO 周）"""
        local = _to_shanghai(dt)
        yr, wk, _ = local.isocalendar()
        return f"{yr}-W{wk:02d}"

    @staticmethod
    def month_key(dt: datetime) -> str:
        local = _to_shanghai(dt)
        return local.strftime("%Y-%m")

    def upsert(self, period_type: str, period_key: str,
               **kwargs) -> TradeReview:
        row = self.s.get(TradeReview, (period_type, period_key))
        if row is None:
            row = TradeReview(period_type=period_type, period_key=period_key)
            self.s.add(row)
        for k, v in kwargs.items():
            if hasattr(row, k):
                setattr(row, k, v)
        row.generated_at = _now_utc()
        self.s.flush()
        return row

    def generate(self, period_type: str = "week",
                 period_key: Optional[str] = None) -> Optional[TradeReview]:
        """根据 paper_trade 数据生成/刷新复盘"""
        now = _now_utc()
        if period_key is None:
            period_key = (
                self.week_key(now) if period_type == "week"
                else self.month_key(now)
            )

        # 确定时间窗口
        local = _to_shanghai(now)
        if period_type == "week":
            # period_key: 'YYYY-Www'
            try:
                yr, wk = period_key.split("-W")
                yr, wk = int(yr), int(wk)
                # ISO 周第 1 天 = 周一
                first_day = datetime.fromisocalendar(yr, wk, 1)
                last_day = datetime.fromisocalendar(yr, wk, 7)
                # 转 UTC naive（+8 → UTC 就是 -8h）
                since = first_day - timedelta(hours=8)
                until = last_day + timedelta(hours=16)   # 到周日 24:00 shanghai
            except (ValueError, IndexError):
                return None
        else:  # month
            try:
                yr, mo = period_key.split("-")
                yr, mo = int(yr), int(mo)
                first_local = datetime(yr, mo, 1)
                if mo == 12:
                    next_first = datetime(yr + 1, 1, 1)
                else:
                    next_first = datetime(yr, mo + 1, 1)
                since = first_local - timedelta(hours=8)
                until = next_first - timedelta(hours=8)
            except (ValueError, IndexError):
                return None

        # 拉取窗口内所有平仓单
        q = select(PaperTrade).where(
            and_(
                PaperTrade.status == "closed",
                PaperTrade.close_at >= since,
                PaperTrade.close_at < until,
            )
        )
        trades = list(self.s.execute(q).scalars().all())

        wins = [t for t in trades if (t.pnl or 0) > 0]
        losses = [t for t in trades if (t.pnl or 0) < 0]
        total_pnl = sum(t.pnl or 0 for t in trades)
        win_rate = (len(wins) / len(trades)) if trades else None
        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else None
        avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else None

        best = max(trades, key=lambda t: t.pnl or 0, default=None)
        worst = min(trades, key=lambda t: t.pnl or 0, default=None)

        return self.upsert(
            period_type=period_type,
            period_key=period_key,
            trade_count=len(trades),
            win_count=len(wins),
            loss_count=len(losses),
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade_id=best.id if best else None,
            worst_trade_id=worst.id if worst else None,
        )

    def by_key(self, period_type: str, period_key: str) -> Optional[TradeReview]:
        return self.s.get(TradeReview, (period_type, period_key))

    def recent(self, period_type: str = "week", limit: int = 8) -> List[TradeReview]:
        q = (
            select(TradeReview)
            .where(TradeReview.period_type == period_type)
            .order_by(desc(TradeReview.period_key))
            .limit(limit)
        )
        return list(self.s.execute(q).scalars().all())
