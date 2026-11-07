import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { ProfilePage } from './ProfilePage';

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }));

vi.mock('../hooks/useMe', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useMe')>('../hooks/useMe');
  return { ...actual, useMe: vi.fn(), useSelfExclude: vi.fn() };
});

vi.mock('../hooks/useLinks', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useLinks')>('../hooks/useLinks');
  return {
    ...actual,
    useLinks: vi.fn(),
    useCreateLink: vi.fn(),
    useRefreshLink: vi.fn(),
  };
});

import { useAuth } from '../auth/useAuth';
import { useMe, useSelfExclude } from '../hooks/useMe';
import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
} from '../hooks/useLinks';

const createMutate = vi.fn();
const selfExcludeMutate = vi.fn();
const verifyCurrentPassword = vi.fn();
const changePassword = vi.fn();

function gameLink(over: Partial<GameLink>): GameLink {
  return {
    game: 'chess.lichess',
    display_name: 'Chess — Lichess',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
    ...over,
  };
}

function mockLinks(...games: GameLink[]) {
  vi.mocked(useLinks).mockReturnValue({
    isLoading: false,
    isError: false,
    data: { games },
  } as unknown as ReturnType<typeof useLinks>);
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    verifyCurrentPassword.mockResolvedValue(true);
    changePassword.mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      signOut: vi.fn(),
      verifyCurrentPassword,
      changePassword,
    } as unknown as ReturnType<typeof useAuth>);
    vi.mocked(useMe).mockReturnValue({
      data: {
        user: {
          id: 'u1',
          username: 'kvem_',
          email: null,
          residence_state: 'MA',
          dob_attested_18plus: true,
          role: 'user',
          status: 'active',
          member_since: new Date().toISOString(),
        },
        needs_onboarding: false,
        limits: {
          daily_loss_cap_cents: 20_000,
          daily_entry_cap_cents: 50_000,
          daily_deposit_cap_cents: 100_000,
          max_concurrent_contests: 3,
          pending_limits: null,
          pending_effective_at: null,
          timeout_until: null,
        },
      },
    } as unknown as ReturnType<typeof useMe>);
    vi.mocked(useSelfExclude).mockReturnValue({
      mutate: selfExcludeMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useSelfExclude>);
    vi.mocked(useCreateLink).mockReturnValue({
      mutate: createMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useCreateLink>);
    vi.mocked(useRefreshLink).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRefreshLink>);
    mockLinks(
      gameLink({
        status: 'LINKED',
        host_username: 'magnus',
        win_streak: 5,
        profile: {
          username: 'magnus',
          display_name: 'magnus',
          url: '',
          link_method: 'username',
          game: 'chess.lichess',
          account_age_days: null,
          win_rate: 0.6,
          draw_rate: 0,
          total_games: 100,
          formats: [],
          primary_speed: 'blitz',
          rating: 2100,
          avatar_url: null,
        },
      }),
    );
  });

  it('renders the linked account, rating + win streak, and editable limits', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('Linked')).toBeInTheDocument();
    expect(screen.getByText('magnus · 100 games')).toBeInTheDocument();
    expect(screen.getByText('Rating 2100')).toBeInTheDocument();
    expect(screen.getByText('5 win streak')).toBeInTheDocument();
    expect(screen.getByDisplayValue('200')).toBeInTheDocument();
  });

  it('shows a blocked account', () => {
    mockLinks(gameLink({ status: 'BLOCKED' }));
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('Blocked')).toBeInTheDocument();
  });

  it('runs the link flow for an unlinked account', () => {
    mockLinks(gameLink({ status: 'UNLINKED' }));
    renderWithProviders(<ProfilePage />);
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    fireEvent.change(screen.getByPlaceholderText('Your Lichess username'), {
      target: { value: 'magnus' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    expect(screen.getByText(/permanently links/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Link account' }));
    expect(createMutate).toHaveBeenCalledWith(
      { game: 'chess.lichess', username: 'magnus' },
      expect.anything(),
    );
  });

  it('confirms before self-excluding', () => {
    renderWithProviders(<ProfilePage />);
    fireEvent.click(screen.getByRole('button', { name: 'Self-exclude' }));
    fireEvent.click(screen.getByRole('button', { name: 'Yes, self-exclude' }));
    expect(selfExcludeMutate).toHaveBeenCalled();
  });

  it('changes password: current-password step (with email fallback) then new password', async () => {
    renderWithProviders(<ProfilePage />);

    expect(
      screen.queryByPlaceholderText('Enter current password'),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));

    expect(screen.getByPlaceholderText('Enter current password')).toBeInTheDocument();
    expect(
      screen.queryByText('Forgot your password? Verify with email.'),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Enter current password'), {
      target: { value: 'oldpass1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(verifyCurrentPassword).toHaveBeenCalledWith('oldpass1');

    await screen.findByPlaceholderText('New password');
    fireEvent.change(screen.getByPlaceholderText('New password'), {
      target: { value: 'newpass1' },
    });
    fireEvent.change(screen.getByPlaceholderText('Confirm new password'), {
      target: { value: 'newpass1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Update password' }));
    expect(changePassword).toHaveBeenCalledWith('newpass1');
  });
});
