import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { ProfilePage } from './ProfilePage';

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ signOut: vi.fn() }),
}));

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

import { useMe, useSelfExclude } from '../hooks/useMe';
import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
} from '../hooks/useLinks';

const createMutate = vi.fn();
const selfExcludeMutate = vi.fn();

function gameLink(over: Partial<GameLink>): GameLink {
  return {
    game: 'chess.lichess',
    display_name: 'Chess — Lichess',
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    ...over,
  };
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
          max_concurrent_contests: 3,
          pending_limits: null,
          pending_effective_at: null,
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
            game: 'cs2.faceit',
            display_name: 'CS2 — FACEIT',
            status: 'LINKED',
            host_username: 's1mple',
            profile: {
              username: 's1mple',
              display_name: 's1mple',
              url: '',
              link_method: 'username',
              game: 'cs2.faceit',
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
  });

  it('renders LINKED / BLOCKED / limits', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('Linked')).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.getByText('s1mple · Level 10 · 100 games')).toBeInTheDocument();
    expect(screen.getByText('$200.00')).toBeInTheDocument(); // daily loss cap
  });

  it('runs the link flow for an unlinked game', () => {
    renderWithProviders(<ProfilePage />);
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    fireEvent.change(screen.getByPlaceholderText('Your username'), {
      target: { value: 'magnus' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Verify' }));
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
});
