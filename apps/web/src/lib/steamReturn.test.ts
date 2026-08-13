import { beforeEach, describe, expect, it } from 'vitest';

import { rememberSteamReturn, takeSteamReturn } from './steamReturn';

describe('steam return path', () => {
  beforeEach(() => sessionStorage.clear());

  it('brings you back to the page you left', () => {
    rememberSteamReturn('/activity');
    expect(takeSteamReturn()).toBe('/activity');
  });

  it('is consumed once, so a later visit is not redirected', () => {
    rememberSteamReturn('/activity');
    takeSteamReturn();
    expect(takeSteamReturn()).toBeNull();
  });

  it('returns null when nothing was remembered', () => {
    // The caller falls back to a default page rather than navigating nowhere.
    expect(takeSteamReturn()).toBeNull();
  });
});
