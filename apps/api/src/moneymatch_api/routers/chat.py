"""`/chat` — friend DMs, the support thread, and invite cards.

Reading any chat surface bumps the presence heartbeat (it's a polled surface,
like friends and notifications). Every write is an intent: the server owns
message timestamps, invite state, and match formation.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..dependencies import CurrentUser
from ..models.chat import Conversation, Message
from ..models.user import User
from ..schemas.chat import (
    ChatReadResponse,
    ConversationsResponse,
    ConversationView,
    MessageView,
    OpenConversationRequest,
    RespondInviteRequest,
    RespondInviteResponse,
    SendMessageRequest,
    ThreadResponse,
)
from ..services import chat_service, friends_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _conversation_view(row: chat_service.ConversationRow) -> ConversationView:
    conversation = row.conversation
    return ConversationView(
        id=conversation.id,
        kind=conversation.kind,
        title=row.title,
        peer_user_id=row.peer.id if row.peer else None,
        peer_username=row.peer.username if row.peer else None,
        # Support is always "on" — a person answers it, just not instantly.
        online=(
            True
            if conversation.kind == "support"
            else friends_service.is_online(row.peer.last_seen_at if row.peer else None)
        ),
        unread=row.unread,
        last_message_at=conversation.last_message_at,
        last_message_preview=chat_service.preview_of(row.last_message),
    )


def _message_view(
    message: Message, *, user: User, names: dict[UUID, str | None]
) -> MessageView:
    return MessageView(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_username=names.get(message.sender_id) if message.sender_id else None,
        mine=message.sender_id == user.id,
        kind=message.kind,
        body=message.body,
        payload=message.payload,
        created_at=message.created_at,
    )


async def _thread(
    session: AsyncSession, user: User, conversation_id: UUID
) -> ThreadResponse:
    row = await chat_service.get_conversation_row(session, user, conversation_id)
    messages = await chat_service.list_messages(session, user, conversation_id)
    names = await chat_service.sender_names(session, messages)
    return ThreadResponse(
        conversation=_conversation_view(row),
        messages=[_message_view(m, user=user, names=names) for m in messages],
    )


@router.get("/conversations", response_model=ConversationsResponse)
async def list_conversations(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> ConversationsResponse:
    await friends_service.heartbeat(session, user)
    rows = await chat_service.list_conversations(session, user)
    return ConversationsResponse(
        unread_total=sum(r.unread for r in rows),
        conversations=[_conversation_view(r) for r in rows],
    )


@router.post("/conversations", response_model=ConversationView)
async def open_conversation(
    body: OpenConversationRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ConversationView:
    """Get-or-create a thread: a friend DM (`user_id`) or support (`kind`)."""
    if body.kind == "support":
        conversation: Conversation = await chat_service.open_support(session, user)
    else:
        if body.user_id is None:
            raise chat_service.ChatError(
                "user_required", "Pick a friend to message.", status_code=422
            )
        conversation = await chat_service.open_dm(session, user, body.user_id)
    row = await chat_service.get_conversation_row(session, user, conversation.id)
    return _conversation_view(row)


@router.get("/conversations/{conversation_id}", response_model=ThreadResponse)
async def get_thread(
    conversation_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ThreadResponse:
    await friends_service.heartbeat(session, user)
    return await _thread(session, user, conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=ThreadResponse)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ThreadResponse:
    """Post a typed line or an invite card, and return the refreshed thread."""
    if (body.body is None) == (body.invite is None):
        raise chat_service.ChatError(
            "invalid_message",
            "Send either a message or an invite.",
            status_code=422,
        )
    if body.invite is not None:
        await chat_service.send_invite(
            session,
            user,
            conversation_id,
            invite_kind=body.invite.invite_kind,
            game=body.invite.game,
            entry_preset_cents=body.invite.entry_preset_cents,
            metric=body.invite.metric,
            difficulty=body.invite.difficulty,
        )
    else:
        await chat_service.send_text(session, user, conversation_id, body.body or "")
    # Sending is also reading — don't badge the sender for their own thread.
    await chat_service.mark_read(session, user, conversation_id)
    return await _thread(session, user, conversation_id)


@router.post("/conversations/{conversation_id}/read", response_model=ChatReadResponse)
async def mark_read(
    conversation_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ChatReadResponse:
    unread = await chat_service.mark_read(session, user, conversation_id)
    return ChatReadResponse(unread_total=unread)


@router.post("/messages/{message_id}/respond", response_model=RespondInviteResponse)
async def respond_invite(
    message_id: UUID,
    body: RespondInviteRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> RespondInviteResponse:
    """Accept or decline an invite card. Accepting a head-to-head forms a PENDING
    match (same lifecycle as the Inbox Respond pill)."""
    message, match_id = await chat_service.respond_invite(
        session, user, message_id, body.action
    )
    names = await chat_service.sender_names(session, [message])
    redirect = message.payload.get("redirect_path") if body.action == "accept" else None
    return RespondInviteResponse(
        message=_message_view(message, user=user, names=names),
        match_id=match_id,
        redirect_path=redirect,
    )
