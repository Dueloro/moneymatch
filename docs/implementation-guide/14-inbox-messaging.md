# Inbox Messaging — friend DMs, support, and invite cards

**Status:** built and green (2026-07-31); **integrated with the rest of the app
2026-08-02** (§10). Added after the original MVP cut at the owner's request;
supersedes the "No chat at MVP" line in
[`08-phase-5-social-retention.md`](./08-phase-5-social-retention.md) §Deliverables 2.

This doc explains what the messaging system is, how each piece works and why it
was built that way, and what the honest next steps are. Read it before touching
anything under `services/chat_service.py` or `components/chat/`.

---

## 0. In plain English (start here)

Skip to §1 for the engineering detail. This section is the whole thing in words
you can read in three minutes.

### What the messaging system is

Inside **Social → Inbox** there is a chat app. The left side is a list of
everything addressed to you; the right side is whatever you picked from it.

- **Notifications** sit at the top of that list. They didn't move or change —
  the Inbox just got bigger around them.
- **MoneyMatch Support** is a thread you can always open. You type a question, it
  confirms receipt immediately, and an agent answers in the same thread later.
- **Direct messages** are one thread per friend. You can only message friends —
  the same rule that stops strangers from challenging you.

You can send three things in a thread: a normal message, a **solo pool or
tournament invite**, or a **head-to-head challenge**. The last one is real money:
the card in the chat is the same challenge as the one in your notifications, so
accepting it in either place creates the same match. Pool and tournament invites
are softer — they record what your friend suggested and drop you on the right tab
to join.

Log in with the demo button and it's already full of people, conversations, and
invite cards to click.

### What changed on 2026-08-02

The chat worked, but it was slightly on its own island. Four things connected it
to the rest of the app — two of them mattered for safety, two for whether you'd
ever notice a message:

| Problem | What it means in practice | Now |
| --- | --- | --- |
| Friendship was only checked when a thread was **created** | You remove or block someone, and they can still message you forever through the old thread | Every message re-checks it. Blocked or removed → nobody can post, but the old messages stay readable (you may need them for a dispute) |
| A **rematch** against someone who was never your friend opened a DM with them | A stranger ends up with a permanent chat channel to you | No thread is created. They can still rematch you — that goes through notifications, as before |
| The bell icon only counted **notifications** | A friend messages you while you're on the Wallet page and nothing anywhere lights up | The bell counts messages too, updates every 15 seconds, and clears the moment you open the thread |
| No phone/browser **push** for messages | You close the tab, you never find out | You get a push — but **only if you're not currently in the app**. If you're online it stays quiet, because your Inbox is already going to badge |
| A broken "Message" button failed **silently** | You click Message on a friend who just removed you, and literally nothing happens | It tells you why |

Plus one small thing you asked for separately: **Inbox is now the first tab in
Social and the one it opens on**, instead of Leaderboard.

### The one design decision worth understanding

A new message does **not** create a notification row. It could have — and then
messages would show up in the notification feed like everything else. It doesn't,
because you'd see every message twice (once in the feed, once in the thread), and
"mark as read" would mean two different things in two places that then have to
agree. Instead, messages are counted for the badge and pushed to your device, but
the feed stays a feed. §10.3 has the longer argument.

### Checking it yourself

The automated proof is `E2E_AUTH=1 make e2e` (`chat.spec.ts` — two browsers, the
whole loop; §9). Four things are worth clicking through by hand, because they're
the ones that only show up with two real people and a real clock:

| Check | What you should see |
| --- | --- |
| Two accounts, one messages the other while the second sits on **Wallet** | The bell dot appears within ~15 s, and clears the moment they open the thread |
| Remove the friend, then try to send | A clear "this thread is closed" message; scrolling back still shows the old conversation |
| Message someone who's **offline** (VAPID keys configured) | One browser push, landing directly in that thread. Message someone who's **online** → no push, just the badge |
| Open **Support**, send a question | Greeting → your line → instant acknowledgement, and no `+` invite button (support takes text only) |

---

## 1. What was asked for, and what shipped

The ask, in the owner's words: a fully functional chat system inside the Inbox so
players can message friends or support; invites (solo pool, tournament) sent to a
friend should **appear in that chat**; there should be a way to send an invite
straight from the chat interface; it should look good; it should come with mock
data to play with; and **the existing notification feed must not disappear**.

What shipped:

| Ask | How it landed |
| --- | --- |
| Message a friend | Real DM threads, one per accepted friend pair, server-owned |
| Message support | A per-user `support` thread answered by the platform |
| Invites appear in the chat | Invites are a **message kind** — they render as cards in the thread |
| Invite from the chat | A `+` button beside the typing bar → Solo pool / Tournament / Head-to-head |
| Looks good | Two-pane surface, avatars, presence, day dividers, bubbles, unread badges |
| Mock data | Demo login seeds 3 friends, 4 threads, ~20 backdated messages, 5 invite cards in 4 different states, and one live acceptable challenge |
| Notifications stay | The feed is untouched — it is now the **pinned first row** of the Inbox list |

