"""AuthZ gate on the whole `/admin` tree."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from moneymatch_api.main import create_app
from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


def _admin_routes() -> list[tuple[str, str]]:
    schema = create_app().openapi()
    out: list[tuple[str, str]] = []
    for path, methods in schema.get("paths", {}).items():
        if "/admin" not in path:
            continue
        concrete = path
        while "{" in concrete:
            start = concrete.index("{")
            end = concrete.index("}")
            concrete = concrete[:start] + uuid.uuid4().hex + concrete[end + 1 :]
        for method in methods:
            if method.upper() in {"HEAD", "OPTIONS"}:
                continue
            out.append((method.upper(), concrete))
    return out


ADMIN_ROUTES = _admin_routes()


async def _onboard(client, auth_id: str, name: str, *, admin: bool = False):
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        if admin:
            user.role = "admin"
        await s.commit()
        return user.id


async def test_admin_routes_exist():
    assert ADMIN_ROUTES, "no /admin routes registered"


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
async def test_non_admin_forbidden(client, method, path):
    await _onboard(client, "auth_plain", "plain_user")
    r = await client.request(method, path, headers=auth_headers("auth_plain"), json={})
    assert r.status_code == 403, f"{method} {path} → {r.status_code}: {r.text}"


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
async def test_unauthenticated_rejected(client, method, path):
    r = await client.request(method, path, json={})
    assert r.status_code in (401, 403), f"{method} {path} → {r.status_code}"


async def test_admin_passes_gate(client):
    await _onboard(client, "auth_admin", "the_admin", admin=True)
    r = await client.get(f"{V1}/admin/flags", headers=auth_headers("auth_admin"))
    assert r.status_code == 200, r.text
