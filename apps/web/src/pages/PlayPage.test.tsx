import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, pts } from '../test/testUtils';
import { PlayPage } from './PlayPage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
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

const H2H_MARKET = {
  key: 'win_h2h',
  label: 'Win the game',
  kind: 'win_h2h' as const,
  requires_speed: true,
  speeds: ['bullet', 'blitz', 'rapid'],
  multiplier_bps: 18000,
  queue_depth: 0,
  resolution_note: 'Win the game · draw = push.',
};

const MATCH = {
  game: 'chess.lichess',
  market: 'win_h2h',
  market_label: 'Win the game',
  kind: 'win_h2h',
  speed: 'blitz',
  entry_cents: 1000,
  pot_cents: 2000,
  prize_cents: 1800,
  rake_cents: 200,
  multiplier_bps: 18000,
  state: 'PENDING',
  host_game_id: null,
  matched_at: null,
  window_ends_at: null,
  you_confirmed: false,
  your_play_url: null,
};

function mockStatus(status: unknown) {
  vi.mocked(useQueueStatus).mockReturnValue({ data: status } as ReturnType<
    typeof useQueueStatus
  >);
}

describe('PlayPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useMarkets).mockReturnValue({
      data: {
        game: 'chess.lichess',
        linked: true,
        entry_presets_cents: [500, 1000, 2500],
        markets: [H2H_MARKET],
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

  it('renders one 1v1 card per market with the derived payout inside it', () => {
    renderWithProviders(<PlayPage />);
    expect(screen.getAllByRole('button', { name: 'Find match' })).toHaveLength(1);
    expect(screen.getByText(pts('1,800 pts'))).toBeInTheDocument();
  });

  it('joining a card finds a match with the entry selected inside it', () => {
    renderWithProviders(<PlayPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Find match' }));
    expect(joinMutate).toHaveBeenCalledWith({
      game: 'chess.lichess',
      market: 'win_h2h',
      speed: 'blitz',
      entry_preset_cents: 1000,
    });
  });

  it('shows the searching state with a cancel affordance', () => {
    mockStatus({
      status: 'searching',
      match: null,
      waited_seconds: 12,
      can_cancel: true,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByText('Searching…')).toBeInTheDocument();
    expect(
      screen.getByText('Matching you with someone at your skill level…'),
    ).toBeInTheDocument();
    expect(screen.getByText('Waiting 12s')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel search' })).toBeInTheDocument();
  });

  it('links to the Lichess game once the match is on', () => {
    mockStatus({
      status: 'matched',
      match: {
        ...MATCH,
        id: 'm2',
        state: 'ACTIVE',
        players: [],
        you_confirmed: true,
        your_play_url: 'https://lichess.org/abcd1234',
        forecast: null,
      },
      can_cancel: false,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByRole('link', { name: /Go play your game/ })).toHaveAttribute(
      'href',
      'https://lichess.org/abcd1234',
    );
  });

  it('shows the matched card with the honest forecast and confirms', () => {
    mockStatus({
      status: 'matched',
      match: {
        ...MATCH,
        id: 'm1',
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
        forecast: { you_win_prob: 0.52, label: 'Even duel — model gives you 52%' },
      },
      can_cancel: false,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByTestId('forecast')).toHaveTextContent(/52%/);
    fireEvent.click(screen.getByRole('button', { name: /Confirm & stake/ }));
    expect(confirmMutate).toHaveBeenCalledWith('m1');
  });

  it('opens the confirm card for a ?match= deep-link (Inbox "Respond")', () => {
    mockStatus({ status: 'idle', match: null, can_cancel: false });
    vi.mocked(useMatch).mockReturnValue({
      data: {
        ...MATCH,
        id: 'deep1',
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
