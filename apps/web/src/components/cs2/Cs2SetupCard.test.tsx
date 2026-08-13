import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

const connect = vi.fn();
const sync = vi.fn();
let chain: {
  connected: boolean;
  state?: string | null;
  last_error?: string | null;
} = { connected: false };
let connectState = { isPending: false, isError: false, error: null as Error | null };
// Steam state now comes from the links hook rather than a prop, because the
// card owns the whole setup: step 1 is the link, not a precondition for it.
let steamLinked = true;

const STEAM_ID = '76561198748110372';

vi.mock('../../hooks/useLinks', () => ({
  useLinks: () => ({
    data: {
      games: steamLinked
        ? [
            {
              game: 'cs2.steam',
              status: 'LINKED',
              profile: { username: STEAM_ID, display_name: 'demo', total_games: 2 },
            },
          ]
        : [{ game: 'cs2.steam', status: 'UNLINKED', profile: null }],
    },
  }),
}));

vi.mock('../../hooks/useCs2', () => ({
  useSteamLoginUrl: () => ({ data: 'https://steamcommunity.com/openid/login' }),
  useChainStatus: () => ({ data: chain }),
  useConnectChain: () => ({ mutate: connect, ...connectState }),
  useSyncChain: () => ({
    mutate: sync,
    isPending: false,
    isError: false,
    isSuccess: false,
  }),
}));

import { Cs2SetupCard } from './Cs2SetupCard';

function setup(
  overrides: Partial<{
    chain: typeof chain;
    connectState: typeof connectState;
    steamLinked: boolean;
  }> = {},
) {
  chain = overrides.chain ?? { connected: false };
  steamLinked = overrides.steamLinked ?? true;
  connectState = overrides.connectState ?? {
    isPending: false,
    isError: false,
    error: null,
  };
  connect.mockReset();
  sync.mockReset();
}

describe('Cs2SetupCard', () => {
  it('asks for both codes in one place, so setup is one pass', () => {
    setup();
    render(<Cs2SetupCard />);
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/share code/i)).toBeInTheDocument();
  });

  it('saves both codes together', async () => {
    setup();
    render(<Cs2SetupCard />);
    await userEvent.type(screen.getByLabelText(/authentication code/i), 'ABCD-EFGHI');
    await userEvent.type(
      screen.getByLabelText(/share code/i),
      'CSGO-UxSfp-RRcZ4-hp5uP-9ntcq-oXc3K',
    );
    await userEvent.click(screen.getByRole('button', { name: /finish setup/i }));

    expect(connect).toHaveBeenCalledWith({
      authCode: 'ABCD-EFGHI',
      knownCode: 'CSGO-UxSfp-RRcZ4-hp5uP-9ntcq-oXc3K',
    });
  });

  it('does not ask for the codes before Steam is connected', () => {
    // They are meaningless without a SteamID to attach them to. Two greyed-out
    // boxes above a greyed-out button only ask the reader to work out which
    // thing to do first.
    setup({ steamLinked: false });
    render(<Cs2SetupCard />);
    expect(screen.queryByLabelText(/authentication code/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/share code/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /finish setup/i }),
    ).not.toBeInTheDocument();
  });

  it('asks for the codes as soon as Steam is connected', () => {
    setup({ steamLinked: true });
    render(<Cs2SetupCard />);
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /finish setup/i })).toBeInTheDocument();
  });

  it('offers Steam sign-in when that step is outstanding', () => {
    setup({ steamLinked: false });
    render(<Cs2SetupCard />);
    expect(
      screen.getByRole('link', { name: /sign in through steam/i }),
    ).toBeInTheDocument();
  });

  it('links straight to the authentication code page', () => {
    // Buried in Steam support. Describing where to click loses people.
    setup();
    render(<Cs2SetupCard />);
    const link = screen.getByRole('link', { name: /create yours/i });
    expect(link).toHaveAttribute('href', expect.stringContaining('appid=730'));
  });

  it('stops asking once it is set up', () => {
    // The whole promise: enter these once and never think about them again.
    setup({ chain: { connected: true, state: 'active' } });
    render(<Cs2SetupCard />);
    expect(screen.queryByLabelText(/authentication code/i)).not.toBeInTheDocument();
    expect(screen.getByText(/collecting automatically/i)).toBeInTheDocument();
  });

  it('says why collection stopped rather than hiding it', () => {
    setup({
      chain: {
        connected: true,
        state: 'broken',
        last_error: 'Steam rejected your authentication code.',
      },
    });
    render(<Cs2SetupCard />);
    expect(screen.getByTestId('cs2-chain-broken')).toHaveTextContent(/rejected/i);
    // And the form comes back, because reconnecting is the fix.
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
  });

  it('surfaces the server reason for a rejected setup', () => {
    // "That share code is not from a match on this Steam account" tells the
    // player what to do. "Could not connect" does not.
    setup({
      connectState: {
        isPending: false,
        isError: true,
        error: new Error('That share code is not from a match on this Steam account.'),
      },
    });
    render(<Cs2SetupCard />);
    expect(screen.getByTestId('cs2-connect-error')).toHaveTextContent(
      /not from a match on this Steam account/i,
    );
  });
});

