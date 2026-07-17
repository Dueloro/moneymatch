import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useMe } from '../hooks/useMe';
import { useAuth } from './useAuth';

/**
 * Route guard. Unauthenticated → /signin. Authenticated but not yet onboarded
 * → /signin (the flow resumes at the username/state step). Otherwise renders
 * the protected shell.
 */
export function RequireAuth() {
  const { session, loading } = useAuth();
  const location = useLocation();
  const me = useMe();

  if (loading) return <FullScreenLoader />;
  if (!session) return <Navigate to="/signin" replace state={{ from: location }} />;
  if (me.isLoading) return <FullScreenLoader />;
  if (me.data?.needs_onboarding && location.pathname !== '/signin') {
    return <Navigate to="/signin" replace />;
  }
  return <Outlet />;
}

function FullScreenLoader() {
  return (
    <div className="flex h-full items-center justify-center bg-bg text-text-secondary">
      Loading…
    </div>
  );
}
