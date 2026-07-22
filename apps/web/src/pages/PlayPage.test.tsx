import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { PlayPage } from './PlayPage';

vi.mock('../hooks/useLinks', () => ({ useLinks: vi.fn() }));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
vi.mock('../hooks/useMatchmaking', async () => {
  const actual = await vi.importActual<typeof import('../hooks/useMatchmaking')>(
    '../hooks/useMatchmaking',
  );
  return {
    ...actual,
    useMarkets: vi.fn(),
    useMatch: vi.fn(),
    useQueueStatus: vi.fn(),
    useWaiting: vi.fn(),
    useJoinQueue: vi.fn(),
    useTakeWaiting: vi.fn(),
    useConfirmMatch: vi.fn(),
    useDeclineMatch: vi.fn(),
    useLeaveQueue: vi.fn(),
    prizeForEntry: actual.prizeForEntry,
  };
});

import { useLinks } from '../hooks/useLinks';
import {
  prizeForEntry,
  useConfirmMatch,
  useDeclineMatch,
  useJoinQueue,
  useLeaveQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
} from '../hooks/useMatchmaking';

const joinMutate = vi.fn();
const confirmMutate = vi.fn();

const KD_MARKET = {
  key: 'kd_ratio',
  label: 'K/D ratio',
  kind: 'stat_race' as const,
  metric: 'cs2_kd_ratio',
  requires_speed: false,
  speeds: [],
  multiplier_bps: 18000,
  queue_depth: 0,
  provisional: false,
  resolution_note: 'Higher K/D ratio wins · equal = push.',
};

function mockStatus(status: unknown) {
  vi.mocked(useQueueStatus).mockReturnValue({ data: status } as ReturnType<
    typeof useQueueStatus
  >);
}

describe('PlayPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useLinks).mockReturnValue({
      data: {
        games: [
          {
            game: 'cs2.faceit',
            display_name: 'CS2 — FACEIT',
            status: 'LINKED',
            host_username: 'me',
            linked_at: null,
            profile: null,
          },
        ],
      },
    } as unknown as ReturnType<typeof useLinks>);
    vi.mocked(useMarkets).mockReturnValue({
      data: {
        game: 'cs2.faceit',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        markets: [KD_MARKET],
      },
    } as unknown as ReturnType<typeof useMarkets>);
    mockStatus({ status: 'idle', match: null, can_cancel: false });
    vi.mocked(useMatch).mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof useMatch>);
    vi.mocked(useWaiting).mockReturnValue({
      data: { waiting: [] },
    } as unknown as ReturnType<typeof useWaiting>);
    vi.mocked(useJoinQueue).mockReturnValue({
      mutate: joinMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useJoinQueue>);
    vi.mocked(useTakeWaiting).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTakeWaiting>);
    vi.mocked(useConfirmMatch).mockReturnValue({
      mutate: confirmMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useConfirmMatch>);
    vi.mocked(useDeclineMatch).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useDeclineMatch>);
    vi.mocked(useLeaveQueue).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useLeaveQueue>);
  });

  it('renders a market with its derived ×1.80 multiplier', () => {
    renderWithProviders(<PlayPage />);
    expect(screen.getByText('K/D ratio')).toBeInTheDocument();
    expect(screen.getByText('×1.80')).toBeInTheDocument();
  });

  it('pick market + entry surfaces the derived "You\'d win" and finds a match', () => {
    renderWithProviders(<PlayPage />);
    fireEvent.click(screen.getByText('K/D ratio'));
    fireEvent.click(screen.getByRole('button', { name: '$10.00' }));
    // 2 × $10 × (1 − 0.10) = $18.00, derived — never an odds line.
    expect(screen.getByText('$18.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Find match' }));
    expect(joinMutate).toHaveBeenCalledWith({
      game: 'cs2.faceit',
      market: 'kd_ratio',
      speed: undefined,
      entry_preset_cents: 1000,
    });
  });

  it('shows the searching state with a cancel affordance', () => {
    mockStatus({
      status: 'searching',
      match: null,
      waited_seconds: 12,
      tolerance_stage: 0,
      can_cancel: true,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByText('Searching…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel search' })).toBeInTheDocument();
  });

  it('shows the matched card with the honest forecast and confirms', () => {
    mockStatus({
      status: 'matched',
      match: {
        id: 'm1',
        game: 'cs2.faceit',
        market: 'kd_ratio',
        market_label: 'K/D ratio',
        kind: 'stat_race',
        speed: null,
        entry_cents: 1000,
        pot_cents: 2000,
        prize_cents: 1800,
        rake_cents: 200,
        multiplier_bps: 18000,
        state: 'PENDING',
        brokered: false,
        host_game_id: null,
        matched_at: null,
        window_ends_at: null,
        players: [
          {
            user_id: 'u2',
            username: 'kvem_',
            rating: 1800,
            color: null,
            confirmed: false,
            payout_cents: 0,
            stat_line: null,
            is_you: false,
          },
        ],
        you_confirmed: false,
        your_play_url: null,
        forecast: { you_win_prob: 0.52, label: 'Even duel — model gives you 52%' },
      },
      can_cancel: false,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByTestId('forecast')).toHaveTextContent(
      'Even duel — model gives you 52%',
    );
    fireEvent.click(screen.getByRole('button', { name: /Confirm & stake/ }));
    expect(confirmMutate).toHaveBeenCalledWith('m1');
  });

  it('opens the confirm card for a ?match= deep-link (Inbox "Respond")', () => {
    // Queue is idle — the accepted-challenge match only comes from ?match=.
    mockStatus({ status: 'idle', match: null, can_cancel: false });
    vi.mocked(useMatch).mockReturnValue({
      data: {
        id: 'deep1',
        game: 'cs2.faceit',
        market: 'kd_ratio',
        market_label: 'K/D ratio',
        kind: 'stat_race',
        speed: null,
        entry_cents: 1000,
        pot_cents: 2000,
        prize_cents: 1800,
        rake_cents: 200,
        multiplier_bps: 18000,
        state: 'PENDING',
        brokered: false,
        host_game_id: null,
        matched_at: null,
        window_ends_at: null,
        players: [
          {
            user_id: 'u3',
            username: 'friend_',
            rating: 1750,
            color: null,
            confirmed: false,
            payout_cents: 0,
            stat_line: null,
            is_you: false,
          },
        ],
        you_confirmed: false,
        your_play_url: null,
        forecast: null,
      },
    } as unknown as ReturnType<typeof useMatch>);

    renderWithProviders(<PlayPage />, { route: '/play?match=deep1' });
    fireEvent.click(screen.getByRole('button', { name: /Confirm & stake/ }));
    expect(confirmMutate).toHaveBeenCalledWith('deep1');
  });
});

describe('prizeForEntry', () => {
  it('derives 2·(1 − rake) exactly in integer cents', () => {
    expect(prizeForEntry(1000, 18000)).toBe(1800);
    expect(prizeForEntry(500, 18000)).toBe(900);
    expect(prizeForEntry(2500, 18000)).toBe(4500);
  });
});
