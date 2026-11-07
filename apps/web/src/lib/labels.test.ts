import { describe, expect, it } from 'vitest';

import { humanizeIds, ledgerLabel } from './labels';

describe('humanizeIds — no raw identifiers reach the player', () => {
  it('maps known metric ids inside a pool memo', () => {
    expect(humanizeIds('chess_accuracy easy pool entry')).toBe(
      'Chess accuracy easy pool entry',
    );
  });

  it('maps the H2H market id', () => {
    expect(humanizeIds('win_h2h entry')).toBe('Head to head entry');
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
    expect(humanizeIds('pool refund')).toBe('pool refund');
    expect(humanizeIds('Points added')).toBe('Points added');
  });
});

describe('ledgerLabel', () => {
  const row = (entry_type: string, ref_type = 'match', memo: string | null = null) => ({
    entry_type,
    ref_type,
    memo,
  });

  it('welcomes the signup grant and names top-ups', () => {
    expect(ledgerLabel(row('demo_deposit', 'demo_rail', 'signup grant'))).toBe(
      'Welcome points',
    );
    expect(ledgerLabel(row('demo_deposit', 'demo_rail', 'Add funds'))).toBe(
      'Points added',
    );
  });

  it('names stakes and winnings by contest type', () => {
    expect(ledgerLabel(row('escrow_hold', 'match', 'win_h2h entry'))).toBe(
      'Match stake',
    );
    expect(ledgerLabel(row('escrow_hold', 'solo_pool'))).toBe('Pool stake');
    expect(ledgerLabel(row('payout', 'tournament'))).toBe('Tournament winnings');
  });

  it('covers every entry type the API writes', () => {
    for (const type of [
      'demo_deposit',
      'demo_withdrawal',
      'escrow_hold',
      'escrow_release',
      'payout',
      'rake',
      'refund',
      'adjustment',
    ]) {
      expect(ledgerLabel(row(type, 'admin'))).not.toMatch(/_|\$|cash|funds/i);
    }
    expect(ledgerLabel(row('refund'))).toBe('Stake refunded');
    expect(ledgerLabel(row('rake'))).toBe('Platform fee');
  });
});
