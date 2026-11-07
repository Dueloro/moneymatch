"""Secrets must not reach the logs.

A host API that takes a key as a query parameter leaks it through any logger
that prints a full URL, and from stdout it reaches Sentry and log aggregation.
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
