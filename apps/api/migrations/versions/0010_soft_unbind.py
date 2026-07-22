"""linked_accounts soft-unbind (partial-unique bindings)

Makes the two binding-uniqueness rules **partial** (only rows with
`status <> 'unbound'` occupy a slot) and adds the `unbound` status, so an admin
can soft-unbind an account that has contest history — the row is retained (its
match_players / queue_tickets FKs stay intact) while the host account is freed to
rebind to a new row. Replaces the hard-delete path that FK RESTRICT forbade
(backlog · "soft-unbind with contest history").

Revision ID: 0010_soft_unbind
Revises: 0009_risk_flag_kinds
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_soft_unbind"
down_revision: str | None = "0009_risk_flag_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE = sa.text("status <> 'unbound'")


def upgrade() -> None:
    op.drop_constraint(
        "uq_linked_accounts_user_game", "linked_accounts", type_="unique"
    )
    op.drop_constraint(
        "uq_linked_accounts_game_host", "linked_accounts", type_="unique"
    )
    op.create_index(
        "uq_linked_accounts_user_game",
        "linked_accounts",
        ["user_id", "game"],
        unique=True,
        postgresql_where=_ACTIVE,
    )
    op.create_index(
        "uq_linked_accounts_game_host",
        "linked_accounts",
        ["game", "host_account_id"],
        unique=True,
        postgresql_where=_ACTIVE,
    )
    op.drop_constraint(
        "ck_linked_accounts_status", "linked_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_linked_accounts_status",
        "linked_accounts",
        "status IN ('active', 'frozen', 'unbound')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_linked_accounts_status", "linked_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_linked_accounts_status",
        "linked_accounts",
        "status IN ('active', 'frozen')",
    )
    op.drop_index("uq_linked_accounts_game_host", "linked_accounts")
    op.drop_index("uq_linked_accounts_user_game", "linked_accounts")
    op.create_unique_constraint(
        "uq_linked_accounts_game_host",
        "linked_accounts",
        ["game", "host_account_id"],
    )
    op.create_unique_constraint(
        "uq_linked_accounts_user_game",
        "linked_accounts",
        ["user_id", "game"],
    )