The last row is the one design decision worth calling out. "Inbox" used to mean
"the notification feed". It now means "everything addressed to you", and the feed
is one entry in that list — the first one, selected by default. Nothing about the
feed's behavior changed: same rows, same Respond/Decline pills, same mark-read-on-view.

---

## 2. The shape of it

```
Social  ▸  Inbox (3) | Leaderboard | Friends
             │
                    ┌──────────────┴──────────────────────────────┐
                    │  ConversationList        │   right pane     │
                    ├──────────────────────────┼──────────────────┤
                    │ 🔔 Notifications      3  │                  │
                    │ 🛟 MoneyMatch Support  1 │   NotificationsFeed
                    │ ── Direct messages ───── │        or        │
                    │ 🟢 s1mple_fan         5  │   MessageThread  │
                    │ ⚪ chocoTaco          3  │   (+ Composer)   │
                    │ ⚪ kvem_              2  │                  │
                    └──────────────────────────┴──────────────────┘
```

On desktop both panes are visible (`md:grid md:grid-cols-[23rem_1fr]`). On mobile
exactly one is: picking a row swaps to the thread, and a back arrow returns to the
list. That is `mobilePane` state in `ChatPanel`, not a media-query hack — the same
components render in both layouts.

### File map

**Backend** (`apps/api/src/moneymatch_api/`)

| File | Role |
| --- | --- |
| `models/chat.py` | `Conversation`, `ConversationMember`, `Message` + the kind vocabularies |
| `migrations/versions/0017_chat.py` | The three tables, their indexes and check constraints |
| `services/chat_service.py` | All the logic. Threads, messages, invites, unread math |
| `schemas/chat.py` | Wire types (Pydantic) |
| `routers/chat.py` | `/api/v1/chat/*` — thin; every rule lives in the service |
| `services/challenge_service.py` | *Changed*: posts + syncs the head-to-head invite card |
| `routers/demo.py` | *Changed*: `_ensure_demo_social` seeds the mock threads |

**Frontend** (`apps/web/src/`)

| File | Role |
| --- | --- |
| `hooks/useChat.ts` | Every query and mutation, typed against the generated client |
| `components/chat/ChatPanel.tsx` | The two-pane shell, selection state, deep links |
| `components/chat/ConversationList.tsx` | Left rail incl. the pinned Notifications + Support rows |
| `components/chat/MessageThread.tsx` | Header, transcript, day dividers, scroll pinning |
| `components/chat/MessageBubble.tsx` | One line: yours / theirs / a system note |
| `components/chat/InviteCard.tsx` | An invite rendered in-thread, with Accept/Join/Decline |
| `components/chat/Composer.tsx` | Typing bar + the `+` invite menu |
| `components/chat/InviteSheet.tsx` | Compose a pool/tournament invite; also the "Open <tab> ↗" redirect |
| `components/chat/NewMessageSheet.tsx` | Friend picker for starting a thread |
| `components/chat/Avatar.tsx` | Deterministic initials + presence ring |
| `components/NotificationsFeed.tsx` | The old `InboxPage` body, moved out unchanged apart from dropping its page heading |
| `pages/InboxPage.tsx` | Now just renders `<ChatPanel />` |
| `pages/SocialPage.tsx` | *Changed*: Inbox is the first sub-tab and the default; carries the unread badge |
| `components/ui/SidebarNav.tsx`, `ui/MobileNav.tsx` | *Changed*: the bell dot reads the live inbox count (§10.3) |
| `components/ui/SubTabs.tsx` | *Changed*: optional `badge?: number` |
| `components/FriendsPanel.tsx` | *Changed*: a **Message** pill per friend row |
| `e2e/chat.spec.ts` | The two-browser proof of the whole loop (§9) |

---

## 3. Data model

Three tables. The design goal was that **the conversation list renders from one
cheap query per concern** — no N+1 walk over messages.

### `conversations`

| Column | Why |
| --- | --- |
| `kind` | `dm` (exactly two members) or `support` (one member + the platform) |
| `subject` | Support threads carry a title; a DM takes its title from the peer |
| `last_message_at` | **Denormalized.** The list sorts on this without touching `messages` |

### `conversation_members`

| Column | Why |
| --- | --- |
| `conversation_id`, `user_id` | Membership. Unique as a pair (`uq_conversation_members_pair`) |
| `last_read_at` | The **read cursor**. Unread = messages after this that you didn't write |

