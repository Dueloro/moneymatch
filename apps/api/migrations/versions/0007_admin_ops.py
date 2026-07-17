"""seed worker_heartbeat feature flag (admin ops)

Phase 6 adds no new tables — the admin surface reads the existing model. The one
data change is seeding the `worker_heartbeat` feature flag the settlement worker
upserts each cycle and `/health` + the admin reconciliation view read for
liveness. Seeded disabled with an empty payload until the worker's first cycle.

Revision ID: 0007_admin_ops
Revises: 0006_social
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_admin_ops"
down_revision: str | None = "0006_social"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('worker_heartbeat', false, '{}'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'worker_heartbeat'")
