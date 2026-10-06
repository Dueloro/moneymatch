"""ledger ref_type — allow bucketing wagers to book to the ledgers (Phase 5)

The wallet ledgers whitelist `ref_type` (migration 0002). Bucketing settlements
move money through the same `wallet_service`, so `bucket_contest` (per-player
stake/payout/refund legs) and `bucket_room` (the room's rake) must be accepted
values. Extend both check constraints; nothing else changes.

Revision ID: 0030_ledger_bucket_ref_type
Revises: 0029_bucket_contests
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_ledger_bucket_ref_type"
down_revision: str | None = "0029_bucket_contests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail')"
_NEW = (
    "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail', "
    "'bucket_contest', 'bucket_room')"
)


def _swap(table: str, name: str, expr: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expr)


def upgrade() -> None:
    _swap("ledger_entries", "ck_ledger_ref_type", _NEW)
    _swap("platform_ledger", "ck_platform_ledger_ref_type", _NEW)


def downgrade() -> None:
    _swap("ledger_entries", "ck_ledger_ref_type", _OLD)
    _swap("platform_ledger", "ck_platform_ledger_ref_type", _OLD)
