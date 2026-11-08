"""Linking request/response schemas (drives the Profile screen)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .profile import ProfileSnapshot

LinkStatus = Literal["LINKED", "BLOCKED", "UNLINKED"]


class CreateLinkRequest(BaseModel):
    """Intent to bind a host account."""

    game: str
    username: str = Field(..., min_length=1, max_length=128)


class LichessOAuthStartResponse(BaseModel):
    authorize_url: str


class LichessOAuthCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=1024)
    state: str = Field(..., min_length=1, max_length=128)


class GameLink(BaseModel):
    """One game's row on Profile: linked snapshot or an empty/blocked slot."""

    game: str
    display_name: str
    status: LinkStatus
    host_username: str | None = None
    linked_at: datetime | None = None
    profile: ProfileSnapshot | None = None
    win_streak: int = 0


class LinksResponse(BaseModel):
    """Every registered game with the viewer's link state — drives Profile."""

    games: list[GameLink]
