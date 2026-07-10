"""数据库连接管理

关键设计：
- DB URL 支持环境变量覆盖（MARKET_DB_URL），默认 SQLite
- SQLite 启用 WAL 模式（并发读友好）
- 未来切 PG：只需改 MARKET_DB_URL=postgresql+psycopg2://...
- 业务代码永远只调 get_session()，不知道底层是啥
"""
import os
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine


# ─── 默认 DB 位置 ───────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "market.db"
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("MARKET_DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")


# ─── Engine（全局单例） ─────────────────────────────
def _make_engine():
    is_sqlite = DB_URL.startswith("sqlite")
    kwargs = dict(pool_pre_ping=True)
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(DB_URL, **kwargs)


_engine: Engine = _make_engine()


@event.listens_for(_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """SQLite 启用 WAL + 外键约束"""
    if DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")  # 写入更快，代价可接受
        cur.close()


_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine() -> Engine:
    return _engine


@contextmanager
def get_session() -> Session:
    """标准 session 上下文管理器，自动 commit/rollback

    用法:
        with get_session() as s:
            PushLogRepository(s).create(...)
    """
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(create_all: bool = True):
    """初始化 DB（首次运行时用）

    正式流程用 Alembic 迁移，但 create_all 用于快速起步。
    """
    from .models import Base
    if create_all:
        Base.metadata.create_all(_engine)


def db_info() -> dict:
    """返回当前 DB 状态（供 CLI/API 使用）"""
    return {
        "url": DB_URL,
        "is_sqlite": DB_URL.startswith("sqlite"),
        "path": str(DEFAULT_DB_PATH) if DB_URL.startswith("sqlite") else None,
    }
