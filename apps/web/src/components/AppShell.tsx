import { Outlet, useLocation } from 'react-router-dom';

import { FooterBreadcrumb } from './ui/FooterBreadcrumb';
import { SidebarNav } from './ui/SidebarNav';

const BREADCRUMB: Record<string, string[]> = {
  '/play': ['PLAY'],
  '/pools': ['POOLS'],
  '/tournament': ['TOURNAMENT'],
  '/activity': ['ACTIVITY'],
  '/wallet': ['WALLET'],
  '/inbox': ['INBOX'],
  '/profile': ['PROFILE'],
};

/** Authenticated layout: sidebar + routed main column + footer breadcrumb. */
export function AppShell() {
  const location = useLocation();
  const segments = BREADCRUMB[location.pathname] ?? ['MONEY MATCH'];

  return (
    <div className="flex h-full min-h-screen bg-bg text-text">
      <SidebarNav />
      <main className="flex-1 overflow-y-auto px-10 py-8">
        <Outlet />
      </main>
      <FooterBreadcrumb segments={segments} />
    </div>
  );
}
