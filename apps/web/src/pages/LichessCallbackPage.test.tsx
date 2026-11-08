import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { LichessCallbackPage } from './LichessCallbackPage';

const completeMutate = vi.fn();
const connectMutate = vi.fn();
let complete: Record<string, unknown> = {};

vi.mock('../hooks/useLinks', () => ({
  useCompleteLichessLink: () => ({ mutate: completeMutate, ...complete }),
  useConnectLichess: () => ({ mutate: connectMutate, isPending: false, error: null }),
}));

function renderAt(route: string) {
  renderWithProviders(
    <Routes>
      <Route path="/link/lichess/callback" element={<LichessCallbackPage />} />
      <Route path="/pools" element={<p>pools page</p>} />
      <Route path="/play" element={<p>play page</p>} />
      <Route path="/i/:token" element={<p>invite preview</p>} />
    </Routes>,
    { route },
  );
}

describe('LichessCallbackPage', () => {
  beforeEach(() => {
    completeMutate.mockClear();
    connectMutate.mockClear();
    complete = { isSuccess: false, isError: false };
    sessionStorage.clear();
  });

  it('posts the code and state once', () => {
    renderAt('/link/lichess/callback?code=liu_1&state=s1');
    expect(completeMutate).toHaveBeenCalledTimes(1);
    expect(completeMutate).toHaveBeenCalledWith({ code: 'liu_1', state: 's1' });
    expect(
      screen.getByRole('status', { name: 'Confirming with Lichess' }),
    ).toBeInTheDocument();
  });

  it('shows the linked account and returns to where the user started', async () => {
    sessionStorage.setItem('mm.linkReturnTo', '/pools');
    complete = {
      isSuccess: true,
      isError: false,
      data: {
        games: [{ game: 'chess.lichess', status: 'LINKED', host_username: 'Magnus' }],
      },
    };
    renderAt('/link/lichess/callback?code=liu_1&state=s1');
    expect(screen.getByText('Linked as Magnus.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('pools page')).toBeInTheDocument();
    expect(sessionStorage.getItem('mm.linkReturnTo')).toBeNull();
  });

  it('finishes onboarding on the pending invite, once', async () => {
    sessionStorage.setItem('mm.returnTo', '/i/tok123');
    sessionStorage.setItem('mm.linkReturnTo', '/i/tok123');
    complete = { isSuccess: true, isError: false, data: { games: [] } };
    renderAt('/link/lichess/callback?code=c&state=s');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('invite preview')).toBeInTheDocument();
    expect(sessionStorage.getItem('mm.returnTo')).toBeNull();
  });

  it('ignores an off-site return path', async () => {
    sessionStorage.setItem('mm.linkReturnTo', '//evil.example');
    complete = { isSuccess: true, isError: false, data: { games: [] } };
    renderAt('/link/lichess/callback?code=c&state=s');
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('play page')).toBeInTheDocument();
  });

  it('handles a cancel on Lichess without calling the API, and can retry', async () => {
    renderAt('/link/lichess/callback?error=access_denied&state=s1');
    expect(completeMutate).not.toHaveBeenCalled();
    expect(screen.getByText('You cancelled on Lichess.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(connectMutate).toHaveBeenCalledWith(null);
  });

  it('shows the API error', async () => {
    complete = {
      isSuccess: false,
      isError: true,
      error: new Error(
        'That Lichess sign-in expired or wasn’t started here. Try again.',
      ),
    };
    renderAt('/link/lichess/callback?code=c&state=s');
    await waitFor(() =>
      expect(screen.getByText(/sign-in expired/)).toBeInTheDocument(),
    );
  });
});
