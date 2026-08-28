import { Link, NavLink, useLocation } from 'react-router-dom';

import { useInboxUnread } from '../../hooks/useChat';
import { useDisplayBalance } from '../../hooks/useDisplayBalance';
import { useMe } from '../../hooks/useMe';
import { AnimatedBalance } from './AnimatedBalance';
import { Badge, BadgeDot } from './Badge';
import { Logo } from './brand';
import { BellIcon, NavIcon } from './icons';
import { NAV, isPlayPath } from './nav';

/**
 * Sticky top bar on mobile: logo left, balance and account right. The balance
 * moves here because the rail doesn't render on a phone, and it is the number a
 * returning player checks first.
 */
export function MobileTopBar() {
  const me = useMe();
  const available = useDisplayBalance();
  const unread = useInboxUnread();
  const username = me.data?.user.username ?? '…';

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-hairline bg-bg px-4 py-3 md:hidden">
      <Logo />
      <div className="flex items-center gap-2">
        <NavLink
          to="/wallet"
          className="rounded-pill bg-panel px-3 py-1.5 text-xs font-semibold text-green"
        >
          <AnimatedBalance cents={available} testId="mobile-balance" />
        </NavLink>
        <NavLink
          to="/social?tab=inbox"
          aria-label={unread > 0 ? `Inbox, ${unread} unread` : 'Inbox'}
          className="relative grid h-11 w-11 place-items-center rounded-inset text-text-secondary"
        >
          <BellIcon />
          <BadgeDot
            show={unread > 0}
            testId="inbox-unread-dot"
            className="absolute right-2 top-2"
          />
        </NavLink>
        <NavLink
          to="/profile"
          aria-label="Profile"
          className="grid h-9 w-9 place-items-center rounded-full bg-panel-raised text-xs font-semibold"
        >
          {username.slice(0, 1).toUpperCase()}
        </NavLink>
      </div>
    </header>
  );
}

/**
 * Fixed bottom tab bar on mobile. Four tabs at ~94px each on a 375px screen,
 * down from six at ~62px, so every target clears 44px comfortably.
 */
export function MobileTabBar() {
  const unread = useInboxUnread();
  const { pathname } = useLocation();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-20 flex items-stretch border-t border-hairline bg-bg pb-[env(safe-area-inset-bottom)] md:hidden"
      aria-label="Primary"
    >
      {NAV.map((item) => {
        const active =
          item.label === 'Play' ? isPlayPath(pathname) : pathname === item.to;
        return (
          <Link
            key={item.to}
            to={item.to}
            aria-current={active ? 'page' : undefined}
            className={[
              'relative flex min-h-[3.25rem] flex-1 flex-col items-center justify-center gap-1 py-2 text-micro font-medium transition-colors',
              active ? 'text-text' : 'text-text-secondary',
            ].join(' ')}
          >
            <span className="relative">
              <NavIcon to={item.to} />
              {item.to === '/social' && unread > 0 && (
                <Badge count={unread} className="absolute -right-3 -top-1.5" />
              )}
            </span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
