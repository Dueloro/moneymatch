import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useMe } from '../hooks/useMe';
import { useAuth } from './useAuth';

/**
 * Route guard. Unauthenticated → /signin. Authenticated but not yet onboarded
 * → /signin (the flow resumes at the username/state step). Otherwise renders
 * the protected shell.
 */
export function RequireAuth() {
  const { session, loading, signOut } = useAuth();
  const location = useLocation();
  const me = useMe();

  // Stale/invalid JWT: /me fails — clear the session once so we don't spin on
  // Loading forever (seen when a kid-less HS256 token hit JWKS verification).
  useEffect(() => {
    if (session && me.isError) {
      void signOut();
    }
  }, [session, me.isError, signOut]);

  if (loading) return <FullScreenLoader />;
  if (!session) return <Navigate to="/signin" replace state={{ from: location }} />;
  if (me.isError) return <FullScreenLoader />;
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
