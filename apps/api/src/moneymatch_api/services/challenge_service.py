"""Challenges — direct friend challenges, rematches, and invite links.

A challenge is an *intent* to play a specific market at a preset entry; accepting
it forms a PENDING match through the same lifecycle as a paired game (both
confirm → escrow → activate), so no money moves until confirm and the server owns
every number (08-phase-5 · deliverable 3).

Two anti-collusion rules bite here, both on the **money flow, not the fun**:

- Rake-bearing contests between the same pair are capped (config: 3/day, 10/week,
  friends included). Past the cap a challenge becomes a **friendly** — zero-rake,
  entries refunded on settle, excluded from the leaderboard.
- Direct challenges are only to accepted friends (or a rematch of a shared,
  settled match); strangers meet through the fair matcher, not a hand-picked slip.

Invite links carry a single-use `invite_token` (24 h TTL); the recipient signs
in, links the game, and accepts. Flushes, never commits.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import (
    CHALLENGE_TTL_SECONDS,
    ENTRY_PRESETS_CENTS,
    PAIR_RAKE_CONTESTS_PER_DAY,
    PAIR_RAKE_CONTESTS_PER_WEEK,
    game_flag_key,
)
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer
from ..models.social import Challenge
from ..models.user import User
from . import friends_service, matchmaking, notifications_service
from .feature_flags import get_boolean_flags
from .markets import MarketDef
from .markets import get as get_market
from .match_states import CANCELED

log = structlog.get_logger(__name__)


class ChallengeError(APIError):
    """A challenge-flow failure (RFC-7807 via APIError)."""


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Pair rake-cap → friendly.
# --------------------------------------------------------------------------- #


async def _pair_rake_count(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID, since: datetime
) -> int:
    """Rake-bearing (non-friendly, non-canceled) matches between two users since
    a cutoff — the anti-collusion counter (friends included)."""
    p1 = MatchPlayer.__table__.alias("cp1")
    p2 = MatchPlayer.__table__.alias("cp2")
    stmt = (
        select(func.count())
        .select_from(
            Match.__table__.join(p1, p1.c.match_id == Match.id).join(
                p2, p2.c.match_id == Match.id
            )
        )
        .where(
            p1.c.user_id == a,
            p2.c.user_id == b,
            Match.friendly.is_(False),
            Match.state != CANCELED,
            Match.created_at >= since,
        )
    )
    return int(await session.scalar(stmt) or 0)


async def pair_over_cap(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID, *, now: datetime | None = None
) -> bool:
    """Whether the pair is at/over its rake-bearing cap (⇒ the next contest is a
    friendly). Checks both the daily and the weekly window."""
    now = now or _now()
    day = await _pair_rake_count(session, a, b, now - timedelta(days=1))
    if day >= PAIR_RAKE_CONTESTS_PER_DAY:
        return True
    week = await _pair_rake_count(session, a, b, now - timedelta(days=7))
    return week >= PAIR_RAKE_CONTESTS_PER_WEEK


# --------------------------------------------------------------------------- #
# Shared validation.
# --------------------------------------------------------------------------- #


def _resolve_market(game: str, market_key: str, speed: str | None) -> MarketDef:
    market = get_market(game, market_key)
    if market is None:
        raise ChallengeError(
            "unknown_market",
            f"'{market_key}' is not a market for {game}.",
            status_code=404,
        )
    if market.requires_speed and not speed:
        raise ChallengeError(
            "speed_required", "This market needs a time control.", status_code=422
        )
    return market


def _validate_entry(entry_cents: int) -> None:
    if entry_cents not in ENTRY_PRESETS_CENTS:
        raise ChallengeError(
            "invalid_entry",
            "Entry must be one of the offered presets.",
            status_code=422,
            detail={"allowed": list(ENTRY_PRESETS_CENTS)},
        )


async def _link_for(
    session: AsyncSession, user_id: uuid.UUID, game: str
) -> LinkedAccount | None:
    return await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user_id, LinkedAccount.game == game
        )
    )


async def _assert_game_enabled(session: AsyncSession, game: str) -> None:
    flags = await get_boolean_flags(session)
    if not flags.get(game_flag_key(game), True):
        raise ChallengeError(
            "game_disabled", "This game is currently disabled.", status_code=409
        )


async def _require_challenger_ready(
    session: AsyncSession, challenger: User, game: str
) -> LinkedAccount:
    if challenger.status != "active":
        raise ChallengeError(
            "account_not_active",
            f"Account is {challenger.status}; play is disabled.",
            status_code=409,
        )
    await _assert_game_enabled(session, game)
    link = await _link_for(session, challenger.id, game)
    if link is None or link.status != "active":
        raise ChallengeError(
            "not_linked",
            f"Link a {game} account before you can challenge on it.",
            status_code=409,
            detail={"game": game},
        )
    return link


# --------------------------------------------------------------------------- #
# Creation.
# --------------------------------------------------------------------------- #


async def create_direct(
    session: AsyncSession,
    challenger: User,
    *,
    challengee_id: uuid.UUID,
    game: str,
    market_key: str,
    entry_cents: int,
    speed: str | None = None,
    rematch_of: uuid.UUID | None = None,
) -> Challenge:
    """Send a direct challenge to a friend (or a rematch opponent)."""
    if challengee_id == challenger.id:
        raise ChallengeError(
            "self_challenge", "You can't challenge yourself.", status_code=422
        )
    challengee = await session.get(User, challengee_id)
    if challengee is None:
        raise ChallengeError("challengee_not_found", "No such player.", status_code=404)

    # Authorization: friends, or a rematch of a shared settled match.
    if rematch_of is None and not await friends_service.are_friends(
        session, challenger.id, challengee_id
    ):
        raise ChallengeError(
            "not_friends",
            "You can only challenge friends directly.",
            status_code=403,
        )

    market = _resolve_market(game, market_key, speed)
    _validate_entry(entry_cents)
    await _require_challenger_ready(session, challenger, game)

    friendly = await pair_over_cap(session, challenger.id, challengee_id)
    challenge = await _create(
        session,
        challenger=challenger,
        challengee_id=challengee_id,
        invite_token=None,
        market=market,
        entry_cents=entry_cents,
        speed=speed,
        friendly=friendly,
        rematch_of=rematch_of,
    )
    await notifications_service.emit(
        session,
        challengee_id,
        "challenge_received",
        {
            "challenge_id": str(challenge.id),
            "from_user_id": str(challenger.id),
            "from_username": challenger.username,
            "game": game,
            "market": market_key,
            "entry_cents": entry_cents,
            "friendly": friendly,
        },
    )
    return challenge


async def create_rematch(
    session: AsyncSession, user: User, match_id: uuid.UUID
) -> Challenge:
    """One-tap rematch of a settled H2H match — same game/market/entry, same
    opponent, subject to the same friend/cap checks (08-phase-5 · deliverable 6)."""
    match = await session.get(Match, match_id)
    if match is None:
        raise ChallengeError("match_not_found", "No such match.", status_code=404)
    seats = list(
        await session.scalars(
            select(MatchPlayer).where(MatchPlayer.match_id == match_id)
        )
    )
    if not any(s.user_id == user.id for s in seats):
        raise ChallengeError(
            "not_a_player", "You weren't in that match.", status_code=403
        )
    opp = next((s for s in seats if s.user_id != user.id), None)
    if opp is None:
        raise ChallengeError(
            "no_opponent", "That match has no opponent.", status_code=409
        )
    return await create_direct(
        session,
        user,
        challengee_id=opp.user_id,
        game=match.game,
        market_key=match.market,
        entry_cents=match.entry_cents,
        speed=match.speed,
        rematch_of=match_id,
    )


async def create_invite(
    session: AsyncSession,
    challenger: User,
    *,
    game: str,
    market_key: str,
    entry_cents: int,
    speed: str | None = None,
) -> Challenge:
    """Create a shareable single-use invite link (no challengee yet)."""
    market = _resolve_market(game, market_key, speed)
    _validate_entry(entry_cents)
    await _require_challenger_ready(session, challenger, game)
    token = secrets.token_urlsafe(16)
    return await _create(
        session,
        challenger=challenger,
        challengee_id=None,
        invite_token=token,
        market=market,
        entry_cents=entry_cents,
        speed=speed,
        friendly=False,  # determined at accept, once the recipient is known
        rematch_of=None,
    )


async def _create(
    session: AsyncSession,
    *,
    challenger: User,
    challengee_id: uuid.UUID | None,
    invite_token: str | None,
    market: MarketDef,
    entry_cents: int,
    speed: str | None,
    friendly: bool,
    rematch_of: uuid.UUID | None,
) -> Challenge:
    challenge = Challenge(
        challenger_id=challenger.id,
        challengee_id=challengee_id,
        invite_token=invite_token,
        game=market.game,
        market=market.key,
        speed=speed,
        entry_cents=entry_cents,
        friendly=friendly,
        state="sent",
        rematch_of=rematch_of,
        expires_at=_now() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
    )
    session.add(challenge)
    await session.flush()
    log.info(
        "challenge.created",
        challenge_id=str(challenge.id),
        invite=invite_token is not None,
        game=market.game,
        market=market.key,
        friendly=friendly,
    )
    return challenge


# --------------------------------------------------------------------------- #
# Accept / decline.
# --------------------------------------------------------------------------- #


def _assert_live(challenge: Challenge, now: datetime) -> None:
    if challenge.state != "sent":
        raise ChallengeError(
            "not_open", f"This challenge is {challenge.state}.", status_code=409
        )
    if challenge.expires_at <= now:
        raise ChallengeError("expired", "This challenge has expired.", status_code=409)


async def _accept(
    session: AsyncSession, challenge: Challenge, challengee: User
) -> Match:
    """Shared accept: verify the challengee is ready, form the PENDING match,
    resolve the challenge, notify the challenger."""
    now = _now()
    _assert_live(challenge, now)
    if challengee.id == challenge.challenger_id:
        raise ChallengeError(
            "self_accept", "You can't accept your own challenge.", status_code=422
        )
    if challengee.status != "active":
        raise ChallengeError(
            "account_not_active",
            f"Account is {challengee.status}; play is disabled.",
            status_code=409,
        )
    await _assert_game_enabled(session, challenge.game)

    challengee_link = await _link_for(session, challengee.id, challenge.game)
    if challengee_link is None or challengee_link.status != "active":
        # The invite/challenge funnel: prompt linking, then accept.
        raise ChallengeError(
            "needs_link",
            f"Link your {challenge.game} account to accept this challenge.",
            status_code=409,
            detail={"game": challenge.game},
        )

    challenger = await session.get(User, challenge.challenger_id)
    challenger_link = await _link_for(session, challenge.challenger_id, challenge.game)
    if challenger is None or challenger_link is None:
        raise ChallengeError(
            "challenger_unavailable",
            "The challenger is no longer able to play this.",
            status_code=409,
        )

    market = _resolve_market(challenge.game, challenge.market, challenge.speed)
    # Recompute the friendly flag now that both parties are known (invite links
    # had no challengee at creation; direct challenges may have crossed the cap
    # since). The accept-time value governs the match economics.
    friendly = await pair_over_cap(session, challenge.challenger_id, challengee.id)

    match = await matchmaking.create_challenge_match(
        session,
        market=market,
        challenger=challenger,
        challenger_link=challenger_link,
        challengee=challengee,
        challengee_link=challengee_link,
        entry_cents=challenge.entry_cents,
        speed=challenge.speed,
        friendly=friendly,
    )

    challenge.challengee_id = challengee.id
    challenge.friendly = friendly
    challenge.state = "accepted"
    challenge.match_id = match.id
    challenge.resolved_at = now
    await session.flush()

    await notifications_service.emit(
        session,
        challenge.challenger_id,
        "challenge_accepted",
        {
            "challenge_id": str(challenge.id),
            "match_id": str(match.id),
            "by_user_id": str(challengee.id),
            "by_username": challengee.username,
            "friendly": friendly,
        },
    )
    log.info(
        "challenge.accepted",
        challenge_id=str(challenge.id),
        match_id=str(match.id),
        friendly=friendly,
    )
    return match


async def accept_direct(
    session: AsyncSession, user: User, challenge_id: uuid.UUID
) -> Match:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None or challenge.invite_token is not None:
        raise ChallengeError(
            "challenge_not_found", "No such challenge.", status_code=404
        )
    if challenge.challengee_id != user.id:
        raise ChallengeError(
            "not_challengee", "This challenge isn't addressed to you.", status_code=403
        )
    return await _accept(session, challenge, user)


async def accept_invite(session: AsyncSession, user: User, token: str) -> Match:
    challenge = await _load_token(session, token)
    return await _accept(session, challenge, user)


async def decline(
    session: AsyncSession, user: User, challenge_id: uuid.UUID
) -> Challenge:
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None or challenge.challengee_id != user.id:
        raise ChallengeError(
            "challenge_not_found", "No such challenge.", status_code=404
        )
    _assert_live(challenge, _now())
    challenge.state = "declined"
    challenge.resolved_at = _now()
    await session.flush()
    await notifications_service.emit(
        session,
        challenge.challenger_id,
        "system",
        {
            "event": "challenge_declined",
            "challenge_id": str(challenge.id),
            "by_username": user.username,
        },
    )
    return challenge


# --------------------------------------------------------------------------- #
# Preview + lookups + worker expiry.
# --------------------------------------------------------------------------- #


async def _load_token(session: AsyncSession, token: str) -> Challenge:
    challenge = await session.scalar(
        select(Challenge).where(Challenge.invite_token == token)
    )
    if challenge is None:
        raise ChallengeError(
            "invalid_token", "This invite link is invalid.", status_code=404
        )
    return challenge


@dataclass
class ChallengePreview:
    challenge: Challenge
    challenger_username: str | None
    valid: bool  # still open + unexpired (can be accepted)


async def preview_token(session: AsyncSession, token: str) -> ChallengePreview:
    """Public invite-link preview (market, entry, challenger name) — no auth."""
    challenge = await _load_token(session, token)
    challenger = await session.get(User, challenge.challenger_id)
    valid = challenge.state == "sent" and challenge.expires_at > _now()
    return ChallengePreview(
        challenge=challenge,
        challenger_username=challenger.username if challenger else None,
        valid=valid,
    )


async def get_for_user(
    session: AsyncSession, user: User, challenge_id: uuid.UUID
) -> Challenge:
    """Fetch a direct challenge the user is a party to (renders the Respond slip)."""
    challenge = await session.get(Challenge, challenge_id)
    if challenge is None or user.id not in (
        challenge.challenger_id,
        challenge.challengee_id,
    ):
        raise ChallengeError(
            "challenge_not_found", "No such challenge.", status_code=404
        )
    return challenge


async def expire_due(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Worker: expire past-TTL open challenges and notify the challenger."""
    now = now or _now()
    due = list(
        await session.scalars(
            select(Challenge)
            .where(and_(Challenge.state == "sent", Challenge.expires_at <= now))
            .with_for_update(skip_locked=True)
        )
    )
    for challenge in due:
        challenge.state = "expired"
        challenge.resolved_at = now
        await notifications_service.emit(
            session,
            challenge.challenger_id,
            "system",
            {"event": "challenge_expired", "challenge_id": str(challenge.id)},
        )
    await session.flush()
    return len(due)
