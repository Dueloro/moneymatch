"""DB-backed matchmaking — the PoC's in-memory queue, moved onto Postgres.

Ports `poc-reference/api/_lib/match_queue.py` (11-migration-map §1) with the
substrate rewritten: in-memory dicts → `queue_tickets`/`matches` rows, floats →
integer cents, and pairing upgraded to the launch-plan §4.5(d) **duel-forecast**
model (the pure math lives in `services/pairing.py`).

The load-bearing property is **match-on-write, race-safe**: a pairing pass locks
candidate tickets with `FOR UPDATE SKIP LOCKED`, so two concurrent enqueues
racing for one waiting ticket produce exactly one match (the loser simply keeps
waiting). No escrow is taken while waiting — escrow happens at match confirm
(`services/match_lifecycle.py`); a ticket past its TTL is expired by the worker.

The **`can_pair` seam is the one anti-collusion chokepoint** (self-pair,
same-host, 24 h repeat, provisional metrics); keep every rejection here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    ENTRY_PRESETS_CENTS,
    FLAG_QUEUE_PAUSED,
    MATCH_CONFIRM_TTL_SECONDS,
    METRIC_PROVISIONAL_MIN_N,
    QUEUE_TICKET_TTL_SECONDS,
    REPAIR_COOLDOWN_SECONDS,
    game_flag_key,
)
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer, QueueTicket
from ..models.skill import MetricModel
from ..models.user import User
from ..schemas.play import Forecast
from ..schemas.profile import ProfileSnapshot
from . import (
    analytics,
    money_math,
    notifications_service,
    pairing,
    sandbagging_service,
    skill_rating,
)
from .feature_flags import get_boolean_flags
from .markets import (
    KIND_STAT_RACE,
    KIND_WIN_H2H,
    MarketDef,
)
from .markets import (
    get as get_market,
)
from .match_states import PENDING

log = structlog.get_logger(__name__)


class MatchmakingError(APIError):
    """A queue/pairing failure (RFC-7807 via APIError)."""


@dataclass
class EnqueueResult:
    status: str  # "matched" | "searching"
    match: Match | None = None
    ticket: QueueTicket | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _age_seconds(ticket: QueueTicket, now: datetime) -> float:
    return max(0.0, (now - ticket.created_at).total_seconds())


# --------------------------------------------------------------------------- #
# Eligibility (who may queue this market at all).
# --------------------------------------------------------------------------- #


async def _flags(session: AsyncSession) -> dict[str, bool]:
    return await get_boolean_flags(session)


def _resolve_market(game: str, market_key: str, speed: str | None) -> MarketDef:
    market = get_market(game, market_key)
    if market is None:
        raise MatchmakingError(
            "unknown_market",
            f"'{market_key}' is not a market for {game}.",
            status_code=404,
        )
    if market.requires_speed and not speed:
        raise MatchmakingError(
            "speed_required",
            "This market needs a time control.",
            status_code=422,
        )
    return market


async def _require_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount:
    link = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id,
            LinkedAccount.game == game,
            LinkedAccount.status != "unbound",  # ignore soft-unbound history rows
        )
    )
    if link is None:
        raise MatchmakingError(
            "not_linked",
            f"Link a {game} account before you can play it.",
            status_code=409,
        )
    if link.status != "active":
        raise MatchmakingError(
            "account_frozen",
            "This linked account is frozen.",
            status_code=409,
        )
    return link


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


async def _assert_eligible(
    session: AsyncSession,
    user: User,
    game: str,
    market: MarketDef,
    link: LinkedAccount,
) -> None:
    """Account active, game enabled, and (stat races) non-provisional on the metric."""
    if user.status != "active":
        raise MatchmakingError(
            "account_not_active",
            f"Account is {user.status}; play is disabled.",
            status_code=409,
        )
    flags = await _flags(session)
    if not flags.get(game_flag_key(game), True):
        raise MatchmakingError(
            "game_disabled", "This game is currently disabled.", status_code=409
        )
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        model = await _metric_model(session, user.id, game, market.metric)
        n = model.n if model else 0
        if n < METRIC_PROVISIONAL_MIN_N:
            raise MatchmakingError(
                "metric_provisional",
                "Not enough recent matches to duel on this stat yet — "
                "play a few more and check back.",
                status_code=409,
                detail={"metric": market.metric, "n": n},
            )
        # Cheap sandbagging gate for H2H stat duels: honor an existing flag from
        # the nightly sweep without a per-enqueue host call (backlog · Phase B —
        # "extend the sandbagging block to H2H stat duels" + "cache the eval").
        await sandbagging_service.assert_not_flagged(
            session, user.id, game, market.metric
        )


# --------------------------------------------------------------------------- #
# Baselines — frozen at enqueue so a later model refresh can't move an in-flight
# pairing (06-phase-3 · baseline snapshots frozen).
# --------------------------------------------------------------------------- #


async def _build_baseline(
    session: AsyncSession,
    user: User,
    market: MarketDef,
    link: LinkedAccount,
    speed: str | None,
) -> dict:
    snapshot = link.profile_snapshot or {}
    baseline: dict = {
        "linked_account_id": str(link.id),
        "host_account_id": link.host_account_id,
    }
    if market.kind == KIND_WIN_H2H:  # chess — Elo band
        profile = ProfileSnapshot(**snapshot) if snapshot else None
        baseline["rating"] = (
            skill_rating.rating_for_speed(profile, speed) if profile else 1500
        )
    else:
        baseline["rating"] = snapshot.get("rating")  # faceit elo / mmr (may be None)
    if market.kind == KIND_STAT_RACE and market.metric is not None:
        model = await _metric_model(session, user.id, market.game, market.metric)
        baseline["metric"] = market.metric
        baseline["mu"] = float(model.mu) if model else 0.0
        baseline["sigma"] = float(model.sigma) if model else 0.0
        baseline["n"] = int(model.n) if model else 0
    return baseline


# --------------------------------------------------------------------------- #
# can_pair — the anti-collusion seam (keep every rejection in one function).
# --------------------------------------------------------------------------- #


async def _recent_pair_exists(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID, now: datetime
) -> bool:
    since = now - timedelta(seconds=REPAIR_COOLDOWN_SECONDS)
    p1 = MatchPlayer.__table__.alias("p1")
    p2 = MatchPlayer.__table__.alias("p2")
    stmt = select(
        exists().where(
            and_(
                p1.c.match_id == p2.c.match_id,
                p1.c.user_id == a,
                p2.c.user_id == b,
                p1.c.created_at >= since,
            )
        )
    )
    return bool(await session.scalar(stmt))


async def can_pair(
    session: AsyncSession, me: QueueTicket, cand: QueueTicket, now: datetime
) -> bool:
    """Whether two waiting tickets are allowed to be paired (anti-collusion).

    Rejects: the same platform user, the same linked host account, a re-pair of
    the same two accounts within the cooldown, and (stat races) a provisional
    metric on either frozen baseline.
    """
    if me.user_id == cand.user_id:
        return False
    if me.baseline_snapshot.get("host_account_id") == cand.baseline_snapshot.get(
        "host_account_id"
    ):
        return False
    if "metric" in me.baseline_snapshot or "metric" in cand.baseline_snapshot:
        if (
            me.baseline_snapshot.get("n", 0) < METRIC_PROVISIONAL_MIN_N
            or cand.baseline_snapshot.get("n", 0) < METRIC_PROVISIONAL_MIN_N
        ):
            return False
    if await _recent_pair_exists(session, me.user_id, cand.user_id, now):
        return False
    return True


# --------------------------------------------------------------------------- #
# Forecast eligibility + composite selection (pure math, fed frozen baselines).
# --------------------------------------------------------------------------- #


def _is_eligible(
    market: MarketDef, me: QueueTicket, cand: QueueTicket, now: datetime
) -> bool:
    age_a, age_b = _age_seconds(me, now), _age_seconds(cand, now)
    if market.kind == KIND_WIN_H2H:
        band = pairing.effective_chess_band(age_a, age_b)
        ra = me.baseline_snapshot.get("rating") or 1500
        rb = cand.baseline_snapshot.get("rating") or 1500
        return pairing.is_chess_eligible(int(ra), int(rb), band)
    if market.kind == KIND_STAT_RACE:
        prob = pairing.forecast_prob(
            me.baseline_snapshot.get("mu", 0.0),
            me.baseline_snapshot.get("sigma", 0.0),
            cand.baseline_snapshot.get("mu", 0.0),
            cand.baseline_snapshot.get("sigma", 0.0),
        )
        w = pairing.effective_w(age_a, age_b)
        return pairing.is_forecast_eligible(prob, w)
    return True  # win_next — compatibility-only


def _selection_score(market: MarketDef, me: QueueTicket, cand: QueueTicket) -> float:
    if market.kind == KIND_WIN_H2H:
        ra = me.baseline_snapshot.get("rating") or 1500
        rb = cand.baseline_snapshot.get("rating") or 1500
        return abs(int(ra) - int(rb))
    ra = me.baseline_snapshot.get("rating")
    rb = cand.baseline_snapshot.get("rating")
    return pairing.composite_score(
        me.baseline_snapshot.get("mu", 0.0),
        me.baseline_snapshot.get("sigma", 0.0),
        cand.baseline_snapshot.get("mu", 0.0),
        cand.baseline_snapshot.get("sigma", 0.0),
        rating_a=int(ra) if ra is not None else None,
        rating_b=int(rb) if rb is not None else None,
    )


def forecast_between(market: MarketDef, mine: dict, theirs: dict) -> Forecast:
    """The honest matched-card disclosure: P(you beat opponent) + a one-liner."""
    if market.kind == KIND_STAT_RACE:
        prob = pairing.forecast_prob(
            mine.get("mu", 0.0),
            mine.get("sigma", 0.0),
            theirs.get("mu", 0.0),
            theirs.get("sigma", 0.0),
        )
    elif market.kind == KIND_WIN_H2H:
        prob = skill_rating.win_expectancy(
            int(mine.get("rating") or 1500), int(theirs.get("rating") or 1500)
        )
    else:
        prob = 0.5  # win_next has no skill forecast — an even coin by construction
    pct = round(prob * 100)
    if 0.45 <= prob <= 0.55:
        label = f"Even duel — model gives you {pct}%"
    elif prob > 0.55:
        label = f"Slight edge to you — model gives you {pct}%"
    else:
        label = f"You're the underdog — model gives you {pct}%"
    return Forecast(you_win_prob=round(prob, 4), label=label)


# --------------------------------------------------------------------------- #
# Ticket + match formation.
# --------------------------------------------------------------------------- #


async def _current_match_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> Match | None:
    """A live (non-terminal) match the user is already in — enqueue is idempotent."""
    return await session.scalar(
        select(Match)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(
            MatchPlayer.user_id == user_id,
            Match.state.in_((PENDING, "ACTIVE", "AWAITING_RESULT")),
        )
        .order_by(Match.created_at.desc())
        .limit(1)
    )


async def get_waiting_ticket(
    session: AsyncSession, user_id: uuid.UUID
) -> QueueTicket | None:
    return await session.scalar(
        select(QueueTicket).where(
            QueueTicket.user_id == user_id, QueueTicket.state == "waiting"
        )
    )


async def _get_or_create_ticket(
    session: AsyncSession,
    user: User,
    market: MarketDef,
    entry_cents: int,
    speed: str | None,
    baseline: dict,
    link: LinkedAccount,
    now: datetime,
) -> QueueTicket:
    """One waiting duel ticket per user; reuse the same bucket to preserve wait age."""
    existing = await get_waiting_ticket(session, user.id)
    if existing is not None:
        same = (
            existing.game == market.game
            and existing.market == market.key
            and existing.entry_cents == entry_cents
            and existing.speed == speed
        )
        if same:
            return existing
        existing.state = "canceled"  # switched buckets — retire the old ticket
        await session.flush()

    ticket = QueueTicket(
        user_id=user.id,
        linked_account_id=link.id,
        game=market.game,
        product="duel",
        market=market.key,
        speed=speed,
        entry_cents=entry_cents,
        rating=baseline.get("rating"),
        baseline_snapshot=baseline,
        tolerance_stage=0,
        state="waiting",
        expires_at=now + timedelta(seconds=QUEUE_TICKET_TTL_SECONDS),
    )
    session.add(ticket)
    await session.flush()
    return ticket


@dataclass
class MatchSide:
    """One seat's frozen inputs — the shared shape the ticket-paired and the
    challenge-formed paths both assemble a match from."""

    user_id: uuid.UUID
    linked_account_id: uuid.UUID
    host_account_id: str
    rating: int | None
    baseline_snapshot: dict


async def _assemble_match(
    session: AsyncSession,
    market: MarketDef,
    entry_cents: int,
    sides: list[MatchSide],
    now: datetime,
    *,
    speed: str | None,
    friendly: bool = False,
) -> Match:
    """Create a PENDING match + both seats from two frozen sides.

    `sides[0]` takes white (chess), `sides[1]` black. A `friendly` match books
    **zero rake** and refunds both entries on settle (the pair is past its
    rake-bearing cap — 08-phase-5); the winner is still graded for the record.
    """
    pot = entry_cents * 2
    rake_bps = 0 if friendly else market.rake_bps
    split = money_math.split_pot(pot, 1, rake_bps)
    match = Match(
        game=market.game,
        market=market.key,
        speed=speed,
        entry_cents=entry_cents,
        rake_bps=rake_bps,
        pot_cents=pot,
        prize_cents=split.payouts_cents[0],
        rake_cents=split.rake_cents,
        state=PENDING,
        brokered=market.brokered,
        friendly=friendly,
        window_ends_at=now + timedelta(seconds=MATCH_CONFIRM_TTL_SECONDS),
    )
    session.add(match)
    await session.flush()

    colors = ["white", "black"] if market.brokered else [None, None]
    for side, color in zip(sides, colors, strict=True):
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=side.user_id,
                linked_account_id=side.linked_account_id,
                host_account_id=side.host_account_id,
                color=color,
                rating=side.rating,
                baseline_snapshot=side.baseline_snapshot,
            )
        )
    await session.flush()

    for side in sides:
        await notifications_service.emit(
            session,
            side.user_id,
            "match_found",
            {
                "match_id": str(match.id),
                "game": market.game,
                "market": market.key,
                "entry_cents": match.entry_cents,
                "friendly": friendly,
            },
        )
        analytics.capture(
            analytics.MATCH_FOUND,
            side.user_id,
            {
                "match_id": str(match.id),
                "game": market.game,
                "market": market.key,
                "entry_cents": match.entry_cents,
                "friendly": friendly,
            },
        )
    log.info(
        "match.formed",
        match_id=str(match.id),
        game=market.game,
        market=market.key,
        entry_cents=match.entry_cents,
        friendly=friendly,
    )
    return match


def _ticket_side(ticket: QueueTicket) -> MatchSide:
    return MatchSide(
        user_id=ticket.user_id,
        linked_account_id=ticket.linked_account_id,
        host_account_id=ticket.baseline_snapshot["host_account_id"],
        rating=ticket.baseline_snapshot.get("rating"),
        baseline_snapshot=ticket.baseline_snapshot,
    )


async def _form_match(
    session: AsyncSession,
    market: MarketDef,
    me: QueueTicket,
    opp: QueueTicket,
    now: datetime,
) -> Match:
    """Create the PENDING match + both seats from two tickets and retire the tickets."""
    # Chess assigns colors (the older waiting ticket = white, the newcomer = black).
    match = await _assemble_match(
        session,
        market,
        me.entry_cents,
        [_ticket_side(opp), _ticket_side(me)],
        now,
        speed=me.speed,
    )
    for ticket in (me, opp):
        ticket.state = "matched"
        ticket.match_id = match.id
    await session.flush()
    return match


async def create_challenge_match(
    session: AsyncSession,
    *,
    market: MarketDef,
    challenger: User,
    challenger_link: LinkedAccount,
    challengee: User,
    challengee_link: LinkedAccount,
    entry_cents: int,
    speed: str | None,
    friendly: bool,
) -> Match:
    """Form a PENDING match from an accepted challenge (no queue tickets).

    Runs the same assembly as a paired match — same escrow-at-confirm lifecycle,
    same server-owned economics — but the two sides come from a direct challenge
    rather than the forecast matcher (fairness is by consent here, 08-phase-5).
    The challenger takes seat 0 (white, for chess).
    """
    now = _now()
    challenger_baseline = await _build_baseline(
        session, challenger, market, challenger_link, speed
    )
    challengee_baseline = await _build_baseline(
        session, challengee, market, challengee_link, speed
    )
    sides = [
        MatchSide(
            user_id=challenger.id,
            linked_account_id=challenger_link.id,
            host_account_id=challenger_link.host_account_id,
            rating=challenger_baseline.get("rating"),
            baseline_snapshot=challenger_baseline,
        ),
        MatchSide(
            user_id=challengee.id,
            linked_account_id=challengee_link.id,
            host_account_id=challengee_link.host_account_id,
            rating=challengee_baseline.get("rating"),
            baseline_snapshot=challengee_baseline,
        ),
    ]
    return await _assemble_match(
        session, market, entry_cents, sides, now, speed=speed, friendly=friendly
    )


async def _pair_ticket(
    session: AsyncSession,
    ticket: QueueTicket,
    market: MarketDef,
    now: datetime,
    *,
    only_ticket_id: uuid.UUID | None = None,
) -> Match | None:
    """Lock compatible waiting candidates and form a match with the best eligible one.

    `FOR UPDATE SKIP LOCKED` makes this race-safe: a candidate another pass is
    already pairing is simply skipped, so no ticket is ever double-matched.
    """
    conds = [
        QueueTicket.game == market.game,
        QueueTicket.market == market.key,
        QueueTicket.entry_cents == ticket.entry_cents,
        QueueTicket.state == "waiting",
        QueueTicket.user_id != ticket.user_id,
        QueueTicket.expires_at > now,
    ]
    if market.requires_speed:
        conds.append(QueueTicket.speed == ticket.speed)
    if only_ticket_id is not None:
        conds.append(QueueTicket.id == only_ticket_id)

    candidates = list(
        await session.scalars(
            select(QueueTicket)
            .where(and_(*conds))
            .order_by(QueueTicket.created_at.asc())
            .with_for_update(skip_locked=True)
        )
    )

    best: tuple[float, QueueTicket] | None = None
    for cand in candidates:
        if not await can_pair(session, ticket, cand, now):
            continue
        if not _is_eligible(market, ticket, cand, now):
            continue
        score = _selection_score(market, ticket, cand)
        if best is None or score < best[0]:
            best = (score, cand)

    if best is None:
        return None
    return await _form_match(session, market, ticket, best[1], now)


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


async def enqueue(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    market_key: str,
    entry_cents: int,
    speed: str | None = None,
) -> EnqueueResult:
    """Join the queue for a market, pairing immediately if a fair opponent waits."""
    now = _now()
    if entry_cents not in ENTRY_PRESETS_CENTS:
        raise MatchmakingError(
            "invalid_entry",
            "Entry must be one of the offered presets.",
            status_code=422,
            detail={"allowed": list(ENTRY_PRESETS_CENTS)},
        )
    flags = await _flags(session)
    if flags.get(FLAG_QUEUE_PAUSED, False):
        raise MatchmakingError(
            "queue_paused", "Matchmaking is paused right now.", status_code=503
        )

    market = _resolve_market(game, market_key, speed)
    link = await _require_link(session, user.id, game)
    await _assert_eligible(session, user, game, market, link)

    existing = await _current_match_for_user(session, user.id)
    if existing is not None:
        return EnqueueResult(status="matched", match=existing)

    baseline = await _build_baseline(session, user, market, link, speed)
    ticket = await _get_or_create_ticket(
        session, user, market, entry_cents, speed, baseline, link, now
    )
    analytics.capture(
        analytics.ENTRY_QUEUED,
        user.id,
        {
            "game": game,
            "market": market.key,
            "entry_cents": entry_cents,
            "product": "duel",
        },
    )

    match = await _pair_ticket(session, ticket, market, now)
    if match is not None:
        return EnqueueResult(status="matched", match=match)
    return EnqueueResult(status="searching", ticket=ticket)


async def poll_status(session: AsyncSession, user: User) -> EnqueueResult:
    """Where the user stands: in a live match, still searching (retry pairing), or idle.

    Re-running the pairing pass here converges the two-both-waiting race (each
    side's own enqueue may have missed the other under READ COMMITTED).
    """
    now = _now()
    existing = await _current_match_for_user(session, user.id)
    if existing is not None:
        return EnqueueResult(status="matched", match=existing)

    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return EnqueueResult(status="idle")
    if ticket.expires_at <= now:
        return EnqueueResult(status="searching", ticket=ticket)

    market = get_market(ticket.game, ticket.market)
    if market is not None:
        match = await _pair_ticket(session, ticket, market, now)
        if match is not None:
            return EnqueueResult(status="matched", match=match)
    return EnqueueResult(status="searching", ticket=ticket)


async def take_waiting(
    session: AsyncSession, user: User, ticket_id: uuid.UUID
) -> Match:
    """Take the other side of a specific waiting ticket directly (design's Match pill).

    Runs the identical pairing checks — a crafted request cannot bypass the
    forecast window or `can_pair`.
    """
    now = _now()
    flags = await _flags(session)
    if flags.get(FLAG_QUEUE_PAUSED, False):
        raise MatchmakingError(
            "queue_paused", "Matchmaking is paused right now.", status_code=503
        )

    target = await session.scalar(
        select(QueueTicket).where(QueueTicket.id == ticket_id)
    )
    if target is None or target.state != "waiting" or target.expires_at <= now:
        raise MatchmakingError(
            "ticket_unavailable",
            "That waiting slot is no longer open.",
            status_code=409,
        )
    if target.user_id == user.id:
        raise MatchmakingError(
            "cannot_match_self", "You can't take your own slot.", status_code=409
        )

    market = _resolve_market(target.game, target.market, target.speed)
    link = await _require_link(session, user.id, target.game)
    await _assert_eligible(session, user, target.game, market, link)

    existing = await _current_match_for_user(session, user.id)
    if existing is not None:
        raise MatchmakingError(
            "already_in_match",
            "You're already in a live match — finish it first.",
            status_code=409,
        )

    baseline = await _build_baseline(session, user, market, link, target.speed)
    ticket = await _get_or_create_ticket(
        session, user, market, target.entry_cents, target.speed, baseline, link, now
    )
    match = await _pair_ticket(session, ticket, market, now, only_ticket_id=ticket_id)
    if match is None:
        raise MatchmakingError(
            "not_pairable",
            "That opponent isn't a fair match for you right now.",
            status_code=409,
        )
    return match


async def cancel(session: AsyncSession, user: User) -> bool:
    """Leave the queue (cancel the waiting ticket). No escrow was held. Returns
    whether a ticket was canceled."""
    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return False
    ticket.state = "canceled"
    await session.flush()
    return True


async def list_waiting(
    session: AsyncSession, user: User, *, game: str | None = None
) -> list[QueueTicket]:
    """Open waiting tickets of **other** users (the design's "Waiting to play" list)."""
    now = _now()
    conds = [
        QueueTicket.state == "waiting",
        QueueTicket.user_id != user.id,
        QueueTicket.expires_at > now,
    ]
    if game is not None:
        conds.append(QueueTicket.game == game)
    rows = await session.scalars(
        select(QueueTicket).where(and_(*conds)).order_by(QueueTicket.created_at.asc())
    )
    return list(rows)


async def expire_tickets(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Worker: mark waiting tickets past their TTL as expired. Returns the count."""
    now = now or _now()
    tickets = list(
        await session.scalars(
            select(QueueTicket)
            .where(QueueTicket.state == "waiting", QueueTicket.expires_at <= now)
            .with_for_update(skip_locked=True)
        )
    )
    for ticket in tickets:
        ticket.state = "expired"
    await session.flush()
    return len(tickets)


async def cancel_all_waiting(
    session: AsyncSession, *, now: datetime | None = None
) -> int:
    """Kill switch: drain the whole waiting queue (queue_paused). No escrow was
    held while waiting, so this is a clean cancel — nothing to refund."""
    tickets = list(
        await session.scalars(
            select(QueueTicket)
            .where(QueueTicket.state == "waiting")
            .with_for_update(skip_locked=True)
        )
    )
    for ticket in tickets:
        ticket.state = "canceled"
    await session.flush()
    return len(tickets)
