"""Wallet + limits + self-exclude HTTP endpoints."""

from __future__ import annotations

from .conftest import auth_headers


async def test_get_wallet_shows_signup_grant(client):
    r = await client.get("/api/v1/wallet", headers=auth_headers("w1"))
    assert r.status_code == 200
    body = r.json()
    assert body["available_cents"] == 100_000
    assert body["escrow_cents"] == 0
    assert len(body["recent"]) == 1
    assert body["recent"][0]["memo"] == "signup grant"


async def test_demo_deposit_preset_round_trips(client):
    r = await client.post(
        "/api/v1/wallet/demo-deposit",
        headers=auth_headers("w2"),
        json={"amount_preset_cents": 2500},
    )
    assert r.status_code == 200
    assert r.json()["available_cents"] == 102_500


async def test_demo_deposit_rejects_non_preset(client):
    r = await client.post(
        "/api/v1/wallet/demo-deposit",
        headers=auth_headers("w3"),
        json={"amount_preset_cents": 1234},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_deposit_preset"


async def test_demo_withdrawal_bounded_by_available(client):
    ok = await client.post(
        "/api/v1/wallet/demo-withdrawal",
        headers=auth_headers("w4"),
        json={"amount_cents": 40_000},
    )
    assert ok.status_code == 200
    assert ok.json()["available_cents"] == 60_000

    over = await client.post(
        "/api/v1/wallet/demo-withdrawal",
        headers=auth_headers("w4"),
        json={"amount_cents": 100_000},
    )
    assert over.status_code == 422
    assert over.json()["code"] == "insufficient_funds"


async def test_demo_withdrawal_velocity_capped(client):
    h = auth_headers("w5")
    for _ in range(5):
        r = await client.post(
            "/api/v1/wallet/demo-withdrawal", headers=h, json={"amount_cents": 1_00}
        )
        assert r.status_code == 200
    sixth = await client.post(
        "/api/v1/wallet/demo-withdrawal", headers=h, json={"amount_cents": 1_00}
    )
    assert sixth.status_code == 429
    assert sixth.json()["code"] == "withdrawal_velocity_exceeded"


async def test_ledger_pagination_walks_all_rows(client):
    h = auth_headers("w6")
    # 1 grant + 25 deposits = 26 rows → 2 pages of 20/6.
    for _ in range(25):
        await client.post(
            "/api/v1/wallet/demo-deposit", headers=h, json={"amount_preset_cents": 1000}
        )

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        url = "/api/v1/wallet/ledger" + (f"?cursor={cursor}" if cursor else "")
        r = await client.get(url, headers=h)
        assert r.status_code == 200
        body = r.json()
        seen.extend(e["id"] for e in body["entries"])
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert pages == 2
    assert len(seen) == 26
    assert len(set(seen)) == 26  # no duplicates or gaps across the cursor


async def test_bad_cursor_is_422(client):
    r = await client.get(
        "/api/v1/wallet/ledger?cursor=not-a-cursor", headers=auth_headers("w7")
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_cursor"


# --------------------------------------------------------------------------- #
# Limits + self-exclude via /me
# --------------------------------------------------------------------------- #


async def _onboard(client, sub):
    return await client.patch(
        "/api/v1/me",
        headers=auth_headers(sub),
        json={
            "username": f"user_{sub}",
            "residence_state": "MA",
            "dob_attested_18plus": True,
        },
    )


async def test_lowering_loss_cap_is_instant(client):
    await _onboard(client, "lim1")
    r = await client.patch(
        "/api/v1/me",
        headers=auth_headers("lim1"),
        json={"daily_loss_cap_cents": 5_000},
    )
    assert r.status_code == 200
    limits = r.json()["limits"]
    assert limits["daily_loss_cap_cents"] == 5_000  # applied now
    assert limits["pending_limits"] is None


async def test_raising_loss_cap_is_deferred(client):
    await _onboard(client, "lim2")
    r = await client.patch(
        "/api/v1/me",
        headers=auth_headers("lim2"),
        json={"daily_loss_cap_cents": 40_000},
    )
    assert r.status_code == 200
    limits = r.json()["limits"]
    assert limits["daily_loss_cap_cents"] == 20_000  # unchanged until cooldown
    assert limits["pending_limits"]["daily_loss_cap_cents"] == 40_000
    assert limits["pending_effective_at"] is not None


async def test_self_exclude_freezes_account(client):
    await _onboard(client, "ex1")
    r = await client.post("/api/v1/me/self-exclude", headers=auth_headers("ex1"))
    assert r.status_code == 200
    assert r.json()["user"]["status"] == "self_excluded"
