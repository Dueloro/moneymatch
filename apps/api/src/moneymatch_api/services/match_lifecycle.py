"""Match lifecycle — one transition per function, each transactional (00-README §3.4).

Every state change routes through here and through `wallet_service` for money, so
the invariant `sum(payouts) + rake == sum(entries)` holds on every path and a
tampered client can never move a number (it only sends ids):

- `confirm` — escrow the entry (server-owned amount) after the limit checks;
  when both seats confirm, `activate`.
- `activate` — chess brokers a Lichess open challenge restricted to the two
  linked handles and stores the graded game id; CS2/Dota go coordinated with a
  **server-stamped `matched_at`**. Sets the settlement window.
- `cancel_pending` — decline / PENDING-expiry → refund whoever escrowed, no rake.
- `settle` — WIN (winner payout + rake) · PUSH / CANCEL (refund both, zero rake);
  post-settle reconciliation is fail-closed (a breach raises → worker pauses).

Callers own the transaction boundary; these functions flush, never commit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters import registry
from ..constants import MATCH_SETTLE_WINDOW_SECONDS
from ..errors import APIError
from ..models.play import Match, MatchPlayer
from ..models.user import User
from ..services import (
    limits_service,
    notifications_service,
    reconciliation_service,
    wallet_service,
)
from ..services.hosts.errors import HostUnavailable
from . import match_states
from .match_states import ACTIVE, CANCELED, PENDING, PUSHED, SETTLED

log = structlog.get_logger(__name__)

REF_MATCH = "match"


class LifecycleError(APIError):
    """A match-transition failure (RFC-7807 via APIError)."""


class ReconciliationError(APIError):
    """Post-settle conservation breach — fail closed (00-README §3.3)."""

    def __init__(self, match_id: uuid.UUID, violations: list[str]) -> None:
        super().__init__(
            "reconciliation_breach",
            "Settlement failed its conservation check and was rolled back.",
            status_code=500,
            detail={"match_id": str(match_id), "violations": violations},
        )


# Outcome kinds the worker hands to `settle`.
WIN = "win"
PUSH = "push"
CANCEL = "cancel"

_KIND_TO_STATE = {WIN: SETTLED, PUSH: PUSHED, CANCEL: CANCELED}


@dataclass
class SettlementResult:
    """What the worker's grading pass concluded for a match."""

    kind: str  # WIN | PUSH | CANCEL
    winner_user_id: uuid.UUID | None = None
    stat_lines: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    outcome_detail: dict[str, Any] | None = None
    engine_version: str | None = None
    raw_payload_id: uuid.UUID | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def players(session: AsyncSession, match_id: uuid.UUID) -> list[MatchPlayer]:
    """Both seats of a match (locked-order-stable by created_at)."""
    rows = await session.scalars(
        select(MatchPlayer)
        .where(MatchPlayer.match_id == match_id)
        .order_by(MatchPlayer.created_at.asc())
    )
    return list(rows)


def _seat(seats: list[MatchPlayer], user_id: uuid.UUID) -> MatchPlayer:
    for seat in seats:
        if seat.user_id == user_id:
            return seat
    raise LifecycleError("not_a_player", "You are not in this match.", status_code=403)


# --------------------------------------------------------------------------- #
# Confirm → escrow → activate.
# --------------------------------------------------------------------------- #


async def confirm(session: AsyncSession, match: Match, user: User) -> Match:
    """Confirm a seat: escrow the entry now; when both confirm, activate the match."""
    seats = await players(session, match.id)
    seat = _seat(seats, user.id)
    if seat.confirmed_at is not None:
        return match  # idempotent double-confirm
    if match.state != PENDING:
        raise LifecycleError(
            "not_confirmable",
            "This match can no longer be confirmed.",
            status_code=409,
        )

    # Server-side gate (balance, daily caps, concurrency) — the PoC's `canJoin`
    # tautology dies here. Raises cleanly and leaves the match PENDING.
    await limits_service.assert_can_stake(session, user, match.entry_cents)
    await wallet_service.escrow_hold(
        session,
        user.id,
        match.entry_cents,
        ref_type=REF_MATCH,
        ref_id=match.id,
        memo=f"{match.market} entry",
    )
    seat.confirmed_at = _now()
    await session.flush()

    if all(s.confirmed_at is not None for s in seats):
        await _activate(session, match, seats)
    return match


async def _activate(
    session: AsyncSession, match: Match, seats: list[MatchPlayer]
) -> None:
    """Both confirmed → go ACTIVE. Brokers chess; stamps a server-owned `matched_at`."""
    match_states.assert_transition(match.state, ACTIVE)
    now = _now()

    if match.brokered:
        adapter = registry.get(match.game)
        handles = [s.host_account_id for s in seats]
        try:
            broker = await adapter.create_match(match.speed or "blitz", handles)
        except HostUnavailable as exc:
            raise LifecycleError(
                "broker_unavailable",
                "Couldn't create the game right now — try confirming again shortly.",
                status_code=502,
            ) from exc
        if not broker or not broker.get("game_id"):
            raise LifecycleError(
                "broker_failed",
                "Couldn't create the game right now — try confirming again shortly.",
                status_code=502,
            )
        match.host_game_id = broker["game_id"]
        urls = broker.get("urls") or {}
        for seat in seats:
            seat.play_url = urls.get(seat.color or "")

    match.matched_at = now
    match.window_ends_at = now + timedelta(seconds=MATCH_SETTLE_WINDOW_SECONDS)
    match.state = ACTIVE
    await session.flush()
    log.info(
        "match.activated",
        match_id=str(match.id),
        game=match.game,
        brokered=match.brokered,
        host_game_id=match.host_game_id,
    )


