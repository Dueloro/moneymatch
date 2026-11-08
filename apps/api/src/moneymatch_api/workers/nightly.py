"""The worker's nightly pass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..constants import GAME_RATE_METRICS
from ..models.linked_account import LinkedAccount
from ..models.user import User
from ..services import metric_models_service, risk_detectors, sandbagging_service

log = structlog.get_logger(__name__)


@dataclass
class NightlyReport:
    accounts_refreshed: int = 0
    sandbag_flags: int = 0
    win_streak_flags: int = 0
    pair_cap_flags: int = 0
    errors: int = 0


async def _refresh_account(session: AsyncSession, link: LinkedAccount) -> int:
    await metric_models_service.bootstrap(
        session, link.user_id, link.game, link.host_account_id
    )
    flags = 0
    metrics = GAME_RATE_METRICS.get(link.game, ())
    if metrics:
        user = await session.get(User, link.user_id)
        if user is not None:
            for metric in metrics:
                flag = await sandbagging_service.evaluate(
                    session, user, link.game, metric, link.host_account_id
                )
                if flag is not None:
                    flags += 1
    return flags


async def run_nightly(
    sm: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> NightlyReport:
    report = NightlyReport()

    async with sm() as session:
        link_ids = list(
            await session.scalars(
                select(LinkedAccount.id).where(LinkedAccount.status != "unbound")
            )
        )

    for link_id in link_ids:
        async with sm() as session:
            link = await session.get(LinkedAccount, link_id)
            if link is None:
                continue
            try:
                report.sandbag_flags += await _refresh_account(session, link)
                await session.commit()
                report.accounts_refreshed += 1
            except Exception:  # noqa: BLE001 — one bad account can't stop the pass
                await session.rollback()
                report.errors += 1
                log.exception("nightly.account_failed", link_id=str(link_id))

    async with sm() as session:
        try:
            report.win_streak_flags = await risk_detectors.detect_win_streaks(session)
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("nightly.win_streak_failed")

    async with sm() as session:
        try:
            report.pair_cap_flags = await risk_detectors.detect_pair_cap_breaches(
                session
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
            log.exception("nightly.pair_cap_failed")

    log.info("nightly.complete", **report.__dict__)
    return report
