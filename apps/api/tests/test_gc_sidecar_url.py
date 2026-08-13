"""The sidecar's address, as deployment platforms actually hand it over.

Render exposes a private service as a bare `host:port`. httpx refuses a URL
with no scheme, so without normalising it every share code resolves to a
transport error — which surfaces as "the match service is unavailable" and no
CS2 wager settles, on a deployment where everything else looks healthy.
"""

from __future__ import annotations

import pytest

from moneymatch_api.config import get_settings
from moneymatch_api.services import gc_client

pytestmark = pytest.mark.nodb


@pytest.mark.parametrize(
    "configured,expected",
    [
        ("moneymatch-gc:10000", "http://moneymatch-gc:10000"),
        ("http://127.0.0.1:8787", "http://127.0.0.1:8787"),
        ("https://gc.internal", "https://gc.internal"),
        ("http://127.0.0.1:8787/", "http://127.0.0.1:8787"),
        ("  moneymatch-gc:10000  ", "http://moneymatch-gc:10000"),
    ],
)
def test_the_address_is_usable_however_it_was_supplied(
    monkeypatch, configured, expected
):
    settings = get_settings()
    monkeypatch.setattr(settings, "gc_sidecar_url", configured)
    assert gc_client._base_url() == expected


def test_an_explicit_scheme_is_never_rewritten():
    """Only the missing case is filled in; https must survive untouched."""
    settings = get_settings()
    original = settings.gc_sidecar_url
    try:
        settings.gc_sidecar_url = "https://gc.internal:9000"
        assert gc_client._base_url().startswith("https://")
    finally:
        settings.gc_sidecar_url = original
