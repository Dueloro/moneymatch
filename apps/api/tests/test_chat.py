"""`/chat` — friend DMs, the support thread, and invite cards.

Covers the rules that matter: messaging follows friendship, unread counts are
per-member read cursors, a chat invite is a real intent (an accepted h2h card
forms the PENDING match), and support answers itself.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from moneymatch_api.models.linked_account import LinkedAccount
from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"
GAME = "cs2.faceit"


async def _onboard(client, auth_id: str, name: str) -> str:
    """Provision a user, name them, and link them to CS2 (so they can wager)."""
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        linked = await s.scalar(
            select(LinkedAccount).where(
                LinkedAccount.user_id == user.id, LinkedAccount.game == GAME
            )
        )
        if linked is None:
            s.add(
                LinkedAccount(
                    user_id=user.id,
                    game=GAME,
                    host_account_id=f"faceit_{name}",
                    host_username=name,
                    profile_snapshot={"username": name, "game": GAME},
                )
            )
        await s.commit()
        return str(user.id)


async def _befriend(client, a_auth: str, b_auth: str, b_name: str) -> None:
    r = await client.post(
        f"{V1}/friends", headers=auth_headers(a_auth), json={"username_or_code": b_name}
    )
    assert r.status_code == 200, r.text
    incoming = (await client.get(f"{V1}/friends", headers=auth_headers(b_auth))).json()[
        "incoming"
    ]
    r = await client.post(
        f"{V1}/friends/{incoming[0]['friendship_id']}/accept",
        headers=auth_headers(b_auth),
    )
    assert r.status_code == 200


async def _pair(client):
    """alice + bob, friends, both linked. Returns their ids."""
    alice = await _onboard(client, "chat_a", "alice")
    bob = await _onboard(client, "chat_b", "bob")
    await _befriend(client, "chat_a", "chat_b", "bob")
    return alice, bob


async def test_dm_requires_friendship(client):
    await _onboard(client, "chat_a", "alice")
    bob = await _onboard(client, "chat_b", "bob")

    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers("chat_a"),
        json={"user_id": bob},
    )
    assert r.status_code == 403, r.text


async def test_send_and_read_a_dm(client):
    _, bob = await _pair(client)

    # alice opens the DM and sends a line.
    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers("chat_a"),
        json={"user_id": bob},
    )
    assert r.status_code == 200, r.text
    conversation = r.json()
    assert conversation["kind"] == "dm"
    assert conversation["title"] == "bob"
    cid = conversation["id"]

    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={"body": "  run it back?  "},
    )
    assert r.status_code == 200, r.text
    thread = r.json()
    assert [m["body"] for m in thread["messages"]] == ["run it back?"]
    assert thread["messages"][0]["mine"] is True
    # The sender is never badged for their own message.
    assert thread["conversation"]["unread"] == 0

    # bob sees it as unread, from alice.
    r = await client.get(f"{V1}/chat/conversations", headers=auth_headers("chat_b"))
    body = r.json()
    assert body["unread_total"] == 1
    theirs = body["conversations"][0]
    assert theirs["title"] == "alice"
    assert theirs["last_message_preview"] == "run it back?"
    assert theirs["unread"] == 1

    # Reading clears it, idempotently.
    for _ in range(2):
        r = await client.post(
            f"{V1}/chat/conversations/{cid}/read", headers=auth_headers("chat_b")
        )
        assert r.status_code == 200
        assert r.json()["unread_total"] == 0

    # bob is not a stranger to the thread: he can read and reply.
    r = await client.get(
        f"{V1}/chat/conversations/{cid}", headers=auth_headers("chat_b")
    )
    assert r.status_code == 200
    assert r.json()["messages"][0]["mine"] is False


async def test_outsiders_cannot_see_or_post(client):
    _, bob = await _pair(client)
    await _onboard(client, "chat_c", "carol")
    cid = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"user_id": bob},
        )
    ).json()["id"]

    r = await client.get(
        f"{V1}/chat/conversations/{cid}", headers=auth_headers("chat_c")
    )
    assert r.status_code == 404
    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_c"),
        json={"body": "hello?"},
    )
    assert r.status_code == 404


async def test_empty_message_and_ambiguous_body_are_rejected(client):
    _, bob = await _pair(client)
    cid = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"user_id": bob},
        )
    ).json()["id"]

    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={"body": "   "},
    )
    assert r.status_code == 422
    # Neither a body nor an invite.
    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={},
    )
    assert r.status_code == 422


async def test_pool_invite_card_round_trip(client):
    _, bob = await _pair(client)
    cid = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"user_id": bob},
        )
    ).json()["id"]

    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={
            "invite": {
                "invite_kind": "pool",
                "game": GAME,
                "entry_preset_cents": 1000,
                "metric": "cs2_kd_ratio",
                "difficulty": "medium",
            }
        },
    )
    assert r.status_code == 200, r.text
    card = r.json()["messages"][-1]
    assert card["kind"] == "invite"
    assert card["payload"]["status"] == "pending"
    assert card["payload"]["entry_cents"] == 1000
    assert card["payload"]["redirect_path"] == "/pools"
    assert "K/D" in card["payload"]["title"]

    # The sender can't answer their own invite.
    r = await client.post(
        f"{V1}/chat/messages/{card['id']}/respond",
        headers=auth_headers("chat_a"),
        json={"action": "accept"},
    )
    assert r.status_code == 403

    # bob accepts → the card is stamped and he's pointed at the Solo Pools tab.
    r = await client.post(
        f"{V1}/chat/messages/{card['id']}/respond",
        headers=auth_headers("chat_b"),
        json={"action": "accept"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"]["payload"]["status"] == "accepted"
    assert body["redirect_path"] == "/pools"
    assert body["match_id"] is None

    # Answering twice is a conflict, not a second accept.
    r = await client.post(
        f"{V1}/chat/messages/{card['id']}/respond",
        headers=auth_headers("chat_b"),
        json={"action": "decline"},
    )
    assert r.status_code == 409

    # The outcome is narrated in the thread.
    thread = (
        await client.get(
            f"{V1}/chat/conversations/{cid}", headers=auth_headers("chat_a")
        )
    ).json()
    assert thread["messages"][-1]["kind"] == "system"
    assert "accepted" in thread["messages"][-1]["body"]


async def test_invite_rejects_a_non_preset_entry(client):
    _, bob = await _pair(client)
    cid = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"user_id": bob},
        )
    ).json()["id"]

    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={
            "invite": {
                "invite_kind": "pool",
                "game": GAME,
                "entry_preset_cents": 777,
            }
        },
    )
    assert r.status_code == 422


async def test_a_challenge_lands_in_the_dm_and_accepting_it_there_forms_a_match(client):
    _, bob = await _pair(client)

    # alice challenges bob through the normal challenge flow.
    r = await client.post(
        f"{V1}/challenges",
        headers=auth_headers("chat_a"),
        json={
            "challengee_id": bob,
            "game": GAME,
            "market": "kd_ratio",
            "entry_preset_cents": 1000,
        },
    )
    assert r.status_code in (200, 201), r.text

    # It shows up as an invite card in their conversation, not only in the feed.
    convos = (
        await client.get(f"{V1}/chat/conversations", headers=auth_headers("chat_b"))
    ).json()["conversations"]
    cid = convos[0]["id"]
    thread = (
        await client.get(
            f"{V1}/chat/conversations/{cid}", headers=auth_headers("chat_b")
        )
    ).json()
    card = thread["messages"][-1]
    assert card["kind"] == "invite"
    assert card["payload"]["invite_kind"] == "h2h"
    assert card["payload"]["status"] == "pending"

    # Accepting in chat forms the PENDING match, same as the Inbox pill.
    r = await client.post(
        f"{V1}/chat/messages/{card['id']}/respond",
        headers=auth_headers("chat_b"),
        json={"action": "accept"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_id"] is not None
    assert body["message"]["payload"]["status"] == "accepted"


async def test_declining_a_challenge_elsewhere_stamps_the_chat_card(client):
    _, bob = await _pair(client)
    challenge = (
        await client.post(
            f"{V1}/challenges",
            headers=auth_headers("chat_a"),
            json={
                "challengee_id": bob,
                "game": GAME,
                "market": "kd_ratio",
                "entry_preset_cents": 500,
            },
        )
    ).json()["challenge"]

    r = await client.post(
        f"{V1}/challenges/{challenge['id']}/decline", headers=auth_headers("chat_b")
    )
    assert r.status_code == 200, r.text

    convos = (
        await client.get(f"{V1}/chat/conversations", headers=auth_headers("chat_a"))
    ).json()["conversations"]
    thread = (
        await client.get(
            f"{V1}/chat/conversations/{convos[0]['id']}", headers=auth_headers("chat_a")
        )
    ).json()
    card = next(m for m in thread["messages"] if m["kind"] == "invite")
    # No stale "pending" card left behind in the thread.
    assert card["payload"]["status"] == "declined"


async def test_unfriending_closes_the_thread_to_new_messages(client):
    """Messaging follows friendship for the life of the thread, not only when it
    was opened — otherwise removing (or blocking) someone leaves the channel
    wide open. History stays readable; only writes are refused."""
    _, bob = await _pair(client)
    cid = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"user_id": bob},
        )
    ).json()["id"]
    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={"body": "still friends"},
    )
    assert r.status_code == 200, r.text

    friends = (
        await client.get(f"{V1}/friends", headers=auth_headers("chat_b"))
    ).json()["friends"]
    r = await client.delete(
        f"{V1}/friends/{friends[0]['friendship_id']}", headers=auth_headers("chat_b")
    )
    assert r.status_code == 200, r.text

    # Neither side can post any more — a line or an invite.
    for headers in (auth_headers("chat_a"), auth_headers("chat_b")):
        r = await client.post(
            f"{V1}/chat/conversations/{cid}/messages",
            headers=headers,
            json={"body": "hello?"},
        )
        assert r.status_code == 403, r.text
    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={
            "invite": {
                "invite_kind": "pool",
                "game": GAME,
                "entry_preset_cents": 1000,
            }
        },
    )
    assert r.status_code == 403

    # The transcript is still there for both of them.
    r = await client.get(
        f"{V1}/chat/conversations/{cid}", headers=auth_headers("chat_b")
    )
    assert r.status_code == 200
    assert r.json()["messages"][-1]["body"] == "still friends"


async def test_a_challenge_to_a_non_friend_opens_no_dm(client):
    """A rematch may be against someone who was never a friend. The challenge is
    allowed there; a chat thread is not — chat never opens a channel the
    friendship rule would refuse."""
    from moneymatch_api.models.user import User as UserModel
    from moneymatch_api.services import chat_service

    alice = await _onboard(client, "chat_a", "alice")
    bob = await _onboard(client, "chat_b", "bob")

    sm = new_sessionmaker()
    async with sm() as s:
        challenger = await s.get(UserModel, uuid.UUID(alice))
        assert challenger is not None
        posted = await chat_service.post_challenge_invite(
            s,
            challenger=challenger,
            challengee_id=uuid.UUID(bob),
            challenge_id=uuid.uuid4(),
            game=GAME,
            market="kd_ratio",
            market_label="K/D",
            entry_cents=1000,
            friendly=False,
        )
        await s.commit()
    assert posted is None

    convos = (
        await client.get(f"{V1}/chat/conversations", headers=auth_headers("chat_b"))
    ).json()
    assert convos["conversations"] == []


async def test_support_thread_greets_and_acknowledges(client):
    await _onboard(client, "chat_a", "alice")

    r = await client.post(
        f"{V1}/chat/conversations",
        headers=auth_headers("chat_a"),
        json={"kind": "support"},
    )
    assert r.status_code == 200, r.text
    support = r.json()
    assert support["kind"] == "support"
    assert support["peer_user_id"] is None
    cid = support["id"]

    # Opening it twice returns the same thread (get-or-create).
    again = (
        await client.post(
            f"{V1}/chat/conversations",
            headers=auth_headers("chat_a"),
            json={"kind": "support"},
        )
    ).json()
    assert again["id"] == cid

    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={"body": "Where is my payout?"},
    )
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert messages[0]["kind"] == "system"  # greeting
    assert messages[-2]["body"] == "Where is my payout?"
    assert messages[-1]["kind"] == "system"  # auto-ack
    assert messages[-1]["sender_id"] is None

    # Support takes messages but not invites.
    r = await client.post(
        f"{V1}/chat/conversations/{cid}/messages",
        headers=auth_headers("chat_a"),
        json={
            "invite": {
                "invite_kind": "pool",
                "game": GAME,
                "entry_preset_cents": 1000,
            }
        },
    )
    assert r.status_code == 422
