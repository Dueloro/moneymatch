import { describe, expect, it } from 'vitest';

import { gameMeta } from './games';

describe('gameMeta', () => {
  it('names a live game', () => {
    expect(gameMeta('cs2.steam').short).toBe('CS2');
  });

  it('names a retired game that still appears in settled history', () => {
    // A contest keeps the id it settled under, so 'cs2.faceit' outlives the
    // integration. Rendering the raw id would leak a database value onto a
    // results card.
    expect(gameMeta('cs2.faceit').short).toBe('CS2');
    expect(gameMeta('cs2.faceit').name).not.toMatch(/faceit/i);
  });

  it('falls back readably for a game it has never heard of', () => {
    expect(gameMeta('valorant.riot', 'Valorant — Riot').name).toBe('Valorant');
  });
});
