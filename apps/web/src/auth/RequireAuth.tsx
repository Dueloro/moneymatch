import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { ErrorState } from '../components/ui/ErrorState';
import { Loader } from '../components/ui/Loader';
import { useMe } from '../hooks/useMe';
import { HttpError } from '../lib/apiError';
import { useAuth } from './useAuth';

export function RequireAuth() {
  const { session, loading, signOut } = useAuth();
  const location = useLocation();
  const me = useMe();
  // Only a rejected session ends it; an outage or a 5xx must not log anyone out.
  const rejected = me.error instanceof HttpError && me.error.status === 401;

  useEffect(() => {
    if (session && rejected) {
      void signOut();
    }
  }, [session, rejected, signOut]);

  if (loading) return <Loader />;
  if (!session) return <Navigate to="/signin" replace state={{ from: location }} />;
  if (rejected || me.isLoading) return <Loader />;
  if (!me.data && me.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <ErrorState
          title="Can't reach Money Match"
          subline="You're still signed in. Check your connection and try again."
          onRetry={() => void me.refetch()}
        />
      </div>
    );
  }
  if (me.data?.needs_onboarding && location.pathname !== '/signin') {
    return <Navigate to="/signin" replace />;
  }
  return <Outlet />;
}