# --------------------------------------------------------------------------- #
# Cancel / decline / expiry (PENDING) — refund whoever escrowed, no rake.
# --------------------------------------------------------------------------- #


async def cancel_pending(session: AsyncSession, match: Match, *, reason: str) -> Match:
    """Decline or expire a PENDING match: refund every confirmed seat, zero rake."""
    if match_states.is_terminal(match.state):
        return match  # idempotent
    if match.state != PENDING:
        raise LifecycleError(
            "not_cancelable",
            "Only a pending match can be canceled here.",
            status_code=409,
        )
    match_states.assert_transition(match.state, CANCELED)
    seats = await players(session, match.id)
    for seat in seats:
        if seat.confirmed_at is not None:
            await wallet_service.refund(
                session,
                seat.user_id,
                match.entry_cents,
                ref_type=REF_MATCH,
                ref_id=match.id,
                memo=f"{reason} refund",
            )
            seat.payout_cents = match.entry_cents
            await notifications_service.emit(
                session,
                seat.user_id,
                "refund",
                {"match_id": str(match.id), "reason": reason},
            )
    match.state = CANCELED
    match.outcome_detail = {"reason": reason}
    match.resolved_at = _now()
    await session.flush()
    await _assert_reconciled(session, match)
    log.info("match.canceled", match_id=str(match.id), reason=reason)
    return match


# --------------------------------------------------------------------------- #
# Settle — WIN / PUSH / CANCEL from an ACTIVE (both-escrowed) match.
# --------------------------------------------------------------------------- #


async def settle(
    session: AsyncSession, match: Match, result: SettlementResult
) -> Match:
    """Apply a graded outcome. Winner-take-all with rake, or refund both on a
    push/cancel. Idempotent: a second call on a terminal match is a no-op."""
    if match_states.is_terminal(match.state):
        return match
    target = _KIND_TO_STATE[result.kind]
    match_states.assert_transition(match.state, target)
    seats = await players(session, match.id)

    # A friendly is zero-rake and refunds both entries regardless of who won —
    # only the record is kept (08-phase-5 · collusion posture). We still stamp the
    # graded winner + stat lines, but the money flow is neutralized to refunds.
    if match.friendly and result.kind == WIN:
        match.winner_user_id = result.winner_user_id
        for seat in seats:
            await wallet_service.refund(
                session,
                seat.user_id,
                match.entry_cents,
                ref_type=REF_MATCH,
                ref_id=match.id,
                memo="friendly refund",
            )
            seat.payout_cents = match.entry_cents
    elif result.kind == WIN:
        if result.winner_user_id is None:
            raise LifecycleError(
                "winner_required", "A win needs a winner.", status_code=422
            )
        # Consume both escrowed stakes into the pot, pay the winner, book rake.
        for seat in seats:
            await wallet_service.escrow_release(
                session,
                seat.user_id,
                match.entry_cents,
                ref_type=REF_MATCH,
                ref_id=match.id,
                memo="stake to pot",
            )
        await wallet_service.payout(
            session,
            result.winner_user_id,
            match.prize_cents,
            ref_type=REF_MATCH,
            ref_id=match.id,
            memo=f"{match.market} prize",
        )
        await wallet_service.rake(
            session,
            match.rake_cents,
            ref_type=REF_MATCH,
            ref_id=match.id,
            memo=f"{match.market} rake",
        )
        match.winner_user_id = result.winner_user_id
        for seat in seats:
            seat.payout_cents = (
                match.prize_cents if seat.user_id == result.winner_user_id else 0
            )
    else:  # PUSH / CANCEL → refund both in full, no rake
        for seat in seats:
            await wallet_service.refund(
                session,
                seat.user_id,
                match.entry_cents,
                ref_type=REF_MATCH,
                ref_id=match.id,
                memo=f"{result.kind} refund",
            )
            seat.payout_cents = match.entry_cents

    for seat in seats:
        if seat.user_id in result.stat_lines:
            seat.stat_line = result.stat_lines[seat.user_id]

    match.state = target
    match.outcome_detail = result.outcome_detail
    match.engine_version = result.engine_version
    match.raw_payload_id = result.raw_payload_id
    match.resolved_at = _now()
    await session.flush()

    for seat in seats:
        kind = "settled" if result.kind in (WIN, PUSH) else "refund"
        await notifications_service.emit(
            session,
            seat.user_id,
            kind,
            {
                "match_id": str(match.id),
                "outcome": result.kind,
                "payout_cents": seat.payout_cents,
            },
        )

    await _assert_reconciled(session, match)
    log.info(
        "match.settled",
        match_id=str(match.id),
        outcome=result.kind,
        winner=str(result.winner_user_id) if result.winner_user_id else None,
    )
    return match


async def _assert_reconciled(session: AsyncSession, match: Match) -> None:
    """Fail closed: a per-match conservation breach rolls the transition back."""
    recon = await reconciliation_service.check(session, REF_MATCH, match.id)
    if not recon.ok:
        raise ReconciliationError(match.id, recon.violations)
