import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMe, useSetDismissedChecklists } from './useMe';

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
        username: 'player',
        email: 'player@example.com',
        friend_code: 'MM-TEST',
        residence_state: 'MA',
        dob_attested_18plus: true,
        role: 'user',
        status: 'active',
        member_since: '2026-01-01T00:00:00Z',
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

    act(() => result.current.dismiss.mutate('future.game'));

    // The write lands server-side (not localStorage).
    await waitFor(() => expect(server.dismissed).toEqual(['future.game']));
    expect(apiPatch).toHaveBeenCalledWith('/api/v1/me', {
      body: { dismissed_checklists: ['future.game'] },
    });

    const reloaded = renderMeWithDismiss(makeClient());
    await waitFor(() =>
      expect(reloaded.result.current.me.data?.user.dismissed_checklists).toEqual([
        'future.game',
      ]),
    );
  });

  it('hides the card optimistically, before the round-trip returns', async () => {
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);
    await waitFor(() => expect(result.current.me.data).toBeTruthy());

    act(() => result.current.dismiss.mutate('future.game'));

    await waitFor(() =>
      expect(result.current.me.data?.user.dismissed_checklists).toContain(
        'future.game',
      ),
    );
  });

  it('dismissing two cards in a row keeps both (no stale-closure race)', async () => {
    const client = makeClient();
    const { result } = renderMeWithDismiss(client);
    await waitFor(() => expect(result.current.me.data).toBeTruthy());

    act(() => {
      result.current.dismiss.mutate('chess.lichess');
      result.current.dismiss.mutate('future.game');
    });

    await waitFor(() =>
      expect(new Set(server.dismissed)).toEqual(
        new Set(['chess.lichess', 'future.game']),
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

    act(() => result.current.dismiss.mutate('future.game'));

    await waitFor(() => expect(result.current.dismiss.isError).toBe(true));
    expect(server.dismissed).toEqual([]);
    await waitFor(() =>
      expect(result.current.me.data?.user.dismissed_checklists).toEqual([]),
    );
  });
});
