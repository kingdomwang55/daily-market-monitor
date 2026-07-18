"""FastAPI dependencies shared by API routes."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from ..data import get_session


def get_db_session() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session
