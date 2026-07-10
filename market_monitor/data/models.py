"""SQLAlchemy 2.0 表定义（10 张表）

分层：
- Meta   : MonitorRegistry / SymbolRegistry / SignalTypeRegistry
- Raw    : MarketSnapshot
- Event  : PushLog / SignalEvent / AlertDedup
- Derived: DailySummary / SignalOutcome / SymbolOhlcDaily

跨库兼容要点：
- 所有 datetime 存 UTC naive（应用层用 datetime.utcnow()），展示时才转 Asia/Shanghai
- JSON 字段用 sqlalchemy.JSON 类型（SQLite 存 TEXT，PG 自动 JSONB）
- 不写原生 DDL，主键 autoincrement 由 SQLAlchemy 处理
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有表的基类"""
    pass


# ═══════════════════════════════════════════════════════
# Meta Layer
# ═══════════════════════════════════════════════════════

class MonitorRegistry(Base):
    """推送模块字典"""
    __tablename__ = "monitor_registry"

    name:         Mapped[str]  = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str]  = mapped_column(String(128), nullable=False)
    category:     Mapped[str]  = mapped_column(String(32), nullable=False)  # shock/periodic/alert/report
    enabled:      Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description:  Mapped[Optional[str]] = mapped_column(Text)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SymbolRegistry(Base):
    """标的字典（统一 symbol 命名空间）"""
    __tablename__ = "symbol_registry"

    symbol:       Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    market:       Mapped[str] = mapped_column(String(16), nullable=False)   # CN/HK/US/GOLD/FX/BOND
    asset_class:  Mapped[str] = mapped_column(String(16), nullable=False)   # index/stock/etf/commodity/fx/bond
    currency:     Mapped[Optional[str]] = mapped_column(String(8))
    data_source:  Mapped[Optional[str]] = mapped_column(String(32))
    meta_json:    Mapped[Optional[dict]] = mapped_column(JSON)
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SignalTypeRegistry(Base):
    """信号类型字典"""
    __tablename__ = "signal_type_registry"

    signal_type:  Mapped[str] = mapped_column(String(64), primary_key=True)
    monitor:      Mapped[str] = mapped_column(
        String(64), ForeignKey("monitor_registry.name"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction:    Mapped[Optional[int]] = mapped_column(Integer)   # -1/0/+1
    description:  Mapped[Optional[str]] = mapped_column(Text)


# ═══════════════════════════════════════════════════════
# Raw Layer
# ═══════════════════════════════════════════════════════

class MarketSnapshot(Base):
    """行情快照（时序主表）

    未来切 TimescaleDB 时这张表升级为 hypertable，业务查询无感。
    """
    __tablename__ = "market_snapshot"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:         Mapped[datetime] = mapped_column(DateTime, nullable=False)         # UTC
    trade_date: Mapped[datetime] = mapped_column(Date, nullable=False)             # Asia/Shanghai 日期
    symbol:     Mapped[str]      = mapped_column(
        String(64), ForeignKey("symbol_registry.symbol"), nullable=False
    )
    price:      Mapped[Optional[float]] = mapped_column(Float)
    prev_close: Mapped[Optional[float]] = mapped_column(Float)
    pct:        Mapped[Optional[float]] = mapped_column(Float)
    amount:     Mapped[Optional[float]] = mapped_column(Float)
    volume:     Mapped[Optional[float]] = mapped_column(Float)
    stage:      Mapped[Optional[str]]   = mapped_column(String(16))     # live/lunch/closed/pre
    source:     Mapped[Optional[str]]   = mapped_column(String(32))     # sina/eastmoney
    raw_json:   Mapped[Optional[dict]]  = mapped_column(JSON)

    __table_args__ = (
        Index("idx_snapshot_symbol_ts", "symbol", "ts"),
        Index("idx_snapshot_trade_date", "trade_date", "symbol"),
    )


# ═══════════════════════════════════════════════════════
# Event Layer
# ═══════════════════════════════════════════════════════

class PushLog(Base):
    """所有推送落库（可视化主查询源）"""
    __tablename__ = "push_log"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:           Mapped[datetime] = mapped_column(DateTime, nullable=False)       # UTC
    trade_date:   Mapped[datetime] = mapped_column(Date, nullable=False)
    monitor:      Mapped[str]      = mapped_column(
        String(64), ForeignKey("monitor_registry.name"), nullable=False
    )
    scenario:     Mapped[Optional[str]]  = mapped_column(String(64))     # hk_only_down/neutral/...
    max_level:    Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    title:        Mapped[Optional[str]]  = mapped_column(String(256))
    message:      Mapped[str]            = mapped_column(Text, nullable=False)
    context_json: Mapped[Optional[dict]] = mapped_column(JSON)
    sent_ok:      Mapped[Optional[bool]] = mapped_column(Boolean)
    error:        Mapped[Optional[str]]  = mapped_column(Text)

    # 反向关系
    signals: Mapped[list["SignalEvent"]] = relationship(
        back_populates="push_log", cascade="save-update"
    )

    __table_args__ = (
        Index("idx_push_monitor_ts", "monitor", "ts"),
        Index("idx_push_trade_date", "trade_date", "monitor"),
        Index("idx_push_level", "max_level", "ts"),
    )


class SignalEvent(Base):
    """信号识别记录（识别到即记录，不管是否推送）

    与 push_log 分离：支持"识别到但未推送"的信号也可分析。
    """
    __tablename__ = "signal_event"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts:           Mapped[datetime] = mapped_column(DateTime, nullable=False)
    trade_date:   Mapped[datetime] = mapped_column(Date, nullable=False)
    monitor:      Mapped[str]      = mapped_column(
        String(64), ForeignKey("monitor_registry.name"), nullable=False
    )
    signal_type:  Mapped[str]      = mapped_column(
        String(64), ForeignKey("signal_type_registry.signal_type"), nullable=False
    )
    symbol:       Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("symbol_registry.symbol")
    )
    level:        Mapped[Optional[int]]   = mapped_column(Integer)
    hk_avg_pct:   Mapped[Optional[float]] = mapped_column(Float)   # 联动场景冗余字段
    a_avg_pct:    Mapped[Optional[float]] = mapped_column(Float)
    metrics_json: Mapped[Optional[dict]]  = mapped_column(JSON)
    push_log_id:  Mapped[Optional[int]]   = mapped_column(
        Integer, ForeignKey("push_log.id")
    )

    push_log: Mapped[Optional["PushLog"]] = relationship(back_populates="signals")

    __table_args__ = (
        Index("idx_signal_monitor_ts", "monitor", "ts"),
        Index("idx_signal_type_ts", "signal_type", "ts"),
    )


class AlertDedup(Base):
    """告警去重（替代当前 JSON state 文件）

    复合主键：(monitor, dedup_key)
    """
    __tablename__ = "alert_dedup"

    monitor:    Mapped[str]      = mapped_column(String(64), primary_key=True)
    dedup_key:  Mapped[str]      = mapped_column(String(256), primary_key=True)  # e.g. '恒生指数_2026-07-09_L2'
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    trade_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("idx_dedup_trade_date", "trade_date"),
    )