Membership is also the authorization check. There is exactly one function,
`_membership()`, and every read and write goes through it; a non-member gets a
404 (not a 403 — a stranger should not learn a conversation exists).

### `messages`

| Column | Why |
| --- | --- |
| `sender_id` | **Nullable.** `NULL` = platform-authored (support reply, system note) |
| `kind` | `text`, `invite`, or `system` |
| `body` | The typed line (null on invite cards) |
| `payload` | JSONB. An invite card's entire contract lives here |
| `created_at` | `clock_timestamp()`, indexed with `conversation_id` for the thread scan |

Messages are **not** append-only (unlike `ledger_entries`). `body` never changes,
but an invite's `payload.status` flips exactly once, pending → accepted/declined/
expired. That is a deliberate exception, and it is why the table has no
append-only trigger.

### Why unread is a cursor, not a flag

A per-message `read` boolean means one write per message per reader. A cursor
means one write per *thread visit*. The count is a single grouped query:

```sql
SELECT cm.conversation_id, count(m.id)
  FROM conversation_members cm
  JOIN messages m ON m.conversation_id = cm.conversation_id
 WHERE cm.user_id = :me
   AND (m.sender_id IS NULL OR m.sender_id <> :me)   -- your own lines never badge you
   AND (cm.last_read_at IS NULL OR m.created_at > cm.last_read_at)
 GROUP BY cm.conversation_id
```

One subtlety worth preserving: `mark_read` stamps the cursor with
`func.clock_timestamp()` — the **database** clock — not `datetime.now()`. Message
timestamps come from the DB too, so the two are directly comparable. An app server
running a few hundred milliseconds behind the DB would otherwise leave
just-read messages counted as unread.

---

## 4. The rules the server enforces

The client sends ids, a body, and a preset choice. Everything else is the
server's (00-README §3). Concretely:

1. **Messaging follows friendship.** `open_dm` refuses anyone who isn't an
   accepted friend, mirroring the direct-challenge rule. Strangers meet through
   the fair matcher, not a DM.
2. **You cannot answer your own invite** (403), and an invite can only be
   answered once (409 on the second attempt).
3. **Entry amounts are validated against `ENTRY_PRESETS_CENTS`.** A client that
   posts `entry_preset_cents: 777` gets a 422. The client never invents a value.
4. **Games are validated against the adapter registry.** Unknown game → 404.
5. **Bodies are trimmed and capped** at `MAX_MESSAGE_CHARS` (2000). Whitespace-only
   is a 422, not an empty bubble.
6. **A message is either a body or an invite, never both and never neither** —
   the router rejects the ambiguous shape up front.
7. **Invites go to a friend, not to support.** A `support` thread takes text only.
8. **Sending is reading.** Posting into a thread also advances your own cursor, so
   you are never badged for your own message.
9. **Friendship is checked on every write, not just at creation** (§10.1).
   `_assert_writable` re-runs `are_friends` before any line or card is appended
   to a `dm`. Removing or **blocking** someone closes the thread to new messages
   from *both* sides (403), while the transcript stays readable — evidence for a
   dispute survives, the channel does not. Without this, rule 1 would only have
   been true for the first message.
10. **Chat never opens a channel the friendship rule would refuse** (§10.2). A
   *rematch* challenge is allowed against a non-friend (`create_direct` exempts
   it), so `post_challenge_invite` returns `None` rather than creating a DM with
   a stranger; that pair still gets the notification and the Inbox Respond pill.

`chat_service` flushes and never commits — the caller owns the transaction, same
as every other service in the codebase.

---

## 5. API surface

