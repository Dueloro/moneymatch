"""Geo-fence — server-side, read from `geo_config`, enforced before any escrow."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..constants import FLAG_GEO_CONFIG, GEO_REQUIRED_EXCLUDED_STATES
from ..errors import APIError
from ..models.feature_flag import FeatureFlag

log = structlog.get_logger(__name__)


class GeoFenceMisconfigured(RuntimeError):
    """The production geo-fence is absent or smaller than its required floor."""


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
    """The configured exclusions, or ``None`` when configuration is unavailable."""
    try:
        flag = await session.scalar(
            select(FeatureFlag).where(FeatureFlag.key == FLAG_GEO_CONFIG)
        )
    except SQLAlchemyError as exc:
        # Fail closed.
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
        log.error("geo_config.empty")
        return None

    return cleaned


async def excluded_states(session: AsyncSession) -> set[str]:
    return await load_excluded_states(session) or set()


async def assert_can_enter(session: AsyncSession, state: str | None) -> None:
    """Raise `RegionBlockedError` if `state` is geo-fenced (before any escrow)."""
    if state is None:
        raise RegionBlockedError(state)

    configured = await load_excluded_states(session)
    if configured is None:
        log.error("geo.blocked_on_unavailable_config", state=state)
        raise RegionBlockedError(state)

    if state.strip().upper() in configured:
        raise RegionBlockedError(state)


async def assert_configured_for_production(
    session: AsyncSession, *, enforce_floor: bool | None = None
) -> None:
    """Refuse to boot a production deploy whose geo-fence is missing or holed."""
    if enforce_floor is None:
        enforce_floor = get_settings().geo_enforce_seeded_floor

    configured = await load_excluded_states(session)
    if configured is None:
        raise GeoFenceMisconfigured(
            "geo_config is missing, empty, malformed or unreadable with ENV=prod. "
            "Seed the geo_config feature flag before deploying: migration 0001 "
            f"seeds the required {len(GEO_REQUIRED_EXCLUDED_STATES)} states."
        )

    if not enforce_floor:
        log.warning(
            "geo.seeded_floor_check_disabled",
            excluded_count=len(configured),
            missing=sorted(GEO_REQUIRED_EXCLUDED_STATES - configured),
        )
        return

    missing = GEO_REQUIRED_EXCLUDED_STATES - configured
    if missing:
        raise GeoFenceMisconfigured(
            f"geo_config is missing required excluded states: {sorted(missing)}. "
            "With ENV=prod the fence may be widened but not dropped below the "
            "seeded floor (see constants.GEO_REQUIRED_EXCLUDED_STATES). If that "
            "floor is deliberately being lowered, set "
            "GEO_ENFORCE_SEEDED_FLOOR=false — and record why."
        )

    log.info("geo.fence_verified", excluded_count=len(configured))
