"""Chat wire types — conversations, messages, and invite cards.

Requests carry **ids, a body, and a preset choice only** (00-README §3): the
server owns entry cents, timestamps, invite state, and every derived label.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ..models.chat import MAX_MESSAGE_CHARS

# --- reads ---------------------------------------------------------------- #


class MessageView(BaseModel):
    """One rendered message. `payload` is populated for invite cards only."""

    id: UUID
    conversation_id: UUID
    sender_id: UUID | None  # null = platform-authored (support / system line)
    sender_username: str | None
    mine: bool  # the caller wrote it → right-aligned bubble
    kind: str  # text | invite | system
    body: str | None
    payload: dict
    created_at: datetime


class ConversationView(BaseModel):
    """A row in the conversation list (and the header of an open thread)."""

    id: UUID
    kind: str  # dm | support
    title: str
    peer_user_id: UUID | None  # null for the support thread
    peer_username: str | None
    online: bool  # peer presence dot (always true for support)
    unread: int
    last_message_at: datetime | None
    last_message_preview: str | None


class ConversationsResponse(BaseModel):
    unread_total: int
    conversations: list[ConversationView]


class ThreadResponse(BaseModel):
    conversation: ConversationView
    messages: list[MessageView]  # oldest → newest


# --- writes --------------------------------------------------------------- #


class OpenConversationRequest(BaseModel):
    """Open (or reopen) a thread: a friend's `user_id` for a DM, or
    `kind='support'` for the support thread."""

    user_id: UUID | None = None
    kind: str = "dm"


class InviteDraft(BaseModel):
    """The client's half of an invite card. Entry is a preset choice — the
    server validates it against the offered presets and owns the cents."""

    invite_kind: str  # pool | tournament
    game: str
    entry_preset_cents: int
    metric: str | None = None
    difficulty: str | None = None


class SendMessageRequest(BaseModel):
    """Either a typed line or an invite card (exactly one of the two)."""

    body: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    invite: InviteDraft | None = None


class RespondInviteRequest(BaseModel):
    action: str  # accept | decline


class RespondInviteResponse(BaseModel):
    message: MessageView
    # Set when accepting a head-to-head invite formed a PENDING match.
    match_id: UUID | None = None
    # Where the client should go to act on the invite (e.g. /pools).
    redirect_path: str | None = None


class ChatReadResponse(BaseModel):
    """Named apart from the notifications mark-read so the two never collide in
    the generated OpenAPI component map."""

    unread_total: int
