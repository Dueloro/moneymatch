"""/config serves the values the web app used to hard-code."""

from __future__ import annotations

from moneymatch_api.constants import GEO_REQUIRED_EXCLUDED_STATES
from moneymatch_api.models.wallet import DEMO_DEPOSIT_PRESETS_CENTS
from moneymatch_api.services import money_math


async def test_config_is_public_and_matches_the_server(client):
    r = await client.get("/api/v1/config")
    assert r.status_code == 200
    body = r.json()
    assert set(body["excluded_states"]) == set(GEO_REQUIRED_EXCLUDED_STATES)
    assert body["rake_bps"] == money_math.DEFAULT_RAKE_BPS
    assert body["deposit_presets_cents"] == list(DEMO_DEPOSIT_PRESETS_CENTS)
