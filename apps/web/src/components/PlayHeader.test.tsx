import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { introKey } from '../hooks/useHowItWorksIntro';
import { renderWithProviders } from '../test/testUtils';
import { PlayHeader } from './PlayHeader';

const auth = vi.hoisted(() => ({ userId: 'u1' as string | null }));
vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: auth.userId ? { user: { id: auth.userId } } : null }),
}));

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

const HOW = 'Winner takes the pot.';

function renderHeader() {
  return renderWithProviders(<PlayHeader id="play" how={HOW} />, { route: '/play' });
}

describe('PlayHeader', () => {
  beforeEach(() => {
    window.localStorage.clear();
    auth.userId = 'u1';
  });

  it('shows the explainer inline on the first visit and remembers it', () => {
    renderHeader();
    expect(screen.getByRole('note')).toHaveTextContent(HOW);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.localStorage.getItem(introKey('u1'))).toBe('1');

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /how it works/i })).toBeInTheDocument();
  });

  it('is closed on later visits until the trigger is pressed', () => {
    window.localStorage.setItem(introKey('u1'), '1');
    renderHeader();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /how it works/i }));
    expect(screen.getByRole('dialog')).toHaveTextContent(HOW);
  });

  it('shows once per user, not once per device', () => {
    window.localStorage.setItem(introKey('u1'), '1');
    auth.userId = 'u2';
    renderHeader();
    expect(screen.getByRole('note')).toBeInTheDocument();
  });

  it('respects a dismissal from the old per-page popover', () => {
    window.localStorage.setItem('mm.dismissed.howitworks.pools', '1');
    renderHeader();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});
