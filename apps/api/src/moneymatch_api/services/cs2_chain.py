"""Walking Valve's share-code chain, so matches arrive without a paste.

Pasting a share code after every match is fine for a demo and hopeless as a
product: it puts a manual step between playing and getting paid, and every
player who forgets is a support ticket. Valve stores a player's matches as a
linked list, so `GetNextMatchSharingCode` turns one code they own into the next
one, forever. A cursor is all that has to persist.

Setup costs one auth code and one starting share code, and after that this is
the entire ingest path. Codes it collects go through the *same* resolve-and-
store used by a paste, so nothing downstream knows or cares where a match came
from.

Two rules that exist because getting them wrong is expensive:

- **A rejected cursor or auth code stops the chain.** Valve temporarily blocks
  an API key that keeps presenting bad auth codes, so one player's stale cursor
  retried in a loop would take settlement down for everyone. A broken chain
  waits for the player instead.
- **A walk is bounded.** A player returning after a hundred matches should not
  hold a request, or a worker cycle, open while it drains their whole history.
  It catches up over successive syncs.

Collecting codes is worth doing even before anything reads them: share codes
never expire, but the demos they point at do, in about a month. A code not
collected now is ADR that can never be computed later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..errors import APIError
from ..models.cs2 import Cs2Match, Cs2ShareChain
from . import cs2_matches, gc_client
from . import sharecode as sharecode_service
from .hosts import steam
from .sharecode import ShareCodeError

log = structlog.get_logger(__name__)

#: How many new matches one sync will ingest before stopping.
#:
#: Each code costs a Valve call plus a Game Coordinator resolve (~1.2s apart,
#: single-flight), so an unbounded walk over a long absence would stall whatever
#: called it. Whatever is left is picked up next time.
MAX_CODES_PER_SYNC = 10


class ChainNotConnected(APIError):
    def __init__(self) -> None:
        super().__init__(
            "chain_not_connected",
            "Automatic match collection is not set up for this account yet.",
            status_code=409,
        )


def is_enabled() -> bool:
    return bool(get_settings().valve_chain_enabled)


async def get_chain(session: AsyncSession, user_id: uuid.UUID) -> Cs2ShareChain | None:
    return await session.scalar(
        select(Cs2ShareChain).where(Cs2ShareChain.user_id == user_id)
    )


async def _ingest(
    session: AsyncSession, *, user_id: uuid.UUID, steam_id: str, code: str
) -> Cs2Match | None:
    """Resolve one code and store the scoreboard. Returns None if unresolvable.

    Deliberately not `cs2_submission.submit`: that enforces the rules for
    *settling a wager* (the match must post-date the wager you joined, the code
    must not already be spent). Those are questions for grading time. This is
    collection, and a match that cannot settle today is still evidence for a
    baseline and still a demo worth capturing before it expires.
    """
    existing = await cs2_matches.get_by_share_code(session, code)
    if existing is not None:
        return existing
    try:
        resolved = await gc_client.resolve(code)
    except gc_client.GcError as exc:
        if exc.retryable:
            # The sidecar is down or busy. This match is fine and will resolve
            # later, so it must not be skipped: raise, and let the caller stop
            # the walk with the cursor still pointing at it. Advancing past a
            # match because the *fetcher* was briefly unavailable loses a real
            # result the player has already staked money on.
            raise
        # Permanently unresolvable (the GC does not know this code). Skipping is
        # correct here, or the chain wedges behind it forever.
        log.warning("cs2.chain_code_unresolvable", share_code=code, error=str(exc))
        return None
    return await cs2_matches.store(
        session, code=code, resolved=resolved, submitted_by_user_id=user_id
    )


async def connect(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    steam_id: str,
    auth_code: str,
    known_code: str,
) -> Cs2ShareChain:
    """Set up (or repair) automatic collection, proving it works before saving.

    The first poll happens here on purpose. A cursor that is stored and only
    tried later fails silently at settlement time, which is the worst possible
    moment to discover a typo'd auth code -- the player has already staked money
    and played a match. Failing now costs them ten seconds.
    """
    try:
        decoded = sharecode_service.decode(known_code)
    except ShareCodeError as exc:
        raise APIError("sharecode_malformed", str(exc), status_code=409) from exc

    try:
        # A 412 here is Valve saying this code is not from this account, which
        # is the check that the cursor actually belongs to the player.
        await steam.get_next_share_code(steam_id, auth_code.strip(), decoded.code)
    except steam.ChainError as exc:
        raise APIError(
            exc.code, str(exc), status_code=503 if exc.retryable else 409
        ) from exc

    chain = await get_chain(session, user_id)
    if chain is None:
        chain = Cs2ShareChain(
            user_id=user_id,
            steam_id=steam_id,
            auth_code=auth_code.strip(),
            known_code=decoded.code,
        )
        session.add(chain)
    else:
        chain.steam_id = steam_id
        chain.auth_code = auth_code.strip()
        chain.known_code = decoded.code
    chain.state = "active"
    chain.last_error = None
    await session.flush()

    log.info("cs2.chain_connected", user_id=str(user_id), steam_id=steam_id)
    return chain


async def sync(session: AsyncSession, chain: Cs2ShareChain) -> list[Cs2Match]:
    """Ingest every match after the cursor, up to `MAX_CODES_PER_SYNC`."""
    if not chain.is_active():
        return []

    collected: list[Cs2Match] = []
    cursor = chain.known_code
    for _ in range(MAX_CODES_PER_SYNC):
        try:
            nxt = await steam.get_next_share_code(
                chain.steam_id, chain.auth_code, cursor
            )
        except steam.ChainError as exc:
            if exc.retryable:
                # Rate limited or Steam is down. Leave the cursor where it is
                # and keep the chain active: nothing is wrong with it.
                log.warning("cs2.chain_deferred", user_id=str(chain.user_id))
                break
            chain.state = "broken"
            chain.last_error = str(exc)[:200]
            log.warning("cs2.chain_broken", user_id=str(chain.user_id), reason=exc.code)
            break

        if nxt is None:
            break  # Caught up. The normal ending, not an error.

        try:
            match = await _ingest(
                session, user_id=chain.user_id, steam_id=chain.steam_id, code=nxt
            )
        except gc_client.GcError:
            # Leave the cursor on this code so the next sync picks it up again.
            # The player played this match; losing it because the sidecar was
            # restarting would be indistinguishable, to them, from the product
            # not working.
            log.warning(
                "cs2.chain_ingest_deferred",
                user_id=str(chain.user_id),
                share_code=nxt,
            )
            break

        # Only now does the cursor move. It marks the last code we are done
        # with, not the last code Valve mentioned.
        cursor = nxt
        chain.known_code = nxt
        if match is not None:
            collected.append(match)
            chain.last_code_at = datetime.now(UTC)

    chain.last_polled_at = datetime.now(UTC)
    await session.flush()

    if collected:
        # New matches change what this player should be asked to clear next.
        from . import cs2_baseline

        await cs2_baseline.refresh(session, chain.user_id, chain.steam_id)
        log.info(
            "cs2.chain_synced",
            user_id=str(chain.user_id),
            collected=len(collected),
        )
    return collected


async def sync_user(session: AsyncSession, user_id: uuid.UUID) -> list[Cs2Match]:
    chain = await get_chain(session, user_id)
    if chain is None:
        raise ChainNotConnected()
    return await sync(session, chain)


async def sync_all(session: AsyncSession) -> int:
    """Every active chain, for the worker. One player's failure isolates."""
    if not is_enabled():
        return 0
    chains = await session.scalars(
        select(Cs2ShareChain).where(Cs2ShareChain.state == "active")
    )
    total = 0
    for chain in chains:
        try:
            total += len(await sync(session, chain))
        except Exception as exc:  # noqa: BLE001 - one bad chain must not stop the rest
            log.warning(
                "cs2.chain_sync_failed", user_id=str(chain.user_id), error=str(exc)
            )
    return total


__all__ = [
    "ChainNotConnected",
    "MAX_CODES_PER_SYNC",
    "connect",
    "get_chain",
    "is_enabled",
    "sync",
    "sync_all",
    "sync_user",
]
