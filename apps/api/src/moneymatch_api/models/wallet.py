"""Money aggregates (01-architecture §2 · Money).

`wallets` holds the **cached** balances (available / escrow / lifetime-net);
they are only ever mutated by `wallet_service` inside the same transaction that
appends the authoritative `ledger_entries` row. `ledger_entries` is append-only
(a DB trigger blocks UPDATE/DELETE — see migration 0002); every row records the
`balance_after_cents` so any point-in-time balance is a range query.

`platform_ledger` is the wallet-less chart of accounts (`platform:promo`,
`platform:rake`): promo funds every demo/signup credit so demo money never
appears from nowhere, and rake is booked here so both the per-contest invariant
`sum(payouts) + rake == sum(entries)` and the global solvency invariant
`sum(user available + escrow) == promo funding − rake` are checkable from the DB
alone. All money is integer cents (`BIGINT`); floats never touch a balance.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..caps import CAPS
from ..db.base import Base, TimestampMixin, uuid_pk

# Currencies. Only DEMO exists at MVP; CASH/GEMS reserve the column shape.
CURRENCIES = ("DEMO", "CASH", "GEMS")

# Ledger entry types (01-architecture §2). `amount_cents` applies to available,
# `escrow_delta_cents` to escrow; both signed.
ENTRY_TYPES = (
    "demo_deposit",
    "demo_withdrawal",
    "escrow_hold",
    "escrow_release",
    "payout",
    "rake",
    "refund",
    "adjustment",
)

# What a ledger row points at (the contest or rail that caused it).
REF_TYPES = ("match", "solo_pool", "tournament", "admin", "demo_rail")

# Chart of accounts for the wallet-less platform ledger.
PLATFORM_ACCOUNTS = ("platform:rake", "platform:promo")

# Default per-user staking limits. Sourced from the single Phase-1 caps table
# (caps.py) so the `limits` server-defaults and that table can never drift.
DEFAULT_DAILY_LOSS_CAP_CENTS = CAPS.daily_loss_cap_cents  # $200.00
DEFAULT_DAILY_ENTRY_CAP_CENTS = CAPS.daily_entry_cap_cents  # $500.00
DEFAULT_MAX_CONCURRENT_CONTESTS = CAPS.max_concurrent_contests

# Demo signup credit, booked as a real ledger row funded from platform:promo —
# not a magic starting balance (04-phase-1 · deliverable 3).
SIGNUP_GRANT_CENTS = 100_000  # $1,000.00

# Server-defined "Add funds" presets (no arbitrary client amounts — 04-phase-1
# design rules). $10 / $25 / $50 / $100.
DEMO_DEPOSIT_PRESETS_CENTS = (1_000, 2_500, 5_000, 10_000)

# Demo withdrawals are velocity-capped (04-phase-1 · deliverable 4).
DEMO_WITHDRAWAL_DAILY_LIMIT = 5


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_wallets_user_currency"),
        CheckConstraint(
            "currency IN ('DEMO', 'CASH', 'GEMS')", name="ck_wallets_currency"
        ),
        CheckConstraint("available_cents >= 0", name="ck_wallets_available_nonneg"),
        CheckConstraint("escrow_cents >= 0", name="ck_wallets_escrow_nonneg"),
    )

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(8), default="DEMO", server_default="DEMO", nullable=False
    )
    available_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    escrow_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    lifetime_net_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )


class LedgerEntry(Base):
    """Append-only wallet mutation. No `updated_at`: rows are immutable (the DB
    trigger in migration 0002 rejects UPDATE/DELETE)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('demo_deposit', 'demo_withdrawal', 'escrow_hold', "
            "'escrow_release', 'payout', 'rake', 'refund', 'adjustment')",
            name="ck_ledger_entry_type",
        ),
        CheckConstraint(
            "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail')",
            name="ck_ledger_ref_type",
        ),
        # Contest money-trail lookups (admin, reconciliation) hit (ref_type, ref_id).
        Index("ix_ledger_entries_ref", "ref_type", "ref_id"),
    )

    id = uuid_pk()
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    # Signed. Applied to the wallet's available balance.
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Signed. Applied to the wallet's escrow balance.
    escrow_delta_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    # Available balance after this row applied — makes any statement a range query.
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # clock_timestamp() (not now()) so every append gets its true insertion
    # instant — appends within one transaction stay totally ordered for audit
    # and cursor pagination.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )


class PlatformLedgerEntry(Base):
    """Append-only wallet-less ledger for the platform chart of accounts."""

    __tablename__ = "platform_ledger"
    __table_args__ = (
        CheckConstraint(
            "account IN ('platform:rake', 'platform:promo')",
            name="ck_platform_ledger_account",
        ),
        CheckConstraint(
            "ref_type IN ('match', 'solo_pool', 'tournament', 'admin', 'demo_rail')",
            name="ck_platform_ledger_ref_type",
        ),
    )

    id = uuid_pk()
    account: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Signed, from the account's perspective: promo goes negative as it funds
    # user credits; rake goes positive as it collects fees.
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # clock_timestamp() (not now()) so every append gets its true insertion
    # instant — appends within one transaction stay totally ordered for audit
    # and cursor pagination.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )


class Limit(Base, TimestampMixin):
    """Per-user staking limits, enforced server-side at escrow time. Raising a
    protective cap is delayed (`pending_*` + `effective_at`, promoted lazily);
    lowering is instant."""

    __tablename__ = "limits"

    id = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    daily_loss_cap_cents: Mapped[int] = mapped_column(
        BigInteger,
        default=DEFAULT_DAILY_LOSS_CAP_CENTS,
        server_default=str(DEFAULT_DAILY_LOSS_CAP_CENTS),
        nullable=False,
    )
    daily_entry_cap_cents: Mapped[int] = mapped_column(
        BigInteger,
        default=DEFAULT_DAILY_ENTRY_CAP_CENTS,
        server_default=str(DEFAULT_DAILY_ENTRY_CAP_CENTS),
        nullable=False,
    )
    max_concurrent_contests: Mapped[int] = mapped_column(
        Integer,
        default=DEFAULT_MAX_CONCURRENT_CONTESTS,
        server_default=str(DEFAULT_MAX_CONCURRENT_CONTESTS),
        nullable=False,
    )
    # A raise awaiting its 24h cooldown; promoted into the live caps once
    # `pending_effective_at` has passed (01-architecture §4 · PATCH /me).
    pending_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pending_effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
