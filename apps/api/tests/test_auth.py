"""JWT verification, user auto-provisioning, and onboarding."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from moneymatch_api.db.session import get_sessionmaker
from moneymatch_api.models.user import User

from .conftest import auth_headers, make_token


async def _user_count() -> int:
    async with get_sessionmaker()() as session:
        return (await session.execute(select(func.count(User.id)))).scalar_one()


# --- token validity ---------------------------------------------------------


async def test_missing_authorization_rejected(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


async def test_garbage_token_rejected(client):
    resp = await client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthenticated"


async def test_expired_token_rejected(client):
    headers = auth_headers("auth-expired", exp_offset=-10)
    resp = await client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 401


async def test_wrong_secret_rejected(client):
    headers = {"Authorization": f"Bearer {make_token('a', secret='wrong-secret')}"}
    resp = await client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 401


async def test_wrong_audience_rejected(client):
    headers = {"Authorization": f"Bearer {make_token('a', audience='other')}"}
    resp = await client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 401


async def test_valid_token_accepted(client):
    resp = await client.get("/api/v1/me", headers=auth_headers("auth-valid"))
    assert resp.status_code == 200


# --- auto-provisioning ------------------------------------------------------


async def test_first_call_provisions_user(client):
    assert await _user_count() == 0
    resp = await client.get("/api/v1/me", headers=auth_headers("auth-new"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_onboarding"] is True
    assert body["user"]["username"] is None
    assert body["user"]["email"] == "player@example.com"
    assert await _user_count() == 1


async def test_second_login_reuses_row(client):
    headers = auth_headers("auth-repeat")
    first = (await client.get("/api/v1/me", headers=headers)).json()
    second = (await client.get("/api/v1/me", headers=headers)).json()
    assert first["user"]["id"] == second["user"]["id"]
    assert await _user_count() == 1


async def test_distinct_subjects_get_distinct_users(client):
    await client.get("/api/v1/me", headers=auth_headers("auth-1"))
    await client.get("/api/v1/me", headers=auth_headers("auth-2"))
    assert await _user_count() == 2


# --- onboarding -------------------------------------------------------------


async def test_onboarding_sets_identity(client):
    headers = auth_headers("auth-onboard")
    await client.get("/api/v1/me", headers=headers)
    resp = await client.patch(
        "/api/v1/me",
        headers=headers,
        json={
            "username": "kvem_",
            "residence_state": "ma",
            "dob_attested_18plus": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_onboarding"] is False
    assert body["user"]["username"] == "kvem_"
    assert body["user"]["residence_state"] == "MA"
    assert body["user"]["dob_attested_18plus"] is True


@pytest.mark.parametrize("bad", ["ab", "no", "Has Space", "toolongusername_over20x"])
async def test_onboarding_rejects_bad_username(client, bad):
    headers = auth_headers("auth-badname")
    await client.get("/api/v1/me", headers=headers)
    resp = await client.patch(
        "/api/v1/me",
        headers=headers,
        json={"username": bad, "residence_state": "MA", "dob_attested_18plus": True},
    )
    assert resp.status_code == 422


async def test_onboarding_requires_18plus(client):
    headers = auth_headers("auth-under18")
    await client.get("/api/v1/me", headers=headers)
    resp = await client.patch(
        "/api/v1/me",
        headers=headers,
        json={
            "username": "minor1",
            "residence_state": "MA",
            "dob_attested_18plus": False,
        },
    )
    assert resp.status_code == 422


async def test_username_is_immutable(client):
    headers = auth_headers("auth-immutable")
    await client.get("/api/v1/me", headers=headers)
    payload = {
        "username": "first1",
        "residence_state": "MA",
        "dob_attested_18plus": True,
    }
    assert (
        await client.patch("/api/v1/me", headers=headers, json=payload)
    ).status_code == 200
    payload["username"] = "second2"
    resp = await client.patch("/api/v1/me", headers=headers, json=payload)
    assert resp.status_code == 409
    assert resp.json()["code"] == "username_immutable"


async def test_username_uniqueness_enforced(client):
    h1 = auth_headers("auth-uniq-1")
    h2 = auth_headers("auth-uniq-2")
    await client.get("/api/v1/me", headers=h1)
    await client.get("/api/v1/me", headers=h2)
    payload = {
        "username": "dupe_1",
        "residence_state": "MA",
        "dob_attested_18plus": True,
    }
    assert (
        await client.patch("/api/v1/me", headers=h1, json=payload)
    ).status_code == 200
    resp = await client.patch("/api/v1/me", headers=h2, json=payload)
    assert resp.status_code == 409
    assert resp.json()["code"] == "username_taken"
