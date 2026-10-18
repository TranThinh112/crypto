"""SQLAlchemy engine, sessions and transactional helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    """Owns the database engine and transaction boundaries."""

    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            path = Path(url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    def create_schema(self) -> None:
        from app.models import basket, bot_state, event_log, trade  # noqa: F401

        Base.metadata.create_all(self.engine)
        self._migrate_sqlite_schema()

    def _migrate_sqlite_schema(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        trade_columns = {
            "entry_number": "INTEGER",
            "initial_risk_amount": "FLOAT",
            "max_adverse_profit": "FLOAT DEFAULT 0",
            "max_favorable_profit": "FLOAT DEFAULT 0",
            "max_adverse_r": "FLOAT DEFAULT 0",
            "max_favorable_r": "FLOAT DEFAULT 0",
        }
        with self.engine.begin() as connection:
            existing = {row[1] for row in connection.execute(text("PRAGMA table_info(trades)"))}
            for column, ddl in trade_columns.items():
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE trades ADD COLUMN {column} {ddl}"))

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            with session.begin():
                yield session
        finally:
            session.close()

    def healthcheck(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


def session_dependency(database: Database) -> Generator[Session, None, None]:
    with database.transaction() as session:
        yield session
