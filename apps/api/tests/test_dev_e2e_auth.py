"""The dev/e2e sign-in bypass (backlog · "Browser e2e test-auth seam").

The `/dev/e2e/token` route is mounted only when `e2e_auth_enabled` and env != prod,
and the token it mints must be accepted by the same verification path as a real
Supabase JWT — proving Playwright can authenticate seeded users without a live
Supabase project.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from moneymatch_api.auth import verify_token
from moneymatch_api.config import Settings, get_settings
from moneymatch_api.main import create_app

from .conftest import TEST_DB_URL, TEST_JWT_SECRET, auth_headers


def _settings(**overrides) -> Settings:
    base = dict(
        env="local",
        database_url=TEST_DB_URL,
        supabase_url="https://test-project.supabase.co",
        supabase_jwt_secret=TEST_JWT_SECRET,
        supabase_jwt_audience="authenticated",
    )
    base.update(overrides)
    return Settings(**base)


def _app_with(settings: Settings):
    """Build an app whose handlers resolve `settings` (prod uses the cached
    get_settings; tests pin it so mount + handler agree)."""
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


async def test_token_route_absent_when_disabled(client):
    """Default app (e2e_auth_enabled=False) does not expose the route at all."""
    resp = await client.post("/api/v1/dev/e2e/token", json={"auth_id": "x"})
    assert resp.status_code == 404


async def test_minted_token_verifies_and_authenticates():
    app = _app_with(_settings(e2e_auth_enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/dev/e2e/token",
            json={"auth_id": "seed_player1", "email": "p1@demo.test"},
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        # The minted token authenticates a real API call (provisions the user).
        me = await c.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200

    # And it verifies through the exact production auth path.
    identity = verify_token(token, _settings(e2e_auth_enabled=True))
    assert identity.auth_id == "seed_player1"
    assert identity.email == "p1@demo.test"


async def test_route_refuses_in_prod_even_if_enabled():
    # Guard is defense-in-depth: even a stray prod mount must not mint tokens.
    app = _app_with(_settings(env="prod", e2e_auth_enabled=True))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/dev/e2e/token", json={"auth_id": "seed_x"})
        assert resp.status_code == 404


async def test_seeded_token_matches_conftest_secret():
    """Sanity: a token minted here is interchangeable with conftest's own mint."""
    real = auth_headers("seed_player2")
    assert real["Authorization"].startswith("Bearer ")
