import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { Loader } from '../components/ui/Loader';
import { useMe } from '../hooks/useMe';
import { useAuth } from './useAuth';

export function RequireAuth() {
  const { session, loading, signOut } = useAuth();
  const location = useLocation();
  const me = useMe();

  useEffect(() => {
    if (session && me.isError) {
      void signOut();
    }
  }, [session, me.isError, signOut]);

  if (loading) return <Loader />;
  if (!session) return <Navigate to="/signin" replace state={{ from: location }} />;
  if (me.isError) return <Loader />;
  if (me.isLoading) return <Loader />;
  if (me.data?.needs_onboarding && location.pathname !== '/signin') {
    return <Navigate to="/signin" replace />;
  }
  return <Outlet />;
}