describe('Cs2SetupCard · changing codes', () => {
  it('lets a connected player get back to the form', async () => {
    // Steam can regenerate an authentication code, which silently invalidates
    // ours. Without this the only route back is waiting for collection to fail.
    setup({ chain: { connected: true, state: 'active' } });
    render(<Cs2SetupCard />);
    await userEvent.click(screen.getByRole('button', { name: /change codes/i }));
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
  });
});

describe('Cs2SetupCard · the connected Steam account', () => {
  it('shows which account is connected, not just that one is', () => {
    // "Linked" alone is unverifiable from the outside. Naming the account is
    // how someone confirms the wager is reading the right profile.
    setup();
    render(<Cs2SetupCard />);
    expect(screen.getByText(new RegExp(STEAM_ID))).toBeInTheDocument();
  });

  it('offers a way to reconnect a different Steam account', () => {
    setup();
    render(<Cs2SetupCard />);
    expect(screen.getByRole('link', { name: /reconnect steam/i })).toBeInTheDocument();
  });
});

describe('Cs2SetupCard · connection status', () => {
  it('reads green once Steam and both codes are in', () => {
    setup({ chain: { connected: true, state: 'active' } });
    render(<Cs2SetupCard />);
    const status = screen.getByTestId('cs2-status');
    expect(status).toHaveAttribute('data-status', 'connected');
    expect(status).toHaveTextContent(/connected/i);
  });

  it('reads red until setup is finished', () => {
    // The state worth shouting about: a wager can be joined and played with
    // nothing in place to settle it.
    setup();
    render(<Cs2SetupCard />);
    const status = screen.getByTestId('cs2-status');
    expect(status).toHaveAttribute('data-status', 'not-connected');
    expect(status).toHaveTextContent(/not connected/i);
  });

  it('reads red when collection has stopped, and says so differently', () => {
    setup({
      chain: { connected: true, state: 'broken', last_error: 'Steam rejected it.' },
    });
    render(<Cs2SetupCard />);
    const status = screen.getByTestId('cs2-status');
    expect(status).toHaveAttribute('data-status', 'not-connected');
    expect(status).toHaveTextContent(/disconnected/i);
  });

  it('still checks for matches when the green control is pressed', async () => {
    setup({ chain: { connected: true, state: 'active' } });
    render(<Cs2SetupCard />);
    await userEvent.click(screen.getByTestId('cs2-status'));
    expect(sync).toHaveBeenCalled();
  });

  it('is not pressable when there is nothing to check', () => {
    // A dead control that still looks pressable reads as a broken page.
    setup();
    render(<Cs2SetupCard />);
    expect(screen.getByTestId('cs2-status')).toBeDisabled();
  });
});
