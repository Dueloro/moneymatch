import { lazy, Suspense, type ComponentType } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireAdmin } from './auth/RequireAdmin';
import { RequireAuth } from './auth/RequireAuth';
import { useAuth } from './auth/useAuth';
import { AppShell } from './components/AppShell';
import { Loader } from './components/ui/Loader';

const ActivityPage = lazyPage(() => import('./pages/ActivityPage'), 'ActivityPage');
const InvitePage = lazyPage(() => import('./pages/InvitePage'), 'InvitePage');
const LichessCallbackPage = lazyPage(
  () => import('./pages/LichessCallbackPage'),
  'LichessCallbackPage',
);
const PlayPage = lazyPage(() => import('./pages/PlayPage'), 'PlayPage');
const PoolsPage = lazyPage(() => import('./pages/PoolsPage'), 'PoolsPage');
const ProfilePage = lazyPage(() => import('./pages/ProfilePage'), 'ProfilePage');
const SignInPage = lazyPage(() => import('./pages/SignInPage'), 'SignInPage');
const SocialPage = lazyPage(() => import('./pages/SocialPage'), 'SocialPage');
const TournamentPage = lazyPage(
  () => import('./pages/TournamentPage'),
  'TournamentPage',
);
const WalletPage = lazyPage(() => import('./pages/WalletPage'), 'WalletPage');
const AdminLayout = lazyPage(() => import('./pages/admin/AdminLayout'), 'AdminLayout');
const AdminUsersPage = lazyPage(
  () => import('./pages/admin/AdminUsersPage'),
  'AdminUsersPage',
);
const AdminContestsPage = lazyPage(
  () => import('./pages/admin/AdminContestsPage'),
  'AdminContestsPage',
);
const AdminDisputesPage = lazyPage(
  () => import('./pages/admin/AdminDisputesPage'),
  'AdminDisputesPage',
);
const AdminSupportPage = lazyPage(
  () => import('./pages/admin/AdminSupportPage'),
  'AdminSupportPage',
);
const AdminFlagsPage = lazyPage(
  () => import('./pages/admin/AdminFlagsPage'),
  'AdminFlagsPage',
);
const AdminQueuePage = lazyPage(
  () => import('./pages/admin/AdminQueuePage'),
  'AdminQueuePage',
);
const AdminReconciliationPage = lazyPage(
  () => import('./pages/admin/AdminReconciliationPage'),
  'AdminReconciliationPage',
);
const AdminRiskPage = lazyPage(
  () => import('./pages/admin/AdminRiskPage'),
  'AdminRiskPage',
);

function lazyPage<T extends Record<K, ComponentType>, K extends keyof T>(
  load: () => Promise<T>,
  name: K,
) {
  return lazy(async () => ({ default: (await load())[name] }));
}

export function App() {
  return (
    <Suspense fallback={<Loader />}>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/signin" element={<SignInPage />} />
        <Route path="/i/:token" element={<InvitePage />} />
        <Route element={<RequireAuth />}>
          <Route path="link/lichess/callback" element={<LichessCallbackPage />} />
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
          <Route element={<RequireAdmin />}>
            <Route path="admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="/admin/users" replace />} />
              <Route path="users" element={<AdminUsersPage />} />
              <Route path="contests" element={<AdminContestsPage />} />
              <Route path="disputes" element={<AdminDisputesPage />} />
              <Route path="support" element={<AdminSupportPage />} />
              <Route path="queue" element={<AdminQueuePage />} />
              <Route path="flags" element={<AdminFlagsPage />} />
              <Route path="reconciliation" element={<AdminReconciliationPage />} />
              <Route path="risk" element={<AdminRiskPage />} />
            </Route>
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function RootRedirect() {
  const { session, loading } = useAuth();
  if (loading) return <Loader />;
  return <Navigate to={session ? '/play' : '/signin'} replace />;
}
