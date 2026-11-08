import { Outlet, useLocation } from 'react-router-dom';

import { useEventStream } from '../hooks/useEventStream';
import { ConnectPrompt } from './ConnectPrompt';
import { SettlementCelebration } from './SettlementCelebration';
import { SettlementProvider } from './SettlementProvider';
import { useMe } from '../hooks/useMe';
import { isExcludedState, stateName } from '../lib/usStates';
import { SideRail } from './rail/SideRail';
import { Card } from './ui/Card';
import { MobileTabBar, MobileTopBar } from './ui/MobileNav';
import { SidebarNav } from './ui/SidebarNav';
import { Ticker } from './ui/Ticker';

export function AppShell() {
  const { pathname } = useLocation();
  useEventStream();

  return (
    <SettlementProvider>
      <div className="flex min-h-screen flex-col bg-bg text-text md:h-screen md:flex-row md:overflow-hidden">
        <SettlementCelebration />
        <MobileTopBar />
        <SidebarNav />
        <main className="flex min-w-0 flex-1 flex-col pb-24 md:min-h-0 md:pb-0">
          <Ticker />
          <div className="mx-auto flex w-full max-w-app flex-col px-4 py-6 md:min-h-0 md:flex-1 md:px-8 md:py-8">
            <EligibilityBanner />
            <div className="grid grid-cols-1 gap-8 md:min-h-0 md:flex-1 xl:grid-cols-[minmax(0,1fr)_20rem]">
              <div className="min-w-0 md:overflow-y-auto md:pr-3">
                <ConnectPrompt />
                <Outlet />
              </div>
              <aside
                aria-label="Your board"
                className="hidden xl:block xl:overflow-y-auto"
              >
                <SideRail showBalance={pathname !== '/wallet'} />
              </aside>
            </div>
          </div>
        </main>
        <MobileTabBar />
      </div>
    </SettlementProvider>
  );
}

function EligibilityBanner() {
  const me = useMe();
  const state = me.data?.user.residence_state;
  if (!isExcludedState(state)) return null;

  return (
    <Card className="mb-6 px-4 py-3">
      <p className="text-sm text-text-secondary">
        Staked matches aren't available in {stateName(state)} yet. You can play every
        match for free until it is.
      </p>
    </Card>
  );
}
