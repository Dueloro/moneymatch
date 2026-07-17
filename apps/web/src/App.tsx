import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireAdmin } from './auth/RequireAdmin';
import { RequireAuth } from './auth/RequireAuth';
import { AppShell } from './components/AppShell';
import { ActivityPage } from './pages/ActivityPage';
import { InboxPage } from './pages/InboxPage';
import { InvitePage } from './pages/InvitePage';
import { PlayPage } from './pages/PlayPage';
import { PoolsPage } from './pages/PoolsPage';
import { ProfilePage } from './pages/ProfilePage';
import { SignInPage } from './pages/SignInPage';
import { TournamentPage } from './pages/TournamentPage';
import { WalletPage } from './pages/WalletPage';
import { AdminContestsPage } from './pages/admin/AdminContestsPage';
import { AdminFlagsPage } from './pages/admin/AdminFlagsPage';
import { AdminLayout } from './pages/admin/AdminLayout';
import { AdminQueuePage } from './pages/admin/AdminQueuePage';
import { AdminReconciliationPage } from './pages/admin/AdminReconciliationPage';
import { AdminRiskPage } from './pages/admin/AdminRiskPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';

export function App() {
  return (
    <Routes>
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/i/:token" element={<InvitePage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/play" replace />} />
          <Route path="play" element={<PlayPage />} />
          <Route path="pools" element={<PoolsPage />} />
          <Route path="tournament" element={<TournamentPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="wallet" element={<WalletPage />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>
        {/* Admin tree: separate, dense layout (not the consumer design system). */}
        <Route element={<RequireAdmin />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="/admin/users" replace />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="contests" element={<AdminContestsPage />} />
            <Route path="queue" element={<AdminQueuePage />} />
            <Route path="flags" element={<AdminFlagsPage />} />
            <Route path="reconciliation" element={<AdminReconciliationPage />} />
            <Route path="risk" element={<AdminRiskPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/play" replace />} />
    </Routes>
  );
}
