"""Alembic environment — async engine, URL from Settings, autogenerate metadata."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from moneymatch_api.config import get_settings
from moneymatch_api.models import Base  # registers all tables on the metadata

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is load-bearing, not tidiness.
    #
    # `fileConfig` defaults to True, which switches off every logger configured
    # *before* it runs. Alembic is normally a standalone process where that is
    # harmless, but anything that migrates in-process — a management command, a
    # data backfill, a test fixture — silently loses `httpx`, `httpcore` and any
    # other already-configured logger for the rest of that process.
    #
    # The symptom is the absence of log lines, which is the hardest kind of
    # failure to notice: nothing errors, output just stops. Caught by
    # `test_secret_logging.py` when the test suite began running migrations
    # (AUDIT_FINDINGS.md P2-2).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


# Columns whose server default is a Postgres function/expression that the server
# normalizes on read (casts, spacing), so the stored text never round-trips equal
# to the model's rendered default. Comparing them yields a permanent false drift;
# skip just these (the values are still enforced by the migration + model).
_SERVER_DEFAULT_SKIP = {("users", "friend_code")}

# Tables migrations 0028-0033 create for the bucketing layer, whose models live
# on feat/bucket_system. The migration chain is shared, so on a branch without
# those models the tables exist in the database with nothing on the metadata,
# and autogenerate would propose dropping them. `match_stats` is also range-
# partitioned by month (`match_stats_YYYYMM`, `match_stats_default`), and
# partitions never have models. Only *unmodeled* tables are skipped: once a
# model for one of these exists, it is compared like any other.
_UNMODELED_TABLES = {
    "audit_events",
    "bucket_contest",
    "bucket_dispute",
    "bucket_room",
    "market_reference",
    "market_state",
    "match_stats",
    "player_fingerprint",
    "player_streak",
    "settlement",
}


def _is_unmodeled(table_name: str | None) -> bool:
    if table_name is None or table_name in target_metadata.tables:
        return False
    return table_name in _UNMODELED_TABLES or table_name.startswith("match_stats_")


def _include_object(obj, name, type_, reflected, compare_to) -> bool:
    if not reflected or compare_to is not None:
        return True
    if type_ == "table":
        return not _is_unmodeled(name)
    table = getattr(obj, "table", None)
    return not _is_unmodeled(getattr(table, "name", None))


def _compare_server_default(
    _context,
    _inspected_column,
    metadata_column,
    _inspected_default,
    _metadata_default,
    _rendered_metadata_default,
) -> bool | None:
    if (metadata_column.table.name, metadata_column.name) in _SERVER_DEFAULT_SKIP:
        return False  # treat as "not different" → no spurious autogenerate op
    return None  # fall back to alembic's default comparison


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=_compare_server_default,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