All under `/api/v1/chat`. Reading any chat surface bumps the presence heartbeat,
like `/friends` and `/notifications` do.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/conversations` | The list + `unread_total` |
| `POST` | `/conversations` | Get-or-create: `{user_id}` for a DM, `{kind:"support"}` for support |
| `GET` | `/conversations/{id}` | One thread (conversation header + last 200 messages, oldest→newest) |
| `POST` | `/conversations/{id}/messages` | Send `{body}` **or** `{invite}`; returns the refreshed thread |
| `POST` | `/conversations/{id}/read` | Advance the cursor; returns the new `unread_total` |
| `POST` | `/messages/{id}/respond` | `{action: "accept" \| "decline"}` on an invite card |

Two shapes are worth knowing:

**Send returns the whole thread, not the created message.** The client paints the
server's transcript directly (`qc.setQueryData`) instead of reconciling an
optimistic bubble against a later poll. Simpler, and it means server-side
side-effects — a support auto-reply, the read-cursor bump — appear immediately.

**Respond returns `{message, match_id, redirect_path}`.** `match_id` is set when
an accepted head-to-head formed a PENDING match; `redirect_path` is where the
client should navigate (`/play`, `/pools`, `/tournament`). The server decides the
destination so a new invite kind doesn't require a client change.

> **Regeneration note.** `packages/api-client` is generated from the OpenAPI
> spec. Two Pydantic models sharing a class name across schema modules produce
> ugly `moneymatch_api__schemas__*__X` component names, which is why the chat
> mark-read response is `ChatReadResponse` and not a second `MarkReadResponse`.

---

## 6. Invites — the interesting part

An invite is a message whose `payload` is the whole contract:

```jsonc
{
  "invite_kind": "pool" | "tournament" | "h2h",
  "game": "cs2.faceit",
  "entry_cents": 1000,
  "metric": "cs2_kd_ratio",      // pool/tournament
  "difficulty": "medium",        // pool
  "market": "kd_ratio",          // h2h
  "market_label": "K/D ratio",   // h2h
  "challenge_id": "…",           // h2h — the real `challenges` row
  "friendly": false,             // h2h — zero-rake (pair past the rake cap)
  "status": "pending",           // → accepted | declined | expired
  "match_id": "…",               // set once an accepted h2h forms a match
  "title": "Head-to-head · K/D ratio",
  "redirect_path": "/play"
}
```

There are **two tiers**, and the distinction is the important thing:

### Tier 1 — head-to-head: a real, binding invite

An `h2h` card **wraps an existing `challenges` row**. It is not a copy or a
notification; it points at the same aggregate the Inbox's Respond pill points at.
Accepting it in chat calls `challenge_service.accept_direct`, which forms the
PENDING match through the normal lifecycle (both confirm → escrow → activate).

`challenge_service.create_direct` now posts that card into the pair's DM,
opening the thread if it doesn't exist yet:

```
alice challenges bob
        │
        ├─→ notifications.emit("challenge_received")     ← the feed (unchanged)
        └─→ chat_service.post_challenge_invite(...)      ← the card in their DM
```

Because a challenge can be answered from three places (the chat card, the Inbox
pill, an invite link) and can also expire on its own, the card would go stale.
So the challenge service calls `chat_service.note_challenge_resolved(...)` at
every terminal transition — accept, decline, and the expiry worker:

```
       ┌──────────── accept (chat card) ──────────┐
       │                                          ▼
   pending ──── accept (Inbox pill / link) ──→ accepted  (+ match_id)
       │
       ├──────── decline (either surface) ──→ declined
       │
       └──────── expiry worker ─────────────→ expired
