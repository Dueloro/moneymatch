import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../test/testUtils';
import type { TournamentView } from '../../hooks/useTournaments';
import { SideRail } from '../rail/SideRail';
import { RailTournamentCard } from './TournamentPanel';

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ isDemo: false, session: null }),
}));
vi.mock('../../hooks/useTournaments', async () => {
  const actual = await vi.importActual<typeof import('../../hooks/useTournaments')>(
    '../../hooks/useTournaments',
  );
  return {
    ...actual,
    useTournamentStatus: vi.fn(),
    useMyTournaments: vi.fn(),
    useLeaveTournament: vi.fn(),
  };
});

import {
  useLeaveTournament,
  useMyTournaments,
  useTournamentStatus,
} from '../../hooks/useTournaments';

function tournament(over: Partial<TournamentView> = {}): TournamentView {
  return {
    id: 't1',
    game: 'pubg.steam',
    metric: 'pubg_kills',
    metric_label: 'Kills',
    entry_cents: 2500,
    pot_cents: 25000,
    prize_cents: 0,
    rake_cents: 0,
    prize_split: [60, 25, 15],
    field_size: 10,
    players: 3,
    score_matches: 3,
    state: 'LOCKED',
    window_starts_at: new Date().toISOString(),
    window_ends_at: new Date(Date.now() + 3600_000).toISOString(),
    join_closes_at: null,
    your_entered_at: null,
    field_mu_low: null,
    field_mu_high: null,
    standings: [
      {
        user_id: 'u1',
        username: 'demo',
        score: 8,
        matches: 2,
        rank: 1,
        is_you: true,
        payout_cents: 0,
      },
      {
        user_id: 'u2',
        username: 'testbot_ada',
        score: null,
        matches: 0,
        rank: null,
        is_you: false,
        payout_cents: 0,
      },
      {
        user_id: 'u3',
        username: 'testbot_bo',
        score: null,
        matches: 0,
        rank: null,
        is_you: false,
        payout_cents: 0,
      },
    ],
    your_rank: 1,
    your_payout_cents: null,
    your_games: [
      {
        host_match_id: 'g1',
        started_at: new Date().toISOString(),
        ended_at: null,
        mode: 'solo',
        result: 'loss',
        reason: 'COUNTED',
        reason_text: 'Counted',
        value: 8,
      },
    ],
    outcome_reason: null,
    resolved_at: null,
    ...over,
  };
}

describe('RailTournamentCard', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(useLeaveTournament).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveTournament>);
  });

  it('shows your place, every player, and the games we fetched', () => {
    renderWithProviders(<RailTournamentCard tournament={tournament()} />);
    expect(screen.getByTestId('rail-tournament-summary')).toHaveTextContent(
      'You: #1 · 8 · 2 of 3 games',
    );
    expect(screen.getByText(/testbot_ada/)).toBeInTheDocument();
    expect(
      within(screen.getByTestId('your-games')).getByText('Counted'),
    ).toBeInTheDocument();
  });

  it('collapses to the summary and remembers it', () => {
    const { unmount } = renderWithProviders(
      <RailTournamentCard tournament={tournament()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Kills tournament/ }));
    expect(screen.queryByText(/testbot_ada/)).not.toBeInTheDocument();
    expect(screen.getByTestId('rail-tournament-summary')).toBeInTheDocument();
    unmount();

    renderWithProviders(<RailTournamentCard tournament={tournament()} />);
    expect(screen.queryByText(/testbot_ada/)).not.toBeInTheDocument();
  });

  it('collapses the player list on its own', () => {
    renderWithProviders(<RailTournamentCard tournament={tournament()} />);
    fireEvent.click(screen.getByTestId('rail-tournament-players'));
    expect(screen.queryByText(/testbot_ada/)).not.toBeInTheDocument();
    expect(screen.getByTestId('your-games')).toBeInTheDocument();
  });

  it('shows the prize once settled', () => {
    renderWithProviders(
      <RailTournamentCard
        tournament={tournament({
          state: 'SETTLED',
          standings: [
            {
              user_id: 'u1',
              username: 'demo',
              score: 8,
              matches: 2,
              rank: 1,
              is_you: true,
              payout_cents: 22500,
            },
          ],
        })}
      />,
    );
    expect(screen.getAllByText('+$225.00').length).toBeGreaterThan(0);
  });
});

describe('SideRail with a tournament', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(useLeaveTournament).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveTournament>);
    vi.mocked(useMyTournaments).mockReturnValue({ data: [] } as unknown as ReturnType<
      typeof useMyTournaments
    >);
  });

  it('puts your live tournament in its own rail section', () => {
    vi.mocked(useTournamentStatus).mockReturnValue({
      data: { status: 'formed', tournament: tournament() },
    } as unknown as ReturnType<typeof useTournamentStatus>);
    renderWithProviders(<SideRail />);
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['Tournament']);
    expect(screen.getByTestId('rail-tournament-card')).toBeInTheDocument();
    expect(screen.queryByText(/Nothing running/)).not.toBeInTheDocument();
  });

  it('takes the tournament off the rail once it is paid out', () => {
    vi.mocked(useTournamentStatus).mockReturnValue({
      data: { status: 'formed', tournament: tournament({ state: 'SETTLED' }) },
    } as unknown as ReturnType<typeof useTournamentStatus>);
    renderWithProviders(<SideRail />);
    expect(screen.queryByTestId('rail-tournament-card')).not.toBeInTheDocument();
  });

  it('shows nothing extra without a tournament', () => {
    vi.mocked(useTournamentStatus).mockReturnValue({
      data: { status: 'idle', tournament: null },
    } as unknown as ReturnType<typeof useTournamentStatus>);
    renderWithProviders(<SideRail />);
    expect(screen.queryByTestId('rail-tournament-card')).not.toBeInTheDocument();
  });
});
