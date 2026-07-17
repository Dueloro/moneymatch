"""Persist host-derived evidence to the append-only `raw_payloads` table.

Every host response that feeds a profile or grading decision is retained with a
content hash, so a derived record (a linked account now; a match/entry in later
phases) can point back to the exact evidence it was computed from (audit
requirement — 01-architecture §2). Rows are immutable (append-only trigger).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.skill import RawPayload


def _canonical(payload: Any) -> str:
    """Stable JSON encoding so identical evidence hashes identically."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


async def persist(
    session: AsyncSession,
    source: str,
    payload: Any,
    *,
    memo: str | None = None,
) -> RawPayload:
    """Append a raw-payload record and return it (flushed, not committed)."""
    canonical = _canonical(payload)
    row = RawPayload(
        source=source,
        payload=payload,
        content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        size_bytes=len(canonical.encode()),
        memo=memo,
    )
    session.add(row)
    await session.flush()
    return row
