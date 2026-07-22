import { NavLink } from 'react-router-dom';

import { useMe } from '../../hooks/useMe';
import { Logo } from './brand';
import { BellIcon } from './icons';
import { NAV } from './nav';

/** Minimal stroke icons for the bottom tab bar (currentColor, 22px). */
const ICONS: Record<string, JSX.Element> = {
  '/play': (
    <path
      d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/pools': (
    <path
      d="M12 3s6 6.5 6 10.5A6 6 0 0 1 6 13.5C6 9.5 12 3 12 3Z"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/tournament': (
    <path
      d="M7 4h10v3a5 5 0 0 1-10 0V4Zm0 1H4v1a3 3 0 0 0 3 3m10-4h3v1a3 3 0 0 1-3 3M9 13.5V16h6v-2.5M8 20h8"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/activity': (
    <path d="M3 12h4l2 6 4-14 2 8h6" strokeLinejoin="round" strokeLinecap="round" />
  ),
  '/social': (
    <path
      d="M8.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.5 0a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 19v-1a4 4 0 0 1 4-4h3a4 4 0 0 1 4 4v1m1-5h1a4 4 0 0 1 4 4v1"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
  '/wallet': (
    <path
      d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm14 4h-3a2 2 0 0 0 0 4h3"
      strokeLinejoin="round"
      strokeLinecap="round"
    />
  ),
};

const MOBILE_LABEL: Record<string, string> = {
  '/play': 'H2H',
  '/pools': 'Pools',
  '/tournament': 'Tourneys',
};

/** Sticky top bar on mobile: logo left, inbox + avatar right. Desktop hides it
 * (the sidebar carries these). */
export function MobileTopBar() {
  const me = useMe();
  const username = me.data?.user.username ?? '…';
  const unread = me.data?.unread_notifications ?? 0;

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-hairline bg-bg px-4 py-3 md:hidden">
      <Logo />
      <div className="flex items-center gap-1">
        <NavLink
          to="/social?tab=inbox"
          aria-label={unread > 0 ? `Inbox (${unread} unread)` : 'Inbox'}
          className="relative grid h-9 w-9 place-items-center rounded-lg text-text-secondary"
        >
          <BellIcon />
          {unread > 0 && (
            <span
              data-testid="inbox-unread-dot"
              className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-green"
            />
          )}
        </NavLink>
        <NavLink
          to="/profile"
          aria-label="Profile"
          className="grid h-8 w-8 place-items-center rounded-full bg-panel-raised text-xs"
        >
          {username.slice(0, 1).toUpperCase()}
        </NavLink>
      </div>
    </header>
  );
}

/** Fixed bottom tab bar on mobile. Desktop hides it (the sidebar takes over). */
export function MobileTabBar() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-20 flex items-stretch border-t border-hairline bg-bg pb-[env(safe-area-inset-bottom)] md:hidden"
      aria-label="Primary"
    >
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            [
              'flex flex-1 flex-col items-center justify-center gap-1 py-2 text-[11px] font-medium transition',
              isActive ? 'text-green' : 'text-text-secondary',
            ].join(' ')
          }
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.7}
            className="h-[22px] w-[22px]"
            aria-hidden
          >
            {ICONS[item.to]}
          </svg>
          {MOBILE_LABEL[item.to] ?? item.label}
        </NavLink>
      ))}
    </nav>
  );
}
