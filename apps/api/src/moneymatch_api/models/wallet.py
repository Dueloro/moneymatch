"""Money aggregates. `wallets` holds the **cached** balances (available / escrow /
lifetime-net); they are only ever mutated by `wallet_service` inside the same
transaction that appends the authoritative `ledger_entries` row.
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

CURRENCIES = ("DEMO", "CASH", "GEMS")

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

REF_TYPES = ("match", "solo_pool", "tournament", "admin", "demo_rail")

PLATFORM_ACCOUNTS = ("platform:rake", "platform:promo")

DEFAULT_DAILY_LOSS_CAP_CENTS = CAPS.daily_loss_cap_cents
DEFAULT_DAILY_ENTRY_CAP_CENTS = CAPS.daily_entry_cap_cents
DEFAULT_DAILY_DEPOSIT_CAP_CENTS = CAPS.daily_deposit_cap_cents
DEFAULT_MAX_CONCURRENT_CONTESTS = CAPS.max_concurrent_contests

# Demo signup credit, booked as a real ledger row funded from platform:promo — not a
# magic starting balance.
SIGNUP_GRANT_CENTS = 100_000
SIGNUP_GRANT_MEMO = "signup grant"

DEMO_DEPOSIT_PRESETS_CENTS = (1_000, 2_500, 5_000, 10_000)

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
    """Append-only wallet mutation."""

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
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    escrow_delta_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    # Signed, from the account's perspective: promo goes negative as it funds user
    # credits; rake goes positive as it collects fees.
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
        index=True,
    )


class Limit(Base, TimestampMixin):
    """Per-user staking limits, enforced server-side at escrow time."""

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
    daily_deposit_cap_cents: Mapped[int] = mapped_column(
        BigInteger,
        default=DEFAULT_DAILY_DEPOSIT_CAP_CENTS,
        server_default=str(DEFAULT_DAILY_DEPOSIT_CAP_CENTS),
        nullable=False,
    )
    max_concurrent_contests: Mapped[int] = mapped_column(
        Integer,
        default=DEFAULT_MAX_CONCURRENT_CONTESTS,
        server_default=str(DEFAULT_MAX_CONCURRENT_CONTESTS),
        nullable=False,
    )
    timeout_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pending_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pending_effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
