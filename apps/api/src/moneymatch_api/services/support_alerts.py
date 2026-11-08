"""Email SUPPORT_EMAIL when a user writes in their support thread.

Fire-and-forget after commit. Per thread, the first message mails at once; anything
else within WINDOW_SECONDS is batched into one follow-up, so a thread sends at most
one email per window. State is in-process: a restart only forgets pending batches'
timing, not committed messages (staff still have the thread).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from ..config import get_settings
from ..models.user import User
from . import email_service, support_mail

log = structlog.get_logger(__name__)

WINDOW_SECONDS = 60.0
MAX_LINE_CHARS = 2000
MAX_LINES = 20

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class _Line:
    at: datetime
    text: str


@dataclass
class _Thread:
    username: str
    user_id: uuid.UUID
    reply_to: str | None
    lines: list[_Line] = field(default_factory=list)


_threads: dict[uuid.UUID, _Thread] = {}
_tasks: set[asyncio.Task[None]] = set()


def _clean(text: str, limit: int) -> str:
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    return text if len(text) <= limit else f"{text[:limit]}… [truncated]"


def _render(
    conversation_id: uuid.UUID, thread: _Thread, lines: list[_Line]
) -> tuple[str, str]:
    name = _clean(thread.username, 60).replace("\n", " ")
    head = (
        f"{len(lines)} messages from {name} since the last alert."
        if len(lines) > 1
        else f"New message from {name}."
    )
    shown = lines[-MAX_LINES:]
    parts = [
        head,
        "",
        f"User: {name}",
        f"User ID: {thread.user_id}",
        f"Email: {thread.reply_to or 'none on file'}",
        f"Conversation: {conversation_id}",
        "",
    ]
    if len(lines) > len(shown):
        parts += [f"({len(lines) - len(shown)} earlier messages not shown.)", ""]
    for line in shown:
        stamp = line.at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        parts += [f"[{stamp}]", _clean(line.text, MAX_LINE_CHARS), ""]
    parts.append("Replying to this email posts your response in the support thread.")
    return f"Support: {name}", "\n".join(parts)


async def _run(conversation_id: uuid.UUID) -> None:
    try:
        while True:
            thread = _threads[conversation_id]
            if not thread.lines:
                return
            batch, thread.lines = thread.lines, []
            try:
                subject, text = _render(conversation_id, thread, batch)
                await email_service.send_plain(
                    to=get_settings().support_email,
                    subject=subject,
                    text=text,
                    reply_to=support_mail.reply_address(conversation_id),
                )
            except Exception as exc:  # noqa: BLE001 — never surfaces to the user
                log.warning(
                    "support_alert.failed",
                    conversation_id=str(conversation_id),
                    error=str(exc),
                )
            await asyncio.sleep(WINDOW_SECONDS)
    finally:
        _threads.pop(conversation_id, None)


def notify(
    user: User, conversation_id: uuid.UUID, text: str, at: datetime | None = None
) -> None:
    """Queue an alert for a committed user message in their support thread."""
    if not email_service.is_enabled() or not get_settings().support_email:
        return
    line = _Line(at=at or datetime.now(UTC), text=text)
    thread = _threads.get(conversation_id)
    if thread is not None:
        thread.lines.append(line)
        return
    _threads[conversation_id] = _Thread(
        username=user.username or "player",
        user_id=user.id,
        reply_to=user.email if email_service.is_deliverable(user.email) else None,
        lines=[line],
    )
    task = asyncio.create_task(_run(conversation_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """Wait for pending alerts (tests)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def reset() -> None:
    for task in _tasks:
        task.cancel()
    _tasks.clear()
    _threads.clear()
