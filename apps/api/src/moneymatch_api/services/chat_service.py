"""Chat — friend DMs, the support thread, and invite cards inside a thread.

The Inbox's messaging surface. Three things live here:

- **Threads.** A DM is get-or-created per *accepted friend pair* (never with a
  stranger — same rule the direct-challenge flow enforces); the support thread is
  get-or-created per user and answered by the platform (`sender_id IS NULL`).
- **Messages.** A typed line (`text`), a platform line (`system`), or an
  **invite card** (`invite`) whose whole contract lives in `payload`.
- **Invites.** A head-to-head invite wraps a real `challenges` row, so accepting
  it in chat forms a PENDING match through the same lifecycle as the Inbox's
  Respond pill. Pool/tournament invites are a nudge: accepting stamps the card
  and hands the client the tab to open (the rooms themselves are joined there).

Flushes, never commits — the caller owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..adapters import registry
from ..constants import ENTRY_PRESETS_CENTS, metric_label
from ..errors import APIError
from ..models.chat import (
    INVITE_KINDS,
    MAX_MESSAGE_CHARS,
    Conversation,
    ConversationMember,
    Message,
)
from ..models.user import User
from . import friends_service, push_service

log = structlog.get_logger(__name__)

SUPPORT_TITLE = "MoneyMatch Support"
SUPPORT_GREETING = (
    "Hey — this is MoneyMatch Support. Ask us anything about a contest, a "
    "payout, or your account and we'll pick it up here."
)
# Support is staffed asynchronously; the auto-ack sets the expectation instead of
# leaving a message sitting in silence.
SUPPORT_AUTO_REPLY = (
    "Thanks — we've got your message. An agent picks this up within a few hours "
    "and replies right in this thread."
)

# Where each invite kind sends the client once it's accepted.
_INVITE_REDIRECT = {
    "pool": "/pools",
    "tournament": "/tournament",
    "h2h": "/play",
}

_MESSAGE_LIMIT = 200


class ChatError(APIError):
    """A chat-flow failure (RFC-7807 via APIError)."""


# --------------------------------------------------------------------------- #
# Threads.
# --------------------------------------------------------------------------- #


async def _find_dm(
    session: AsyncSession, a: uuid.UUID, b: uuid.UUID
) -> Conversation | None:
    ma = aliased(ConversationMember)
    mb = aliased(ConversationMember)
    return await session.scalar(
        select(Conversation)
        .join(ma, ma.conversation_id == Conversation.id)
        .join(mb, mb.conversation_id == Conversation.id)
        .where(Conversation.kind == "dm", ma.user_id == a, mb.user_id == b)
        .limit(1)
    )


async def _open_dm(session: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> Conversation:
    """Get-or-create the DM between two users. Callers own authorization."""
    existing = await _find_dm(session, a, b)
    if existing is not None:
        return existing
    conversation = Conversation(kind="dm")
    session.add(conversation)
    await session.flush()
    session.add_all(
        [
            ConversationMember(conversation_id=conversation.id, user_id=a),
            ConversationMember(conversation_id=conversation.id, user_id=b),
        ]
    )
    await session.flush()
    log.info("chat.dm_opened", conversation_id=str(conversation.id))
    return conversation


async def open_dm(
    session: AsyncSession, user: User, other_id: uuid.UUID
) -> Conversation:
    """Open the DM with a friend. Messaging follows friendship, exactly like the
    direct-challenge rule — strangers can't start a thread."""
    if other_id == user.id:
        raise ChatError(
            "self_conversation", "You can't message yourself.", status_code=422
        )
    other = await session.get(User, other_id)
    if other is None:
        raise ChatError("user_not_found", "No such player.", status_code=404)
    if not await friends_service.are_friends(session, user.id, other_id):
        raise ChatError("not_friends", "You can only message friends.", status_code=403)
    return await _open_dm(session, user.id, other_id)


async def open_support(session: AsyncSession, user: User) -> Conversation:
    """Get-or-create this user's support thread, greeting included."""
    existing = await session.scalar(
        select(Conversation)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(Conversation.kind == "support", ConversationMember.user_id == user.id)
        .limit(1)
    )
    if existing is not None:
        return existing

    conversation = Conversation(kind="support", subject=SUPPORT_TITLE)
    session.add(conversation)
    await session.flush()
    session.add(ConversationMember(conversation_id=conversation.id, user_id=user.id))
    await _append(
        session, conversation, sender_id=None, kind="system", body=SUPPORT_GREETING
    )
    log.info("chat.support_opened", conversation_id=str(conversation.id))
    return conversation


