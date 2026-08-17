"""Geo-fence — server-side, read from `geo_config`, enforced before any escrow.

The 14 excluded ("Any Chance") states live in the admin-flippable `geo_config`
feature flag (seeded in migration 0001), **not** a code constant, so the list
changes without a deploy (07-phase-4 · geo-fence test). `assert_can_enter` runs
before a pool/tournament entry escrows a fee — a blocked resident is refused with
a clean 403 and no ledger row is ever written.

**This module fails closed, and that is load-bearing.** It previously did not:
an unreadable database, a missing flag row, a missing key, or an empty list each
returned an empty set, and an empty set excludes nobody — so on a fresh database
every state was allowed while an inline comment claimed the opposite.

The distinction the code now makes is between:

- *"these states are excluded"* — a configured, non-empty list, and
- *"we do not know which states are excluded"* — everything else.

The second is not the same as "none are excluded". The only safe answer to
"may this person stake money?" when the configuration is unreadable is **no**.
An empty list is treated as unconfigured rather than as a deliberate "nowhere is
excluded", because there is no legitimate reason to run a real-money product
with the geo-fence deliberately empty, and the failure mode of guessing wrong is
regulatory rather than cosmetic.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import FLAG_GEO_CONFIG, GEO_REQUIRED_EXCLUDED_STATES
from ..errors import APIError
from ..models.feature_flag import FeatureFlag

log = structlog.get_logger(__name__)


class GeoFenceMisconfigured(RuntimeError):
    """The production geo-fence is absent or smaller than its required floor.

    Raised at startup only. A refused boot is a failed deploy — loud, and cheap
    to fix. Booting with a hole in the geo-fence is neither: nothing errors, and
    the first symptom is a stake taken from someone who should have been
    refused.
    """


class RegionBlockedError(APIError):
    """Residence state is geo-fenced out of real-money play (403)."""

    def __init__(self, state: str | None) -> None:
        super().__init__(
            "region_blocked",
            f"Contests are not available in {state or 'your region'}.",
            status_code=403,
            detail={"state": state},
        )


async def load_excluded_states(session: AsyncSession) -> set[str] | None:
    """The configured exclusions, or ``None`` when configuration is unavailable.

    ``None`` is returned — and callers must treat it as "block" — when the flag
    row is missing, the payload is null, the `excluded_states` key is absent,
    the value is not a list, the list contains anything that is not a non-empty
    string, or the list is empty. Also when the read itself fails.

    Returning a set and returning ``None`` are different answers. Collapsing
    them into "empty set" is precisely the bug this module used to have.
    """
    try:
        flag = await session.scalar(
            select(FeatureFlag).where(FeatureFlag.key == FLAG_GEO_CONFIG)
        )
    except SQLAlchemyError as exc:
        # Fail closed. We cannot tell whether this player is permitted, so we
        # must not let them stake.
        log.error("geo_config.read_failed", error=str(exc))
        return None

    if flag is None:
        log.error("geo_config.missing")
        return None

    payload = flag.payload
    if not isinstance(payload, dict):
        log.error("geo_config.malformed", reason="payload is not an object")
        return None

    if "excluded_states" not in payload:
        log.error("geo_config.malformed", reason="excluded_states key absent")
        return None

    codes = payload["excluded_states"]
    if not isinstance(codes, list):
        log.error("geo_config.malformed", reason="excluded_states is not a list")
        return None

    cleaned: set[str] = set()
    for code in codes:
        if not isinstance(code, str) or not code.strip():
            log.error("geo_config.malformed", reason="non-string or empty code")
            return None
        cleaned.add(code.strip().upper())

    if not cleaned:
        # An empty list is "unconfigured", not "nowhere is excluded".
        log.error("geo_config.empty")
        return None

    return cleaned


async def excluded_states(session: AsyncSession) -> set[str]:
    """Read-only view of the exclusion list, for admin surfaces.

    **An empty set from this function means "unconfigured", not "nothing is
    excluded".** Never gate a stake on this — use `assert_can_enter`, which
    distinguishes the two.
    """
    return await load_excluded_states(session) or set()


async def assert_can_enter(session: AsyncSession, state: str | None) -> None:
    """Raise `RegionBlockedError` if `state` is geo-fenced (before any escrow).

    Refuses when the state is unknown *or* when the exclusion list cannot be
    established. Both are "we cannot prove this is allowed".
    """
    if state is None:
        raise RegionBlockedError(state)

    configured = await load_excluded_states(session)
    if configured is None:
        log.error("geo.blocked_on_unavailable_config", state=state)
        raise RegionBlockedError(state)

    if state.strip().upper() in configured:
        raise RegionBlockedError(state)


async def assert_configured_for_production(session: AsyncSession) -> None:
    """Refuse to boot a production deploy whose geo-fence is missing or holed.

    Called from the app lifespan when `ENV=prod`. Not called otherwise: local
    and dev databases are routinely reset, and failing their boot on a seed row
    would be noise rather than signal.
    """
    configured = await load_excluded_states(session)
    if configured is None:
        raise GeoFenceMisconfigured(
            "geo_config is missing, empty, malformed or unreadable with ENV=prod. "
            "Seed the geo_config feature flag before deploying: migration 0001 "
            f"seeds the required {len(GEO_REQUIRED_EXCLUDED_STATES)} states."
        )

    missing = GEO_REQUIRED_EXCLUDED_STATES - configured
    if missing:
        raise GeoFenceMisconfigured(
            f"geo_config is missing required excluded states: {sorted(missing)}. "
            "With ENV=prod the fence may be widened but not dropped below the "
            "seeded floor (see constants.GEO_REQUIRED_EXCLUDED_STATES)."
        )

    log.info("geo.fence_verified", excluded_count=len(configured))
