import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders, pts } from '../test/testUtils';
import { PlayPage } from './PlayPage';

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

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ session: null }),
}));
vi.mock('../hooks/useWallet', () => ({
  useWallet: () => ({
    data: { available_cents: 100_000, escrow_cents: 0, lifetime_net_cents: 0 },
  }),
}));
vi.mock('../hooks/useLinks', () => ({
  useConnectLichess: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useLinks: () => ({
    data: {
      games: [
        {
          game: 'chess.lichess',
          status: 'LINKED',
          host_username: 'ana',
          profile: {
            username: 'ana',
            rating: 1712,
            formats: [
              { speed: 'blitz', rating: 1712, games: 900, provisional: false },
              { speed: 'rapid', rating: 1790, games: 40, provisional: true },
            ],
          },
        },
      ],
    },
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
  speeds: ['bullet', 'blitz', 'rapid', 'classical'],
  clocks: [
    { speed: 'bullet', limit_seconds: 60, increment_seconds: 0 },
    { speed: 'blitz', limit_seconds: 300, increment_seconds: 0 },
    { speed: 'rapid', limit_seconds: 600, increment_seconds: 0 },
    { speed: 'classical', limit_seconds: 1800, increment_seconds: 0 },
  ],
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

const PLAYERS = [
  {
    user_id: 'u1',
    username: 'ana',
    rating: 1712,
    color: 'black',
    confirmed: true,
    payout_cents: 0,
    stat_line: null,
    is_you: true,
  },
  {
    user_id: 'u2',
    username: 'kvem_',
    rating: 1779,
    color: 'white',
    confirmed: true,
    payout_cents: 0,
    stat_line: null,
    is_you: false,
  },
];

function stageMatch(over: Record<string, unknown>) {
  const data = {
    ...MATCH,
    id: 'mx',
    host_game_id: 'abcd1234',
    players: PLAYERS,
    you_confirmed: true,
    your_play_url: 'https://lichess.org/abcd1234/black',
    forecast: null,
    matched_at: new Date().toISOString(),
    ...over,
  };
  vi.mocked(useMatch).mockImplementation(
    (id) => ({ data: id ? data : undefined }) as unknown as ReturnType<typeof useMatch>,
  );
  renderWithProviders(<PlayPage />, { route: '/play?match=mx' });
}

function mockStatus(status: unknown) {
  vi.mocked(useQueueStatus).mockReturnValue({ data: status } as ReturnType<
    typeof useQueueStatus
  >);
}

describe('PlayPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
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

  it('sets the desk with defaults: blitz, the middle stake, payout and fee', () => {
    renderWithProviders(<PlayPage />);
    expect(screen.getByRole('tab', { name: /Blitz/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByTestId('desk-rating')).toHaveTextContent('1712');
    expect(screen.getByText('Matched with someone at your skill level')).toBeVisible();
    expect(screen.getByText(pts('1,800 pts'))).toBeInTheDocument();
    expect(screen.getByText(/Fee/)).toHaveTextContent('Fee 200 pts');
    fireEvent.click(screen.getByRole('button', { name: 'Find match · 1,000 pts' }));
    expect(joinMutate).toHaveBeenCalledWith({
      game: 'chess.lichess',
      market: 'win_h2h',
      speed: 'blitz',
      entry_preset_cents: 1000,
    });
  });

  it('time control and stake change the rating, payout and the join', () => {
    renderWithProviders(<PlayPage />);
    fireEvent.click(screen.getByRole('tab', { name: /Rapid/ }));
    expect(screen.getByTestId('desk-rating')).toHaveTextContent('1790?');
    fireEvent.click(screen.getByRole('tab', { name: '2,500 pts' }));
    expect(screen.getByText(pts('4,500 pts'))).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Find match · 2,500 pts' }));
    expect(joinMutate).toHaveBeenCalledWith(
      expect.objectContaining({ speed: 'rapid', entry_preset_cents: 2500 }),
    );
  });

  it('says where the rating comes from when there are no games at that speed', () => {
    renderWithProviders(<PlayPage />);
    fireEvent.click(screen.getByRole('tab', { name: /Classical/ }));
    expect(screen.getByTestId('desk-rating')).toHaveTextContent('1712From blitz');
  });

  it('degrades to a Link Lichess prompt when unlinked', () => {
    vi.mocked(useMarkets).mockReturnValue({
      data: {
        game: 'chess.lichess',
        linked: false,
        entry_presets_cents: [500, 1000, 2500],
        markets: [H2H_MARKET],
      },
    } as unknown as ReturnType<typeof useMarkets>);
    renderWithProviders(<PlayPage />);
    expect(screen.queryByTestId('match-desk')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect Lichess' })).toBeInTheDocument();
  });

  it('lists open seats with rating and time control', () => {
    vi.mocked(useWaiting).mockReturnValue({
      data: {
        waiting: [
          {
            ticket_id: 't1',
            game: 'chess.lichess',
            market: 'win_h2h',
            market_label: 'Win the game',
            speed: 'blitz',
            entry_cents: 1000,
            username: 'dana',
            rating: 1689,
            waited_seconds: 40,
          },
        ],
      },
    } as unknown as ReturnType<typeof useWaiting>);
    renderWithProviders(<PlayPage />);
    expect(screen.getByText('1689')).toBeInTheDocument();
    expect(screen.getByText('Blitz 5+0 · 1,000 pts')).toBeInTheDocument();
  });

  it('searching shows the waited time and your current range on the ruler', () => {
    mockStatus({
      status: 'searching',
      match: null,
      waited_seconds: 30,
      can_cancel: true,
      ticket: {
        market: 'win_h2h',
        speed: 'blitz',
        clock: { speed: 'blitz', limit_seconds: 300, increment_seconds: 0 },
        entry_cents: 2500,
        rating: 1712,
      },
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByText('Searching')).toBeInTheDocument();
    expect(screen.getByText('Blitz 5+0 · 2,500 pts stake')).toBeInTheDocument();
    expect(screen.getByTestId('waited')).toHaveTextContent('0:30');
    expect(screen.getByTestId('band-range')).toHaveTextContent('1252–2172');
    expect(screen.getByTestId('skill-band-ruler')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel search' })).toBeInTheDocument();
  });

  it('searching without a ticket recap shows the band width only', () => {
    mockStatus({
      status: 'searching',
      match: null,
      waited_seconds: 0,
      can_cancel: true,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByTestId('band-range')).toHaveTextContent('±100');
  });

  it('puts the match on the stage once both confirm, with the Lichess link', () => {
    mockStatus({
      status: 'matched',
      match: {
        ...MATCH,
        id: 'm2',
        state: 'ACTIVE',
        players: PLAYERS,
        you_confirmed: true,
        your_play_url: 'https://lichess.org/abcd1234',
        forecast: null,
        matched_at: new Date().toISOString(),
        live: null,
      },
      can_cancel: false,
    });
    renderWithProviders(<PlayPage />);
    expect(screen.getByTestId('match-stage')).toHaveAttribute('data-state', 'waiting');
    expect(screen.getByRole('link', { name: /Open game on Lichess/ })).toHaveAttribute(
      'href',
      'https://lichess.org/abcd1234',
    );
    expect(screen.getByText('Blitz 5+0')).toBeInTheDocument();
    expect(screen.getByTestId('stage-line')).toHaveTextContent(
      'Waiting for the first move',
    );
  });

  it('shows the live board, the move and whose turn it is', async () => {
    stageMatch({
      state: 'ACTIVE',
      live: {
        kind: 'match',
        format: 'chess',
        status: 'live',
        moves: 2,
        your_color: 'black',
        turn: 'you',
        result: null,
        termination: null,
        san: ['e4', 'e5', 'Nf3'],
        clocks: { white_ms: 291_000, black_ms: 300_000 },
        clock: { limit: 300, increment: 0 },
        last_move_at: new Date().toISOString(),
      },
    });
    expect(screen.getByTestId('stage-line')).toHaveTextContent('Move 2 · your move');
    expect(
      await screen.findByRole('img', { name: 'Board after 2. Nf3' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('strip-you')).toHaveTextContent('Black');
    expect(screen.getByLabelText(/^Your clock [45]:/)).toHaveAttribute(
      'data-running',
      'true',
    );
  });

  it('falls back to just the Lichess link when the board is unavailable', () => {
    stageMatch({
      state: 'AWAITING_RESULT',
      live: null,
      matched_at: '2020-01-01T00:00:00Z',
    });
    expect(screen.queryByTestId('board-frame')).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Open game on Lichess/ }),
    ).toBeInTheDocument();
  });

  it('turns into a result card on a win: winnings, how it ended, settle time', () => {
    stageMatch({
      state: 'SETTLED',
      winner_user_id: 'u1',
      termination: 'resignation',
      game_ended_at: '2025-01-08T10:00:00Z',
      resolved_at: '2025-01-08T10:00:38Z',
    });
    const card = screen.getByTestId('result-card');
    expect(card).toHaveAttribute('data-outcome', 'win');
    expect(screen.getByTestId('result-headline')).toHaveTextContent('You won');
    expect(screen.getByText('vs kvem_ · by resignation')).toBeInTheDocument();
    expect(screen.getByTestId('result-amount')).toHaveTextContent('1,800 pts');
    expect(card).toHaveTextContent('fee 200 pts');
    expect(screen.getByTestId('settled-in')).toHaveTextContent(
      'Settled from Lichess in 38s',
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'You won 1,800 points by resignation',
    );
    expect(screen.getByRole('button', { name: 'Rematch' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View game on Lichess/ })).toHaveAttribute(
      'href',
      'https://lichess.org/abcd1234/black',
    );
  });

  it('a loss is calm: the stake, how it ended, no settle claim without an end time', () => {
    stageMatch({ state: 'SETTLED', winner_user_id: 'u2', termination: 'time' });
    expect(screen.getByTestId('result-headline')).toHaveTextContent('You lost');
    expect(screen.getByText('vs kvem_ · on time')).toBeInTheDocument();
    expect(screen.getByTestId('result-amount')).toHaveTextContent('-1,000 pts');
    expect(screen.queryByTestId('settled-in')).not.toBeInTheDocument();
  });

  it('a draw refunds both stakes with no fee', () => {
    stageMatch({ state: 'PUSHED', termination: 'draw' });
    expect(screen.getByTestId('result-headline')).toHaveTextContent('Draw');
    expect(screen.getByTestId('result-card')).toHaveTextContent(
      'Both stakes refunded · no fee',
    );
  });

  it('play again returns to the desk', () => {
    stageMatch({ state: 'PUSHED' });
    fireEvent.click(screen.getByRole('button', { name: 'Play again' }));
    expect(screen.getByTestId('match-desk')).toBeInTheDocument();
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
