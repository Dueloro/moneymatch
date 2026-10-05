"""Tournament engine — rolling, join-and-play stat tournaments.

How a tournament runs:

1. **Join.** A player picks a stat tournament (game + stat + entry) and joins
   the one that is currently open for exactly that choice. If none is open (or
   the open one is full), a new one opens with them as its first player. Their
   entry is held immediately; there is no queue and no waiting for a full field.
2. **Joins close** after the join window (default 1 h) or as soon as it has
   `TOURNAMENT_FIELD_SIZE` players. It keeps running either way, even with one
   player, so a solo entrant still sees their games scored.
3. **Play.** Each player's games count from the moment *they* joined until the
   tournament ends (default 3 h after it opened; see `tournament_timing`). Only their
   first `TOURNAMENT_SCORE_N` qualifying games count, so joining late costs
   nothing but time. The rules live in `tournament_scoring`.
4. **Settle.** After the end plus a per-game grace period, once every entrant's
   account has been polled one last time, the worker scores everyone from the
   stored matches and pays the top places 60/25/15 (fewer places in a small
   field). Fewer than two verifiable players, or nobody scored → everyone is
   refunded, no rake. An entrant whose account cannot be read is refunded.

Skill grouping is deliberately absent for now: anyone can join any open
tournament. Every entry still snapshots the player's skill at join time
(`baseline_snapshot`), so fields can be grouped later from real data.

Every number is server-derived; no API surface accepts a score, rank, or payout.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .. import clock
from ..constants import (
    DEMO_AUTH_ID,
    ENTRY_PRESETS_CENTS,
    FLAG_QUEUE_PAUSED,
    TOURNAMENT_FIELD_SIZE,
    TOURNAMENT_GAMES,
    TOURNAMENT_METRICS,
    TOURNAMENT_MIN_FIELD,
    TOURNAMENT_MIN_RANKED,
    TOURNAMENT_PRIZE_SPLIT,
    TOURNAMENT_SCORE_N,
    game_flag_key,
)
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import QueueTicket
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import (
    aggregate_metrics,
    geo_service,
    limits_service,
    linking_service,
    metric_models_service,
    money_math,
    notifications_service,
    sandbagging_service,
    skill_prior,
    tournament_timing,
    wallet_service,
)
from .feature_flags import get_boolean_flags

log = structlog.get_logger(__name__)

REF_TOURNAMENT = "tournament"
TOURNAMENT_ENGINE_VERSION = "tourney-2-rolling"

# Tournament states: OPEN (taking joiners) → LOCKED (joins closed, running) →
# SETTLED | CANCELED. Scoring runs on both OPEN and LOCKED.
OPEN = "OPEN"
LOCKED = "LOCKED"
LIVE_STATES = (OPEN, LOCKED)
# An entry that is still in the contest (vs REFUNDED after leaving / voiding).
ACTIVE_ENTRY = "LOCKED"


class TournamentError(APIError):
    """A tournament join/leave failure (RFC-7807 via APIError)."""


@dataclass
class TournamentEnqueueResult:
    status: str  # "idle" | "formed"
    tournament: Tournament | None = None
    ticket: QueueTicket | None = None


@dataclass
class TournamentGrade:
    """The worker's per-entry grading input.

    - ``values is None`` ⇒ **unverifiable** (the account could not be read) →
      refunded.
    - ``score`` set ⇒ used as the entry's score.
    - else ``values`` non-empty ⇒ score is the best value; ``[]`` ⇒ played no
      counted game → forfeit (ranked last, paid nothing).
    """

    values: list[float] | None
    score: float | None = None
    counted: int | None = None
    telemetry: dict[str, Any] | None = None
    raw_payload_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- #
# Eligibility + skill snapshot.
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


async def _require_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount:
    link = await linking_service.get_link(session, user_id, game)
    if link is None or link.status != "active":
        raise TournamentError(
            "not_linked", f"Link a {game} account first.", status_code=409
        )
    return link


def host_rating(link: LinkedAccount) -> float | None:
    """The linked account's rating on its primary speed (chess), if any."""
    return skill_prior.host_rating(link)


