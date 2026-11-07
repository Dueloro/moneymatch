"""Secrets must not reach the logs."""

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
    assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


@pytest.mark.parametrize("name", ["httpx", "httpcore"])
def test_they_can_still_report_trouble(name):
    assert logging.getLogger(name).isEnabledFor(logging.WARNING)
