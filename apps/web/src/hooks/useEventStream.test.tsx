import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useEventStream } from './useEventStream';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: { access_token: 'tok', user: { id: 'u1' } } }),
}));
vi.mock('../lib/env', () => ({ env: { apiBaseUrl: 'http://api.test' } }));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  emit(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
}

function setup() {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useEventStream(), { wrapper });
  return { invalidate, view };
}

describe('useEventStream', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource);
    // The ticket exchange: bearer token in the header, opaque ticket back.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => ({ ticket: 'tk1' }) })),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it('trades the token for a ticket and connects with it (never the token)', async () => {
    const { invalidate } = setup();

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    // The stream URL carries only the single-use ticket — not the access token.
    expect(es.url).toBe('http://api.test/api/v1/events/stream?ticket=tk1');
    expect(es.url).not.toContain('tok');
    // The token was sent in the ticket request's Authorization header.
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/v1/events/ticket', {
      method: 'POST',
      headers: { Authorization: 'Bearer tok' },
    });

    es.emit(JSON.stringify({ user_id: 'u1', kind: 'settled' }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['activity'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['pool-status'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['wallet'] });
  });

  it('closes the stream on unmount', async () => {
    const { view } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    view.unmount();
    expect(es.closed).toBe(true);
  });
});
