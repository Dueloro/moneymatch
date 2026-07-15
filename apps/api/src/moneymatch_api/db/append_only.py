"""Append-only guard DDL for the immutable ledgers.

Shared by migration 0002 (production schema) and the test schema builder so the
UPDATE/DELETE rejection is identical in both — `ledger_entries` and
`platform_ledger` are audit trails and must never be rewritten (00-README §3.2).
"""

from __future__ import annotations

APPEND_ONLY_TABLES = ("ledger_entries", "platform_ledger")

_FUNCTION_DDL = """
CREATE OR REPLACE FUNCTION mm_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger is append-only: % on % is forbidden',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""


def _trigger_ddl(table: str) -> str:
    return (
        f"CREATE TRIGGER {table}_append_only "
        f"BEFORE UPDATE OR DELETE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation();"
    )


def install_statements() -> list[str]:
    """DDL statements that install the append-only guard, in order."""
    return [_FUNCTION_DDL, *[_trigger_ddl(t) for t in APPEND_ONLY_TABLES]]
