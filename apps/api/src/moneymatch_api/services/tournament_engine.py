"""Tournament engine — matchmade single-metric fields (07-phase-4).

Ports the leaderboard settlement invariant from
`poc-reference/api/_lib/tournament.py` (top-N split by weight, renormalize when
fewer ranked than places, unverifiable refunded off the top, floats → integer
cents; the single-elim bracket is **cut**) and adds:

- **field formation** under a **μ-dispersion cap** `max(μ) − min(μ) ≤ cap·σ_pooled`
  (match-on-write, escrow at formation, no escrow while waiting).
- **first-N-average scoring**: the mean of the metric over the first N qualifying
  matches in the window (first-N, not best-of — extra games buy zero chances).
- **tie handling**: tied scores split their combined prize slices, remainder cents
  to the earlier enqueue (deterministic, disclosed); zero-match entrants forfeit
  (ranked last, paid nothing); fewer than `min_ranked` play → CANCELED + refund.

Every number is server-derived; no API surface accepts a score, rank, or payout.
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
    METRIC_PROVISIONAL_MIN_N,
    QUEUE_TICKET_TTL_SECONDS,
    TOURNAMENT_DISPERSION_CAP,
    TOURNAMENT_ENGINE_VERSION,
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_GAMES,
    TOURNAMENT_METRICS,
    TOURNAMENT_MIN_FIELD,
    TOURNAMENT_MIN_RANKED,
    TOURNAMENT_PRIZE_SPLIT,
    TOURNAMENT_SCORE_N,
    TOURNAMENT_WINDOW_SECONDS,
    game_flag_key,
)
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import QueueTicket
from ..models.skill import MetricModel
from ..models.tournaments import Tournament, TournamentEntry
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

log = structlog.get_logger(__name__)

REF_TOURNAMENT = "tournament"


class TournamentError(APIError):
    """A tournament enqueue/formation failure (RFC-7807 via APIError)."""


@dataclass
class TournamentEnqueueResult:
    status: str  # "searching" | "formed"
    tournament: Tournament | None = None
    ticket: QueueTicket | None = None


@dataclass
class TournamentGrade:
    """The worker's per-entry grading input.

    `values` is the metric from the entrant's first-N qualifying matches (in
    order); `None` = unverifiable (host couldn't fetch) → refund; `[]` = played no
    qualifying match → forfeit (ranked last, paid nothing).
    """

    values: list[float] | None
    telemetry: dict[str, Any] | None = None
    raw_payload_id: uuid.UUID | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _mu(ticket: QueueTicket) -> float:
    return float(ticket.baseline_snapshot["mu"])


# --------------------------------------------------------------------------- #
# Eligibility + baseline.
# --------------------------------------------------------------------------- #


def _validate_bucket(game: str, metric: str, entry_cents: int) -> None:
    if game not in TOURNAMENT_GAMES:
        raise TournamentError(
            "tournament_game_unavailable",
            f"Tournaments aren't offered for {game}.",
            status_code=404,
        )
    if metric not in TOURNAMENT_METRICS.get(game, ()):
        raise TournamentError(
            "unknown_tournament_metric",
            f"'{metric}' isn't a tournament metric.",
            status_code=404,
        )
    if entry_cents not in ENTRY_PRESETS_CENTS:
        raise TournamentError(
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
        raise TournamentError(
            "not_linked", f"Link a {game} account first.", status_code=409
        )
    return link


async def _build_baseline(
    session: AsyncSession, user: User, game: str, metric: str, link: LinkedAccount
) -> dict[str, Any]:
    model = await _metric_model(session, user.id, game, metric)
    if model is None or model.n < METRIC_PROVISIONAL_MIN_N:
        raise TournamentError(
            "metric_provisional",
            "Not enough recent matches to enter a tournament on this stat yet.",
            status_code=409,
            detail={"metric": metric, "n": model.n if model else 0},
        )
    return {
        "linked_account_id": str(link.id),
        "host_account_id": link.host_account_id,
        "metric": metric,
        "mu": float(model.mu),
        "sigma": float(model.sigma),
        "n": int(model.n),
    }


# --------------------------------------------------------------------------- #
# Field formation.
# --------------------------------------------------------------------------- #


def _field_ok(tickets: list[QueueTicket]) -> bool:
    mus = [_mu(t) for t in tickets]
    sigmas = [float(t.baseline_snapshot["sigma"]) for t in tickets]
    return fairness.dispersion_ok(mus, sigmas, TOURNAMENT_DISPERSION_CAP)


async def _all_pairs_pairable(
    session: AsyncSession, tickets: list[QueueTicket], now: datetime
) -> bool:
    for i in range(len(tickets)):
        for j in range(i + 1, len(tickets)):
            if not await matchmaking.can_pair(session, tickets[i], tickets[j], now):
                return False
    return True


async def get_waiting_ticket(
    session: AsyncSession, user_id: uuid.UUID
) -> QueueTicket | None:
    return await session.scalar(
        select(QueueTicket).where(
            QueueTicket.user_id == user_id,
            QueueTicket.product == "tournament",
            QueueTicket.state == "waiting",
        )
    )


async def _current_tournament_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> Tournament | None:
    return await session.scalar(
        select(Tournament)
        .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
        .where(TournamentEntry.user_id == user_id, Tournament.state == "LOCKED")
        .order_by(Tournament.created_at.desc())
        .limit(1)
    )


async def _users_by_id(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    rows = await session.scalars(select(User).where(User.id.in_(ids)))
    return {u.id: u for u in rows}


async def _get_or_create_ticket(
    session: AsyncSession,
    user: User,
    game: str,
    metric: str,
    entry_cents: int,
    baseline: dict[str, Any],
    link: LinkedAccount,
    now: datetime,
) -> QueueTicket:
    existing = await get_waiting_ticket(session, user.id)
    if existing is not None:
        if (
            existing.game == game
            and existing.market == metric
            and existing.entry_cents == entry_cents
        ):
            return existing
        existing.state = "canceled"
        await session.flush()

    ticket = QueueTicket(
        user_id=user.id,
        linked_account_id=link.id,
        game=game,
        product="tournament",
        market=metric,
        entry_cents=entry_cents,
        baseline_snapshot=baseline,
        state="waiting",
        expires_at=now + timedelta(seconds=QUEUE_TICKET_TTL_SECONDS),
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def _form_field(
    session: AsyncSession,
    tickets: list[QueueTicket],
    game: str,
    metric: str,
    entry_cents: int,
    now: datetime,
) -> Tournament:
    tournament = Tournament(
        game=game,
        ranking_metric=metric,
        entry_cents=entry_cents,
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        prize_split=list(TOURNAMENT_PRIZE_SPLIT),
        field_size=len(tickets),
        min_field=TOURNAMENT_MIN_FIELD,
        min_ranked=TOURNAMENT_MIN_RANKED,
        score_matches=TOURNAMENT_SCORE_N,
        pot_cents=entry_cents * len(tickets),
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(seconds=TOURNAMENT_WINDOW_SECONDS),
        engine_version=TOURNAMENT_ENGINE_VERSION,
    )
    session.add(tournament)
    await session.flush()

    for ticket in tickets:
        await wallet_service.escrow_hold(
            session,
            ticket.user_id,
            entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo=f"{metric} tournament entry",
        )
        session.add(
            TournamentEntry(
                tournament_id=tournament.id,
                user_id=ticket.user_id,
                linked_account_id=ticket.linked_account_id,
                host_account_id=ticket.baseline_snapshot["host_account_id"],
                baseline_snapshot=ticket.baseline_snapshot,
                enqueued_at=ticket.created_at,
            )
        )
        ticket.state = "matched"
        ticket.tournament_id = tournament.id
        await notifications_service.emit(
            session,
            ticket.user_id,
            "match_found",
            {
                "kind": "tournament",
                "tournament_id": str(tournament.id),
                "metric": metric,
                "entry_cents": entry_cents,
            },
        )
    await session.flush()
    log.info(
        "tournament.formed",
        tournament_id=str(tournament.id),
        metric=metric,
        size=len(tickets),
    )
    return tournament


async def _try_form_field(
    session: AsyncSession,
    user: User,
    ticket: QueueTicket,
    game: str,
    metric: str,
    entry_cents: int,
    now: datetime,
) -> Tournament | None:
    if not await limits_service.can_stake(session, user, entry_cents):
        return None

    candidates = list(
        await session.scalars(
            select(QueueTicket)
            .where(
                and_(
                    QueueTicket.product == "tournament",
                    QueueTicket.game == game,
                    QueueTicket.market == metric,
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
    stakeable.sort(key=lambda c: abs(_mu(c) - _mu(ticket)))

    age = max(0.0, (now - ticket.created_at).total_seconds())
    sizes = [TOURNAMENT_FIELD_SIZE]
    if pairing.is_widening_exhausted(age):
        sizes.append(TOURNAMENT_MIN_FIELD)

    for size in sizes:
        if len(stakeable) < size - 1:
            continue
        group = [ticket, *stakeable[: size - 1]]
        if not _field_ok(group):
            continue
        if not await _all_pairs_pairable(session, group, now):
            continue
        return await _form_field(session, group, game, metric, entry_cents, now)
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
    entry_cents: int,
) -> TournamentEnqueueResult:
    """Enter a tournament (enqueue). Gates in order; escrow at field formation."""
    now = _now()
    _validate_bucket(game, metric, entry_cents)

    flags = await get_boolean_flags(session)
    if flags.get(FLAG_QUEUE_PAUSED, False):
        raise TournamentError(
            "queue_paused", "Tournaments are paused right now.", status_code=503
        )
    if not flags.get(game_flag_key(game), True):
        raise TournamentError(
            "game_disabled", "This game is disabled.", status_code=409
        )
    if user.status != "active":
        raise TournamentError(
            "account_not_active", f"Account is {user.status}.", status_code=409
        )

    await geo_service.assert_can_enter(session, user.residence_state)
    link = await _require_link(session, user.id, game)
    await sandbagging_service.assert_not_sandbagging(
        session, user, game, metric, link.host_account_id
    )

    existing = await _current_tournament_for_user(session, user.id)
    if existing is not None:
        return TournamentEnqueueResult(status="formed", tournament=existing)

    baseline = await _build_baseline(session, user, game, metric, link)
    ticket = await _get_or_create_ticket(
        session, user, game, metric, entry_cents, baseline, link, now
    )
    tournament = await _try_form_field(
        session, user, ticket, game, metric, entry_cents, now
    )
    if tournament is not None:
        return TournamentEnqueueResult(status="formed", tournament=tournament)
    return TournamentEnqueueResult(status="searching", ticket=ticket)


async def poll_status(session: AsyncSession, user: User) -> TournamentEnqueueResult:
    now = _now()
    existing = await _current_tournament_for_user(session, user.id)
    if existing is not None:
        return TournamentEnqueueResult(status="formed", tournament=existing)
    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return TournamentEnqueueResult(status="idle")
    if ticket.expires_at > now:
        tournament = await _try_form_field(
            session, user, ticket, ticket.game, ticket.market, ticket.entry_cents, now
        )
        if tournament is not None:
            return TournamentEnqueueResult(status="formed", tournament=tournament)
    return TournamentEnqueueResult(status="searching", ticket=ticket)


async def cancel(session: AsyncSession, user: User) -> bool:
    ticket = await get_waiting_ticket(session, user.id)
    if ticket is None:
        return False
    ticket.state = "canceled"
    await session.flush()
    return True


# --------------------------------------------------------------------------- #
# Scoring + settlement.
# --------------------------------------------------------------------------- #


async def _entries(
    session: AsyncSession, tournament_id: uuid.UUID
) -> list[TournamentEntry]:
    rows = await session.scalars(
        select(TournamentEntry)
        .where(TournamentEntry.tournament_id == tournament_id)
        .order_by(TournamentEntry.enqueued_at.asc())
    )
    return list(rows)


def compute_standings(
    entries: list[TournamentEntry],
    scores: dict[uuid.UUID, float | None],
) -> list[tuple[TournamentEntry, int]]:
    """Rank scored entries (higher first); ties share a rank; forfeits rank last.

    Returns (entry, rank) best-first. Deterministic tie order by `enqueued_at`.
    """
    ranked = [e for e in entries if scores.get(e.id) is not None]
    ranked.sort(key=lambda e: (-scores[e.id], e.enqueued_at))  # type: ignore[operator]
    out: list[tuple[TournamentEntry, int]] = []
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and scores[ranked[j].id] == scores[ranked[i].id]:
            j += 1
        for e in ranked[i:j]:
            out.append((e, i + 1))  # tied share the group's starting rank
        i = j
    return out


def _assign_prizes(
    ranked: list[tuple[TournamentEntry, int]],
    slices: tuple[int, ...],
    scores: dict[uuid.UUID, float | None],
) -> dict[uuid.UUID, int]:
    """Map best-first ranked entries to prize slices, splitting tied places and
    sending any tie remainder to the earlier enqueue (invariant-exact)."""
    places = len(slices)
    payouts: dict[uuid.UUID, int] = {}
    pos = 0
    i = 0
    entries = [e for e, _ in ranked]
    while i < len(entries):
        j = i
        while j < len(entries) and scores[entries[j].id] == scores[entries[i].id]:
            j += 1
        group = entries[i:j]
        combined = sum(slices[p] for p in range(pos, min(pos + len(group), places)))
        if combined > 0:
            group_sorted = sorted(group, key=lambda e: e.enqueued_at)
            base, rem = divmod(combined, len(group))
            for idx, e in enumerate(group_sorted):
                payouts[e.id] = base + (1 if idx < rem else 0)
        else:
            for e in group:
                payouts[e.id] = 0
        pos += len(group)
        i = j
    return payouts


async def settle_tournament(
    session: AsyncSession,
    tournament: Tournament,
    grades: dict[uuid.UUID, TournamentGrade],
) -> Tournament:
    """Score (first-N average), rank, and pay top places. Unverifiable refunded
    off the top; fewer than `min_ranked` scored → CANCELED, full refund."""
    if tournament.state in ("SETTLED", "CANCELED"):
        return tournament
    entries = await _entries(session, tournament.id)
    entry_cents = tournament.entry_cents

    scores: dict[uuid.UUID, float | None] = {}
    unverifiable: list[TournamentEntry] = []
    for e in entries:
        g = grades.get(e.id, TournamentGrade(values=None))
        e.telemetry = g.telemetry
        e.raw_payload_id = g.raw_payload_id
        if g.values is None:
            unverifiable.append(e)
            scores[e.id] = None
            continue
        avg, count = fairness.first_n_average(g.values, tournament.score_matches)
        e.score = avg
        e.matches_counted = count
        scores[e.id] = avg

    ranked = compute_standings(entries, scores)

    if len(ranked) < tournament.min_ranked:
        return await _cancel(session, tournament, reason="min_ranked")

    # Unverifiable refunded off the top; their stake leaves the prize pool.
    for e in unverifiable:
        await wallet_service.refund(
            session,
            e.user_id,
            entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo="tournament refund (unverifiable)",
        )
        e.status = "REFUNDED"
        e.payout_cents = entry_cents
        await _notify(session, e.user_id, tournament, "refund", entry_cents)

    non_refunded = [e for e in entries if e.status != "REFUNDED"]
    distributable = entry_cents * len(non_refunded)
    places = min(len(tournament.prize_split), len(ranked))
    weights = tuple(tournament.prize_split[:places])
    split = money_math.split_weighted(distributable, weights, tournament.rake_bps)
    prizes = _assign_prizes(ranked, split.payouts_cents, scores)

    for e in non_refunded:
        await wallet_service.escrow_release(
            session,
            e.user_id,
            entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo="stake to tournament pool",
        )

    for e, rank in ranked:
        e.rank = rank
        prize = prizes.get(e.id, 0)
        if prize > 0:
            await wallet_service.payout(
                session,
                e.user_id,
                prize,
                ref_type=REF_TOURNAMENT,
                ref_id=tournament.id,
                memo="tournament prize",
            )
            e.status = "RANKED"
            e.payout_cents = prize
        else:
            e.status = "OUT"
            e.payout_cents = 0
        await _notify(session, e.user_id, tournament, "settled", e.payout_cents)

    # Forfeits (played nothing) — ranked below all who played, paid nothing.
    for e in non_refunded:
        if scores.get(e.id) is None:
            e.status = "OUT"
            e.payout_cents = 0
            await _notify(session, e.user_id, tournament, "settled", 0)

    await wallet_service.rake(
        session,
        split.rake_cents,
        ref_type=REF_TOURNAMENT,
        ref_id=tournament.id,
        memo="tournament rake",
    )
    tournament.prize_cents = sum(split.payouts_cents)
    tournament.rake_cents = split.rake_cents
    tournament.state = "SETTLED"
    tournament.resolved_at = _now()
    await session.flush()
    await _assert_reconciled(session, tournament)
    log.info(
        "tournament.settled",
        tournament_id=str(tournament.id),
        ranked=len(ranked),
        refunded=len(unverifiable),
    )
    return tournament


async def _cancel(
    session: AsyncSession, tournament: Tournament, *, reason: str
) -> Tournament:
    """Refund every entry, zero rake (under-min / kill switch)."""
    for e in await _entries(session, tournament.id):
        await wallet_service.refund(
            session,
            e.user_id,
            tournament.entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo=f"tournament refund ({reason})",
        )
        e.status = "REFUNDED"
        e.payout_cents = tournament.entry_cents
        await _notify(session, e.user_id, tournament, "refund", tournament.entry_cents)
    tournament.prize_cents = 0
    tournament.rake_cents = 0
    tournament.state = "CANCELED"
    tournament.outcome_detail = {"reason": reason}
    tournament.resolved_at = _now()
    await session.flush()
    await _assert_reconciled(session, tournament)
    return tournament


async def cancel_tournament(
    session: AsyncSession, tournament: Tournament, *, reason: str
) -> Tournament:
    if tournament.state in ("SETTLED", "CANCELED"):
        return tournament
    return await _cancel(session, tournament, reason=reason)


async def _notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    tournament: Tournament,
    kind: str,
    payout: int,
) -> None:
    await notifications_service.emit(
        session,
        user_id,
        kind,
        {
            "kind": "tournament",
            "tournament_id": str(tournament.id),
            "payout_cents": payout,
        },
    )


async def _assert_reconciled(session: AsyncSession, tournament: Tournament) -> None:
    from . import reconciliation_service
    from .match_lifecycle import ReconciliationError

    recon = await reconciliation_service.check(session, REF_TOURNAMENT, tournament.id)
    if not recon.ok:
        raise ReconciliationError(tournament.id, recon.violations)
