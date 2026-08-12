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
  overrides: Partial<{ chain: typeof chain; connectState: typeof connectState }> = {},
) {
  chain = overrides.chain ?? { connected: false };
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
    render(<Cs2SetupCard linked />);
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/share code/i)).toBeInTheDocument();
  });

  it('saves both codes together', async () => {
    setup();
    render(<Cs2SetupCard linked />);
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

  it('cannot be submitted before Steam is connected', () => {
    // The codes are meaningless without a SteamID to attach them to, and a
    // request that can only fail is worse than a disabled button.
    setup();
    render(<Cs2SetupCard linked={false} />);
    expect(screen.getByRole('button', { name: /finish setup/i })).toBeDisabled();
    expect(screen.getByLabelText(/authentication code/i)).toBeDisabled();
  });

  it('offers Steam sign-in when that step is outstanding', () => {
    setup();
    render(<Cs2SetupCard linked={false} />);
    expect(
      screen.getByRole('link', { name: /sign in through steam/i }),
    ).toBeInTheDocument();
  });

  it('links straight to the authentication code page', () => {
    // Buried in Steam support. Describing where to click loses people.
    setup();
    render(<Cs2SetupCard linked />);
    const link = screen.getByRole('link', { name: /create yours/i });
    expect(link).toHaveAttribute('href', expect.stringContaining('appid=730'));
  });

  it('stops asking once it is set up', () => {
    // The whole promise: enter these once and never think about them again.
    setup({ chain: { connected: true, state: 'active' } });
    render(<Cs2SetupCard linked />);
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
    render(<Cs2SetupCard linked />);
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
    render(<Cs2SetupCard linked />);
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
    render(<Cs2SetupCard linked />);
    await userEvent.click(screen.getByRole('button', { name: /change codes/i }));
    expect(screen.getByLabelText(/authentication code/i)).toBeInTheDocument();
  });
});