async def _peer_id(
    session: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    """The other member of a DM (None for the support thread)."""
    return await session.scalar(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != user_id,
        )
    )


async def _membership(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationMember:
    member = await session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
    )
    if member is None:
        raise ChatError(
            "conversation_not_found", "No such conversation.", status_code=404
        )
    return member


# --------------------------------------------------------------------------- #
# Writes.
# --------------------------------------------------------------------------- #


async def _assert_writable(
    session: AsyncSession, user: User, conversation: Conversation
) -> uuid.UUID | None:
    """Guard a write into a thread, returning the DM peer.

    Messaging follows friendship for the life of the thread, not just at its
    creation: removing or blocking someone closes the thread to new messages
    from both sides. The transcript stays readable — only writes are gated.
    """
    if conversation.kind != "dm":
        return None
    peer_id = await _peer_id(session, conversation.id, user.id)
    if peer_id is None:  # pragma: no cover — a dm always has two members
        return None
    if not await friends_service.are_friends(session, user.id, peer_id):
        raise ChatError(
            "not_friends",
            "You're no longer friends with this player, so this thread is closed.",
            status_code=403,
        )
    return peer_id


async def _push_to_peer(
    session: AsyncSession,
    conversation: Conversation,
    *,
    peer_id: uuid.UUID | None,
    sender: User,
    preview: str,
) -> None:
    """Browser-push a DM to the recipient **only when they're not in the app**.

    An online peer's Inbox polls every 15 s and badges on its own; pushing at
    them as well is noise. Best-effort — a push failure must never fail a send.
    """
    if conversation.kind != "dm" or peer_id is None:
        return
    try:
        peer = await session.get(User, peer_id)
        if peer is None or friends_service.is_online(peer.last_seen_at):
            return
        await push_service.send_to_user(
            session,
            peer_id,
            title=sender.username or "New message",
            body=preview[:120],
            url=f"/social?tab=inbox&dm={sender.id}",
        )
    except Exception as exc:  # noqa: BLE001 — never break the send
        log.warning(
            "chat.push_failed", conversation_id=str(conversation.id), error=str(exc)
        )


async def _append(
    session: AsyncSession,
    conversation: Conversation,
    *,
    sender_id: uuid.UUID | None,
    kind: str,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        sender_id=sender_id,
        kind=kind,
        body=body,
        payload=payload or {},
    )
    session.add(message)
    await session.flush()
    # Denormalized so the conversation list sorts without touching `messages`.
    conversation.last_message_at = message.created_at
    await session.flush()
    return message


async def send_text(
    session: AsyncSession, user: User, conversation_id: uuid.UUID, body: str
) -> Message:
    """Post a typed line. A support thread auto-acks so the sender isn't left
    staring at silence."""
    await _membership(session, user.id, conversation_id)
    text = body.strip()
    if not text:
        raise ChatError("empty_message", "Write something first.", status_code=422)
    if len(text) > MAX_MESSAGE_CHARS:
        raise ChatError(
            "message_too_long",
            f"Messages are capped at {MAX_MESSAGE_CHARS} characters.",
            status_code=422,
        )
    conversation = await session.get(Conversation, conversation_id)
    assert conversation is not None  # membership implies the row exists
    peer_id = await _assert_writable(session, user, conversation)
    message = await _append(
        session, conversation, sender_id=user.id, kind="text", body=text
    )
    if conversation.kind == "support":
        await _append(
            session,
            conversation,
            sender_id=None,
            kind="system",
            body=SUPPORT_AUTO_REPLY,
        )
    await _push_to_peer(
        session, conversation, peer_id=peer_id, sender=user, preview=text
    )
    return message


