import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireAdmin } from './auth/RequireAdmin';
import { RequireAuth } from './auth/RequireAuth';
import { useAuth } from './auth/useAuth';
import { AppShell } from './components/AppShell';
import { ActivityPage } from './pages/ActivityPage';
import { InvitePage } from './pages/InvitePage';
import { PlayPage } from './pages/PlayPage';
import { PoolsPage } from './pages/PoolsPage';
import { ProfilePage } from './pages/ProfilePage';
import { SignInPage } from './pages/SignInPage';
import { SocialPage } from './pages/SocialPage';
import { TournamentPage } from './pages/TournamentPage';
import { WalletPage } from './pages/WalletPage';
import { AdminContestsPage } from './pages/admin/AdminContestsPage';
import { AdminDisputesPage } from './pages/admin/AdminDisputesPage';
import { AdminFlagsPage } from './pages/admin/AdminFlagsPage';
import { AdminLayout } from './pages/admin/AdminLayout';
import { AdminQueuePage } from './pages/admin/AdminQueuePage';
import { AdminReconciliationPage } from './pages/admin/AdminReconciliationPage';
import { AdminRiskPage } from './pages/admin/AdminRiskPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/i/:token" element={<InvitePage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="play" element={<PlayPage />} />
          <Route path="pools" element={<PoolsPage />} />
          <Route path="tournament" element={<TournamentPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="social" element={<SocialPage />} />
          <Route path="wallet" element={<WalletPage />} />
          <Route path="inbox" element={<Navigate to="/social?tab=inbox" replace />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>
        {/* Admin tree: separate, dense layout (not the consumer design system). */}
        <Route element={<RequireAdmin />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="/admin/users" replace />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="contests" element={<AdminContestsPage />} />
            <Route path="disputes" element={<AdminDisputesPage />} />
            <Route path="queue" element={<AdminQueuePage />} />
            <Route path="flags" element={<AdminFlagsPage />} />
            <Route path="reconciliation" element={<AdminReconciliationPage />} />
            <Route path="risk" element={<AdminRiskPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

/**
 * The bare domain has no marketing page: send visitors straight into the app.
 * Authenticated → Solo Pools (the default mode); everyone else → sign-in.
 */
function RootRedirect() {
  const { session, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-bg text-text-secondary">
        Loading…
      </div>
    );
  }
  return <Navigate to={session ? '/pools' : '/signin'} replace />;
}
