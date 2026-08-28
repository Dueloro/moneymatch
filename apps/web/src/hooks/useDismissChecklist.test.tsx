import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMe, useSetDismissedChecklists } from './useMe';

/**
 * These tests exercise the *real* dismiss path — the click → PATCH → cache →
 * reload chain — instead of stubbing the mutation. The previous coverage mocked
 * `useSetDismissedChecklists` to a bare `vi.fn`, so a broken write (or a card
 * that reappears on reload) sailed through green. Here only the transport
 * (`lib/api`) and auth are mocked; the mutation, cache, and `/me` refetch are
 * the code under test.
 */

// A stand-in server: the mocked PATCH persists here, the mocked GET reads back
// from here — so "reload" (a fresh QueryClient) genuinely re-reads server state.
const { server, apiGet, apiPatch } = vi.hoisted(() => {
  const server = { dismissed: [] as string[] };
  return {
    server,
    apiGet: vi.fn(async (): Promise<{ data: unknown; error: unknown }> => ({
      data: meResponse(server.dismissed),
      error: undefined,
    })),
    apiPatch: vi.fn(
      async (
        _path: string,
        opts: { body: { dismissed_checklists: string[] } },
      ): Promise<{ data: unknown; error: unknown }> => {
        // Simulate a real round-trip so concurrent dismisses can interleave.
        await new Promise((r) => setTimeout(r, 5));
        server.dismissed = opts.body.dismissed_checklists;
        return { data: meResponse(server.dismissed), error: undefined };
      },
    ),
  };

  function meResponse(dismissed: string[]) {
    return {
      user: {
        id: 'u1',
        username: 'demo',
        email: 'demo@dueloro.com',
        friend_code: 'MM-TEST',
        residence_state: 'MA',
        dob_attested_18plus: true,
        role: 'user',
        status: 'active',
        member_since: '2026-01-01T00:00:00Z',
        active_games: ['chess.lichess', 'cs2.steam'],
        dismissed_checklists: dismissed,
      },
      needs_onboarding: false,
      limits: null,
      unread_notifications: 0,
      getting_started: null,
      contested_games: [],
    };
  }
});

vi.mock('../lib/api', () => ({ api: { GET: apiGet, PATCH: apiPatch } }));
vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: { user: { id: 'u1' } } }),
}));

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapperFor(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

/** Render `/me` + the dismiss mutation together on one client, like the app. */
function renderMeWithDismiss(client: QueryClient) {
  return renderHook(() => ({ me: useMe(), dismiss: useSetDismissedChecklists() }), {
    wrapper: wrapperFor(client),
  });
}

describe('useSetDismissedChecklists — real dismiss → persist path', () => {
  beforeEach(() => {
    server.dismissed = [];
    apiGet.mockClear();
    apiPatch.mockClear();
  });

  it('dismissing a card writes through to the server and survives a reload', async () => {
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);

    await waitFor(() =>
      expect(result.current.me.data?.user.dismissed_checklists).toEqual([]),
    );

    act(() => result.current.dismiss.mutate('cs2.steam'));

    // The write lands server-side (not localStorage).
    await waitFor(() => expect(server.dismissed).toEqual(['cs2.steam']));
    expect(apiPatch).toHaveBeenCalledWith('/api/v1/me', {
      body: { dismissed_checklists: ['cs2.steam'] },
    });

    // Reload: a brand-new client with an empty cache must re-read the dismissal
    // from the server, proving it was persisted and not just optimistic.
    const reloaded = renderMeWithDismiss(makeClient());
    await waitFor(() =>
      expect(reloaded.result.current.me.data?.user.dismissed_checklists).toEqual([
        'cs2.steam',
      ]),
    );
  });

  it('hides the card optimistically, before the round-trip returns', async () => {
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);
    await waitFor(() => expect(result.current.me.data).toBeTruthy());

    act(() => result.current.dismiss.mutate('cs2.steam'));

    // Cache reflects the dismissal immediately — the PATCH has a 5ms delay, so
    // this can only be the optimistic update, which is what makes the X feel
    // like it did something on a slow connection.
    await waitFor(() =>
      expect(result.current.me.data?.user.dismissed_checklists).toContain('cs2.steam'),
    );
  });

  it('dismissing two cards in a row keeps both (no stale-closure race)', async () => {
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);
    await waitFor(() => expect(result.current.me.data).toBeTruthy());

    act(() => {
      result.current.dismiss.mutate('chess.lichess');
      result.current.dismiss.mutate('cs2.steam');
    });

    // The old code built the list from a stale `dismissed_checklists`, so the
    // second dismiss overwrote the first ([cs2] instead of [chess, cs2]) and a
    // card reappeared on reload. Both must persist.
    await waitFor(() =>
      expect(new Set(server.dismissed)).toEqual(
        new Set(['chess.lichess', 'cs2.steam']),
      ),
    );
  });

  it('rolls back the card on a failed write', async () => {
    apiPatch.mockImplementationOnce(async () => ({
      data: undefined,
      error: { detail: 'boom' },
    }));
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);
    await waitFor(() => expect(result.current.me.data).toBeTruthy());

    act(() => result.current.dismiss.mutate('cs2.steam'));

    // After the error settles, the dismissal is rolled back and the server was
    // never mutated — the card comes back rather than silently vanishing.
    await waitFor(() => expect(result.current.dismiss.isError).toBe(true));
    expect(server.dismissed).toEqual([]);
    await waitFor(() =>
      expect(result.current.me.data?.user.dismissed_checklists).toEqual([]),
    );
  });
});
