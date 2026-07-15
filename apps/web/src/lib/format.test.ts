import { describe, expect, it } from 'vitest';

import {
  formatCurrency,
  formatPct,
  formatRelativeTime,
  formatSignedCurrency,
} from './format';

describe('formatCurrency', () => {
  it('formats cents exactly with thousands separators', () => {
    expect(formatCurrency(102394)).toBe('$1,023.94');
    expect(formatCurrency(0)).toBe('$0.00');
    expect(formatCurrency(5)).toBe('$0.05');
    expect(formatCurrency(100000)).toBe('$1,000.00');
  });

  it('carries a leading minus on negatives', () => {
    expect(formatCurrency(-500)).toBe('-$5.00');
  });
});

describe('formatSignedCurrency', () => {
  it('shows an explicit + on positives', () => {
    expect(formatSignedCurrency(1800)).toBe('+$18.00');
    expect(formatSignedCurrency(-1800)).toBe('-$18.00');
    expect(formatSignedCurrency(0)).toBe('$0.00');
  });
});

describe('formatPct', () => {
  it('rounds a 0..1 share to a whole percent', () => {
    expect(formatPct(0.555)).toBe('56%');
  });
});

describe('formatRelativeTime', () => {
  const now = new Date('2026-07-15T12:00:00Z');
  it('bins recent times', () => {
    expect(formatRelativeTime('2026-07-15T11:59:50Z', now)).toBe('just now');
    expect(formatRelativeTime('2026-07-15T11:55:00Z', now)).toBe('5m ago');
    expect(formatRelativeTime('2026-07-15T09:00:00Z', now)).toBe('3h ago');
    expect(formatRelativeTime('2026-07-13T12:00:00Z', now)).toBe('2d ago');
  });
});
