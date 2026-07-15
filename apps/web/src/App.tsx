import { Navigate, Route, Routes } from 'react-router-dom';

import { RequireAuth } from './auth/RequireAuth';
import { AppShell } from './components/AppShell';
import { ActivityPage } from './pages/ActivityPage';
import { InboxPage } from './pages/InboxPage';
import { PlayPage } from './pages/PlayPage';
import { PoolsPage } from './pages/PoolsPage';
import { ProfilePage } from './pages/ProfilePage';
import { SignInPage } from './pages/SignInPage';
import { TournamentPage } from './pages/TournamentPage';
import { WalletPage } from './pages/WalletPage';

export function App() {
  return (
    <Routes>
      <Route path="/signin" element={<SignInPage />} />
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
      </Route>
      <Route path="*" element={<Navigate to="/play" replace />} />
    </Routes>
  );
}
