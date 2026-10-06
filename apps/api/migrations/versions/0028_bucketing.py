"""bucketing — the one-bar-per-bucket ranking & matchmaking data model (Phase 0)

Adds the tables the bucketing layer reads and writes, with the constraints that
make the later phases safe baked in from day one (idempotency, versioning,
append-only audit). Everything here is inert until the `bucketing_enabled`
feature flag (seeded off, below) is turned on.

Five tables:

- ``match_stats``      — append-only raw event log, one row per finished gradable
                         match per linked player, **every** field in ``metrics``.
                         Partitioned monthly by ``created_at_ms``; the idempotency
                         key ``(player_id, game, host_match_id, created_at_ms)``
                         is what makes re-ingestion a no-op. Append-only trigger.
- ``market_state``     — derived per-(player, game, mode, metric) state (Welford
                         mean/m2, window, index, confidence, bucket, placement).
                         Mutable, updated in place.
- ``market_reference`` — versioned, seasoned cut points + one bar per bucket. A
                         partial unique index enforces exactly one active row per
                         market.
- ``settlement``       — the audit row: which bucket/bar/reference_version graded
                         each contest, plus stake/payout. Append-only.
- ``audit_events``     — append-only log of anything that touched money or
                         placement (Phase 6). Created empty now.

The partition key interaction is deliberate: Postgres requires a partitioned
table's UNIQUE constraint to include the partition column, so the idempotency key
carries ``created_at_ms``. That is safe because a match's ``created_at_ms`` is
derived deterministically from the host record — re-ingesting the same match
yields the same tuple and conflicts, so ``ON CONFLICT DO NOTHING`` still bites.

Revision ID: 0028_bucketing
Revises: 0027_dismissed_checklists
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_bucketing"
down_revision: str | None = "0027_dismissed_checklists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Monthly partitions are pre-created across this window; a DEFAULT partition
# catches anything outside it so an insert can never fail for lack of a
# partition (a maintenance job — Phase 8 — extends the window before it's hit).
_PARTITION_FROM = (2025, 1)
_PARTITION_TO = (2028, 1)  # exclusive upper bound


def _month_ms(year: int, month: int) -> int:
    return int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)


def _iter_months(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) < end:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield (y, m), (ny, nm)
        y, m = ny, nm


def upgrade() -> None:
    # ----------------------------------------------------------------- #
    # match_stats — append-only, partitioned monthly by created_at_ms.
    # ----------------------------------------------------------------- #
    op.execute(
        """
        CREATE TABLE match_stats (
            id            uuid        NOT NULL DEFAULT gen_random_uuid(),
            player_id     uuid        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            game          varchar(32) NOT NULL,
            mode          varchar(24) NOT NULL,
            host_match_id varchar(128) NOT NULL,
            created_at_ms bigint      NOT NULL,
            won           boolean,
            metrics       jsonb       NOT NULL DEFAULT '{}',
            recorded_at   timestamptz NOT NULL DEFAULT now(),
            -- The partition key must be part of every unique key on a partitioned
            -- table; created_at_ms is deterministic from the match, so including
            -- it does not weaken the idempotency guarantee.
            PRIMARY KEY (id, created_at_ms),
            CONSTRAINT uq_match_stats_idem
                UNIQUE (player_id, game, host_match_id, created_at_ms)
        ) PARTITION BY RANGE (created_at_ms);
        """
    )
    op.create_index(
        "ix_match_stats_player_game_mode",
        "match_stats",
        ["player_id", "game", "mode"],
    )

    # Monthly partitions across the window, plus a DEFAULT safety net.
    for (y, m), (ny, nm) in _iter_months(_PARTITION_FROM, _PARTITION_TO):
        lo, hi = _month_ms(y, m), _month_ms(ny, nm)
        op.execute(
            f"CREATE TABLE match_stats_{y}{m:02d} PARTITION OF match_stats "
            f"FOR VALUES FROM ({lo}) TO ({hi});"
        )
    op.execute(
        "CREATE TABLE match_stats_default PARTITION OF match_stats DEFAULT;"
    )

    # Append-only guard: the shared mm_reject_mutation() trigger (installed by
    # migration 0002) rejects UPDATE/DELETE. Attach it to the parent; partitions
    # inherit row-level triggers in PG 13+.
    op.execute(
        "CREATE TRIGGER match_stats_append_only "
        "BEFORE UPDATE OR DELETE ON match_stats "
        "FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation();"
    )

    # ----------------------------------------------------------------- #
    # market_state — derived, mutable, one row per (player, game, mode, metric).
    # ----------------------------------------------------------------- #
    op.create_table(
        "market_state",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        # Welford state.
        sa.Column("mean", sa.Float, nullable=False, server_default="0"),
        sa.Column("m2", sa.Float, nullable=False, server_default="0"),
        sa.Column("n_samples", sa.Integer, nullable=False, server_default="0"),
        # Rolling last-20 window (oldest-first) + the damped index.
        sa.Column(
            "window",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("index_value", sa.Float, nullable=False, server_default="0"),
        sa.Column("index_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("peak_goodness", sa.Float, nullable=True),
        # Placement / bucket.
        sa.Column("bucket", sa.Integer, nullable=True),
        sa.Column("bucket_version", sa.Integer, nullable=True),
        sa.Column("placed_from", sa.String(16), nullable=True),
        sa.Column(
            "provisional", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "player_id",
            "game",
            "mode",
            "metric",
            name="uq_market_state_player_market",
        ),
    )
    op.create_index(
        "ix_market_state_market", "market_state", ["game", "mode", "metric"]
    )

    # ----------------------------------------------------------------- #
    # market_reference — versioned cut points + bars; one active per market.
    # ----------------------------------------------------------------- #
    op.create_table(
        "market_reference",
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("season", sa.Integer, nullable=False, server_default="1"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "cuts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "bars",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("k", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "lower_is_better", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("source", sa.String(16), nullable=False, server_default="'public'"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "game", "mode", "metric", "season", "version", name="pk_market_reference"
        ),
    )
    # Exactly one active version per market — a partial unique index, so trying to
    # activate two versions at once raises.
    op.execute(
        "CREATE UNIQUE INDEX uq_market_reference_one_active "
        "ON market_reference (game, mode, metric) WHERE active;"
    )

    # ----------------------------------------------------------------- #
    # settlement — append-only audit row, one per (contest, player).
    # ----------------------------------------------------------------- #
    op.create_table(
        "settlement",
        sa.Column("contest_id", sa.String(64), nullable=False),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("game", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("bucket", sa.Integer, nullable=False),
        sa.Column("bar", sa.Float, nullable=False),
        sa.Column("reference_season", sa.Integer, nullable=False),
        sa.Column("reference_version", sa.Integer, nullable=False),
        sa.Column("result_value", sa.Float, nullable=True),
        sa.Column("cleared", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("stake_cents", sa.BigInteger, nullable=False),
        sa.Column("payout_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("rake_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("refunded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "settled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("contest_id", "player_id", name="pk_settlement"),
    )
    op.create_index("ix_settlement_player", "settlement", ["player_id"])
    op.execute(
        "CREATE TRIGGER settlement_append_only "
        "BEFORE UPDATE OR DELETE ON settlement "
        "FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation();"
    )

    # ----------------------------------------------------------------- #
    # audit_events — append-only, everything that touched money/placement.
    # ----------------------------------------------------------------- #
    op.create_table(
        "audit_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("market", sa.String(112), nullable=True),
        sa.Column("contest_id", sa.String(64), nullable=True),
        sa.Column(
            "before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("actor", sa.String(16), nullable=False, server_default="'system'"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            index=True,
        ),
    )
    op.create_index("ix_audit_events_player", "audit_events", ["player_id"])
    op.create_index("ix_audit_events_contest", "audit_events", ["contest_id"])
    op.execute(
        "CREATE TRIGGER audit_events_append_only "
        "BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION mm_reject_mutation();"
    )

    # ----------------------------------------------------------------- #
    # Feature flag — seeded OFF. Nothing in this layer runs until it's on.
    # ----------------------------------------------------------------- #
    op.execute(
        "INSERT INTO feature_flags (key, enabled, payload) "
        "VALUES ('bucketing_enabled', false, '{}') "
        "ON CONFLICT (key) DO NOTHING;"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'bucketing_enabled';")
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;")
    op.drop_table("audit_events")
    op.execute("DROP TRIGGER IF EXISTS settlement_append_only ON settlement;")
    op.drop_table("settlement")
    op.execute(
        "DROP INDEX IF EXISTS uq_market_reference_one_active;"
    )
    op.drop_table("market_reference")
    op.drop_table("market_state")
    op.execute("DROP TRIGGER IF EXISTS match_stats_append_only ON match_stats;")
    # Dropping the parent cascades to every partition.
    op.execute("DROP TABLE IF EXISTS match_stats CASCADE;")