async def _skill_snapshot(
    session: AsyncSession, user: User, game: str, metric: str, link: LinkedAccount
) -> dict[str, Any]:
    """What we knew about the player's skill when they joined.

    Not used to decide who plays whom yet; recorded so fields can be grouped
    later and so a result can be reviewed against the skill it was entered at.
    """
    snap: dict[str, Any] = {
        "linked_account_id": str(link.id),
        "host_account_id": link.host_account_id,
        "metric": metric,
        "rating": host_rating(link),
    }
    model_metric = None if metric.startswith("chess_") else metric
    if model_metric:
        model = await metric_models_service.get_metric_model(
            session, user.id, game, model_metric
        )
        if model is not None and model.n > 0:
            snap.update(mu=float(model.mu), sigma=float(model.sigma), n=int(model.n))
        else:
            snap["n"] = 0
    if model_metric:
        snap["new_player"] = snap.get("n") == 0
    else:
        snap["new_player"] = snap["rating"] is None
    return snap


# --------------------------------------------------------------------------- #
# Lookups.
# --------------------------------------------------------------------------- #


async def _active_entries(
    session: AsyncSession, tournament_id: uuid.UUID
) -> list[TournamentEntry]:
    rows = await session.scalars(
        select(TournamentEntry)
        .where(
            TournamentEntry.tournament_id == tournament_id,
            TournamentEntry.status == ACTIVE_ENTRY,
        )
        .order_by(TournamentEntry.enqueued_at.asc())
    )
    return list(rows)


async def _entries(
    session: AsyncSession, tournament_id: uuid.UUID
) -> list[TournamentEntry]:
    rows = await session.scalars(
        select(TournamentEntry)
        .where(TournamentEntry.tournament_id == tournament_id)
        .order_by(TournamentEntry.enqueued_at.asc())
    )
    return list(rows)


async def active_count(session: AsyncSession, tournament_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(TournamentEntry)
            .where(
                TournamentEntry.tournament_id == tournament_id,
                TournamentEntry.status == ACTIVE_ENTRY,
            )
        )
        or 0
    )


async def current_tournament_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> Tournament | None:
    """The live tournament the user is playing in, if any (one at a time)."""
    return await session.scalar(
        select(Tournament)
        .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
        .where(
            TournamentEntry.user_id == user_id,
            TournamentEntry.status == ACTIVE_ENTRY,
            Tournament.state.in_(LIVE_STATES),
        )
        .order_by(Tournament.created_at.desc())
        .limit(1)
    )


def _is_sandbox_user(user: User) -> bool:
    """The demo account and its practice opponents (test_opponents.py)."""
    from .test_opponents import TEST_AUTH_PREFIX  # local: it imports this module

    return user.auth_id == DEMO_AUTH_ID or user.auth_id.startswith(TEST_AUTH_PREFIX)


def _has_sandbox_entry() -> Any:
    """SQL: the tournament has an entry from the demo or a practice opponent."""
    from .test_opponents import TEST_AUTH_PREFIX

    return exists(
        select(TournamentEntry.id)
        .join(User, User.id == TournamentEntry.user_id)
        .where(
            TournamentEntry.tournament_id == Tournament.id,
            or_(
                User.auth_id == DEMO_AUTH_ID,
                User.auth_id.startswith(TEST_AUTH_PREFIX, autoescape=True),
            ),
        )
    )


async def _open_tournament(
    session: AsyncSession,
    game: str,
    metric: str,
    entry_cents: int,
    now: datetime,
    *,
    sandbox: bool,
) -> Tournament | None:
    # Demo tournaments (the demo account + practice opponents) and real ones
    # never mix: a real player must never be ranked against a bot, and the
    # demo's bots must never be paid out of real entries.
    return await session.scalar(
        select(Tournament)
        .where(
            Tournament.game == game,
            Tournament.ranking_metric == metric,
            Tournament.entry_cents == entry_cents,
            Tournament.state == OPEN,
            Tournament.join_closes_at > now,
            _has_sandbox_entry() if sandbox else ~_has_sandbox_entry(),
        )
        .order_by(Tournament.created_at.asc())
        .limit(1)
        .with_for_update()
    )


async def open_counts(
    session: AsyncSession, game: str, now: datetime | None = None
) -> dict[tuple[str, int], int]:
    """Players already in the open tournament per (metric, entry), for the cards."""
    now = now or clock.now()
    rows = await session.execute(
        select(Tournament.ranking_metric, Tournament.entry_cents, func.count())
        .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
        .where(
            Tournament.game == game,
            Tournament.state == OPEN,
            Tournament.join_closes_at > now,
            TournamentEntry.status == ACTIVE_ENTRY,
        )
        .group_by(Tournament.ranking_metric, Tournament.entry_cents)
    )
    return {(m, e): int(c) for m, e, c in rows}


# --------------------------------------------------------------------------- #
# Join / leave.
# --------------------------------------------------------------------------- #


