"""Solo-pool engine — queue-matched rooms with personalized bars (07-phase-4).

Ports the settlement invariant from `poc-reference/api/_lib/solo_challenge.py`
(clearers split pool − rake; none clear → full refund, zero rake; unverifiable
refunded off the top; floats → integer cents) and adds the new fairness layer:

- **enqueue** freezes the player's baseline and `personal_bar = round(μ + k·σ)`
  after the gates (geo-fence *before* anything, provisional metric, sandbagging).
  No escrow while waiting (architecture §3.3) — escrow happens at room formation.
- **room formation** (match-on-write, `FOR UPDATE SKIP LOCKED`) groups compatible
  tickets, derives `room_bar = round(mean(personal_bars))`, and forms **only if
  the composition predicate holds for every member** (a shark or a hopeless
  outlier is refused) — then escrows the group.
- **settle** grades each entry's first qualifying match vs. `room_bar` and splits
  the pool; `reconciliation_service` is the money enforcer.

No API surface accepts a bar, room bar, or payout — every number is derived here
from stored inputs and re-derives byte-for-byte for audit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    ENTRY_PRESETS_CENTS,
    FLAG_QUEUE_PAUSED,
    METRIC_BAR_INCREMENT,
    METRIC_PROVISIONAL_MIN_N,
    POOL_BAR_SPREAD_CAP_SIGMA,
    POOL_DIFFICULTY_K,
    POOL_ENGINE_VERSION,
    POOL_GAMES,
    POOL_METRICS,
    POOL_MIN_ROOM,
    POOL_ROOM_SIZE,
    POOL_WINDOW_SECONDS,
    QUEUE_TICKET_TTL_SECONDS,
    game_flag_key,
)
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import QueueTicket
from ..models.pools import SoloEntry, SoloPool
from ..models.skill import MetricModel
from ..models.user import User
from . import (
    fairness,
    geo_service,
    limits_service,
    matchmaking,
    money_math,
    notifications_service,
    pairing,
    sandbagging_service,
    wallet_service,
)
from .feature_flags import get_boolean_flags


def _pbar(ticket: QueueTicket) -> float:
    """A pool ticket's frozen personal bar (always set on pool tickets)."""
    return float(ticket.personal_bar or 0.0)


log = structlog.get_logger(__name__)

REF_POOL = "solo_pool"


class PoolError(APIError):
    """A pool enqueue/formation failure (RFC-7807 via APIError)."""


@dataclass
class PoolEnqueueResult:
    status: str  # "searching" | "formed"
    pool: SoloPool | None = None
    ticket: QueueTicket | None = None


@dataclass
class PoolGrade:
    """The worker's per-entry grading input."""

    cleared: bool | None  # True/False, or None = unverifiable → refund
    telemetry: dict[str, Any] | None = None
    raw_payload_id: uuid.UUID | None = None


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Eligibility + baselines.
# --------------------------------------------------------------------------- #


def _validate_bucket(game: str, metric: str, difficulty: str, entry_cents: int) -> None:
    if game not in POOL_GAMES:
        raise PoolError(
            "pool_game_unavailable",
            f"Pools aren't offered for {game}.",
            status_code=404,
        )
    if metric not in POOL_METRICS.get(game, ()):
        raise PoolError(
            "unknown_pool_metric", f"'{metric}' isn't a pool metric.", status_code=404
        )
    if difficulty not in POOL_DIFFICULTY_K:
        raise PoolError(
            "unknown_difficulty", f"'{difficulty}' isn't a difficulty.", status_code=422
        )
    if entry_cents not in ENTRY_PRESETS_CENTS:
        raise PoolError(
            "invalid_entry",
            "Entry must be a preset.",
            status_code=422,
            detail={"allowed": list(ENTRY_PRESETS_CENTS)},
        )


async def _metric_model(
    session: AsyncSession, user_id: uuid.UUID, game: str, metric: str
) -> MetricModel | None:
    return await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user_id,
            MetricModel.game == game,
            MetricModel.metric == metric,
        )
    )


async def _require_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount:
    link = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id, LinkedAccount.game == game
        )
    )
    if link is None or link.status != "active":
        raise PoolError("not_linked", f"Link a {game} account first.", status_code=409)
    return link


