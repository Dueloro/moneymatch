"""Transactional email (Resend) — the email side of notifications.

Guarded like push/analytics: with no `RESEND_API_KEY` the module is a no-op, so
tests and local runs never touch the network. Only real, deliverable addresses
are emailed — the synthetic `@users.moneymatch.app` addresses that back username
sign-in have no inbox and are skipped. Best-effort: a send failure is logged and
never breaks the caller's transaction.
"""

from __future__ import annotations

import uuid

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.user import User

log = structlog.get_logger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"

# Hosted email logo (Decision B — beta domain for now; one-line change later).
_LOGO_URL = "https://moneymatch-beta.vercel.app/email/logo.png"

# The reserved subdomain that username sign-in maps handles onto — a mirror of
# `AUTH_EMAIL_DOMAIN` in apps/web/src/lib/usernameAuth.ts. These addresses have
# no inbox, so mailing them is guaranteed to bounce; skip them entirely.
_SYNTHETIC_EMAIL_DOMAIN = "users.moneymatch.app"


def is_enabled() -> bool:
    """True when a Resend key is configured (otherwise every send is a no-op)."""
    return bool(get_settings().resend_api_key)


def is_deliverable(email: str | None) -> bool:
    """A real address we can mail — present and not a synthetic username alias."""
    if not email:
        return False
    return not email.lower().endswith(f"@{_SYNTHETIC_EMAIL_DOMAIN}")


def _app_url(link_path: str | None) -> str | None:
    """Absolute app link from a relative path, using the first configured origin.

    WEB_ORIGIN is a comma-separated CORS list; the first entry is the canonical
    web app, so deep links in email resolve there.
    """
    if not link_path:
        return None
    origin = get_settings().web_origin.split(",")[0].strip().rstrip("/")
    return f"{origin}{link_path}"


def _render_html(body: str, url: str | None) -> str:
    """Hybrid-brand HTML: dark header/footer bands with the lime mark, light body,
    lime CTA. Table-based + inline styles for email-client reliability."""
    button = (
        f'<tr><td style="padding:8px 0 4px"><a href="{url}" '
        'style="display:inline-block;background:#C6F440;color:#0B0B0C;'
        "padding:12px 22px;border-radius:9999px;text-decoration:none;"
        'font-weight:700;font-size:15px">Open Money Match</a></td></tr>'
        if url
        else ""
    )
    fallback = (
        f'<tr><td style="padding:12px 0 0;font-size:12px;color:#6b7280">'
        f"Button not working? Paste this link: <br>{url}</td></tr>"
        if url
        else ""
    )
    return (
        '<div style="background:#f3f4f6;padding:24px 0;'
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;margin:0 auto;background:#ffffff;'
        'border-radius:16px;overflow:hidden">'
        # Dark header band with the mark + wordmark.
        '<tr><td style="background:#0B0B0C;padding:20px 28px">'
        f'<img src="{_LOGO_URL}" width="28" height="28" alt="Money Match" '
        'style="vertical-align:middle;border-radius:8px">'
        '<span style="color:#ffffff;font-weight:600;font-size:15px;'
        'vertical-align:middle;margin-left:10px">Money Match</span>'
        "</td></tr>"
        # Light body.
        '<tr><td style="padding:28px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:16px;line-height:1.5;color:#111827">{body}</td></tr>'
        f"{button}{fallback}"
        "</table></td></tr>"
        # Dark footer band.
        '<tr><td style="background:#0B0B0C;padding:16px 28px;font-size:12px;'
        'color:#9ca3af">Money Match · peer-to-peer skill wagering<br>'
        "Need help? Contact Dueloro Support.</td></tr>"
        "</table></div>"
    )


async def send_to_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    subject: str,
    body: str,
    link_path: str | None = None,
) -> bool:
    """Best-effort transactional email to `user_id`. Returns whether a message was
    sent. No-ops (returns False) when the seam is off or the address isn't
    deliverable. Never raises — a mail failure must not break a money/notify path.
    """
    if not is_enabled():
        return False
    user = await session.get(User, user_id)
    if user is None or not is_deliverable(user.email):
        return False

    settings = get_settings()
    url = _app_url(link_path)
    payload = {
        "from": settings.email_from,
        "to": [user.email],
        "subject": subject,
        "text": body if url is None else f"{body}\n\nOpen Money Match: {url}",
        "html": _render_html(body, url),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; mail never breaks caller
        log.warning("email.send_failed", user_id=str(user_id), error=str(exc))
        return False
