"""Async engine + session factory and the FastAPI session dependency."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _connect_args(url: str) -> dict[str, Any]:
    """asyncpg options for the database URL.

    Supabase's transaction pooler (port 6543) hands each transaction to any
    server connection, so asyncpg's cached prepared statements would collide
    ("prepared statement already exists"). Behind it: no statement cache, and a
    unique name per statement. The session pooler and direct connections
    (port 5432) need nothing.
    """
    if ":6543/" not in url:
        return {}
    return {
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__",
    }


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
            # At most 10 connections from this process. Supabase's free tier
            # pools ~15 per database; the rest stay free for migrations and the
            # dashboard.
            pool_size=5,
            max_overflow=5,
            connect_args=_connect_args(settings.database_url),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session, committing on success."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
