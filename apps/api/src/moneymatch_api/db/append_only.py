"""Append-only guard DDL for the immutable ledgers + audit tables.

Shared by the migrations and the test schema builder so the UPDATE/DELETE
rejection is identical in both. `ledger_entries` / `platform_ledger` are money
audit trails (migration 0002); `raw_payloads` is the grading-proof audit trail
(migration 0003). All must never be rewritten (00-README §3.2).

`APPEND_ONLY_TABLES` is the set migration 0002 installs and must stay as-is
(forward-only migrations). `ALL_APPEND_ONLY_TABLES` is the full current set the
test schema installs so tests exercise the production immutability.
"""

from __future__ import annotations

from collections.abc import Sequence

# Installed by migration 0002 — do not change (a later table joins the full set).
APPEND_ONLY_TABLES: tuple[str, ...] = ("ledger_entries", "platform_ledger")
# Every append-only table across all migrations (used by the test schema).
ALL_APPEND_ONLY_TABLES: tuple[str, ...] = (*APPEND_ONLY_TABLES, "raw_payloads")

_FUNCTION_DDL = """
CREATE OR REPLACE FUNCTION mm_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger is append-only: % on % is forbidden',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""


def trigger_ddl(table: str) -> str:
    """The trigger that rejects UPDATE/DELETE on ``table`` (function must exist)."""
    return (
        f"CREATE TRIGGER {table}_append_only "
        f"BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation();"
    )


def install_statements(tables: Sequence[str] = APPEND_ONLY_TABLES) -> list[str]:
    """DDL statements installing the guard for ``tables`` (function + triggers)."""
    return [_FUNCTION_DDL, *[trigger_ddl(t) for t in tables]]