```

`note_challenge_resolved` is deliberately **exception-swallowing**. A stale chat
card is a cosmetic problem; it must never fail a challenge accept that is about
to move money.

### Tier 2 — pool / tournament: a nudge with a destination

There is no "pool invite" concept in the backend — solo pools and tournaments are
browse-and-join surfaces, not invitations. Rather than invent an aggregate, a
pool/tournament card records **what was suggested** (game, entry, metric,
difficulty) and hands the accepter a `redirect_path` to the tab where the room is
actually joined. Accepting stamps the card and navigates; it does not escrow
anything. This matches the owner's framing — "for now it can just be a button
that redirects to those tabs" — while still leaving a real, stateful artifact in
the conversation.

If pool/tournament invites later become binding (see §11), the card's payload is
already the right shape: add a `pool_id`, and `respond_invite` grows one branch.

### The composer path

The `+` button beside the typing bar opens a three-item menu:

- **Solo pool** / **Tournament** → `InviteSheet`: pick game, difficulty (pools),
  and entry preset. Primary action posts the card; the secondary **"Open Solo
  Pools ↗"** button is the plain redirect.
- **Head-to-head** → the existing `ChallengeDialog`, pre-targeted at the peer. It
  sends a real challenge, which lands back in the thread as a card via the hook
  above. No new code path — the chat just reuses the challenge flow.

Every response also appends a `system` line ("bob accepted the solo pool
invite."), so the transcript reads as a conversation rather than a card silently
changing color.

---

## 7. Frontend behavior

### Data flow

All server state lives in TanStack Query — there is no chat store.

| Query | Key | Refetch | Why |
| --- | --- | --- | --- |
| `useConversations` | `['chat','conversations',uid]` | 15 s | Matches the notifications feed's cadence |
| `useThread` | `['chat','thread',uid,cid]` | 6 s | The surface you're watching; needs to feel live |

Mutations (`useSendMessage`, `useRespondInvite`, `useMarkConversationRead`,
`useOpenConversation`) invalidate the list, and the send mutation writes the
returned thread straight into the cache.

**This is polling, not realtime.** It is the same mechanism the rest of the app
already uses, it needs no new infrastructure, and at 6 s a conversation feels
responsive enough to demo. It is also the first thing to replace — see §11.

### Details that make it feel like a chat app

- **Message runs.** `startsRun()` shows an avatar only when the sender changes or
  five minutes pass, so a burst reads as one block.
- **Day dividers.** "Today" / "Yesterday" / "Tue, Jul 28", inserted whenever the
  calendar date changes between two messages.
- **Scroll pinning.** An effect scrolls the bottom sentinel into view on message
  count change. It calls `scrollIntoView?.()` — optional-chained because jsdom
  doesn't implement it and the same component renders in tests.
- **Draft isolation.** The composer clears its draft when `conversationId`
  changes, so a half-typed line never follows you into someone else's thread. On
  a send failure the draft is restored rather than lost.
- **Enter sends, Shift+Enter newlines.**
- **Deterministic avatars.** Initials over an accent hashed from the name, so the
  same person looks identical in the list and the header. Lime is reserved for the
  platform (support/system); people cycle through five other accents.
- **Presence.** Green/grey ring on the avatar, from the existing `last_seen_at`
  heartbeat. Support is always "on" with a "usually replies within a few hours"
  subline — honest about being asynchronous.

### Entry points into a thread

- The Inbox list itself.
- **Friends tab → Message** on any friend row, which navigates to
  `/social?tab=inbox&dm=<user_id>`. `ChatPanel` consumes the `dm` param, opens (or
  creates) that DM, selects it, and strips the param so a refresh doesn't re-fire.
  `SocialPage` grew an effect so a later `?tab=` change is honored while the page
  is already mounted.
- **New message** button → `NewMessageSheet`, a searchable friend picker.

### Unread surfacing

One number, `useInboxUnread()` = chat unread + notification unread, feeds every
badge in the app:

- the **Inbox sub-tab** (`SubTabs` gained an optional `badge?: number`), and
- the sidebar / mobile **bell dot**.

The bell used to read `unread_notifications` from `/me`, which is fetched once
per session and never refetched — so a DM that arrived while you were on
`/wallet` lit nothing. `useInboxUnread` composes the two *polling* queries
(15 s each), so the dot is live from any page and clears the moment the thread
is opened. `/me.unread_notifications` is now unused by the web app; it stays on
the API for other clients.

Ordering: **Inbox is the first Social sub-tab and the default**. Messages and
notifications are what you come to this section to check; the leaderboard is a
browse.

---

## 8. Mock data

The owner asked for something to play with. Rather than a separate seed command,
the fixtures hang off **demo login** (`POST /api/v1/demo/login` →
`_ensure_demo_social`), so clicking "Skip sign-up · enter the demo" lands on a
populated Inbox with zero extra steps.

What it creates, once, guarded on "does this user have any conversation yet":

- **Three friends** — `s1mple_fan`, `chocoTaco`, `kvem_` — reused from the demo
  Activity history, so the people you have matches against are the people you can
  talk to. One is seeded online, two offline.
- **Three DM threads**, ~20 messages, **backdated** across several days via an
  explicit `created_at` so the day dividers are real.
- **Five invite cards** covering every visual state: an accepted pool invite, a
  pending tournament invite you sent, a pending pool invite you received, a
  declined hard-ADR pool invite, and —
- **One live head-to-head challenge** created through
  `challenge_service.create_direct`. It is a genuine `challenges` row: accept it
  in chat and a real PENDING match forms.
- **A support thread**: greeting → your question → auto-ack → an agent follow-up.

Two robustness notes, both learned the hard way:

- The friendship insert is guarded **independently** of the conversation check.
  `uq_friendships_pair` covers the pair in one direction, so a pre-existing
  friendship (added by hand, or left behind after clearing threads) used to 500
  the whole demo login.
- The challenge creation is wrapped in `try/except APIError` — if the CS2 game
  flag is off, the threads still seed.

**To reset the mock data**, delete the demo user's conversations; the next demo
login re-seeds them:

```sql
DELETE FROM conversations
 WHERE id IN (SELECT conversation_id FROM conversation_members WHERE user_id = :demo);
