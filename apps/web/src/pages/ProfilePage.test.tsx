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

vi.mock('../hooks/useResetDemo', () => ({ useResetDemo: vi.fn() }));

import { useAuth } from '../auth/useAuth';
import { useMe, useSelfExclude } from '../hooks/useMe';
import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
} from '../hooks/useLinks';
import { useResetDemo } from '../hooks/useResetDemo';

const createMutate = vi.fn();
const selfExcludeMutate = vi.fn();
const resetMutate = vi.fn();
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

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    verifyCurrentPassword.mockResolvedValue(true);
    changePassword.mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      signOut: vi.fn(),
      isDemo: false,
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
          // The play set gates the Games section; a user with these linked games
          // has them active (as the backfill guarantees).
          active_games: ['chess.lichess', 'cs2.steam', 'dota2.opendota'],
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
    vi.mocked(useLinks).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        games: [
          gameLink({
            game: 'cs2.steam',
            display_name: 'CS2 — FACEIT',
            status: 'LINKED',
            host_username: 's1mple',
            win_streak: 5,
            profile: {
              username: 's1mple',
              display_name: 's1mple',
              url: '',
              link_method: 'username',
              game: 'cs2.steam',
              account_age_days: null,
              win_rate: 0.6,
              draw_rate: 0,
              total_games: 100,
              formats: [],
              primary_speed: null,
              rating: 3900,
              rank_label: 'Level 10',
              kd: 1.3,
              avatar_url: null,
            },
          }),
          gameLink({
            game: 'dota2.opendota',
            display_name: 'Dota 2 — OpenDota',
            status: 'BLOCKED',
          }),
          gameLink({ status: 'UNLINKED' }),
        ],
      },
    } as unknown as ReturnType<typeof useLinks>);
    vi.mocked(useResetDemo).mockReturnValue({
      mutate: resetMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useResetDemo>);
  });

  it('renders LINKED / BLOCKED, the skill badge + win streak, and editable limits', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('Linked')).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.getByText('s1mple · 100 games')).toBeInTheDocument();
    expect(screen.getByText('Level 10')).toBeInTheDocument(); // skill badge
    expect(screen.getByText('5 win streak')).toBeInTheDocument(); // win streak
    expect(screen.getByDisplayValue('200')).toBeInTheDocument(); // daily loss cap ($)
  });

  it('runs the link flow for an unlinked game', () => {
    renderWithProviders(<ProfilePage />);
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    fireEvent.change(screen.getByPlaceholderText('Your Lichess username'), {
      target: { value: 'magnus' },
    });
    // First click shows the permanent-link confirmation.
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
    expect(screen.getByText(/permanently links/)).toBeInTheDocument();
    // Second click confirms and triggers the mutation.
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

    // Collapsed until the button is pressed.
    expect(
      screen.queryByPlaceholderText('Enter current password'),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }));

    // Step 1: confirm current password (no email-based reset — accounts are
    // username-only with no inbox on file).
    expect(screen.getByPlaceholderText('Enter current password')).toBeInTheDocument();
    expect(
      screen.queryByText('Forgot your password? Verify with email.'),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Enter current password'), {
      target: { value: 'oldpass1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(verifyCurrentPassword).toHaveBeenCalledWith('oldpass1');

    // Step 2: set + confirm the new password, which calls changePassword.
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

  it('hides the security section for a demo session', () => {
    vi.mocked(useAuth).mockReturnValue({
      signOut: vi.fn(),
      isDemo: true,
      verifyCurrentPassword,
      changePassword,
    } as unknown as ReturnType<typeof useAuth>);
    renderWithProviders(<ProfilePage />);
    expect(
      screen.queryByRole('button', { name: 'Change password' }),
    ).not.toBeInTheDocument();
  });

  it('offers a demo reset that confirms before resetting', () => {
    vi.mocked(useAuth).mockReturnValue({
      signOut: vi.fn(),
      isDemo: true,
      verifyCurrentPassword,
      changePassword,
    } as unknown as ReturnType<typeof useAuth>);
    renderWithProviders(<ProfilePage />);

    fireEvent.click(screen.getByRole('button', { name: 'Reset demo' }));
    // Two-step: nothing resets until the second confirm.
    expect(resetMutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Yes, reset the demo' }));
    expect(resetMutate).toHaveBeenCalled();
  });

  it('hides the demo reset for real accounts', () => {
    renderWithProviders(<ProfilePage />); // isDemo false by default
    expect(
      screen.queryByRole('button', { name: 'Reset demo' }),
    ).not.toBeInTheDocument();
  });
});
