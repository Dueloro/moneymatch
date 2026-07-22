import { Outlet, useLocation } from 'react-router-dom';

import { useMe } from '../hooks/useMe';
import { isExcludedState, stateName } from '../lib/usStates';
import { GlowBackdrop } from './ui/brand';
import { FooterBreadcrumb } from './ui/FooterBreadcrumb';
import { MobileTabBar, MobileTopBar } from './ui/MobileNav';
import { SidebarNav } from './ui/SidebarNav';
import { Ticker } from './ui/Ticker';

const BREADCRUMB: Record<string, string[]> = {
  '/play': ['HEAD-TO-HEAD'],
  '/pools': ['SOLO POOLS'],
  '/tournament': ['TOURNAMENT'],
  '/activity': ['ACTIVITY'],
  '/social': ['SOCIAL'],
  '/wallet': ['WALLET'],
  '/profile': ['PROFILE'],
};

/** Authenticated layout: sidebar (desktop) / tab bars (mobile) + routed main
 * column + footer breadcrumb. */
export function AppShell() {
  const location = useLocation();
  const segments = BREADCRUMB[location.pathname] ?? ['MONEY MATCH'];

  return (
    <div className="relative flex h-full min-h-screen flex-col bg-bg text-text md:flex-row">
      <GlowBackdrop />
      <MobileTopBar />
      <SidebarNav />
      <main className="relative z-10 flex-1 overflow-y-auto pb-24 md:pb-8">
        <Ticker />
        <div className="mx-auto w-full max-w-[1180px] px-4 py-6 md:px-10 md:py-8">
          <EligibilityBanner />
          <Outlet />
        </div>
      </main>
      <MobileTabBar />
      <FooterBreadcrumb segments={segments} />
    </div>
  );
}

/** Persistent notice for users whose residence state has no cash play yet, so
 * they learn it up front rather than being bounced at escrow. Free play is
 * available everywhere (docs/product/overview.md §9.2). */
function EligibilityBanner() {
  const me = useMe();
  const state = me.data?.user.residence_state;
  if (!isExcludedState(state)) return null;

  return (
    <div className="mb-6 rounded-card border border-hairline bg-panel px-4 py-3 text-sm text-text-secondary">
      Cash play is not available in {stateName(state)} yet. You can play every match for
      free until it is.
    </div>
  );
}
