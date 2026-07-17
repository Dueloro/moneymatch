import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../test/testUtils';
import { FriendsPanel } from './FriendsPanel';

vi.mock('../hooks/useFriends', () => ({
  useFriends: vi.fn(),
  useAddFriend: vi.fn(),
  useRespondFriend: vi.fn(),
  useRemoveFriend: vi.fn(),
}));

import {
  useAddFriend,
  useFriends,
  useRemoveFriend,
  useRespondFriend,
} from '../hooks/useFriends';

const addMutate = vi.fn();
const respondMutate = vi.fn();

describe('FriendsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAddFriend).mockReturnValue({
      mutateAsync: addMutate,
      isPending: false,
      error: null,
    } as unknown as ReturnType<typeof useAddFriend>);
    vi.mocked(useRespondFriend).mockReturnValue({
      mutate: respondMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRespondFriend>);
    vi.mocked(useRemoveFriend).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveFriend>);
  });

  it('adds a friend by username and shows the friend code', () => {
    vi.mocked(useFriends).mockReturnValue({
      data: {
        your_friend_code: 'MM-7F3K2Q',
        friends: [],
        incoming: [],
        outgoing: [],
      },
    } as unknown as ReturnType<typeof useFriends>);
    renderWithProviders(<FriendsPanel />);

    expect(screen.getByText('MM-7F3K2Q')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Add friend/), {
      target: { value: 'bob' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(addMutate).toHaveBeenCalledWith('bob');
  });

  it('renders an incoming request with Accept and a friend with a Challenge pill', () => {
    vi.mocked(useFriends).mockReturnValue({
      data: {
        your_friend_code: 'MM-AAA111',
        friends: [
          { friendship_id: 'f1', user_id: 'u1', username: 'carol', online: true },
        ],
        incoming: [
          { friendship_id: 'f2', user_id: 'u2', username: 'dave', online: false },
        ],
        outgoing: [],
      },
    } as unknown as ReturnType<typeof useFriends>);
    renderWithProviders(<FriendsPanel />);

    expect(screen.getByText('carol')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Challenge' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(respondMutate).toHaveBeenCalledWith({
      friendshipId: 'f2',
      action: 'accept',
    });
  });
});
