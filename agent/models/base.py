"""Database engine and base model."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from agent.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables and apply schema migrations for new columns."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure new columns exist on existing tables (SQLAlchemy create_all
        # doesn't ALTER existing tables, only creates missing ones).
        await conn.run_sync(_migrate_columns)


def _migrate_columns(conn) -> None:
    """Add missing columns to existing tables (simple schema migration)."""
    import sqlalchemy as sa

    migrations = [
        ("scenes", "knowledge_json", "TEXT DEFAULT '[]'"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(sa.text(f"SELECT {column} FROM {table} LIMIT 1"))
        except Exception:
            conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            conn.execute(sa.text("COMMIT"))
