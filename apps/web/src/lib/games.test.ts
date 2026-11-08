import { describe, expect, it } from 'vitest';

import { CHESS, gameMeta } from './games';

describe('gameMeta', () => {
  it('names chess', () => {
    expect(gameMeta(CHESS).name).toBe('Chess');
  });

  it('falls back readably for a game it has never heard of', () => {
    expect(gameMeta('valorant.riot', 'Valorant — Riot').name).toBe('Valorant');
  });
});