```

(`ON DELETE CASCADE` takes the members and messages with it.)

---

## 9. Tests and verification

`apps/api/tests/test_chat.py` — 9 tests, covering the rules that would actually
break something:

| Test | Guards |
| --- | --- |
| `test_dm_requires_friendship` | Strangers can't open a thread (403) |
| `test_send_and_read_a_dm` | Trimming, `mine`, unread appears for the peer, mark-read is idempotent |
| `test_outsiders_cannot_see_or_post` | A third party gets 404 on read *and* write |
| `test_empty_message_and_ambiguous_body_are_rejected` | Whitespace-only and neither-body-nor-invite |
| `test_pool_invite_card_round_trip` | Card fields, self-accept 403, double-answer 409, the system line |
| `test_invite_rejects_a_non_preset_entry` | The client can't invent an amount |
| `test_a_challenge_lands_in_the_dm_and_accepting_it_there_forms_a_match` | The h2h tier end-to-end |
| `test_declining_a_challenge_elsewhere_stamps_the_chat_card` | No stale pending cards |
| `test_support_thread_greets_and_acknowledges` | Get-or-create, greeting, auto-ack, invites refused |
| `test_unfriending_closes_the_thread_to_new_messages` | Both sides 403 after a remove/block; the transcript still reads |
| `test_a_challenge_to_a_non_friend_opens_no_dm` | A rematch never manufactures a stranger DM |

`apps/web/src/pages/InboxPage.test.tsx` covers the chat shell (feed pinned and
selected first, opening a thread, the invite card's Join action, the invite menu);
`components/NotificationsFeed.test.tsx` is the original Inbox test, moved with the
component so the feed's behavior stays pinned down;
`components/AppShell.test.tsx` pins the bell dot to the live inbox count.

`apps/web/e2e/chat.spec.ts` is the two-browser proof, and it is the only thing
that exercises what unit tests structurally cannot: two independent sessions, the
poll loop, the unread cursor across them, and a chat invite forming a real match.
It **skips** unless `E2E_AUTH=1` — see `e2e/README.md` for the stack it needs.

Verified on 2026-07-31: **745 backend tests pass**, ruff + mypy clean,
`alembic check` reports no model/migration drift; **71 web tests pass**, typecheck
+ eslint clean. Additionally exercised live against a running API: sent a message,
sent an invite card, accepted the seeded head-to-head and confirmed a real PENDING
match, and confirmed the support auto-ack.

Re-verified on 2026-08-02 after the integration pass below: **72 web tests pass**,
typecheck + eslint clean; ruff + mypy clean on the API. The two new backend tests
were **not executed** — that machine has no Postgres, and the suite needs a real
one (citext/jsonb). Run `make test` before merging.

---

## 10. The integration pass (2026-08-02)

The system above was correct in isolation. This pass asked a different question:
**does it behave when the rest of the app moves around it?** — someone unfriends
you, a rematch names a stranger, you're on a different page, you close the tab.
Five things came out of it. Four were gaps; one was an ordering change the owner
asked for directly.

Nothing here changed the data model, the API shape, or the generated client. It
is all rules and wiring.

### 10.1 Friendship is now checked on every write, not once at creation

**The gap.** `open_dm` refused a non-friend, so a thread could only be *born*
between friends. But `send_text` and `send_invite` only checked `_membership` —
"are you in this conversation". Membership never expires. So:

```
alice & bob become friends  →  thread exists
bob blocks alice            →  friendship row flips to `blocked`
alice sends a message       →  delivered.  ← the hole
```

`friendships.state` has had a `blocked` value since Phase 5, and chat simply
never consulted it. Unfriending had the same effect. For a wagering product where
friends are also the #1 collusion vector, "block does nothing" is not a cosmetic
bug.

**What it does now.** One guard, `_assert_writable`, runs before any append to a
`dm` and returns the peer id as a side benefit (the push in §10.3 needs it):

```python
async def _assert_writable(session, user, conversation) -> uuid.UUID | None:
    if conversation.kind != "dm":
        return None                      # support has no second member
    peer_id = await _peer_id(session, conversation.id, user.id)
    if not await friends_service.are_friends(session, user.id, peer_id):
        raise ChatError("not_friends", "…this thread is closed.", status_code=403)
    return peer_id
```

Both `send_text` and `send_invite` call it. It is symmetric on purpose: after a
block, *neither* side can post — the blocker doesn't get a one-way megaphone.

**Writes are gated; reads are not.** A closed thread still loads in full. That is
deliberate, and it is the one place this decision could be argued either way:

| | Keep reads | Hide the thread |
| --- | --- | --- |
| Dispute evidence | Survives | Gone, and chat is exactly where "you take this one" gets typed |
| Feels like | "This conversation ended" | "This person never existed" |
| Chosen | ✅ | |

If a blocked pair should lose read access too, that's a product call, not a
missing implementation — it's noted in §11.5.

**Deliberately not gated:** `respond_invite`. Answering an invite you already
received is not a new message, and gating it would strand a pending card forever
with no way to decline it. The h2h branch still runs `challenge_service`'s own
authorization, so nothing binding slips through.

### 10.2 A rematch no longer manufactures a DM with a stranger

**The gap.** `create_direct` deliberately exempts rematches from the friends-only
rule — you should be able to run it back with someone the matcher paired you
with, without adding them. Fine on its own. But the mirroring hook added in §6,
`post_challenge_invite`, called `_open_dm`, which creates unconditionally:

```
matcher pairs alice with a stranger  →  match settles
alice hits Rematch                   →  create_direct (allowed, no friendship)
                                     →  post_challenge_invite → _open_dm
                                     →  a permanent DM thread with a stranger
