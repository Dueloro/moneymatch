"""What the API is allowed to hand back to a browser.

The chain endpoints take two secrets — a Steam authentication code that reads a
player's match history, and the share code cursor. Neither has any reason to
come back out. This pins that: a status endpoint reports whether a chain is
connected, not what it was connected with.
"""

from __future__ import annotations

import pytest

from moneymatch_api.routers.cs2 import ChainStatusResponse

pytestmark = pytest.mark.nodb

#: Anything whose presence in a response body would be a leak.
FORBIDDEN = {"auth_code", "authcode", "steamidkey", "api_key", "secret", "token"}


def test_chain_status_cannot_return_the_auth_code():
    fields = set(ChainStatusResponse.model_fields)
    assert not (fields & FORBIDDEN), fields & FORBIDDEN


def test_chain_status_reports_connection_not_credentials():
    """It answers 'is this working', which is all a UI needs to render."""
    assert "connected" in ChainStatusResponse.model_fields
    assert "state" in ChainStatusResponse.model_fields


def test_the_model_has_not_quietly_grown_a_secret_field():
    """A regression guard: adding a field is easy, noticing it leaks is not."""
    assert set(ChainStatusResponse.model_fields) == {
        "connected",
        "state",
        "last_error",
        "last_polled_at",
        "last_code_at",
    }