def invite_title(payload: dict[str, Any]) -> str:
    """Human label for an invite card — also the conversation-list preview."""
    kind = payload.get("invite_kind")
    if kind == "h2h":
        return f"Head-to-head · {payload.get('market_label') or 'match'}"
    metric = payload.get("metric")
    stat = metric_label(metric) if metric else None
    if kind == "pool":
        difficulty = payload.get("difficulty")
        bits = [b for b in (difficulty, stat) if b]
        return "Solo pool" + (f" · {' '.join(bits)}" if bits else "")
    if kind == "tournament":
        return "Tournament" + (f" · {stat}" if stat else "")
    return "Invite"


async def send_invite(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID,
    *,
    invite_kind: str,
    game: str,
    entry_preset_cents: int,
    metric: str | None = None,
    difficulty: str | None = None,
) -> Message:
    """Post a pool/tournament invite card into a thread.

    Head-to-head invites aren't created here — those come from the challenge
    flow, which posts its own card once the `challenges` row exists.
    """
    await _membership(session, user.id, conversation_id)
    if invite_kind not in ("pool", "tournament"):
        raise ChatError(
            "invalid_invite_kind",
            "Invites from chat are for pools and tournaments.",
            status_code=422,
            detail={"allowed": ["pool", "tournament"]},
        )
    if game not in registry.all_ids():
        raise ChatError("unknown_game", f"'{game}' isn't a game here.", status_code=404)
    if entry_preset_cents not in ENTRY_PRESETS_CENTS:
        raise ChatError(
            "invalid_entry",
            "Entry must be one of the offered presets.",
            status_code=422,
            detail={"allowed": list(ENTRY_PRESETS_CENTS)},
        )
    conversation = await session.get(Conversation, conversation_id)
    assert conversation is not None
    if conversation.kind != "dm":
        raise ChatError(
            "not_a_dm", "Invites go to a friend, not to support.", status_code=422
        )
    peer_id = await _assert_writable(session, user, conversation)

    payload: dict[str, Any] = {
        "invite_kind": invite_kind,
        "game": game,
        "entry_cents": entry_preset_cents,
        "metric": metric,
        "difficulty": difficulty,
        "status": "pending",
        "redirect_path": _INVITE_REDIRECT[invite_kind],
    }
    payload["title"] = invite_title(payload)
    message = await _append(
        session, conversation, sender_id=user.id, kind="invite", payload=payload
    )
    await _push_to_peer(
        session,
        conversation,
        peer_id=peer_id,
        sender=user,
        preview=f"Invited you: {payload['title']}",
    )
    log.info(
        "chat.invite_sent",
        conversation_id=str(conversation_id),
        invite_kind=invite_kind,
        game=game,
    )
    return message


async def post_challenge_invite(
    session: AsyncSession,
    *,
    challenger: User,
    challengee_id: uuid.UUID,
    challenge_id: uuid.UUID,
    game: str,
    market: str,
    market_label: str,
    entry_cents: int,
    friendly: bool,
) -> Message | None:
    """Mirror a direct head-to-head challenge into the pair's DM, so the invite
    lands in the same place they talk (called from `challenge_service`).

    Returns None when there's no thread to mirror into: a **rematch** may be
    against someone who was never a friend, and chat doesn't open a channel that
    the friendship rule wouldn't allow. Those players still get the notification
    and the Inbox Respond pill.
    """
    conversation: Conversation | None
    if await friends_service.are_friends(session, challenger.id, challengee_id):
        conversation = await _open_dm(session, challenger.id, challengee_id)
    else:
        conversation = await _find_dm(session, challenger.id, challengee_id)
    if conversation is None:
        return None
    payload: dict[str, Any] = {
        "invite_kind": "h2h",
        "challenge_id": str(challenge_id),
        "game": game,
        "market": market,
        "market_label": market_label,
        "entry_cents": entry_cents,
        "friendly": friendly,
        "status": "pending",
        "redirect_path": _INVITE_REDIRECT["h2h"],
    }
    payload["title"] = invite_title(payload)
    return await _append(
        session, conversation, sender_id=challenger.id, kind="invite", payload=payload
    )


