"""Feature flags (00-README §3.10).

Admin-flippable without a deploy. `payload` carries structured config for
non-boolean flags (e.g. `geo_config` holds the excluded-state list).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
