import { Navigate, Outlet } from 'react-router-dom';

import { useMe } from '../hooks/useMe';

/**
 * Admin route guard. Renders the admin tree only for `role === 'admin'`; anyone
 * else is bounced to /play. The server independently gates every /admin API call
 * (require_admin), so this is a UX guard, not the security boundary.
 */
export function RequireAdmin() {
  const me = useMe();
  if (me.isLoading) return <div style={{ padding: 24 }}>Loading…</div>;
  if (me.data?.user.role !== 'admin') return <Navigate to="/play" replace />;
  return <Outlet />;
}
