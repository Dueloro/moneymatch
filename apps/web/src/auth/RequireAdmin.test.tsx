import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RequireAdmin } from './RequireAdmin';

vi.mock('../hooks/useMe', () => ({ useMe: vi.fn() }));

import { useMe } from '../hooks/useMe';

function renderAt(role: string | undefined, isLoading = false) {
  vi.mocked(useMe).mockReturnValue({
    data: role ? { user: { role } } : undefined,
    isLoading,
  } as unknown as ReturnType<typeof useMe>);
  return render(
    <MemoryRouter initialEntries={['/admin/users']}>
      <Routes>
        <Route element={<RequireAdmin />}>
          <Route path="/admin/users" element={<div>ADMIN CONTENT</div>} />
        </Route>
        <Route path="/play" element={<div>PLAY PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RequireAdmin', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders admin content for an admin', () => {
    renderAt('admin');
    expect(screen.getByText('ADMIN CONTENT')).toBeInTheDocument();
  });

  it('bounces a non-admin to /play', () => {
    renderAt('user');
    expect(screen.getByText('PLAY PAGE')).toBeInTheDocument();
    expect(screen.queryByText('ADMIN CONTENT')).not.toBeInTheDocument();
  });
});
