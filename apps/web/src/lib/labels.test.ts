import { describe, expect, it } from 'vitest';

import { humanizeIds } from './labels';

describe('humanizeIds — no raw identifiers reach the player', () => {
  it('maps known metric ids inside a pool memo', () => {
    expect(humanizeIds('chess_accuracy easy pool entry')).toBe(
      'Chess accuracy easy pool entry',
    );
  });

  it('maps a short H2H market id', () => {
    expect(humanizeIds('kd_ratio entry')).toBe('K/D ratio entry');
  });

  it('maps a multi-word metric id', () => {
    expect(humanizeIds('chess_win_streak tournament entry')).toBe(
      'Longest win streak tournament entry',
    );
  });

  it('de-snakes an unmapped id rather than leaking underscores', () => {
    expect(humanizeIds('some_new_metric entry')).toBe('Some new metric entry');
  });

  it('leaves plain memos with no ids untouched', () => {
    expect(humanizeIds('pool refund (demo reset)')).toBe('pool refund (demo reset)');
    expect(humanizeIds('Added funds')).toBe('Added funds');
  });
});