```

Combined with §10.1's *old* behavior, that thread was then writable forever. The
friends-only rule was being routed around by a feature that had no intention of
doing so.

**What it does now.** `post_challenge_invite` returns `Message | None` and mirrors
only into a thread that is legitimate:

```python
if await friends_service.are_friends(session, challenger.id, challengee_id):
    conversation = await _open_dm(...)     # friends: open it if needed
else:
    conversation = await _find_dm(...)     # not friends: only if one already exists
if conversation is None:
    return None                            # nothing to mirror into — that's fine
```

The rematch still works exactly as before; the challenge simply lands where it
always did, in the notification feed and the Inbox Respond pill. The caller
ignores the return value, and the invariant holds again: **chat never opens a
channel the friendship rule would refuse.**

### 10.3 Messages now reach you when you're not looking at the Inbox

Two separate holes with the same symptom: a message arrives and nothing tells you.

**The bell.** `SidebarNav` and `MobileTopBar` read `me.data.unread_notifications`.
`useMe` has no `refetchInterval` — it is fetched once per session. So the dot was
stale even for *notifications*, and it never counted messages at all. A DM landing
while you sat on `/wallet` lit nothing anywhere in the app.

The fix composes the two queries that already poll, instead of adding a field to
the un-polled `/me`:

```ts
export function useInboxUnread(): number {
  const chat = useConversations();          // polls 15 s
  const notifications = useNotifications(); // polls 15 s
  return (chat.data?.unread_total ?? 0) + (notifications.data?.unread ?? 0);
}
```

One number now drives the sidebar dot, the mobile top-bar dot, and the Inbox
sub-tab badge — they can't disagree, and it clears the instant a thread is opened
because `useMarkConversationRead` invalidates the same query key. TanStack Query
dedupes by key, so mounting this in the nav costs **no extra requests** on the
Social page. `/me.unread_notifications` is now unused by the web app; it stays on
the API for other clients.

**Push.** `push_service` and VAPID already existed, but only
`notifications_service.emit` used them, and messages don't emit notifications
(see below). So closing the tab meant never finding out.

`chat_service._push_to_peer` pushes DMs directly, deep-linked to the sender's
thread. The interesting part is the flood control — **presence, not a timer**:

```python
if peer is None or friends_service.is_online(peer.last_seen_at):
    return          # they're in the app; their Inbox will badge in ≤15 s
