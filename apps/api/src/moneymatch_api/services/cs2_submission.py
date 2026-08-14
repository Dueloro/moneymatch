"""Submitting a share code: resolve it, check it is yours, store it.

This is the whole CS2 intake path. A player finishes a match, copies the share
code from Watch -> Your Matches, pastes it, and the wager settles from the
scoreboard Valve attests to.

Four checks stand between "a code was pasted" and "a wager pays out". Each one
closes a hole that is otherwise trivially exploitable, and each returns a
message the player can act on, because "invalid" tells them nothing:

1. **The code must decode.** Malformed input never reaches the GC.
2. **Your SteamID64 must be in the roster.** Otherwise I paste a stranger's
   good match and get paid for it.
3. **The match must have started after you joined the wager.** Otherwise I
   paste my best game from last month.
4. **The code must not already be recorded.** Otherwise one good match settles
   ten wagers. Enforced by a unique constraint, not just this check, because
   two concurrent submissions would race past any application-level test.

Plus a **round floor**: a real Premier or Competitive match runs at least 16
rounds, Wingman at least 9. Below that the match was surrendered or abandoned,
and grading it would let a three-round forfeit stand in for a real result.

Note what is *not* needed here: a game-mode filter. CS2 only produces share
codes for Premier, Competitive and Wingman. Casual, Deathmatch and Arms Race
generate none at all, so if a code resolves, it was a real matchmaking match.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import cs2_min_rounds
from ..errors import APIError
from ..models.cs2 import Cs2Match
from . import cs2_matches, gc_client
from . import sharecode as sharecode_service
from .sharecode import ShareCodeError

log = structlog.get_logger(__name__)


class ShareCodeRejected(APIError):
    """A submission that will never be accepted, with a reason a player can act on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)


async def submit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    steam_id: str,
    share_code: str,
    joined_at: datetime | None = None,
) -> Cs2Match:
    """Resolve, verify and store one share code. Raises on every rejection."""
    try:
        decoded = sharecode_service.decode(share_code)
    except ShareCodeError as exc:
        raise ShareCodeRejected("sharecode_malformed", str(exc)) from exc

    existing = await cs2_matches.get_by_share_code(session, decoded.code)
    if existing is not None:
        # Already recorded. If the submitter is in the roster this is a
        # harmless re-paste of their own match; if they are not, it is someone
        # trying to reuse a match they did not play.
        if steam_id in existing.steam_ids():
            log.info(
                "cs2.sharecode_resubmitted",
                share_code=decoded.code,
                user_id=str(user_id),
            )
            return existing
        raise ShareCodeRejected(
            "sharecode_already_used",
            "That match has already been submitted, and you were not in it.",
        )

    try:
        resolved = await gc_client.resolve(decoded.code)
    except gc_client.GcError as exc:
        raise APIError(
            "gc_unavailable" if exc.retryable else "sharecode_unknown",
            str(exc),
            status_code=503 if exc.retryable else 409,
        ) from exc

    players = resolved.get("players") or []
    roster = {str(p.get("steamid")) for p in players if p.get("steamid")}
    if str(steam_id) not in roster:
        log.warning(
            "cs2.sharecode_roster_mismatch",
            share_code=decoded.code,
            user_id=str(user_id),
            steam_id=steam_id,
            roster_size=len(roster),
        )
        raise ShareCodeRejected(
            "sharecode_not_your_match",
            "You were not in that match. Paste a share code from a match you "
            "played on this Steam account.",
        )

    scores = resolved.get("scores") or {}
    rounds = int(scores.get("a", 0)) + int(scores.get("b", 0))
    floor = cs2_min_rounds(len(players))
    if rounds < floor:
        raise ShareCodeRejected(
            "sharecode_match_too_short",
            f"That match only ran {rounds} rounds. A completed match runs at "
            f"least {floor}, so a surrendered or abandoned game cannot settle a "
            "wager.",
        )

    match_time_raw = resolved.get("matchTime")
    match_time = (
        datetime.fromtimestamp(int(match_time_raw), UTC)
        if match_time_raw is not None
        else datetime.now(UTC)
    )
    if joined_at is not None and match_time < joined_at:
        raise ShareCodeRejected(
            "sharecode_predates_wager",
            "That match was played before you joined this wager. Play a new "
            "match and submit that share code instead.",
        )

    row = await cs2_matches.store(
        session,
        code=decoded.code,
        resolved=resolved,
        submitted_by_user_id=user_id,
    )
    # A stored match is new evidence about how this player actually performs,
    # so the bars they are offered next should reflect it. Without this the
    # baseline stays frozen at whatever was guessed when they signed in.
    from . import cs2_baseline

    await cs2_baseline.refresh(session, user_id, steam_id)

    log.info(
        "cs2.sharecode_accepted",
        share_code=decoded.code,
        user_id=str(user_id),
        steam_id=steam_id,
        rounds=rounds,
        demo_expired=row.demo_expired,
    )
    return row


__all__ = ["ShareCodeRejected", "submit"]
