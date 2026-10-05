"""Background match ingestion: fetch each linked account's new games, store them.

Every worker cycle picks a few accounts per game that are due a poll, asks the
game's API for games we have not stored yet, and inserts them into
`game_matches` (ON CONFLICT DO NOTHING, so a re-fetch is harmless). Contests
then score from that table and never call a host at settlement time.

Who gets polled, and how often:

- **Final** — an entrant of a tournament whose end + grace period has passed but
  who has not been polled since. Settlement waits on this poll, so it goes
  first.
- **Hot** — anyone in an open or running tournament, or in an active duel, on
  that game: every `INGEST_HOT_INTERVAL_SECONDS`.
- **Cold** — every other linked account: every `INGEST_COLD_INTERVAL_SECONDS`,
  so history keeps accruing for skill grouping even between contests.

Each game has a per-cycle poll cap (`INGEST_MAX_POLLS_PER_CYCLE`). For PUBG that
cap is what spends its ~10 req/min budget evenly instead of in one burst.

A failed poll (host outage, rate limit) moves `ingest_attempted_at` only, so the
account retries on a later cycle without hogging the queue; `ingest_polled_at`
moves only on success, and is what a tournament's final-poll check reads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, case, false, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .. import clock
from ..adapters import registry
from ..adapters.base import NormGame
from ..constants import (
    INGEST_BACKFILL_DAYS,
    INGEST_COLD_INTERVAL_SECONDS,
    INGEST_HOT_INTERVAL_SECONDS,
    INGEST_MAX_POLLS_PER_CYCLE,
    INGEST_RETRY_SECONDS,
    REGISTERED_GAMES,
)
from ..models.game_match import GameMatch
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer
from ..models.tournaments import Tournament, TournamentEntry
from . import demo_mode, test_opponents, tournament_timing

log = structlog.get_logger(__name__)

# Live contest states whose players are polled on the hot cadence.
_LIVE_TOURNAMENT_STATES = ("OPEN", "LOCKED")
_LIVE_MATCH_STATES = ("ACTIVE", "AWAITING_RESULT")


def _dt(ms: int | None) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, UTC) if ms else None


def _result(g: NormGame) -> str | None:
    if g.drawn:
        return "draw"
    if g.won is True:
        return "win"
    if g.won is False:
        return "loss"
    return None


async def store_games(
    session: AsyncSession, link: LinkedAccount, games: list[NormGame]
) -> int:
    """Insert games for one account; already-stored ones are skipped. Returns
    how many rows were new."""
    new = 0
    for g in games:
        if not g.id or not g.created_at_ms:
            continue  # unidentifiable — nothing to key it on
        stmt = (
            insert(GameMatch)
            .values(
                user_id=link.user_id,
                linked_account_id=link.id,
                game=link.game,
                host_account_id=link.host_account_id,
                host_match_id=str(g.id),
                started_at=_dt(g.created_at_ms),
                ended_at=_dt(g.ended_at_ms),
                mode=(g.speed or None) and str(g.speed)[:32],
                rated=bool(g.rated),
                eligible=bool(g.eligible),
                result=_result(g),
                moves=int(g.moves or 0),
                metrics={k: float(v) for k, v in (g.metrics or {}).items()},
                detail=g.detail or {},
            )
            .on_conflict_do_nothing(constraint="uq_game_matches_account_match")
            .returning(GameMatch.id)
        )
        if await session.scalar(stmt) is not None:
            new += 1
    await session.flush()
    return new


async def _known_ids(session: AsyncSession, link: LinkedAccount) -> set[str]:
    rows = await session.scalars(
        select(GameMatch.host_match_id).where(
            GameMatch.game == link.game,
            GameMatch.host_account_id == link.host_account_id,
        )
    )
    return set(rows)


async def poll_account(
    session: AsyncSession, link: LinkedAccount, *, now: datetime | None = None
) -> int:
    """Fetch and store one account's new games. Raises on a host failure (the
    caller records the attempt and retries later). Returns rows inserted.

    `ingest_polled_at` moves only when the account is fully caught up to the
    present; a partial batch (a very active player's backfill) leaves it where
    it was, so the account is polled again next cycle and no tournament settles
    on a history that stops short."""
    now = now or clock.now()
    adapter = registry.host(link.game)
    first_poll = link.ingest_polled_at is None
    since_ms = link.ingest_cursor_ms or int(
        (now - timedelta(days=INGEST_BACKFILL_DAYS)).timestamp() * 1000
    )
    batch = await adapter.fetch_history(
        link.host_account_id,
        since_ms,
        known_ids=await _known_ids(session, link),
        first_poll=first_poll,
    )
    games = batch.games
    inserted = await store_games(session, link, games)
    if games:
        # Page forward from the newest game seen. Hosts whose history is not
        # time-paged (PUBG) ignore the cursor and dedupe by id instead.
        newest = max(g.created_at_ms for g in games)
        link.ingest_cursor_ms = max(link.ingest_cursor_ms or 0, newest + 1)
    if batch.complete:
        link.ingest_polled_at = now
    link.ingest_attempted_at = now
    await session.flush()
    return inserted


# --------------------------------------------------------------------------- #
# Scheduling.
# --------------------------------------------------------------------------- #


async def _live_user_ids(session: AsyncSession, game: str) -> set[uuid.UUID]:
    """Users with a live contest on this game (hot cadence)."""
    t_users = await session.scalars(
        select(TournamentEntry.user_id)
        .join(Tournament, Tournament.id == TournamentEntry.tournament_id)
        .where(
            Tournament.game == game,
            Tournament.state.in_(_LIVE_TOURNAMENT_STATES),
            # A tournament still waiting for its second player has no clock,
            # so nothing can count yet: no need to spend host calls on it.
            Tournament.window_starts_at.isnot(None),
            TournamentEntry.status == "LOCKED",
        )
    )
    m_users = await session.scalars(
        select(MatchPlayer.user_id)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.game == game, Match.state.in_(_LIVE_MATCH_STATES))
    )
    return set(t_users) | set(m_users)


async def final_poll_link_ids(
    session: AsyncSession, game: str, now: datetime
) -> set[uuid.UUID]:
    """Linked accounts a tournament is waiting on: its end + grace has passed
    and the account has not been polled since."""
    grace = timedelta(seconds=tournament_timing.grace_seconds(game))
    rows = await session.execute(
        select(TournamentEntry.linked_account_id, Tournament.window_ends_at)
        .join(Tournament, Tournament.id == TournamentEntry.tournament_id)
        .where(
            Tournament.game == game,
            Tournament.state.in_(_LIVE_TOURNAMENT_STATES),
            Tournament.window_ends_at <= now - grace,
            TournamentEntry.status == "LOCKED",
        )
    )
    wanted = {lid: ends + grace for lid, ends in rows}
    if not wanted:
        return set()
    links = await session.execute(
        select(LinkedAccount.id, LinkedAccount.ingest_polled_at).where(
            LinkedAccount.id.in_(wanted)
        )
    )
    return {lid for lid, polled in links if polled is None or polled < wanted[lid]}


async def due_links(
    session: AsyncSession, game: str, now: datetime, limit: int
) -> list[uuid.UUID]:
    """The accounts to poll this cycle for one game, most urgent first."""
    final_ids = await final_poll_link_ids(session, game, now)
    hot_users = await _live_user_ids(session, game)
    hot_cut = now - timedelta(seconds=INGEST_HOT_INTERVAL_SECONDS)
    cold_cut = now - timedelta(seconds=INGEST_COLD_INTERVAL_SECONDS)

    is_final = LinkedAccount.id.in_(final_ids) if final_ids else false()
    is_hot = LinkedAccount.user_id.in_(hot_users) if hot_users else false()
    never = LinkedAccount.ingest_attempted_at.is_(None)
    # Still catching up: the last attempt did not end fully caught up (a partial
    # backfill, or a failure). Poll again on the next cycle.
    behind = or_(
        LinkedAccount.ingest_polled_at.is_(None),
        LinkedAccount.ingest_polled_at < LinkedAccount.ingest_attempted_at,
    )
    # Nothing is retried sooner than INGEST_RETRY_SECONDS after its last
    # attempt. Without this a failing account (host outage, a rate limit) was
    # "behind" again the very next cycle, every 15 s, and spent the PUBG budget
    # that everyone else's polls need.
    rested = or_(
        never,
        LinkedAccount.ingest_attempted_at
        < now - timedelta(seconds=INGEST_RETRY_SECONDS),
    )
    due = and_(
        rested,
        or_(
            is_final,
            never,
            behind,
            and_(is_hot, LinkedAccount.ingest_attempted_at < hot_cut),
            LinkedAccount.ingest_attempted_at < cold_cut,
        ),
    )
    priority = case((is_final, 0), (is_hot, 1), (behind, 2), else_=3)
    rows = await session.scalars(
        select(LinkedAccount.id)
        .where(
            LinkedAccount.game == game,
            LinkedAccount.status == "active",
            # Demo practice bots have no real host account. Filter them here, not
            # after selection: skipped rows never get an attempt stamped, so they
            # would stay first in line forever and starve real accounts.
            LinkedAccount.host_account_id.notlike(
                f"{test_opponents.TEST_AUTH_PREFIX}%"
            ),
            # Likewise the demo's made-up handles: no host knows them, so every
            # poll would fail and burn a call (demo_mode.is_placeholder_link).
            ~LinkedAccount.host_account_id.startswith(f"{game}_", autoescape=True),
            due,
        )
        .order_by(
            priority,
            LinkedAccount.ingest_attempted_at.asc().nulls_first(),
        )
        .limit(limit)
    )
    return list(rows)


async def run_cycle(
    sm: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> int:
    """One ingestion pass across every game. Returns accounts polled."""
    now = now or clock.now()
    polled = 0
    for game in REGISTERED_GAMES:
        cap = INGEST_MAX_POLLS_PER_CYCLE.get(game, 5)
        async with sm() as session:
            ids = await due_links(session, game, now, cap)
        done = 0
        for link_id in ids:
            if done >= cap:
                break
            async with sm() as session:
                link = await session.get(LinkedAccount, link_id, with_for_update=True)
                if link is None or link.status != "active":
                    continue
                if test_opponents.is_practice_opponent(
                    link.host_account_id
                ) or demo_mode.is_placeholder_link(game, link.host_account_id):
                    continue  # demo bots / handles have no real host account
                try:
                    inserted = await poll_account(session, link, now=now)
                    await session.commit()
                    done += 1
                    if inserted:
                        log.info(
                            "ingest.stored",
                            game=game,
                            link_id=str(link_id),
                            new=inserted,
                        )
                except Exception as exc:  # noqa: BLE001 — host hiccup: retry later
                    await session.rollback()
                    await _mark_attempt(sm, link_id, now)
                    done += 1  # a failed call still spent budget
                    log.warning(
                        "ingest.poll_failed",
                        game=game,
                        link_id=str(link_id),
                        error=str(exc),
                    )
        polled += done
    return polled


async def _mark_attempt(
    sm: async_sessionmaker[AsyncSession], link_id: uuid.UUID, now: datetime
) -> None:
    async with sm() as session:
        link = await session.get(LinkedAccount, link_id)
        if link is not None:
            link.ingest_attempted_at = now
            await session.commit()


async def last_polled(
    session: AsyncSession, link_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime | None]:
    rows = await session.execute(
        select(LinkedAccount.id, LinkedAccount.ingest_polled_at).where(
            LinkedAccount.id.in_(link_ids)
        )
    )
    return {lid: polled for lid, polled in rows.all()}