async def _stamp_challenge_card(
    session: AsyncSession,
    challenge_id: uuid.UUID,
    *,
    status: str,
    match_id: uuid.UUID | None = None,
) -> Message | None:
    """Flip the h2h card for a challenge that was resolved outside chat (the
    Inbox Respond pill, a decline, or the expiry worker), so the thread never
    shows a stale pending invite."""
    message = await session.scalar(
        select(Message).where(
            Message.kind == "invite",
            Message.payload["challenge_id"].astext == str(challenge_id),
        )
    )
    if message is None or message.payload.get("status") != "pending":
        return None
    patch: dict[str, Any] = {"status": status}
    if match_id is not None:
        patch["match_id"] = str(match_id)
    message.payload = {**message.payload, **patch}
    await session.flush()
    return message


async def note_challenge_resolved(
    session: AsyncSession,
    challenge_id: uuid.UUID,
    *,
    status: str,
    match_id: uuid.UUID | None = None,
) -> None:
    """Public hook for `challenge_service`: keep the chat card in step with the
    challenge row. Never raises — chat must not break the challenge flow."""
    try:
        await _stamp_challenge_card(
            session, challenge_id, status=status, match_id=match_id
        )
    except Exception as exc:  # noqa: BLE001 — a stale card is not worth a 500
        log.warning(
            "chat.card_sync_failed", challenge_id=str(challenge_id), error=str(exc)
        )


async def respond_invite(
    session: AsyncSession, user: User, message_id: uuid.UUID, action: str
) -> tuple[Message, uuid.UUID | None]:
    """Accept or decline an invite card. Returns the card and, for an accepted
    head-to-head, the PENDING match it formed."""
    if action not in ("accept", "decline"):
        raise ChatError("invalid_action", "Accept or decline.", status_code=422)
    message = await session.get(Message, message_id)
    if message is None or message.kind != "invite":
        raise ChatError("invite_not_found", "No such invite.", status_code=404)
    await _membership(session, user.id, message.conversation_id)
    if message.sender_id == user.id:
        raise ChatError("own_invite", "You sent this invite.", status_code=403)
    if message.payload.get("status") != "pending":
        raise ChatError(
            "invite_resolved",
            f"This invite is already {message.payload.get('status')}.",
            status_code=409,
        )

    match_id: uuid.UUID | None = None
    if message.payload.get("invite_kind") == "h2h":
        # Late import: challenge_service posts cards here, so this would cycle.
        from . import challenge_service

        challenge_id = uuid.UUID(str(message.payload["challenge_id"]))
        if action == "accept":
            match = await challenge_service.accept_direct(session, user, challenge_id)
            match_id = match.id
        else:
            await challenge_service.decline(session, user, challenge_id)

    patch: dict[str, Any] = {"status": "accepted" if action == "accept" else "declined"}
    if match_id is not None:
        patch["match_id"] = str(match_id)
    message.payload = {**message.payload, **patch}
    await session.flush()

    conversation = await session.get(Conversation, message.conversation_id)
    assert conversation is not None
    verb = "accepted" if action == "accept" else "declined"
    who = user.username or "Your friend"
    what = invite_title(message.payload).lower()
    await _append(
        session,
        conversation,
        sender_id=None,
        kind="system",
        body=f"{who} {verb} the {what} invite.",
    )
    log.info("chat.invite_responded", message_id=str(message_id), action=action)
    return message, match_id


async def mark_read(
    session: AsyncSession, user: User, conversation_id: uuid.UUID
) -> int:
    """Move this user's read cursor to now. Idempotent. Returns the new total.

    Stamped from the **database** clock so it's directly comparable to
    `messages.created_at` (also `clock_timestamp()`) — an app-server clock a few
    hundred ms behind would leave just-read messages counted as unread."""
    member = await _membership(session, user.id, conversation_id)
    member.last_read_at = func.clock_timestamp()
    await session.flush()
    return await unread_total(session, user.id)


# --------------------------------------------------------------------------- #
# Reads.
# --------------------------------------------------------------------------- #


def _unread_stmt(user_id: uuid.UUID):
    """Per-conversation unread counts for one user: messages the user didn't
    write that landed after their read cursor."""
    return (
        select(ConversationMember.conversation_id, func.count(Message.id))
        .select_from(ConversationMember)
        .join(Message, Message.conversation_id == ConversationMember.conversation_id)
        .where(
            ConversationMember.user_id == user_id,
            or_(Message.sender_id.is_(None), Message.sender_id != user_id),
            or_(
                ConversationMember.last_read_at.is_(None),
                Message.created_at > ConversationMember.last_read_at,
            ),
        )
        .group_by(ConversationMember.conversation_id)
    )


