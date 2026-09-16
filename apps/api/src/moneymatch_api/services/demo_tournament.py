"""A self-driving simulation tournament for hands-off testing (browser QA).

**Scaffolding — behind `demo_simulate_enabled`.** Delete with the rest of the
simulation surface before real-money launch.

It lets *any* signed-in player watch the whole tournament loop in the browser
without linking a real game account or playing a game:

- Creates a short-window (default **10 min**) chess tournament and enrols the
  player plus a handful of **competitive bots**.
- **Injects stats the same way the app reads them**: it fetches real games from
  the **Lichess API** for the player's move counts, and gives each bot its own
  varying results, recorded as injected `SimulatedMatch` rows. The stats **keep
  changing** over the window (`tick` injects another finished game per player), so
  standings move — simulating everyone still playing.
- **Standings are recomputed on every tick** (not the slow 10-minute cache) and
  written to `standings_cache`, so the live board updates promptly.
- **Its own settlement** (`settle`) scores each player by the **sum of their
  in-window game values** — so scores are *distinct* and *climb* — ranks them, and
  splits the pot **60 / 25 / 15** of (pot − rake). The worker routes a `demo_live`
  tournament here instead of the generic first-N engine.

The score is a running total (not best-of-N or count-of-wins), which is what makes
the standings both move continuously and separate the field into distinct places
so the 60/25/15 split pays three different players.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import GAME_CHESS_LICHESS
from ..models.demo_simulation import SimulatedMatch
from ..models.linked_account import LinkedAccount
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import demo_simulation, money_math, wallet_service
from .hosts import lichess
from .user_service import provision_new_user

log = structlog.get_logger(__name__)

REF_TOURNAMENT = "tournament"

# A public, always-active Lichess account we borrow realistic move counts from (we
# never link the player to it — only the stat values are used, the same shape the
# chess adapter reads).
_LICHESS_SOURCE = "Zhigalko_Sergei"

# Bots are ordinary users under this prefix. They are graded from their own
# injected games and genuinely compete for a place.
_LIVE_BOT_PREFIX = "zz_livebot_"
_BOT_NAMES = ("Nova", "Pixel", "Echo", "Vega", "Zephyr", "Comet", "Juno", "Orbit")

# The tournament's ranking metric key; the injected value lives here per game.
DEMO_TOURNAMENT_METRIC = "chess_moves"
DEFAULT_MINUTES = 10
DEFAULT_BOTS = 5
DEFAULT_ENTRY_CENTS = 500
DEFAULT_TICK_SECONDS = 45
LIVE_PRIZE_SPLIT = [60, 25, 15]


def _now() -> datetime:
    return datetime.now(UTC)


def _is_bot(host_account_id: str) -> bool:
    return host_account_id.startswith(_LIVE_BOT_PREFIX)


async def _fetch_lichess_move_pool(count: int = 40) -> list[int]:
    """Real move counts from recent Lichess games (best-effort). Falls back to a
    synthetic spread if Lichess is unreachable, so a QA run never hangs."""
    try:
        games = await lichess.get_user_games(
            _LICHESS_SOURCE, since_ms=0, max_games=count, rated_only=True
        )
    except Exception:  # noqa: BLE001 — scaffolding must never 500
        games = []
    moves: list[int] = []
    for g in games or []:
        mv = g.get("moves")
        if isinstance(mv, str) and mv.strip():
            moves.append(len(mv.split()))
    if not moves:
        moves = [random.randint(20, 60) for _ in range(count)]
    return moves


async def _chess_link(
    session: AsyncSession, user_id: uuid.UUID
) -> LinkedAccount | None:
    return await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id,
            LinkedAccount.game == GAME_CHESS_LICHESS,
        )
    )


async def _ensure_sim_link(session: AsyncSession, player: User) -> LinkedAccount:
    """The player's chess link, or a lightweight synthetic 'sim' link if they
    haven't linked chess — so a real signup can join without linking a game. The
    host id never resolves to a real account, so only injected games grade them."""
    link = await _chess_link(session, player.id)
    if link is not None:
        return link
    link = LinkedAccount(
        user_id=player.id,
        game=GAME_CHESS_LICHESS,
        host_account_id=f"sim:{player.id}",
        host_username=player.username or "player",
        profile_snapshot={
            "username": player.username or "player",
            "game": GAME_CHESS_LICHESS,
            "primary_speed": "blitz",
            "formats": [{"speed": "blitz", "rating": 1500, "games": 20}],
            "simulated": True,
        },
    )
    session.add(link)
    await session.flush()
    return link


async def _make_bot(session: AsyncSession, name: str) -> tuple[User, LinkedAccount]:
    """A funded, chess-linked competitive bot (idempotent)."""
    auth_id = f"{_LIVE_BOT_PREFIX}{name.lower()}"
    user = await session.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        user = User(
            auth_id=auth_id,
            username=f"{name}Bot",
            email=f"{auth_id}@livebot.invalid",
            residence_state="NY",
            dob_attested_18plus=True,
        )
        session.add(user)
        await session.flush()
        await provision_new_user(session, user)

    host_id = auth_id
    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == GAME_CHESS_LICHESS
        )
    )
    if linked is None:
        linked = LinkedAccount(
            user_id=user.id,
            game=GAME_CHESS_LICHESS,
            host_account_id=host_id,
            host_username=f"{name}Bot",
            profile_snapshot={
                "username": f"{name}Bot",
                "game": GAME_CHESS_LICHESS,
                "primary_speed": "blitz",
                "formats": [{"speed": "blitz", "rating": 1500, "games": 20}],
            },
        )
        session.add(linked)
    await session.flush()
    return user, linked


async def _inject_game(
    session: AsyncSession,
    user_id: uuid.UUID,
    host_account_id: str,
    value: int,
    played_at: datetime,
) -> None:
    """Record one finished, won chess game carrying `value` as its ranked stat."""
    await demo_simulation.record(
        session,
        user_id=user_id,
        game=GAME_CHESS_LICHESS,
        host_account_id=host_account_id,
        metrics={DEMO_TOURNAMENT_METRIC: float(value)},
        won=True,
        moves=value,
        played_at=played_at,
        created_by="demo_live_tournament",
    )


async def start_live(
    session: AsyncSession,
    player: User,
    *,
    minutes: int = DEFAULT_MINUTES,
    num_bots: int = DEFAULT_BOTS,
    entry_cents: int = DEFAULT_ENTRY_CENTS,
    tick_seconds: int = DEFAULT_TICK_SECONDS,
) -> Tournament:
    """Create + fill a self-driving chess tournament for `player` (any signed-in
    user). Escrows every entry, injects each participant's first game, writes the
    opening standings, and hands the rest to the worker (`tick` + `settle`)."""
    player_link = await _ensure_sim_link(session, player)

    now = _now()
    move_pool = await _fetch_lichess_move_pool()

    field: list[tuple[uuid.UUID, str, uuid.UUID]] = [
        (player.id, player_link.host_account_id, player_link.id)
    ]
    for i in range(num_bots):
        bot, bot_link = await _make_bot(session, _BOT_NAMES[i])
        field.append((bot.id, bot_link.host_account_id, bot_link.id))

    tournament = Tournament(
        game=GAME_CHESS_LICHESS,
        ranking_metric=DEMO_TOURNAMENT_METRIC,
        entry_cents=entry_cents,
        rake_bps=money_math.DEFAULT_RAKE_BPS,
        prize_split=list(LIVE_PRIZE_SPLIT),
        field_size=len(field),
        min_field=2,
        min_ranked=1,
        score_matches=99,  # score sums ALL in-window games (not first-N)
        pot_cents=entry_cents * len(field),
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(minutes=minutes),
        engine_version="demo-live-2",
        outcome_detail={
            "demo_live": True,
            "tick_seconds": tick_seconds,
            "last_tick_ms": int(now.timestamp() * 1000),
            "window_start_ms": int(now.timestamp() * 1000),
            "move_pool": move_pool,
            "pool_cursor": 0,
            "lichess_source": _LICHESS_SOURCE,
        },
    )
    session.add(tournament)
    await session.flush()

    for idx, (user_id, host_id, link_id) in enumerate(field):
        await wallet_service.escrow_hold(
            session,
            user_id,
            entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo="live tournament entry",
        )
        session.add(
            TournamentEntry(
                tournament_id=tournament.id,
                user_id=user_id,
                linked_account_id=link_id,
                host_account_id=host_id,
                baseline_snapshot={
                    "host_account_id": host_id,
                    "game": GAME_CHESS_LICHESS,
                },
                enqueued_at=now,
            )
        )
        value = move_pool[idx % len(move_pool)] if not _is_bot(host_id) else (
            random.randint(20, 60)
        )
        await _inject_game(session, user_id, host_id, value, now)

    await session.flush()
    await _refresh_standings(session, tournament)
    await session.flush()
    log.info(
        "demo.live_tournament.started",
        tournament_id=str(tournament.id),
        field=len(field),
        minutes=minutes,
    )
    return tournament


# --------------------------------------------------------------------------- #
# Scoring + standings (own path — distinct, climbing scores).
# --------------------------------------------------------------------------- #


async def _score_and_count(
    session: AsyncSession, tournament: Tournament, user_id: uuid.UUID
) -> tuple[float, int]:
    """A player's score = the SUM of their in-window injected game values, and the
    number of games counted. Distinct + climbing → distinct, moving standings."""
    detail = tournament.outcome_detail or {}
    start_ms = int(detail.get("window_start_ms", 0))
    end_ms = int(tournament.window_ends_at.timestamp() * 1000)
    rows = await session.scalars(
        select(SimulatedMatch).where(
            SimulatedMatch.user_id == user_id,
            SimulatedMatch.game == GAME_CHESS_LICHESS,
            SimulatedMatch.created_at_ms >= start_ms,
            SimulatedMatch.created_at_ms <= end_ms,
        )
    )
    total = 0.0
    count = 0
    for r in rows:
        val = (r.metrics or {}).get(DEMO_TOURNAMENT_METRIC)
        if val is None:
            continue
        total += float(val)
        count += 1
    return total, count


async def _ranked_entries(
    session: AsyncSession, tournament: Tournament
) -> list[tuple[TournamentEntry, float, int, int]]:
    """(entry, score, games, rank) best-first. Ranks are strict (1..N): scores are
    continuous sums so ties are effectively impossible; an exact tie breaks by the
    earlier enqueue, deterministically."""
    entries = list(
        await session.scalars(
            select(TournamentEntry)
            .where(TournamentEntry.tournament_id == tournament.id)
            .order_by(TournamentEntry.enqueued_at.asc())
        )
    )
    scored = []
    for e in entries:
        score, count = await _score_and_count(session, tournament, e.user_id)
        scored.append((e, score, count))
    scored.sort(key=lambda t: (-t[1], t[0].enqueued_at))
    return [(e, s, c, i + 1) for i, (e, s, c) in enumerate(scored)]


async def _refresh_standings(
    session: AsyncSession, tournament: Tournament, *, now: datetime | None = None
) -> None:
    now = now or _now()
    ranked = await _ranked_entries(session, tournament)
    ids = [e.user_id for e, _, _, _ in ranked]
    names = await _usernames(session, ids)
    rows: list[dict[str, Any]] = [
        {
            "user_id": str(e.user_id),
            "username": names.get(e.user_id),
            "score": round(score, 2),
            "matches": count,
            "rank": rank,
        }
        for e, score, count, rank in ranked
    ]
    tournament.standings_cache = {"rows": rows}
    tournament.standings_updated_at = now


async def _usernames(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    rows = await session.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: uname for uid, uname in rows}


# --------------------------------------------------------------------------- #
# Tick — inject the next round + refresh standings.
# --------------------------------------------------------------------------- #


async def _live_tournaments(
    session: AsyncSession, now: datetime
) -> list[Tournament]:
    rows = await session.scalars(
        select(Tournament).where(
            Tournament.state == "LOCKED",
            Tournament.window_ends_at > now,
        )
    )
    return [t for t in rows if (t.outcome_detail or {}).get("demo_live")]


async def tick(
    session: AsyncSession, *, now: datetime | None = None, force: bool = False
) -> int:
    """Advance live simulation tournaments. Injects one more finished game per
    player when the tick is due (or `force`d), and **always** recomputes standings
    so the board updates promptly. Returns how many tournaments injected a round."""
    now = now or _now()
    advanced = 0
    for t in await _live_tournaments(session, now):
        detail = dict(t.outcome_detail or {})
        due = force or (
            int(now.timestamp() * 1000)
            >= int(detail.get("last_tick_ms", 0))
            + int(detail.get("tick_seconds", DEFAULT_TICK_SECONDS)) * 1000
        )
        if due:
            pool: list[int] = list(detail.get("move_pool") or [30])
            cursor = int(detail.get("pool_cursor", 0))
            entries = list(
                await session.scalars(
                    select(TournamentEntry).where(
                        TournamentEntry.tournament_id == t.id
                    )
                )
            )
            for e in entries:
                value = (
                    random.randint(20, 60)
                    if _is_bot(e.host_account_id)
                    else pool[cursor % len(pool)]
                )
                await _inject_game(session, e.user_id, e.host_account_id, value, now)
            detail["pool_cursor"] = cursor + 1
            detail["last_tick_ms"] = int(now.timestamp() * 1000)
            t.outcome_detail = detail
            advanced += 1
        await _refresh_standings(session, t, now=now)
    await session.flush()
    return advanced


# --------------------------------------------------------------------------- #
# Settlement — own path: distinct ranks, 60/25/15.
# --------------------------------------------------------------------------- #


async def settle(session: AsyncSession, tournament: Tournament) -> Tournament:
    """Settle a live simulation tournament: rank by score (sum of in-window
    games), split the pot 60/25/15 of (pot − rake), release escrow, pay the top
    three, book rake, and reconcile. Distinct scores → three distinct winners."""
    if tournament.state in ("SETTLED", "CANCELED"):
        return tournament

    ranked = await _ranked_entries(session, tournament)
    entry_cents = tournament.entry_cents
    pot = entry_cents * len(ranked)
    places = min(len(tournament.prize_split), len(ranked))
    weights = tuple(tournament.prize_split[:places])
    split = money_math.split_weighted(pot, weights, tournament.rake_bps)

    # Consume every escrowed stake into the pot.
    for e, _score, _count, _rank in ranked:
        await wallet_service.escrow_release(
            session,
            e.user_id,
            entry_cents,
            ref_type=REF_TOURNAMENT,
            ref_id=tournament.id,
            memo="stake to tournament pool",
        )

    for e, score, count, rank in ranked:
        e.rank = rank
        e.score = round(score, 4)
        e.matches_counted = count
        prize = split.payouts_cents[rank - 1] if rank <= places else 0
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
        await _notify(session, e.user_id, tournament, e.payout_cents)

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
    await _refresh_standings(session, tournament)
    await session.flush()
    await _assert_reconciled(session, tournament)
    log.info(
        "demo.live_tournament.settled",
        tournament_id=str(tournament.id),
        winners=places,
    )
    return tournament


async def _notify(
    session: AsyncSession, user_id: uuid.UUID, tournament: Tournament, payout: int
) -> None:
    from . import notifications_service

    await notifications_service.emit(
        session,
        user_id,
        "settled",
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


def is_live_tournament(tournament: Tournament) -> bool:
    """True for a self-driving simulation tournament (route it to `settle`)."""
    return bool((tournament.outcome_detail or {}).get("demo_live"))