async def _new_tournament(
    session: AsyncSession, game: str, metric: str, entry_cents: int, now: datetime
) -> Tournament:
    tournament = Tournament(
        game=game,
        ranking_metric=metric,
        entry_cents=entry_cents,
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        prize_split=list(TOURNAMENT_PRIZE_SPLIT),
        field_size=TOURNAMENT_FIELD_SIZE,
        min_field=TOURNAMENT_MIN_FIELD,
        min_ranked=TOURNAMENT_MIN_RANKED,
        score_matches=TOURNAMENT_SCORE_N,
        pot_cents=0,
        state=OPEN,
        window_starts_at=now,
        join_closes_at=now + timedelta(seconds=tournament_timing.join_window_seconds()),
        window_ends_at=now + timedelta(seconds=tournament_timing.duration_seconds()),
        engine_version=TOURNAMENT_ENGINE_VERSION,
    )
    session.add(tournament)
    await session.flush()
    log.info(
        "tournament.opened",
        tournament_id=str(tournament.id),
        game=game,
        metric=metric,
        entry_cents=entry_cents,
    )
    return tournament


async def enqueue(
    session: AsyncSession,
    user: User,
    *,
    game: str,
    metric: str,
    entry_cents: int,
) -> TournamentEnqueueResult:
    """Join the open tournament for (game, metric, entry), or open one."""
    now = clock.now()
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
    # An existing sandbagging flag blocks entry. No live host check here: the
    # nightly detector writes flags, and a join must never spend host budget.
    await sandbagging_service.assert_not_flagged(session, user.id, game, metric)

    existing = await current_tournament_for_user(session, user.id)
    if existing is not None:
        return TournamentEnqueueResult(status="formed", tournament=existing)

    await limits_service.assert_can_stake(session, user, entry_cents)
    snapshot = await _skill_snapshot(session, user, game, metric, link)

    # One writer per (game, metric, entry) at a time, so two players joining at
    # the same instant land in the same tournament instead of opening two.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"tournament:{game}:{metric}:{entry_cents}"},
    )
    tournament = await _open_tournament(
        session, game, metric, entry_cents, now, sandbox=_is_sandbox_user(user)
    )
    if tournament is not None and await active_count(session, tournament.id) >= (
        tournament.field_size
    ):
        tournament.state = LOCKED  # full; should already be, heal it
        tournament = None
    if tournament is None:
        tournament = await _new_tournament(session, game, metric, entry_cents, now)

    await wallet_service.escrow_hold(
        session,
        user.id,
        entry_cents,
        ref_type=REF_TOURNAMENT,
        ref_id=tournament.id,
        memo=f"{metric} tournament entry",
    )
    session.add(
        TournamentEntry(
            tournament_id=tournament.id,
            user_id=user.id,
            linked_account_id=link.id,
            host_account_id=link.host_account_id,
            baseline_snapshot=snapshot,
            enqueued_at=now,
        )
    )
    tournament.pot_cents += entry_cents
    await session.flush()
    if await active_count(session, tournament.id) >= tournament.field_size:
        tournament.state = LOCKED
        await session.flush()

    await notifications_service.emit(
        session,
        user.id,
        "match_found",
        {
            "kind": "tournament",
            "tournament_id": str(tournament.id),
            "metric": metric,
            "entry_cents": entry_cents,
        },
    )
    log.info(
        "tournament.joined",
        tournament_id=str(tournament.id),
        user_id=str(user.id),
        players=await active_count(session, tournament.id),
    )
    return TournamentEnqueueResult(status="formed", tournament=tournament)


async def poll_status(session: AsyncSession, user: User) -> TournamentEnqueueResult:
    existing = await current_tournament_for_user(session, user.id)
    if existing is not None:
        return TournamentEnqueueResult(status="formed", tournament=existing)
    return TournamentEnqueueResult(status="idle")


async def cancel(session: AsyncSession, user: User) -> bool:
    """Leave. Allowed only while you are the only player in the tournament:
    nobody else is affected, so you get your entry back. Once anyone else has
    joined, your entry is final.

    Also retires any waiting ticket left over from the old queue."""
    for ticket in await session.scalars(
        select(QueueTicket).where(
            QueueTicket.user_id == user.id,
            QueueTicket.product == "tournament",
            QueueTicket.state == "waiting",
        )
    ):
        ticket.state = "canceled"

    tournament = await current_tournament_for_user(session, user.id)
    if tournament is None:
        await session.flush()
        return False
    locked = await session.scalar(
        select(Tournament).where(Tournament.id == tournament.id).with_for_update()
    )
    assert locked is not None
    entries = await _active_entries(session, locked.id)
    if len(entries) > 1:
        raise TournamentError(
            "entry_final",
            "Other players have joined, so your entry is locked in. "
            "Your first games after joining still count.",
            status_code=409,
        )
    await _cancel(session, locked, reason="left")
    return True


