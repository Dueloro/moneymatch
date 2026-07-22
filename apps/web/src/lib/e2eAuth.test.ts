import { afterEach, describe, expect, it, vi } from 'vitest';

// Exercise the bypass with the flag ON; the OFF path is a trivial short-circuit.
vi.mock('./env', () => ({ env: { e2eAuth: true } }));

import { decodeJwtClaims, E2E_TOKEN_KEY, getE2eToken } from './e2eAuth';

function makeToken(payload: Record<string, unknown>): string {
  const body = btoa(JSON.stringify(payload));
  return `header.${body}.sig`;
}

describe('decodeJwtClaims', () => {
  it('extracts sub + email from a JWT payload', () => {
    const token = makeToken({ sub: 'seed_player1', email: 'p1@demo.test' });
    expect(decodeJwtClaims(token)).toEqual({
      sub: 'seed_player1',
      email: 'p1@demo.test',
    });
  });

  it('returns null when there is no subject', () => {
    expect(decodeJwtClaims(makeToken({ email: 'x@y.z' }))).toBeNull();
  });

  it('returns null for a malformed token', () => {
    expect(decodeJwtClaims('not-a-jwt')).toBeNull();
  });
});

describe('getE2eToken', () => {
  afterEach(() => window.localStorage.clear());

  it('returns the injected token when present', () => {
    window.localStorage.setItem(E2E_TOKEN_KEY, 'the-token');
    expect(getE2eToken()).toBe('the-token');
  });

  it('returns null when no token is injected', () => {
    expect(getE2eToken()).toBeNull();
  });
});