async def preview_bars(
    session: AsyncSession, user: User, game: str, metric: str
) -> dict[str, Any]:
    """The three difficulty bars quoted from the viewer's own baseline + the
    disclosed clear rates. Provisional metrics return no bars (can't duel)."""
    model = await _metric_model(session, user.id, game, metric)
    n = model.n if model else 0
    provisional = n < METRIC_PROVISIONAL_MIN_N
    increment = METRIC_BAR_INCREMENT.get(metric, 0.01)
    cards: list[dict[str, Any]] = []
    if model is not None and not provisional:
        for difficulty, k in POOL_DIFFICULTY_K.items():
            cards.append(
                {
                    "difficulty": difficulty,
                    "bar": fairness.personal_bar(model.mu, model.sigma, k, increment),
                    "clear_rate": round(fairness.p_target_for_k(k), 4),
                }
            )
    return {"metric": metric, "provisional": provisional, "n": n, "cards": cards}


async def _build_baseline(
    session: AsyncSession,
    user: User,
    game: str,
    metric: str,
    difficulty: str,
    link: LinkedAccount,
) -> tuple[dict[str, Any], float]:
    """Freeze the metric model + host id, compute the personal bar for `difficulty`."""
    model = await _metric_model(session, user.id, game, metric)
    if model is None or model.n < METRIC_PROVISIONAL_MIN_N:
        raise PoolError(
            "metric_provisional",
            "Not enough recent matches to enter a pool on this stat yet.",
            status_code=409,
            detail={"metric": metric, "n": model.n if model else 0},
        )
    increment = METRIC_BAR_INCREMENT.get(metric, 0.01)
    bar = fairness.personal_bar(
        model.mu, model.sigma, POOL_DIFFICULTY_K[difficulty], increment
    )
    baseline = {
        "linked_account_id": str(link.id),
        "host_account_id": link.host_account_id,
        "metric": metric,
        "mu": float(model.mu),
        "sigma": float(model.sigma),
        "n": int(model.n),
    }
    return baseline, bar


# --------------------------------------------------------------------------- #
# Room composition (all fairness numbers derived from frozen ticket baselines).
# --------------------------------------------------------------------------- #


def _room_bar(tickets: list[QueueTicket], metric: str) -> float:
    increment = METRIC_BAR_INCREMENT.get(metric, 0.01)
    return fairness.room_bar([_pbar(t) for t in tickets], increment)


def _composes(
    tickets: list[QueueTicket], difficulty: str, metric: str
) -> tuple[float, bool]:
    """Return (room_bar, fair?) for a candidate group."""
    bars = [_pbar(t) for t in tickets]
    mus = [float(t.baseline_snapshot["mu"]) for t in tickets]
    sigmas = [float(t.baseline_snapshot["sigma"]) for t in tickets]
    bar = _room_bar(tickets, metric)
    p_target = fairness.p_target_for_k(POOL_DIFFICULTY_K[difficulty])
    ok = fairness.composition_ok(
        bar,
        list(zip(mus, sigmas, strict=True)),
        p_target,
        bars=bars,
        sigmas=sigmas,
        spread_cap_sigma=POOL_BAR_SPREAD_CAP_SIGMA,
    )
    return bar, ok


async def _all_pairs_pairable(
    session: AsyncSession, tickets: list[QueueTicket], now: datetime
) -> bool:
    for i in range(len(tickets)):
        for j in range(i + 1, len(tickets)):
            if not await matchmaking.can_pair(session, tickets[i], tickets[j], now):
                return False
    return True


# --------------------------------------------------------------------------- #
# Ticket + room formation.
# --------------------------------------------------------------------------- #


async def get_waiting_ticket(
    session: AsyncSession, user_id: uuid.UUID
) -> QueueTicket | None:
    return await session.scalar(
        select(QueueTicket).where(
            QueueTicket.user_id == user_id,
            QueueTicket.product == "pool",
            QueueTicket.state == "waiting",
        )
    )


async def _current_pool_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> SoloPool | None:
    return await session.scalar(
        select(SoloPool)
        .join(SoloEntry, SoloEntry.pool_id == SoloPool.id)
        .where(SoloEntry.user_id == user_id, SoloPool.state == "LOCKED")
        .order_by(SoloPool.created_at.desc())
        .limit(1)
    )


