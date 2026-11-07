"""Solo-pool engine — queue-matched rooms with personalized bars."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..constants import (
    ENTRY_PRESETS_CENTS,
    FLAG_QUEUE_PAUSED,
    FORMATION_WIDEN_AFTER_SECONDS,
    METRIC_BAR_INCREMENT,
    POOL_BAR_SPREAD_CAP_SIGMA,
    POOL_DIFFICULTY_K,
    POOL_ENGINE_VERSION,
    POOL_GAMES,
    POOL_METRICS,
    POOL_MIN_ROOM,
    POOL_ROOM_SIZE,
    POOL_WINDOW_SECONDS,
    QUEUE_TICKET_TTL_SECONDS,
    STAT_BASELINE_MIN_N,
    game_flag_key,
    lower_is_better,
    metric_floor,
    positive_support,
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
    linking_service,
    matchmaking,
    metric_models_service,
    money_math,
    notifications_service,
    sandbagging_service,
    skill_prior,
    wallet_service,
)
from .feature_flags import get_boolean_flags


def _pbar(ticket: QueueTicket) -> float:
    return float(ticket.personal_bar or 0.0)


log = structlog.get_logger(__name__)

REF_POOL = "solo_pool"


class PoolError(APIError):
    """A pool enqueue/formation failure (RFC-7807 via APIError)."""


@dataclass
class PoolEnqueueResult:
    status: str
    pool: SoloPool | None = None
    ticket: QueueTicket | None = None


@dataclass
class PoolGrade:
    """The worker's per-entry grading input."""

    cleared: bool | None  # True/False, or None = unverifiable → refund
    telemetry: dict[str, Any] | None = None
    raw_payload_id: uuid.UUID | None = None


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


async def _require_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount:
    link = await linking_service.get_link(session, user_id, game)
    if link is None or link.status != "active":
        raise PoolError("not_linked", f"Link a {game} account first.", status_code=409)
    return link


def _shape(metric: str) -> dict[str, Any]:
    return {
        "increment": METRIC_BAR_INCREMENT.get(metric, 0.01),
        "lower_is_better": lower_is_better(metric),
        "positive": positive_support(metric),
        "floor": metric_floor(metric),
    }


def _corrected(
    model: MetricModel, metric: str, link: LinkedAccount | None
) -> tuple[float, float]:
    rating = skill_prior.host_rating(link) if link is not None else None
    mu, sigma = skill_prior.shrink(
        float(model.mu),
        float(model.sigma),
        int(model.n),
        skill_prior.prior_for(metric, rating),
    )
    return mu, fairness.effective_sigma(sigma, METRIC_BAR_INCREMENT.get(metric, 0.01))


async def preview_bars(
    session: AsyncSession, user: User, game: str, metric: str
) -> dict[str, Any]:
    """The three difficulty bars quoted from the viewer's own baseline + the
    disclosed clear rates.
    """
    model = await metric_models_service.get_metric_model(session, user.id, game, metric)
    n = model.n if model else 0
    provisional = n < STAT_BASELINE_MIN_N
    shape = _shape(metric)
    cards: list[dict[str, Any]] = []
    if model is not None and not provisional:
        link = await linking_service.get_link(session, user.id, game)
        mu, sigma = _corrected(model, metric, link)
        for difficulty, k in POOL_DIFFICULTY_K.items():
            bar = fairness.personal_bar(mu, sigma, k, **shape)
            cards.append(
                {
                    "difficulty": difficulty,
                    "bar": bar,
                    # Rounding to whole moves still shifts it off the nominal rate.
                    "clear_rate": round(
                        fairness.clear_prob(
                            bar,
                            mu,
                            sigma,
                            shape["lower_is_better"],
                            positive=shape["positive"],
                        ),
                        4,
                    ),
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
    model = await metric_models_service.get_metric_model(session, user.id, game, metric)
    if model is None or model.n < STAT_BASELINE_MIN_N:
        raise PoolError(
            "no_stat_baseline",
            "Play a match on this stat first — pools quote a bar from your results.",
            status_code=409,
            detail={"metric": metric, "n": model.n if model else 0},
        )
    mu, sigma_eff = _corrected(model, metric, link)
    bar = fairness.personal_bar(
        mu, sigma_eff, POOL_DIFFICULTY_K[difficulty], **_shape(metric)
    )
    baseline = {
        "linked_account_id": str(link.id),
        "host_account_id": link.host_account_id,
        "metric": metric,
        "mu": mu,
        "sigma": sigma_eff,
        "n": int(model.n),
    }
    return baseline, bar


def _room_bar(tickets: list[QueueTicket], metric: str) -> float:
    increment = METRIC_BAR_INCREMENT.get(metric, 0.01)
    return fairness.room_bar([_pbar(t) for t in tickets], increment)


def _composes(
    tickets: list[QueueTicket], difficulty: str, metric: str
) -> tuple[float, bool]:
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
        lower_is_better=lower_is_better(metric),
        positive=positive_support(metric),
    )
    return bar, ok


async def _all_pairs_pairable(
    session: AsyncSession, tickets: list[QueueTicket], now: datetime
) -> bool:
    for i in range(len(tickets)):
        for j in range(i + 1, len(tickets)):
            if not await matchmaking.can_pair(
                session,
                tickets[i],
                tickets[j],
                now,
            ):
                return False
    return True


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
    min_entrants: int = POOL_MIN_ROOM,
) -> SoloPool:
    pool = SoloPool(
        game=game,
        metric=metric,
        difficulty=difficulty,
        room_bar=room_bar,
        entry_cents=entry_cents,
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        room_size=len(tickets),
        min_entrants=min_entrants,
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
        return None

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
    stakeable = [
        c
        for c in candidates
        if await limits_service.can_stake(session, users[c.user_id], entry_cents)
    ]
    stakeable.sort(key=lambda c: abs(_pbar(c) - _pbar(ticket)))

    age = max(0.0, (now - ticket.created_at).total_seconds())
    sizes = [POOL_ROOM_SIZE]
    if age > FORMATION_WIDEN_AFTER_SECONDS:
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


async def enqueue(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    metric: str,
    difficulty: str,
    entry_cents: int,
) -> PoolEnqueueResult:
    now = clock.now()
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
    """Where the viewer stands: in a formed room, still searching (retry a pass), or
    idle.
    """
    now = clock.now()
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
    if ticket is not None:
        ticket.state = "canceled"
        await session.flush()
        return True
    return False


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
    """Grade + pay a pool. Clearers split pool − rake; unverifiable refunded off the
    top; nobody clears → full refund, zero rake.
    """
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
    pool.resolved_at = clock.now()
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
