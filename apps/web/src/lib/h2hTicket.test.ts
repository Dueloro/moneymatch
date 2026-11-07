import { beforeEach, describe, expect, it } from 'vitest';

import { recallTicket, rememberTicket } from './h2hTicket';

const store = new Map<string, string>();
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  },
});

describe('h2h ticket memory', () => {
  beforeEach(() => store.clear());

  it('recalls what was queued, per user, until the ticket would have expired', () => {
    const t = { speed: 'blitz', entry_cents: 1000, rating: 1712, at: 1_000 };
    rememberTicket('u1', t);
    expect(recallTicket('u1', 2_000)).toEqual(t);
    expect(recallTicket('u2', 2_000)).toBeNull();
    expect(recallTicket('u1', 1_000 + 12 * 60_000)).toBeNull();
  });

  it('ignores junk', () => {
    store.set('mm.h2h.ticket.u1', '{nope');
    expect(recallTicket('u1')).toBeNull();
  });
});
