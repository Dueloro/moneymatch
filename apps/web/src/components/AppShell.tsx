import { Outlet, useLocation } from 'react-router-dom';

import { useEventStream } from '../hooks/useEventStream';
import { SettlementCelebration } from './SettlementCelebration';
import { useMe } from '../hooks/useMe';
import { isExcludedState, stateName } from '../lib/usStates';
import { SideRail } from './rail/SideRail';
import { Card } from './ui/Card';
import { MobileTabBar, MobileTopBar } from './ui/MobileNav';
import { SidebarNav } from './ui/SidebarNav';
import { Ticker } from './ui/Ticker';

/**
 * Authenticated layout: sidebar (desktop) / tab bars (mobile), a routed content
 * column, and a persistent right rail from 1280px up.
 *
 * The rail is what stops the app from being 60% empty black on a widescreen
 * (16-ui-revamp-plan §5). Below 1280px it collapses above the content, and
 * below 768px it doesn't render at all, since the mobile top bar already carries
 * the balance.
 *
 * **The desktop shell is the window, not the document.** From `md` up the root
 * is `h-screen` and the page itself never scrolls; the content column and the
 * rail each scroll on their own. The shell used to be `min-h-screen`, which let
 * the sidebar stretch to the height of the *document* — so on Pools its footer,
 * carrying the balance and the account link, sat a couple of thousand pixels
 * below the fold behind every contest card. Now it is always on screen, and the
 * chrome stays put while you browse. Phones keep native document scroll, where
 * it is the right behaviour and where the sticky top bar already handles this.
 *
 * Gone from the previous shell: the ambient lime corner glows and the fixed
 * footer breadcrumb, both decoration that duplicated information the nav already
 * carried. `GlowBackdrop` and `FooterBreadcrumb` still exist as components.
 */
export function AppShell() {
  const { pathname } = useLocation();
  // One app-wide SSE listener: server-pushed lifecycle events refresh the rail
  // and Activity instantly instead of waiting on the per-hook polls.
  useEventStream();

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text md:h-screen md:flex-row md:overflow-hidden">
      {/* Above everything, on every route: a contest can settle while you are
       * anywhere in the app, and the result is the one moment worth seeing. */}
      <SettlementCelebration />
      <MobileTopBar />
      <SidebarNav />
      <main className="flex min-w-0 flex-1 flex-col pb-24 md:min-h-0 md:pb-0">
        <Ticker />
        <div className="mx-auto flex w-full max-w-app flex-col px-4 py-6 md:min-h-0 md:flex-1 md:px-8 md:py-8">
          <EligibilityBanner />
          <div className="grid grid-cols-1 gap-8 md:min-h-0 md:flex-1 xl:grid-cols-[minmax(0,1fr)_20rem]">
            {/* `pr` keeps the column's own scrollbar off the content. Without
             * it the header's "How it works" and "Filters" buttons sit flush
             * against the scroll gutter. */}
            <div className="min-w-0 md:overflow-y-auto md:pr-3">
              <Outlet />
            </div>
            {/* Only from 1280px. Narrower than that the content column needs the
             * whole width, and the balance is already in the header. */}
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
    <Card className="mb-6 px-4 py-3">
      <p className="text-sm text-text-secondary">
        Cash play is not available in {stateName(state)} yet. You can play every match
        for free until it is.
      </p>
    </Card>
  );
}
