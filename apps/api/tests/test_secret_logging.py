"""Secrets must not reach the logs.

Steam takes its API key and a player's match-history authentication code as
*query parameters*, because it accepts nothing else. Any logger that prints a
full URL therefore prints both, and from stdout they reach Sentry and whatever
aggregates logs in production. This was live: the settlement worker wrote the
API key and a real auth code to stdout on every chain poll.
"""

from __future__ import annotations

import logging

import pytest

from moneymatch_api.config import get_settings
from moneymatch_api.logging import configure_logging

pytestmark = pytest.mark.nodb


@pytest.fixture(autouse=True)
def _configured():
    configure_logging(get_settings())


@pytest.mark.parametrize("name", ["httpx", "httpcore"])
def test_url_logging_libraries_are_quiet(name):
    """They log the whole URL at INFO, query string included."""
    assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


@pytest.mark.parametrize("name", ["httpx", "httpcore"])
def test_they_can_still_report_trouble(name):
    """Silencing the request log must not silence real failures."""
    assert logging.getLogger(name).isEnabledFor(logging.WARNING)