# --------------------------------------------------------------------------- #
# Worker transitions: joins closing, settlement.
# --------------------------------------------------------------------------- #


async def close_joins(
    session: AsyncSession, tournament: Tournament, now: datetime
) -> Tournament:
    """OPEN → LOCKED once the join window has passed.

    A small field is not voided here: it runs to the end so a solo player still
    sees their games fetched and scored, and settlement refunds a tournament
    that ends with fewer than two players."""
    if tournament.state != OPEN:
        return tournament
    if tournament.join_closes_at is not None and tournament.join_closes_at > now:
        return tournament
    tournament.state = LOCKED
    await session.flush()
    return tournament


def compute_standings(
    entries: list[TournamentEntry],
    scores: dict[uuid.UUID, float | None],
    *,
    higher_is_better: bool = True,
) -> list[tuple[TournamentEntry, int]]:
    """Rank scored entries; ties share a rank; unscored entries are left out.

    Returns (entry, rank) best-first, with a deterministic tie order by
    `enqueued_at`.
    """
    sign = 1.0 if higher_is_better else -1.0
    ranked = [e for e in entries if scores.get(e.id) is not None]
    ranked.sort(key=lambda e: (-sign * scores[e.id], e.enqueued_at))  # type: ignore[operator]
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
    sending any tie remainder to the earlier entry (invariant-exact)."""
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


def paid_places(split_len: int, scorers: int, participants: int) -> int:
    """How many places pay. Never more than the split, never more than people
    who scored, and never everyone: at least one participant is paid nothing,
    so a two-player tournament is winner-takes-the-prize, not a partial refund."""
    return max(0, min(split_len, scorers, max(1, participants - 1)))


def _best(values: list[float], higher_is_better: bool) -> float:
    return max(values) if higher_is_better else min(values)


async def settle_tournament(
    session: AsyncSession,
    tournament: Tournament,
    grades: dict[uuid.UUID, TournamentGrade],
) -> Tournament:
    """Rank and pay. Unverifiable entrants are refunded; fewer than
    `min_ranked` verifiable participants, or nobody scored → void + refund."""
    if tournament.state in ("SETTLED", "CANCELED"):
        return tournament
    entries = await _active_entries(session, tournament.id)
    entry_cents = tournament.entry_cents
    higher = aggregate_metrics.higher_is_better(tournament.ranking_metric)

    scores: dict[uuid.UUID, float | None] = {}
    unverifiable: list[TournamentEntry] = []
    for e in entries:
        g = grades.get(e.id, TournamentGrade(values=None))
        e.telemetry = g.telemetry
        e.raw_payload_id = g.raw_payload_id
        if g.values is None and g.score is None:
            unverifiable.append(e)
            scores[e.id] = None
            continue
        if g.score is not None:
            score, count = g.score, (g.counted or len(g.values or []))
        elif g.values:
            score, count = _best(g.values, higher), len(g.values)
        else:
            score, count = None, 0
        e.score = score
        e.matches_counted = count
        scores[e.id] = score

    ranked = compute_standings(entries, scores, higher_is_better=higher)
    unverifiable_ids = {e.id for e in unverifiable}
    participants = [e for e in entries if e.id not in unverifiable_ids]
    if len(participants) < tournament.min_ranked:
        return await _cancel(session, tournament, reason="not_enough_players")
    if not ranked:
        return await _cancel(session, tournament, reason="no_scores")

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

    distributable = entry_cents * len(participants)
    places = paid_places(len(tournament.prize_split), len(ranked), len(participants))
    weights = tuple(tournament.prize_split[:places])
    split = money_math.split_weighted(distributable, weights, tournament.rake_bps)
    prizes = _assign_prizes(ranked, split.payouts_cents, scores)

    for e in participants:
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

    # Played no counted game — ranked below everyone who did, paid nothing.
    for e in participants:
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
    tournament.pot_cents = distributable
    tournament.prize_cents = sum(split.payouts_cents)
    tournament.rake_cents = split.rake_cents
    tournament.state = "SETTLED"
    tournament.resolved_at = clock.now()
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
    """Refund every entry still in the contest, zero rake."""
    for e in await _active_entries(session, tournament.id):
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
    tournament.outcome_detail = {**(tournament.outcome_detail or {}), "reason": reason}
    tournament.resolved_at = clock.now()
    await session.flush()
    await _assert_reconciled(session, tournament)
    log.info("tournament.canceled", tournament_id=str(tournament.id), reason=reason)
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
