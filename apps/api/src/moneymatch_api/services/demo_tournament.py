"""A self-driving simulation tournament for hands-off testing (browser QA).

**Scaffolding — behind `demo_simulate_enabled`.** Delete with the rest of the
simulation surface before real-money launch.

It lets *any* signed-in player watch the whole tournament loop in the browser
without linking a real game account or playing a game. It runs on **whatever game
the player joined** — the field, bots and injected stats all match that game:

- Creates a short-window (default **10 min**) tournament for the joined game and
  enrols the player plus a handful of **competitive bots**.
- **Injects stats the same way the app reads them**: each participant gets its own
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

Chess is deliberately limited to a **single game mode (blitz)** and ranked on
per-game move count ("Moves to win"), so one chess tournament shape settles cleanly.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import GAME_CHESS_LICHESS, metric_label
from ..models.demo_simulation import SimulatedMatch
from ..models.linked_account import LinkedAccount
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import demo_simulation, money_math, wallet_service
from .user_service import provision_new_user

log = structlog.get_logger(__name__)

REF_TOURNAMENT = "tournament"

# Bots are ordinary users under this prefix. They are graded from their own
# injected games and genuinely compete for a place.
_LIVE_BOT_PREFIX = "zz_livebot_"
_BOT_NAMES = ("Nova", "Pixel", "Echo", "Vega", "Zephyr", "Comet", "Juno", "Orbit")

# Chess is limited to one game mode. Blitz is the chosen mode, and chess is ranked
# on per-game move count so the sum-of-values scoring stays distinct and climbing.
_CHESS_METRIC = "chess_moves"
_CHESS_SPEED = "blitz"

# Plausible per-injected-game value ranges (lo, hi) per ranking metric, so the
# numbers on the standings board look like the game and not like noise. A metric we
# don't know falls back to a generic spread — the demo still separates the field.
_METRIC_RANGE: dict[str, tuple[float, float]] = {
    "chess_moves": (20, 60),
    "cs2_kills": (8, 30),
    "cs2_kd_ratio": (0.7, 2.2),
    "cs2_headshot_pct": (30, 65),
    "cs2_adr": (50, 120),
    "pubg_kills": (2, 12),
    "pubg_damage": (150, 700),
    "pubg_headshot_pct": (10, 40),
    "dota2_kda_ratio": (1.5, 6.0),
    "dota2_gpm": (350, 750),
}
_DEFAULT_RANGE = (1.0, 50.0)

DEFAULT_MINUTES = 10
DEFAULT_BOTS = 5
DEFAULT_ENTRY_CENTS = 500
DEFAULT_TICK_SECONDS = 45
LIVE_PRIZE_SPLIT = [60, 25, 15]


def _now() -> datetime:
    return datetime.now(UTC)


def _is_bot(host_account_id: str) -> bool:
    return host_account_id.startswith(_LIVE_BOT_PREFIX)


def _resolve_market(game: str, metric: str) -> tuple[str, str | None]:
    """The (ranking_metric, speed) the self-driving tournament actually runs on.

    Chess collapses to one mode: blitz, ranked on per-game moves — so the joined
    chess metric (total wins / streak / fastest win) is replaced by `chess_moves`.
    Every other game keeps the metric the player joined on."""
    if game == GAME_CHESS_LICHESS:
        return _CHESS_METRIC, _CHESS_SPEED
    return metric, None


def _draw_value(metric: str) -> float:
    lo, hi = _METRIC_RANGE.get(metric, _DEFAULT_RANGE)
    value = random.uniform(lo, hi)
    # Whole units for counts, two decimals for ratios — same as the host would read.
    return float(round(value)) if hi >= 20 else round(value, 2)


def _snapshot(game: str, handle: str) -> dict[str, Any]:
    """A complete ProfileSnapshot-shaped dict so /links and matchmaking accept the
    synthetic account. Chess adds its per-format fields; other titles use the
    generic descriptors."""
    snap: dict[str, Any] = {
        "username": handle,
        "display_name": handle,
        "url": f"https://sim.invalid/{game}/{handle}",
        "link_method": "username",
        "game": game,
        "win_rate": 0.5,
        "draw_rate": 0.0,
        "total_games": 20,
        "simulated": True,
    }
    if game == GAME_CHESS_LICHESS:
        snap["url"] = f"https://lichess.org/@/{handle}"
        snap["primary_speed"] = _CHESS_SPEED
        snap["formats"] = [
            {"speed": _CHESS_SPEED, "rating": 1500, "games": 20, "provisional": False}
        ]
    return snap


async def _game_link(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount | None:
    return await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id,
            LinkedAccount.game == game,
        )
    )


async def _ensure_sim_link(
    session: AsyncSession, player: User, game: str
) -> LinkedAccount:
    """The player's link for `game`, or a lightweight synthetic 'sim' link if they
    haven't linked it — so a real signup can join without linking a game. The host
    id never resolves to a real account; only injected games grade them (scored by
    user_id, so the real host is never polled)."""
    link = await _game_link(session, player.id, game)
    if link is not None:
        return link
    handle = player.username or "player"
    link = LinkedAccount(
        user_id=player.id,
        game=game,
        host_account_id=f"sim:{player.id}",
        host_username=handle,
        profile_snapshot=_snapshot(game, handle),
    )
    session.add(link)
    await session.flush()
    return link


async def _make_bot(
    session: AsyncSession, name: str, game: str
) -> tuple[User, LinkedAccount]:
    """A funded, `game`-linked competitive bot (idempotent)."""
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

    host_id = f"{auth_id}:{game}"
    linked = await _game_link(session, user.id, game)
    if linked is None:
        linked = LinkedAccount(
            user_id=user.id,
            game=game,
            host_account_id=host_id,
            host_username=f"{name}Bot",
            profile_snapshot=_snapshot(game, f"{name}Bot"),
        )
        session.add(linked)
    await session.flush()
    return user, linked


async def _inject_game(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    host_account_id: str,
    game: str,
    metric: str,
    value: float,
    played_at: datetime,
) -> None:
    """Record one finished, won game carrying `value` as its ranked stat."""
    await demo_simulation.record(
        session,
        user_id=user_id,
        game=game,
        host_account_id=host_account_id,
        metrics={metric: float(value)},
        won=True,
        moves=int(value) if metric == _CHESS_METRIC else 0,
        played_at=played_at,
        created_by="demo_live_tournament",
    )


async def start_live(
    session: AsyncSession,
    player: User,
    *,
    game: str = GAME_CHESS_LICHESS,
    metric: str = _CHESS_METRIC,
    minutes: int = DEFAULT_MINUTES,
    num_bots: int = DEFAULT_BOTS,
    entry_cents: int = DEFAULT_ENTRY_CENTS,
    tick_seconds: int = DEFAULT_TICK_SECONDS,
) -> Tournament:
    """Create + fill a self-driving tournament for `player` on `game` (any signed-in
    user). Escrows every entry, injects each participant's first game, writes the
    opening standings, and hands the rest to the worker (`tick` + `settle`)."""
    ranking_metric, _speed = _resolve_market(game, metric)
    player_link = await _ensure_sim_link(session, player, game)

    now = _now()
    field: list[tuple[uuid.UUID, str, uuid.UUID]] = [
        (player.id, player_link.host_account_id, player_link.id)
    ]
    for i in range(num_bots):
        bot, bot_link = await _make_bot(session, _BOT_NAMES[i], game)
        field.append((bot.id, bot_link.host_account_id, bot_link.id))

    tournament = Tournament(
        game=game,
        ranking_metric=ranking_metric,
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
        engine_version="demo-live-3",
        outcome_detail={
            "demo_live": True,
            "tick_seconds": tick_seconds,
            "last_tick_ms": int(now.timestamp() * 1000),
            "window_start_ms": int(now.timestamp() * 1000),
        },
    )
    session.add(tournament)
    await session.flush()

    for user_id, host_id, link_id in field:
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
                baseline_snapshot={"host_account_id": host_id, "game": game},
                enqueued_at=now,
            )
        )
        await _inject_game(
            session,
            user_id=user_id,
            host_account_id=host_id,
            game=game,
            metric=ranking_metric,
            value=_draw_value(ranking_metric),
            played_at=now,
        )

    await session.flush()
    await _refresh_standings(session, tournament)
    await session.flush()
    log.info(
        "demo.live_tournament.started",
        tournament_id=str(tournament.id),
        game=game,
        metric=ranking_metric,
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
    number of games counted. Distinct + climbing → distinct, moving standings.

    Scored by user_id directly off the injected rows, so a synthetic host account is
    never polled against a real host API."""
    detail = tournament.outcome_detail or {}
    start_ms = int(detail.get("window_start_ms", 0))
    end_ms = int(tournament.window_ends_at.timestamp() * 1000)
    metric = tournament.ranking_metric
    rows = await session.scalars(
        select(SimulatedMatch).where(
            SimulatedMatch.user_id == user_id,
            SimulatedMatch.game == tournament.game,
            SimulatedMatch.created_at_ms >= start_ms,
            SimulatedMatch.created_at_ms <= end_ms,
        )
    )
    total = 0.0
    count = 0
    for r in rows:
        val = (r.metrics or {}).get(metric)
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
    tournament.standings_cache = {
        "rows": rows,
        "label": metric_label(tournament.ranking_metric),
    }
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


async def _live_tournaments(session: AsyncSession, now: datetime) -> list[Tournament]:
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
            entries = list(
                await session.scalars(
                    select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
                )
            )
            for e in entries:
                await _inject_game(
                    session,
                    user_id=e.user_id,
                    host_account_id=e.host_account_id,
                    game=t.game,
                    metric=t.ranking_metric,
                    value=_draw_value(t.ranking_metric),
                    played_at=now,
                )
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


async def active_live_for(
    session: AsyncSession, user_id: uuid.UUID
) -> Tournament | None:
    """The player's current in-flight self-driving tournament, if any. Joining
    while one is still running returns it instead of creating a second (and
    double-escrowing) — the join button is idempotent while a tournament is live."""
    rows = await session.scalars(
        select(Tournament)
        .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
        .where(
            TournamentEntry.user_id == user_id,
            Tournament.state == "LOCKED",
        )
        .order_by(Tournament.created_at.desc())
    )
    return next((t for t in rows if is_live_tournament(t)), None)
