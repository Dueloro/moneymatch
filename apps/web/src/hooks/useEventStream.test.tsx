import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { isStreamConnected, queuePollMs } from '../lib/streamStatus';
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
  onopen: (() => void) | null = null;
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
    expect(es.url).toBe('http://api.test/api/v1/events/stream?ticket=tk1');
    expect(es.url).not.toContain('tok');
    expect(fetch).toHaveBeenCalledWith('http://api.test/api/v1/events/ticket', {
      method: 'POST',
      headers: { Authorization: 'Bearer tok' },
    });

    es.emit(JSON.stringify({ user_id: 'u1', kind: 'settled' }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['activity'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['pool-status'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['tournament-status'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['wallet'] });
  });

  it('reports the stream as connected only while it is open', async () => {
    const { view } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    expect(isStreamConnected()).toBe(false);

    es.onopen?.();
    expect(isStreamConnected()).toBe(true);
    es.onerror?.();
    expect(isStreamConnected()).toBe(false);

    es.onopen?.();
    view.unmount();
    expect(isStreamConnected()).toBe(false);
  });

  it('slows the queue poll only for an idle player with a live stream', () => {
    expect(queuePollMs('idle', true)).toBe(15_000);
    expect(queuePollMs('idle', false)).toBe(2000);
    expect(queuePollMs('searching', true)).toBe(2000);
    expect(queuePollMs('matched', true)).toBe(2000);
    expect(queuePollMs(undefined, true)).toBe(2000);
  });

  it('closes the stream on unmount', async () => {
    const { view } = setup();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0];
    view.unmount();
    expect(es.closed).toBe(true);
  });
});
