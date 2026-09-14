"""A self-driving demo tournament for hands-off testing (browser QA).

**Scaffolding — demo account only, behind `demo_simulate_enabled`.** Delete with
the rest of the demo surface before launch.

It lets an automated tester (or a human) watch the *whole* tournament loop in the
browser without linking a real game account or playing a game:

- Creates a short-window (default **10 min**) chess tournament and enrols the demo
  user plus a handful of **competitive bots**.
- **Injects stats the same way the app reads them**: it fetches real games from
  the **Lichess API** (via the chess host client) to get realistic move counts,
  then records them as injected `SimulatedMatch` rows — which the `simulated`
  adapter merges into history exactly like real matches. The demo user's results
  come from that Lichess-derived pool; each bot gets its own varying results.
- **The stats keep changing** over the window (`tick` injects another finished
  game per participant every `tick_seconds`), so standings move — simulating
  everyone still playing.
- The **existing worker settles it** at the window close (standings refresh +
  `settle_tournament`), and the **existing tournament UI renders it live** (any
  tournament the demo user has an entry in shows up), so nothing new is needed on
  the frontend.

Scored on `chess_wins` (higher is better, climbs as games are injected), split
**60/25/15** of (pot − rake). Bots are ordinary users (not the forfeiting
`test_opponents`), so they are graded from their own injected games and genuinely
compete.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import GAME_CHESS_LICHESS
from ..models.linked_account import LinkedAccount
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from . import demo_simulation, money_math, wallet_service
from .hosts import lichess
from .user_service import provision_new_user

log = structlog.get_logger(__name__)

# A public, always-active Lichess account we pull realistic move counts from
# (the docs use this GM). We never link the demo user to it — we only borrow its
# real game stats as the injected values, the same shape the chess adapter reads.
_LICHESS_SOURCE = "Zhigalko_Sergei"

# Bots are ordinary demo users under this prefix (NOT the forfeiting test_opponents
# prefix), so they are graded from their own injected games and compete for real.
_LIVE_BOT_PREFIX = "zz_livebot_"
_BOT_NAMES = ("Nova", "Pixel", "Echo", "Vega", "Zephyr", "Comet", "Juno", "Orbit")

DEMO_TOURNAMENT_METRIC = "chess_wins"
DEFAULT_MINUTES = 10
DEFAULT_BOTS = 5
DEFAULT_ENTRY_CENTS = 500
DEFAULT_TICK_SECONDS = 45
LIVE_PRIZE_SPLIT = [60, 25, 15]


def _now() -> datetime:
    return datetime.now(UTC)


async def _fetch_lichess_move_pool(count: int = 30) -> list[int]:
    """Real move counts from recent Lichess games (best-effort). Falls back to a
    plausible synthetic spread if Lichess is unreachable, so a QA run never hangs
    on a flaky network."""
    try:
        games = await lichess.get_user_games(
            _LICHESS_SOURCE, since_ms=0, max_games=count, rated_only=True
        )
    except Exception:  # noqa: BLE001 — demo scaffolding must never 500
        games = []
    moves: list[int] = []
    for g in games or []:
        mv = g.get("moves")
        if isinstance(mv, str) and mv.strip():
            moves.append(len(mv.split()))
    if not moves:
        # Synthetic fallback: blitz games run ~20–60 half-moves.
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


async def _make_bot(session: AsyncSession, name: str) -> tuple[User, LinkedAccount]:
    """A funded, chess-linked competitive bot (idempotent). Its host id is its own
    handle, which never resolves to a real Lichess account — so real history is
    empty and only its injected games grade it."""
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
        await provision_new_user(session, user)  # wallet + signup grant

    host_id = auth_id  # unresolvable → real history empty; injected games grade it
    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == GAME_CHESS_LICHESS
        )
    )
    snapshot = {
        "username": f"{name}Bot",
        "game": GAME_CHESS_LICHESS,
        "primary_speed": "blitz",
        "formats": [{"speed": "blitz", "rating": 1500, "games": 20}],
    }
    if linked is None:
        linked = LinkedAccount(
            user_id=user.id,
            game=GAME_CHESS_LICHESS,
            host_account_id=host_id,
            host_username=f"{name}Bot",
            profile_snapshot=snapshot,
        )
        session.add(linked)
    await session.flush()
    return user, linked


async def _inject_win(
    session: AsyncSession,
    user_id: uuid.UUID,
    host_account_id: str,
    moves: int,
    played_at: datetime,
) -> None:
    """Record one finished, won chess game (increments `chess_wins`)."""
    await demo_simulation.record(
        session,
        user_id=user_id,
        game=GAME_CHESS_LICHESS,
        host_account_id=host_account_id,
        metrics={"chess_moves": float(moves)},
        won=True,
        moves=moves,
        played_at=played_at,
        created_by="demo_live_tournament",
    )


async def start_live(
    session: AsyncSession,
    demo_user: User,
    *,
    minutes: int = DEFAULT_MINUTES,
    num_bots: int = DEFAULT_BOTS,
    entry_cents: int = DEFAULT_ENTRY_CENTS,
    tick_seconds: int = DEFAULT_TICK_SECONDS,
) -> Tournament:
    """Create + fill a self-driving 10-minute chess tournament for the demo user.

    Returns the `Tournament`. The demo user must already be chess-linked (the demo
    fixture does this on login). Escrows every entry, injects each participant's
    first game, and hands the rest to the worker (standings + settle) and `tick`
    (ongoing injected games)."""
    demo_link = await _chess_link(session, demo_user.id)
    if demo_link is None:
        raise ValueError("demo user is not chess-linked; sign in via demo first")

    now = _now()
    move_pool = await _fetch_lichess_move_pool()

    # (user_id, host_account_id, linked_account_id) per participant.
    field: list[tuple[uuid.UUID, str, uuid.UUID]] = [
        (demo_user.id, demo_link.host_account_id, demo_link.id)
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
        score_matches=5,
        pot_cents=entry_cents * len(field),
        state="LOCKED",
        window_starts_at=now,
        window_ends_at=now + timedelta(minutes=minutes),
        engine_version="demo-live-1",
        outcome_detail={
            "demo_live": True,
            "tick_seconds": tick_seconds,
            "last_tick_ms": int(now.timestamp() * 1000),
            "move_pool": move_pool,
            "pool_cursor": 0,
            "lichess_source": _LICHESS_SOURCE,
        },
    )
    session.add(tournament)
    await session.flush()

    # Escrow each entry, create the entry row, and inject the first game so the
    # standings board isn't empty when the tester opens it.
    for idx, (user_id, host_id, link_id) in enumerate(field):
        await wallet_service.escrow_hold(
            session,
            user_id,
            entry_cents,
            ref_type="tournament",
            ref_id=tournament.id,
            memo="demo live tournament entry",
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
        moves = (
            move_pool[idx % len(move_pool)]
            if user_id == demo_user.id
            else random.randint(20, 60)
        )
        await _inject_win(session, user_id, host_id, moves, now)

    await session.flush()
    log.info(
        "demo.live_tournament.started",
        tournament_id=str(tournament.id),
        field=len(field),
        minutes=minutes,
    )
    return tournament


async def _due_live_tournaments(
    session: AsyncSession, now: datetime
) -> list[Tournament]:
    rows = await session.scalars(
        select(Tournament).where(
            Tournament.state == "LOCKED",
            Tournament.window_ends_at > now,
        )
    )
    out: list[Tournament] = []
    for t in rows:
        detail = t.outcome_detail or {}
        if not detail.get("demo_live"):
            continue
        last = int(detail.get("last_tick_ms", 0))
        due_ms = last + int(detail.get("tick_seconds", DEFAULT_TICK_SECONDS)) * 1000
        if int(now.timestamp() * 1000) >= due_ms:
            out.append(t)
    return out


async def tick(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Inject one more finished game per participant for every live demo
    tournament whose tick is due. Returns how many tournaments advanced. The
    ongoing injections are what make the standings move over the window."""
    now = now or _now()
    advanced = 0
    for t in await _due_live_tournaments(session, now):
        detail = dict(t.outcome_detail or {})
        pool: list[int] = list(detail.get("move_pool") or [30])
        cursor = int(detail.get("pool_cursor", 0))
        entries = await session.scalars(
            select(TournamentEntry).where(TournamentEntry.tournament_id == t.id)
        )
        demo_host = None
        entry_list = list(entries)
        for e in entry_list:
            is_bot = e.host_account_id.startswith(_LIVE_BOT_PREFIX)
            if not is_bot:
                demo_host = e.host_account_id
            moves = (
                random.randint(20, 60)
                if is_bot
                else pool[cursor % len(pool)]
            )
            await _inject_win(session, e.user_id, e.host_account_id, moves, now)
        if demo_host is not None:
            cursor += 1
        detail["pool_cursor"] = cursor
        detail["last_tick_ms"] = int(now.timestamp() * 1000)
        t.outcome_detail = detail
        advanced += 1
    await session.flush()
    return advanced
