"""Sentry setup shared by the API and the settlement worker."""

from __future__ import annotations

import os

from .config import Settings


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=os.getenv("RENDER_GIT_COMMIT") or settings.release,
        traces_sample_rate=0.0,
        send_default_pii=True,
    )