async def unread_total(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = await session.execute(_unread_stmt(user_id))
    return sum(int(count) for _, count in rows)


def preview_of(message: Message | None) -> str | None:
    """One-line summary of a thread's latest message for the conversation list."""
    if message is None:
        return None
    if message.kind == "invite":
        return invite_title(message.payload)
    return message.body


@dataclass
class ConversationRow:
    conversation: Conversation
    peer: User | None
    unread: int
    last_message: Message | None

    @property
    def title(self) -> str:
        if self.conversation.kind == "support":
            return self.conversation.subject or SUPPORT_TITLE
        return (self.peer.username if self.peer else None) or "Player"


async def list_conversations(
    session: AsyncSession, user: User
) -> list[ConversationRow]:
    """Every thread this user is in, newest activity first."""
    member_rows = list(
        await session.scalars(
            select(ConversationMember).where(ConversationMember.user_id == user.id)
        )
    )
    ids = [m.conversation_id for m in member_rows]
    if not ids:
        return []

    conversations = list(
        await session.scalars(select(Conversation).where(Conversation.id.in_(ids)))
    )

    # Peers (DMs only — the support thread has a single member).
    peers: dict[uuid.UUID, User] = {}
    peer_rows = await session.execute(
        select(ConversationMember.conversation_id, User)
        .join(User, User.id == ConversationMember.user_id)
        .where(
            ConversationMember.conversation_id.in_(ids),
            ConversationMember.user_id != user.id,
        )
    )
    for conversation_id, peer in peer_rows:
        peers[conversation_id] = peer

    # Latest message per thread (DISTINCT ON is the cheap Postgres idiom here).
    latest: dict[uuid.UUID, Message] = {}
    for message in await session.scalars(
        select(Message)
        .where(Message.conversation_id.in_(ids))
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.created_at.desc())
    ):
        latest[message.conversation_id] = message

    unread = {
        conversation_id: int(count)
        for conversation_id, count in await session.execute(_unread_stmt(user.id))
    }

    rows = [
        ConversationRow(
            conversation=c,
            peer=peers.get(c.id),
            unread=unread.get(c.id, 0),
            last_message=latest.get(c.id),
        )
        for c in conversations
    ]
    # Newest activity first; a thread with no messages yet sorts by creation.
    rows.sort(
        key=lambda r: r.conversation.last_message_at or r.conversation.created_at,
        reverse=True,
    )
    return rows


async def get_conversation_row(
    session: AsyncSession, user: User, conversation_id: uuid.UUID
) -> ConversationRow:
    """One thread's list row (the header of an open thread)."""
    await _membership(session, user.id, conversation_id)
    rows = await list_conversations(session, user)
    row = next((r for r in rows if r.conversation.id == conversation_id), None)
    if row is None:  # pragma: no cover — membership implies presence
        raise ChatError(
            "conversation_not_found", "No such conversation.", status_code=404
        )
    return row


async def list_messages(
    session: AsyncSession,
    user: User,
    conversation_id: uuid.UUID,
    *,
    limit: int = _MESSAGE_LIMIT,
) -> list[Message]:
    """The last `limit` messages, oldest → newest (render order)."""
    await _membership(session, user.id, conversation_id)
    newest = list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
    )
    return list(reversed(newest))


async def sender_names(
    session: AsyncSession, messages: list[Message]
) -> dict[uuid.UUID, str | None]:
    """Usernames for the senders in a batch of messages (one query)."""
    ids = {m.sender_id for m in messages if m.sender_id is not None}
    if not ids:
        return {}
    return {
        u.id: u.username
        for u in await session.scalars(select(User).where(User.id.in_(ids)))
    }


__all__ = [
    "ChatError",
    "ConversationRow",
    "INVITE_KINDS",
    "invite_title",
    "SUPPORT_TITLE",
    "get_conversation_row",
    "list_conversations",
    "list_messages",
    "mark_read",
    "note_challenge_resolved",
    "open_dm",
    "open_support",
    "post_challenge_invite",
    "preview_of",
    "respond_invite",
    "send_invite",
    "send_text",
    "sender_names",
    "unread_total",
]
