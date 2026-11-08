import { Navigate, Outlet } from 'react-router-dom';

import { Loader } from '../components/ui/Loader';
import { useMe } from '../hooks/useMe';

export function RequireAdmin() {
  const me = useMe();
  if (me.isLoading) return <Loader />;
  if (me.data?.user.role !== 'admin') return <Navigate to="/play" replace />;
  return <Outlet />;
}