```

`last_seen_at` is the same heartbeat that draws the presence dot, bumped by every
polled social surface. So the rule reads: *you only get pushed when a push is the
only thing that could reach you.* A back-and-forth conversation between two
online people produces zero pushes; a message to someone who left produces one.
That is strictly better than a debounce window, which would have to guess.

It is best-effort and swallows exceptions, the same contract as
`note_challenge_resolved` — a failed push must never fail a send.

**Why a message does not create a notification row.** The obvious implementation
was a `message_received` kind in `notifications_service`, which would have gotten
push and the bell for free. It was rejected:

- **Double-render.** Every message would appear twice — a feed row *and* a
  thread line — in the same Inbox, two rows apart.
- **Two mark-read paths that must agree.** The feed marks read on view; a thread
  marks read on open. A message present in both has two independent cursors and
  no correct answer for what happens when you read one and not the other.
- **The feed is for events, not correspondence.** `settled`, `match_found`,
  `challenge_received` are things that happened *to* you and are done. A
  conversation isn't.

The cost of that choice is one extra query in the nav (`useConversations`), which
was already running on the Social page. Revisit only if messages need to persist
in the feed for some other reason.

### 10.4 A thread that won't open now says why

`ChatPanel`'s `?dm=<user_id>` deep link swallowed its rejection
(`() => { /* the list still works */ }`). The realistic path to that error is
narrow but exact: **Friends tab → Message, on someone who removed you between
your page load and your click** — precisely the case §10.1 made possible. You'd
get a button that does nothing.

The mutation error is now held in `ChatPanel` state and rendered in one of two
places depending on where the attempt came from — the friend picker sheet if it's
open (`NewMessageSheet` grew an `error` prop; it previously had a comment
claiming its mutation state showed the copy, and nothing rendered it), otherwise
a `role="alert"` line under the Inbox rail header. The server's message comes
through as-is, because every API error is `{code, message, detail}` and
`useChat`'s `messageOf()` reads `.message`.

### 10.5 Inbox leads the Social section

Owner's ask, and it matches the section's purpose: messages and notifications are
things addressed to *you*; the leaderboard is a browse. `SocialPage`'s `TABS`
array and the `SubTabs` list both put `inbox` first, and it is the fallback when
`?tab=` is absent or unrecognized.

### What changed, by file

| File | Change |
| --- | --- |
| `services/chat_service.py` | `_peer_id`, `_assert_writable`, `_push_to_peer`; `send_text` / `send_invite` gated + pushing; `post_challenge_invite` → `Message \| None` |
| `tests/test_chat.py` | +2 tests (unfriend closes the thread; a non-friend challenge opens no DM) |
| `hooks/useChat.ts` | `useInboxUnread()` |
| `ui/SidebarNav.tsx`, `ui/MobileNav.tsx` | Bell dot reads the live count instead of `/me` |
| `pages/SocialPage.tsx` | Inbox first + default; uses the shared count |
| `chat/ChatPanel.tsx`, `chat/ConversationList.tsx`, `chat/NewMessageSheet.tsx` | Surface a failed open |
| `components/AppShell.test.tsx` | +1 test pinning the bell to the live count |
| `e2e/chat.spec.ts` | New: the two-browser proof (§9) |

Unchanged, deliberately: the three tables, `0017_chat.py`, `schemas/chat.py`, the
router, and `packages/api-client`. No migration, no client regeneration.

---

## 11. What's next

Ordered by what actually bites first.

### Near term

1. **Replace polling with a live stream.** A 6-second poll is the single biggest
   thing separating this from a real chat app, and it costs a query per open
   thread per client. Server-Sent Events is the right fit: the API is already
   stateless, the payload is one-directional (server → client), and SSE survives
   proxies that WebSockets don't. Publish over Postgres `LISTEN/NOTIFY` so any API
   replica can fan out. Keep the polling path as the fallback.
2. ~~**Push + bell for messages.**~~ **Done (2026-08-02) — see §10.3.** Both
   halves landed, deliberately *without* the `message_received` notification kind
   this entry originally proposed; the argument against it is in §10.3.
3. **Pagination.** Threads load the last 200 messages and stop. Add a cursor
   (`before=<created_at>`) and an infinite-scroll trigger at the top of the
   transcript before any thread realistically passes 200.
4. **Rate limiting on sends.** The global `RateLimitMiddleware` applies, but
   messaging deserves its own per-conversation budget. Chat is the cheapest
   surface to abuse on the platform.

### Safety and moderation — needed before real users, not after

5. **Block and report.** *Block is done (2026-08-02) — see §10.1:* a blocked or
   removed pair's thread goes **read-only** in both directions. Still open:
   **report**, a per-message action feeding the admin surface, and the product
   call on whether a blocked pair should lose *read* access too (they keep it
   today, which is what preserves the evidence).
6. **Retention and disclosure.** Decide how long messages live and say so in the
   ToS. Two forces pull against each other: collusion investigations want the
   history (chat is where "you take this one, I'll take the next" gets typed —
   see the launch plan's §5.4 posture on friends as the #1 collusion vector), and
   privacy law wants a deletion path. Pick a window, document it, enforce it in a
   nightly job.
7. **Chat as a risk signal.** `risk_detectors` should see message metadata —
   pairs who only ever talk right before a rake-bearing contest are worth a flag.
   Metadata first (who, when, how often), content only if the flag is real.

### Support, properly

8. **An agent-side inbox.** Today `support` threads auto-ack on *every* user
   message and no human can reply — there is no admin UI for it, and platform
   messages are written with `sender_id IS NULL` by the service alone. The
   schema is ready; what's missing is `/admin/support` (list open threads, reply,
   resolve), an agent identity on the message so replies aren't anonymous, and
   replacing the blanket auto-ack with a first-message-only acknowledgement.
9. **Link a thread to a dispute.** `disputes` is polymorphic already; a support
   thread about a contest should carry the contest id so the agent has context
   without asking.

### Product depth

10. **Make pool/tournament invites binding.** Let the sender pick an actual open
    room (`GET /pools/open`) so accepting joins it directly — escrow, fairness
    gates and all — instead of redirecting. The payload shape already anticipates
    this; the work is a room picker in `InviteSheet` and one branch in
    `respond_invite`.
11. **Group threads for pools and tournaments.** `conversations.kind` is a
    string and membership is already many-to-many, so a `room` kind is a small
    change: every member of a locked pool gets a thread for the window's duration.
    This is the highest-value retention feature in the list.
12. **The expected niceties** — typing indicators, read receipts, message search,
    emoji reactions, image attachments (needs object storage + scanning, so it is
    genuinely bigger than it looks).
13. **A Playwright e2e** alongside `e2e/invite.spec.ts`: two browsers, one sends,
    the other receives and accepts.
