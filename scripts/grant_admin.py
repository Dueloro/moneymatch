#!/usr/bin/env python
"""Grant (or revoke) the `admin` role on a user — the only way in (09-phase-6 · d.1).

Run in the API venv so `moneymatch_api` and `DATABASE_URL` resolve:

    cd apps/api && uv run python ../../scripts/grant_admin.py <username>
    cd apps/api && uv run python ../../scripts/grant_admin.py <username> --revoke

The change is audited (`admin_audit`, action `role.grant` / `role.revoke`) in the
same transaction as the role update, so there is no unaudited path to admin.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make `moneymatch_api` importable when run from the repo root or apps/api.
_API_SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from moneymatch_api.db.session import (  # noqa: E402
    dispose_engine,
    get_sessionmaker,
)
from moneymatch_api.services import (  # noqa: E402
    admin_audit_service,
    admin_service,
)


async def _run(username: str, *, revoke: bool) -> int:
    role = "user" if revoke else "admin"
    action = "role.revoke" if revoke else "role.grant"
    sm = get_sessionmaker()
    try:
        async with sm() as session:
            user = await admin_service.get_user_by_username(session, username)
            if user is None:
                print(f"error: no user with username {username!r}", file=sys.stderr)
                return 1
            await admin_service.set_role(session, user, role)
            # Self-audited: the acted-on user is the audit subject (bootstraps the
            # first admin, where no other admin exists yet).
            await admin_audit_service.record(
                session,
                admin_id=user.id,
                action=action,
                target=username,
                detail={"role": role, "via": "scripts/grant_admin.py"},
            )
            await session.commit()
        print(f"ok: {username} role -> {role}")
        return 0
    finally:
        # Dispose inside this loop so pooled connections close cleanly.
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant/revoke the admin role.")
    parser.add_argument("username", help="target user's username")
    parser.add_argument(
        "--revoke", action="store_true", help="revoke admin (set role back to user)"
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.username, revoke=args.revoke))


if __name__ == "__main__":
    raise SystemExit(main())
