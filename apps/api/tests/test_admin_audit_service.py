"""The admin audit write path (09-phase-6 · deliverable 1)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.models.admin_audit import AdminAudit
from moneymatch_api.services import admin_audit_service

from . import factories

pytestmark = pytest.mark.asyncio


async def test_record_writes_a_row(session):
    admin = await factories.create_user(session, username="auditor")
    row = await admin_audit_service.record(
        session,
        admin_id=admin.id,
        action="user.freeze",
        target="someuser",
        detail={"reason": "test"},
    )
    fetched = await session.scalar(select(AdminAudit).where(AdminAudit.id == row.id))
    assert fetched is not None
    assert fetched.admin_id == admin.id
    assert fetched.action == "user.freeze"
    assert fetched.target == "someuser"
    assert fetched.detail == {"reason": "test"}