async def _get_or_create_ticket(
    session: AsyncSession,
    user: User,
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
    baseline: dict[str, Any],
    bar: float,
    link: LinkedAccount,
    now: datetime,
) -> QueueTicket:
    existing = await get_waiting_ticket(session, user.id)
    if existing is not None:
        same = (
            existing.game == game
            and existing.market == metric
            and existing.difficulty == difficulty
            and existing.entry_cents == entry_cents
        )
        if same:
            return existing
        existing.state = "canceled"
        await session.flush()

    ticket = QueueTicket(
        user_id=user.id,
        linked_account_id=link.id,
        game=game,
        product="pool",
        market=metric,
        difficulty=difficulty,
        entry_cents=entry_cents,
        baseline_snapshot=baseline,
        personal_bar=bar,
        state="waiting",
        expires_at=now + timedelta(seconds=QUEUE_TICKET_TTL_SECONDS),
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def _form_room(
    session: AsyncSession,
    tickets: list[QueueTicket],
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
    room_bar: float,
    now: datetime,
) -> SoloPool:
    """Create the room, escrow every member, and retire their tickets."""
    pool = SoloPool(
        game=game,
        metric=metric,
        difficulty=difficulty,
        room_bar=room_bar,
        entry_cents=entry_cents,
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        room_size=len(tickets),
        min_entrants=POOL_MIN_ROOM,
        pot_cents=entry_cents * len(tickets),
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(seconds=POOL_WINDOW_SECONDS),
        engine_version=POOL_ENGINE_VERSION,
    )
    session.add(pool)
    await session.flush()

    for ticket in tickets:
        await wallet_service.escrow_hold(
            session,
            ticket.user_id,
            entry_cents,
            ref_type=REF_POOL,
            ref_id=pool.id,
            memo=f"{metric} {difficulty} pool entry",
        )
        session.add(
            SoloEntry(
                pool_id=pool.id,
                user_id=ticket.user_id,
                linked_account_id=ticket.linked_account_id,
                host_account_id=ticket.baseline_snapshot["host_account_id"],
                personal_bar=_pbar(ticket),
                baseline_snapshot=ticket.baseline_snapshot,
            )
        )
        ticket.state = "matched"
        ticket.pool_id = pool.id
        await notifications_service.emit(
            session,
            ticket.user_id,
            "room_filled",
            {
                "kind": "pool",
                "pool_id": str(pool.id),
                "metric": metric,
                "difficulty": difficulty,
                "room_bar": room_bar,
                "entry_cents": entry_cents,
            },
        )
    await session.flush()
    log.info(
        "pool.formed",
        pool_id=str(pool.id),
        metric=metric,
        difficulty=difficulty,
        room_bar=room_bar,
        size=len(tickets),
    )
    return pool


async def _users_by_id(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    rows = await session.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: u for u in rows}


async def _try_form_room(
    session: AsyncSession,
    user: User,
    ticket: QueueTicket,
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
    now: datetime,
) -> SoloPool | None:
    """Lock compatible waiting tickets and form a fair room if one exists."""
    if not await limits_service.can_stake(session, user, entry_cents):
        return None  # the enqueuer can't stake yet — keep waiting

    candidates = list(
        await session.scalars(
            select(QueueTicket)
            .where(
                and_(
                    QueueTicket.product == "pool",
                    QueueTicket.game == game,
                    QueueTicket.market == metric,
                    QueueTicket.difficulty == difficulty,
                    QueueTicket.entry_cents == entry_cents,
                    QueueTicket.state == "waiting",
                    QueueTicket.user_id != ticket.user_id,
                    QueueTicket.expires_at > now,
                )
            )
            .order_by(QueueTicket.created_at.asc())
            .with_for_update(skip_locked=True)
        )
    )
    users = await _users_by_id(session, [c.user_id for c in candidates])
    # Only consider candidates who can currently be escrowed.
    stakeable = [
        c
        for c in candidates
        if await limits_service.can_stake(session, users[c.user_id], entry_cents)
    ]
    # Nearest personal bars first (tightest room).
    stakeable.sort(key=lambda c: abs(_pbar(c) - _pbar(ticket)))

    age = max(0.0, (now - ticket.created_at).total_seconds())
    sizes = [POOL_ROOM_SIZE]
    if pairing.is_widening_exhausted(age):
        sizes.append(POOL_MIN_ROOM)

    for size in sizes:
        if len(stakeable) < size - 1:
            continue
        group = [ticket, *stakeable[: size - 1]]
        if not await _all_pairs_pairable(session, group, now):
            continue
        room_bar, ok = _composes(group, difficulty, metric)
        if ok:
            return await _form_room(
                session, group, game, metric, difficulty, entry_cents, room_bar, now
            )
    return None


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


async def enqueue(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
) -> PoolEnqueueResult:
    """Enter a pool (enqueue). Gates run in order; escrow waits for formation."""
    now = _now()
    _validate_bucket(game, metric, difficulty, entry_cents)

    flags = await get_boolean_flags(session)
    if flags.get(FLAG_QUEUE_PAUSED, False):
        raise PoolError("queue_paused", "Pools are paused right now.", status_code=503)
    if not flags.get(game_flag_key(game), True):
        raise PoolError("game_disabled", "This game is disabled.", status_code=409)
    if user.status != "active":
        raise PoolError(
            "account_not_active", f"Account is {user.status}.", status_code=409
        )

    # Geo-fence BEFORE anything else can touch money.
    await geo_service.assert_can_enter(session, user.residence_state)

    link = await _require_link(session, user.id, game)
    # Sandbagging block (metric wagers) — with the personal-bar feature.
    await sandbagging_service.assert_not_sandbagging(
        session, user, game, metric, link.host_account_id
    )

    existing = await _current_pool_for_user(session, user.id)
    if existing is not None:
        return PoolEnqueueResult(status="formed", pool=existing)

    baseline, bar = await _build_baseline(session, user, game, metric, difficulty, link)
    ticket = await _get_or_create_ticket(
        session, user, game, metric, difficulty, entry_cents, baseline, bar, link, now
    )

    pool = await _try_form_room(
        session, user, ticket, game, metric, difficulty, entry_cents, now
    )
    if pool is not None:
        return PoolEnqueueResult(status="formed", pool=pool)
    return PoolEnqueueResult(status="searching", ticket=ticket)


async def poll_status(session: AsyncSession, user: User) -> PoolEnqueueResult:
    """Where the viewer stands: in a formed room, still searching (retry a pass),
    or idle."""
    now = _now()
    existing = await _current_pool_for_user(session, user.id)
    if existing is not None:
        return PoolEnqueueResult(status="formed", pool=existing)
    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return PoolEnqueueResult(status="idle")
    if ticket.expires_at > now:
        pool = await _try_form_room(
            session,
            user,
            ticket,
            ticket.game,
            ticket.market,
            ticket.difficulty or "medium",
            ticket.entry_cents,
            now,
        )
        if pool is not None:
            return PoolEnqueueResult(status="formed", pool=pool)
    return PoolEnqueueResult(status="searching", ticket=ticket)


async def cancel(session: AsyncSession, user: User) -> bool:
    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return False
    ticket.state = "canceled"
    await session.flush()
    return True


# --------------------------------------------------------------------------- #
# Settlement (called by the worker with server-fetched grading).
# --------------------------------------------------------------------------- #


async def _entries(session: AsyncSession, pool_id: uuid.UUID) -> list[SoloEntry]:
    rows = await session.scalars(
        select(SoloEntry)
        .where(SoloEntry.pool_id == pool_id)
        .order_by(SoloEntry.created_at.asc())
    )
    return list(rows)


async def settle_pool(
    session: AsyncSession, pool: SoloPool, grades: dict[uuid.UUID, PoolGrade]
) -> SoloPool:
    """Grade + pay a pool. Clearers split pool − rake; unverifiable refunded off
    the top; nobody clears → full refund, zero rake. Idempotent on terminal."""
    if pool.state in ("SETTLED", "CANCELED"):
        return pool
    entries = await _entries(session, pool.id)
    entry_cents = pool.entry_cents

    for e in entries:
        g = grades.get(e.user_id, PoolGrade(cleared=None))
        e.telemetry = g.telemetry
        e.raw_payload_id = g.raw_payload_id

    clearers = [
        e for e in entries if grades.get(e.user_id, PoolGrade(None)).cleared is True
    ]
    missers = [
        e for e in entries if grades.get(e.user_id, PoolGrade(None)).cleared is False
    ]
    unverifiable = [
        e for e in entries if grades.get(e.user_id, PoolGrade(None)).cleared is None
    ]

    if not clearers:
        # No verifiable winner → refund every entry, zero rake.
        for e in entries:
            await wallet_service.refund(
                session,
                e.user_id,
                entry_cents,
                ref_type=REF_POOL,
                ref_id=pool.id,
                memo="pool refund (no clearers)",
            )
            e.status = "REFUNDED"
            e.payout_cents = entry_cents
            await _notify(session, e.user_id, pool, "refund", entry_cents)
        pool.prize_cents = 0
        pool.rake_cents = 0
    else:
        for e in unverifiable:
            await wallet_service.refund(
                session,
                e.user_id,
                entry_cents,
                ref_type=REF_POOL,
                ref_id=pool.id,
                memo="pool refund (unverifiable)",
            )
            e.status = "REFUNDED"
            e.payout_cents = entry_cents
            await _notify(session, e.user_id, pool, "refund", entry_cents)

        consuming = clearers + missers
        distributable = entry_cents * len(consuming)
        split = money_math.split_pot(distributable, len(clearers), pool.rake_bps)
        for e in consuming:
            await wallet_service.escrow_release(
                session,
                e.user_id,
                entry_cents,
                ref_type=REF_POOL,
                ref_id=pool.id,
                memo="stake to pool",
            )
        share = split.payouts_cents[0]
        for e in clearers:
            await wallet_service.payout(
                session,
                e.user_id,
                share,
                ref_type=REF_POOL,
                ref_id=pool.id,
                memo="pool prize",
            )
            e.status = "CLEARED"
            e.payout_cents = share
            await _notify(session, e.user_id, pool, "settled", share)
        for e in missers:
            e.status = "MISSED"
            e.payout_cents = 0
            await _notify(session, e.user_id, pool, "settled", 0)
        await wallet_service.rake(
            session,
            split.rake_cents,
            ref_type=REF_POOL,
            ref_id=pool.id,
            memo="pool rake",
        )
        pool.prize_cents = share * len(clearers)
        pool.rake_cents = split.rake_cents

    pool.state = "SETTLED"
    pool.resolved_at = _now()
    await session.flush()
    await _assert_reconciled(session, pool)
    log.info(
        "pool.settled",
        pool_id=str(pool.id),
        clearers=len(clearers),
        missers=len(missers),
        refunded=len(unverifiable) if clearers else len(entries),
    )
    return pool


async def cancel_pool(
    session: AsyncSession, pool: SoloPool, *, reason: str
) -> SoloPool:
    """Under-min / kill-switch cancel: refund every entry, zero rake."""
    if pool.state in ("SETTLED", "CANCELED"):
        return pool
    for e in await _entries(session, pool.id):
        await wallet_service.refund(
            session,
            e.user_id,
            pool.entry_cents,
            ref_type=REF_POOL,
            ref_id=pool.id,
            memo=f"pool refund ({reason})",
        )
        e.status = "REFUNDED"
        e.payout_cents = pool.entry_cents
        await _notify(session, e.user_id, pool, "refund", pool.entry_cents)
    pool.prize_cents = 0
    pool.rake_cents = 0
    pool.state = "CANCELED"
    pool.outcome_detail = {"reason": reason}
    pool.resolved_at = _now()
    await session.flush()
    await _assert_reconciled(session, pool)
    return pool


async def _notify(
    session: AsyncSession, user_id: uuid.UUID, pool: SoloPool, kind: str, payout: int
) -> None:
    await notifications_service.emit(
        session,
        user_id,
        kind,
        {"kind": "pool", "pool_id": str(pool.id), "payout_cents": payout},
    )


async def _assert_reconciled(session: AsyncSession, pool: SoloPool) -> None:
    from . import reconciliation_service

    recon = await reconciliation_service.check(session, REF_POOL, pool.id)
    if not recon.ok:
        from .match_lifecycle import ReconciliationError

        raise ReconciliationError(pool.id, recon.violations)
