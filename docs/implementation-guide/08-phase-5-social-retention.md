# Phase 5 — Social & Retention Surfaces

**Objective:** friends, direct challenges + invite links, the Inbox, and the
Leaderboard — the liquidity and return-trigger layer (a P2P platform must be
able to *summon* opponents; see `docs/business/business-and-competition.md` §3).

**Depends on:** Phase 3. Parallel with Phase 4.

---

## Deliverables

1. Migrations: `friendships`, `challenges`, (extend) `notifications`.
2. **Friends service + endpoints**: add by username (exact match on MoneyMatch
   handle, never host-game accounts — don't leak linkage) or by **friend code**
   (short immutable code like `MM-7F3K2Q` on Profile; the design's "Add by
   username or code" input) — codes avoid a scrapeable public directory.
   Request/accept/decline/block; caps (500 friends, 20 pending outbound);
   presence-lite (`last_seen_at` heartbeat; green dot = active in last 5 min).
   No chat at MVP.
3. **Challenges** (the design's "Invite friend" slip + Friends "Challenge" pill):
   - Direct: challenger picks market + entry preset → challengee gets an inbox
     notification + Respond → accept creates a `match` (PENDING) through the
     same lifecycle service (both confirm → escrow → activate).
   - **Collusion posture for friends** (launch plan §5.4 — friends are the #1
     collusion vector; design for it): **rake-bearing contests between the
     same pair are capped** (config: 3/day, 10/week — friends included);
     beyond the cap, offer a **friendly**: unlimited, zero-rake,
     leaderboard-excluded, entry refunded on settle. Controls bite the money
     flow, not the fun. Friends may also play **across skill bands/forecast
     windows** — allowed with honest disclosure on the card ("heavily
     favored") instead of blocking; fairness protection exists for strangers,
     consenting friends choose their own risk.
   - **Invite link**: `POST /challenges` without a challengee returns
     `invite_token` + URL (`/i/{token}`). Public preview page (market, entry,
     challenger name) → sign-in/sign-up → link required game → accept. This is
     the acquisition loop from `docs/business/gtm-prelaunch.md` §3.2 — treat
     the funnel as first-class (instrument every step).
   - Expiry 24 h; decline/expire notifies the challenger.
4. **Inbox screen** (PDF p.11): notification rows (unread green dot, age,
   action pills — View → deep link to match/pool, Respond → challenge accept
   flow). Bell in sidebar shows unread dot. Mark-read on view.
5. **Leaderboard** (PDF p.7, under the Tournament section's sub-tabs):
   `GET /leaderboard` ranks **real users** by ROI (net / staked, ≥3 settled
   contests to qualify) over a rolling 30 days. The PoC's seeded bot field is
   gone. You-row highlighted. Port the ROI/ranking math from
   `poc-reference/api/_lib/leaderboard.py` + the PoC's client-side merge logic,
   but computed server-side from the ledger.
6. **Rematch**: one-tap rematch button on settled H2H rows in Activity —
   creates a challenge to the same opponent (subject to the same checks).
7. Notification fan-out consolidated: every lifecycle event writes
   `notifications` rows (match_found, settled, refund, challenge_received,
   challenge_accepted, friend_request, room_filled). Email/push are post-MVP;
   the table schema carries a `channel_sent jsonb` for it.

## Reuse from `poc-reference/`

| What | From | Change |
| --- | --- | --- |
| ROI leaderboard math | `api/_lib/leaderboard.py` | real users from ledger, not seeded bots |
| Head-to-head record display | PoC Profile "My Contests" (`frontend/src/hooks/useContracts.ts` derived lists) | becomes per-opponent record on Friends rows (optional) |
| Toast patterns | `frontend/src/hooks/useToasts.ts` | port |

## Tests required

- Friendship state machine (duplicate requests, blocked users, self-add rejected).
- Challenge: full accept path creates a correct PENDING match; decline/expiry
  notify; invite token is single-use, expires, and survives the
  sign-up-then-accept flow; challenge to an unlinked-game user prompts linking.
- Leaderboard: qualification threshold, ROI math against ledger fixtures,
  rolling window boundary.
- Notifications: unread counts; mark-read idempotent.
- e2e: user A sends invite link → user B (fresh signup) accepts → both confirm
  → fixture settle → both inboxes correct.

## Exit criteria

- [x] Friends/Inbox/Leaderboard match PDF p.7, 8, 11. — `FriendsPanel`,
      `LeaderboardPanel`, `InboxPage` under the Tournament sub-tabs + sidebar bell
      dot (component tests: `FriendsPanel.test.tsx`, `LeaderboardPanel.test.tsx`,
      `InboxPage.test.tsx`).
- [x] Invite-link funnel works for a brand-new user end-to-end and every step
      emits an analytics event. — public `/i/:token` preview → sign-in (return-to)
      → link → accept, with `invite_created/viewed/accepted` telemetry;
      `test_challenge_service.py` proves single-use token, expiry, and the
      fresh-signup accept; e2e in `apps/web/e2e/invite.spec.ts` (needs the
      test-auth seam — see BACKLOG).
- [x] A settled match can be rematched in two clicks. — Rematch pill on terminal
      H2H Activity rows → `POST /challenges {rematch_of}` (`test_challenges_endpoints.py`
      `test_rematch_recreates_challenge`).
