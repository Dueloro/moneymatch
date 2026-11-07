import { request, type APIRequestContext, type APIResponse } from '@playwright/test';

import { API_BASE, mintToken } from './auth';

/**
 * Test players built through the public API (no seed script): mint a token via
 * the `/dev/e2e/token` seam, finish the profile with `PATCH /me`, and, when a
 * Lichess handle is given, bind it with `POST /links`. Every step is idempotent
 * so a stable `authId` can be reused across runs.
 *
 * Linking verifies the handle against the live Lichess API, and a handle can be
 * bound to one account only, so reuse the same `authId` for the same handle.
 */

export const CHESS = 'chess.lichess';

export interface Player {
  authId: string;
  username: string;
  userId: string;
}

/** Real Lichess handles for the linked players, from the environment. */
export const LICHESS_A = process.env.E2E_LICHESS_A;
export const LICHESS_B = process.env.E2E_LICHESS_B;
export const lichessConfigured = (): boolean => Boolean(LICHESS_A && LICHESS_B);

/** The two linked players. A handle binds to one account, so every spec that
 * links uses these same ids. */
export const linkedA = () =>
  ensurePlayer({
    authId: process.env.E2E_AUTH_ID_A ?? 'e2e_linked_a',
    username: process.env.E2E_USERNAME_A ?? 'e2e_linked_a',
    lichess: LICHESS_A,
  });
export const linkedB = () =>
  ensurePlayer({
    authId: process.env.E2E_AUTH_ID_B ?? 'e2e_linked_b',
    username: process.env.E2E_USERNAME_B ?? 'e2e_linked_b',
    lichess: LICHESS_B,
  });

async function api(authId: string): Promise<APIRequestContext> {
  const token = await mintToken(authId);
  return request.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
}

async function json<T>(resp: APIResponse): Promise<T> {
  if (!resp.ok()) {
    throw new Error(`${resp.url()} → ${resp.status()}: ${await resp.text()}`);
  }
  return (await resp.json()) as T;
}

/** A short random suffix so per-run players never collide on username. */
export function runId(): string {
  return Math.random().toString(36).slice(2, 8);
}

/** Provision and onboard a player; link Lichess when `lichess` is set. */
export async function ensurePlayer(opts: {
  authId: string;
  username: string;
  lichess?: string;
}): Promise<Player> {
  const ctx = await api(opts.authId);
  try {
    let me = await json<{
      user: { id: string; username: string | null };
      needs_onboarding: boolean;
    }>(await ctx.get('/api/v1/me'));
    if (me.needs_onboarding) {
      await json(
        await ctx.patch('/api/v1/me', {
          data: {
            username: opts.username,
            residence_state: 'NY',
            dob_attested_18plus: true,
          },
        }),
      );
      me = await json(await ctx.get('/api/v1/me'));
    }

    if (opts.lichess) {
      const links = await json<{ games: { game: string; status: string }[] }>(
        await ctx.get('/api/v1/links'),
      );
      const chess = links.games.find((g) => g.game === CHESS);
      if (chess?.status !== 'LINKED') {
        await json(
          await ctx.post('/api/v1/links', {
            data: { game: CHESS, username: opts.lichess },
          }),
        );
      }
      // A leftover search from an earlier run would pair with the wrong ticket.
      await ctx.delete('/api/v1/play/queue');
    }

    return {
      authId: opts.authId,
      username: me.user.username ?? opts.username,
      userId: me.user.id,
    };
  } finally {
    await ctx.dispose();
  }
}

/** Make `a` and `b` friends (request + accept), if they are not already. */
export async function ensureFriends(a: Player, b: Player): Promise<void> {
  const ctxA = await api(a.authId);
  const ctxB = await api(b.authId);
  type Friends = { friends: { user_id: string }[]; incoming: FriendRow[] };
  type FriendRow = { friendship_id: string; user_id: string };
  try {
    const mine = await json<Friends>(await ctxA.get('/api/v1/friends'));
    if (mine.friends.some((f) => f.user_id === b.userId)) return;
    // 409: a request between the two already exists (e.g. from an earlier run).
    const add = await ctxA.post('/api/v1/friends', {
      data: { username_or_code: b.username },
    });
    if (!add.ok() && add.status() !== 409) {
      throw new Error(`add friend → ${add.status()}: ${await add.text()}`);
    }
    const theirs = await json<Friends>(await ctxB.get('/api/v1/friends'));
    const req = theirs.incoming.find((f) => f.user_id === a.userId);
    if (!req) throw new Error(`no friend request from ${a.username} to ${b.username}`);
    await json(await ctxB.post(`/api/v1/friends/${req.friendship_id}/accept`));
  } finally {
    await ctxA.dispose();
    await ctxB.dispose();
  }
}

/** Mint a shareable head-to-head invite link as `player`; returns its path. */
export async function createInviteLink(
  player: Player,
  opts: { speed?: string; entryCents?: number } = {},
): Promise<string> {
  const ctx = await api(player.authId);
  try {
    const body = await json<{ invite_path: string | null }>(
      await ctx.post('/api/v1/challenges', {
        data: {
          game: CHESS,
          market: 'win_h2h',
          speed: opts.speed ?? 'blitz',
          entry_preset_cents: opts.entryCents ?? 1000,
        },
      }),
    );
    if (!body.invite_path) throw new Error('challenge created without an invite path');
    return body.invite_path;
  } finally {
    await ctx.dispose();
  }
}

/** The player's available balance, in cents. */
export async function availableCents(player: Player): Promise<number> {
  const ctx = await api(player.authId);
  try {
    const wallet = await json<{ available_cents: number }>(
      await ctx.get('/api/v1/wallet'),
    );
    return wallet.available_cents;
  } finally {
    await ctx.dispose();
  }
}
