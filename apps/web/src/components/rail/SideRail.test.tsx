import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import { SideRail } from './SideRail';

// No session, so wallet/activity stay disabled and fall to their empty states.
// The tournament queue status is the thing under test, so drive it directly.
vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ isDemo: false, session: null }),
}));
vi.mock('../../hooks/useTournaments', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/useTournaments')>(
    '../../hooks/useTournaments',
  );
  return { ...actual, useTournamentStatus: vi.fn(), useLeaveTournament: vi.fn() };
});

import { useLeaveTournament, useTournamentStatus } from '../../hooks/useTournaments';

function mockStatus(s: unknown) {
  vi.mocked(useTournamentStatus).mockReturnValue({ data: s } as ReturnType<
    typeof useTournamentStatus
  >);
}

describe('SideRail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStatus({ status: 'idle' });
    vi.mocked(useLeaveTournament).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveTournament>);
  });

  it('stacks the board as balance, then one In play section', () => {
    renderWithProviders(<SideRail />);
    expect(screen.getByText('Balance')).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['In play']);
  });

  it('shows a cue when nothing is running', () => {
    renderWithProviders(<SideRail />);
    expect(screen.getByText(/Nothing running/)).toBeInTheDocument();
  });

  it('separates queuing from in play, with a cancel while forming', () => {
    mockStatus({ status: 'searching' });
    renderWithProviders(<SideRail />);

    // Waiting for a field is its own labelled state, not "In play".
    const headings = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(headings).toEqual(['Queuing', 'In play']);

    expect(screen.getByTestId('rail-tournament-status')).toHaveTextContent(
      'Finding your tournament field',
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByText(/lands here once it forms/)).toBeInTheDocument();
  });

  it('drops the Queuing section once nothing is searching', () => {
    mockStatus({ status: 'idle' });
    renderWithProviders(<SideRail />);
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['In play']);
    expect(screen.queryByTestId('rail-tournament-status')).not.toBeInTheDocument();
  });
});
