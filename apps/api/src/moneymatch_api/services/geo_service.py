"""Geo-fence — server-side, read from `geo_config`, enforced before any escrow.

The 14 excluded ("Any Chance") states live in the admin-flippable `geo_config`
feature flag (seeded in migration 0001), **not** a code constant, so the list
changes without a deploy (07-phase-4 · geo-fence test). `assert_can_enter` runs
before a pool/tournament entry escrows a fee — a blocked resident is refused with
a clean 403 and no ledger row is ever written.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import FLAG_GEO_CONFIG
from ..errors import APIError
from ..models.feature_flag import FeatureFlag

log = structlog.get_logger(__name__)


class RegionBlockedError(APIError):
    """Residence state is geo-fenced out of real-money play (403)."""

    def __init__(self, state: str | None) -> None:
        super().__init__(
            "region_blocked",
            f"Contests are not available in {state or 'your region'}.",
            status_code=403,
            detail={"state": state},
        )


async def excluded_states(session: AsyncSession) -> set[str]:
    """The current excluded-state codes from `geo_config` (uppercased)."""
    try:
        flag = await session.scalar(
            select(FeatureFlag).where(FeatureFlag.key == FLAG_GEO_CONFIG)
        )
    except SQLAlchemyError as exc:  # fail closed: unknown geo ⇒ treat as blocked-none
        log.warning("geo_config.read_failed", error=str(exc))
        return set()
    if flag is None:
        return set()
    codes = (flag.payload or {}).get("excluded_states", [])
    return {str(c).strip().upper() for c in codes}


async def assert_can_enter(session: AsyncSession, state: str | None) -> None:
    """Raise `RegionBlockedError` if `state` is geo-fenced (before any escrow)."""
    if state is None:
        raise RegionBlockedError(state)
    if state.strip().upper() in await excluded_states(session):
        raise RegionBlockedError(state)