# ═══════════════════════════════════════════════════════
# Derived Layer（前端主查询）
# ═══════════════════════════════════════════════════════

class DailySummary(Base):
    """每日推送汇总（前端 dashboard 主视图）"""
    __tablename__ = "daily_summary"

    trade_date:      Mapped[datetime] = mapped_column(Date, primary_key=True)
    total_pushes:    Mapped[Optional[int]]  = mapped_column(Integer)
    l3_count:        Mapped[Optional[int]]  = mapped_column(Integer)
    l2_count:        Mapped[Optional[int]]  = mapped_column(Integer)
    l1_count:        Mapped[Optional[int]]  = mapped_column(Integer)
    monitors_active: Mapped[Optional[list]] = mapped_column(JSON)   # ["hk_shock",...]
    key_events:      Mapped[Optional[list]] = mapped_column(JSON)   # [{"monitor":...,"summary":...}]
    updated_at:      Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class SignalOutcome(Base):
    """信号验证（Phase 2 核心，Phase 1 建表预留）"""
    __tablename__ = "signal_outcome"

    id:                  Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_event_id:     Mapped[int] = mapped_column(
        Integer, ForeignKey("signal_event.id"), nullable=False
    )
    signal_type:         Mapped[str] = mapped_column(
        String(64), ForeignKey("signal_type_registry.signal_type"), nullable=False
    )
    trade_date:          Mapped[datetime] = mapped_column(Date, nullable=False)
    predicted_direction: Mapped[Optional[int]]   = mapped_column(Integer)   # -1/0/+1
    t1_pct:              Mapped[Optional[float]] = mapped_column(Float)     # T+1 涨跌幅
    t3_pct:              Mapped[Optional[float]] = mapped_column(Float)
    t5_pct:              Mapped[Optional[float]] = mapped_column(Float)
    t1_hit:              Mapped[Optional[bool]]  = mapped_column(Boolean)   # T+1 方向命中
    t3_hit:              Mapped[Optional[bool]]  = mapped_column(Boolean)
    verified_at:         Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        Index("idx_outcome_signal_type", "signal_type"),
    )


class SymbolOhlcDaily(Base):
    """前端专用日 K 表（冗余，防止实时算）

    复合主键：(symbol, trade_date)
    """
    __tablename__ = "symbol_ohlc_daily"

    symbol:     Mapped[str]      = mapped_column(
        String(64), ForeignKey("symbol_registry.symbol"), primary_key=True
    )
    trade_date: Mapped[datetime] = mapped_column(Date, primary_key=True)
    open:       Mapped[Optional[float]] = mapped_column(Float)
    high:       Mapped[Optional[float]] = mapped_column(Float)
    low:        Mapped[Optional[float]] = mapped_column(Float)
    close:      Mapped[Optional[float]] = mapped_column(Float)
    volume:     Mapped[Optional[float]] = mapped_column(Float)
    amount:     Mapped[Optional[float]] = mapped_column(Float)
    pct:        Mapped[Optional[float]] = mapped_column(Float)


# ═══════════════════════════════════════════════════════
# Trade Journal Layer（交易日志系统，W1）
# ═══════════════════════════════════════════════════════

class PaperTrade(Base):
    """纸面交易记录（paper trading）

    一笔记录 = 一个完整持仓（开仓 + 可选平仓）。
    - status='open'  : 未平仓，close_at / close_price / pnl 皆为 NULL
    - status='closed': 已平仓，自动计算 pnl / pnl_pct
    - action='long'  : 做多（买）。内地不支持 short，暂时只支持 long

    与 signal_event 关联：若交易决策来自某个推送信号，可回填 signal_event_id，
    后续能统计"那个信号历史赚亏盖率"。
    """
    __tablename__ = "paper_trade"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol:          Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name:            Mapped[Optional[str]]   = mapped_column(String(128))
    action:          Mapped[str] = mapped_column(String(8), nullable=False, default="long")  # long/short
    strategy:        Mapped[Optional[str]]   = mapped_column(String(64))    # ah_arb/etf_disc/tobacco/manual
    tag:             Mapped[Optional[str]]   = mapped_column(String(64))

    # 开仓
    entry_at:        Mapped[datetime]  = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    entry_price:     Mapped[float]     = mapped_column(Float, nullable=False)
    qty:             Mapped[float]     = mapped_column(Float, nullable=False)
    entry_reason:    Mapped[Optional[str]] = mapped_column(Text)

    # 平仓（可空）
    close_at:        Mapped[Optional[datetime]] = mapped_column(DateTime)
    close_price:     Mapped[Optional[float]]    = mapped_column(Float)
    close_reason:    Mapped[Optional[str]]      = mapped_column(Text)

    # 风控（可选）
    stop_loss:       Mapped[Optional[float]] = mapped_column(Float)
    take_profit:     Mapped[Optional[float]] = mapped_column(Float)

    # 盈亏（平仓后自动计算）
    pnl:             Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct:         Mapped[Optional[float]] = mapped_column(Float)
    hold_days:       Mapped[Optional[int]]   = mapped_column(Integer)

    status:          Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)

    # 关联到推送信号（可选）
    signal_event_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("signal_event.id"), nullable=True
    )

    notes:           Mapped[Optional[str]]  = mapped_column(Text)

    __table_args__ = (
        Index("idx_paper_trade_status", "status"),
        Index("idx_paper_trade_strategy", "strategy"),
        Index("idx_paper_trade_entry_at", "entry_at"),
    )


class TradeSignalLink(Base):
    """推送信号 ↔ 交易决策关联

    一个 signal_event 可能触发了多笔交易，也可能未触发任何交易（看了但没动手）。
    - decision = 'act'  : 已根据信号下单（至少一笔 paper_trade）
    - decision = 'skip' : 看到信号但主动不动（后续可回看是否错过机会）
    - decision = 'noise': 当时判定为噪声

    用途：统计"推送信号"→"实际决策"→"盈亏"的完整链路。
    """
    __tablename__ = "trade_signal_link"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("signal_event.id"), nullable=False, index=True
    )
    paper_trade_id:  Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("paper_trade.id")
    )
    decision:        Mapped[str] = mapped_column(String(16), nullable=False)  # act/skip/noise
    reason:          Mapped[Optional[str]] = mapped_column(Text)
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_signal_link_decision", "decision"),
    )


class TradeReview(Base):
    """周/月复盘归因

    period_type: 'week' 或 'month'
    period_key : 'YYYY-Www'（week）或 'YYYY-MM'（month）
    主键：(period_type, period_key)
    """
    __tablename__ = "trade_review"

    period_type:      Mapped[str]   = mapped_column(String(8),  primary_key=True)
    period_key:       Mapped[str]   = mapped_column(String(16), primary_key=True)

    trade_count:      Mapped[int]   = mapped_column(Integer, default=0, nullable=False)
    win_count:        Mapped[int]   = mapped_column(Integer, default=0, nullable=False)
    loss_count:       Mapped[int]   = mapped_column(Integer, default=0, nullable=False)
    win_rate:         Mapped[Optional[float]] = mapped_column(Float)
    total_pnl:        Mapped[Optional[float]] = mapped_column(Float)
    avg_win:          Mapped[Optional[float]] = mapped_column(Float)
    avg_loss:         Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown:     Mapped[Optional[float]] = mapped_column(Float)
    best_trade_id:    Mapped[Optional[int]]   = mapped_column(Integer, ForeignKey("paper_trade.id"))
    worst_trade_id:   Mapped[Optional[int]]   = mapped_column(Integer, ForeignKey("paper_trade.id"))
    notes:            Mapped[Optional[str]]   = mapped_column(Text)
    generated_at:     Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
