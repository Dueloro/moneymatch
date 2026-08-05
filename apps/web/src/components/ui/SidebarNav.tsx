import { Link, NavLink, useLocation } from 'react-router-dom';

import { useInboxUnread } from '../../hooks/useChat';
import { useMe } from '../../hooks/useMe';
import { useWallet } from '../../hooks/useWallet';
import { formatCurrency } from '../../lib/format';
import { Badge } from './Badge';
import { Logo } from './brand';
import { NavIcon } from './icons';
import { NAV, isPlayPath } from './nav';

/**
 * Left sidebar (224px): logo, four primary nav entries, and a footer that
 * carries the account. The previous version listed six entries and then left
 * ~600px of nothing beneath them; the footer now closes that column with the
 * balance, which is the thing a returning player looks for first.
 *
 * Entries are 16px with the same glyphs as the mobile tab bar. At 14px and
 * text-only, four items in a 224px column read as a caption block rather than
 * as the app's primary navigation, and left the column looking empty. The
 * footer only actually reaches the bottom of the screen because `AppShell`
 * pins the shell to the viewport.
 */
export function SidebarNav() {
  const me = useMe();
  const { data: wallet } = useWallet();
  const unread = useInboxUnread();
  const { pathname } = useLocation();
  const username = me.data?.user.username ?? '…';
  const isAdmin = me.data?.user.role === 'admin';

  const link = (active: boolean) =>
    [
      'flex items-center gap-3 rounded-inset px-3 py-2.5 text-base font-medium transition-colors',
      active
        ? 'bg-panel-raised text-text'
        : 'text-text-secondary hover:bg-panel hover:text-text',
    ].join(' ');

  return (
    <nav
      aria-label="Primary"
      className="hidden w-56 shrink-0 flex-col border-r border-hairline px-3 py-5 md:flex"
    >
      <div className="mb-8 shrink-0 px-2">
        <Logo />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
        {NAV.map((item) => {
          // "Play" stays lit across all three contest modes, which live on
          // separate routes but are one destination to the player. NavLink
          // can't express that (it only knows its own path and would clear
          // aria-current), so active is computed here and announced properly.
          const active =
            item.label === 'Play' ? isPlayPath(pathname) : pathname === item.to;
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-current={active ? 'page' : undefined}
              className={link(active)}
            >
              <NavIcon to={item.to} className="h-5 w-5 shrink-0" />
              <span className="flex-1 truncate">{item.label}</span>
              {item.to === '/social' && <Badge count={unread} />}
            </Link>
          );
        })}
        {isAdmin && (
          <NavLink
            to="/admin"
            className={({ isActive }) => [link(isActive), 'mt-2'].join(' ')}
          >
            <NavIcon to="/admin" className="h-5 w-5 shrink-0" />
            <span className="flex-1 truncate">Admin</span>
          </NavLink>
        )}
      </div>

      <div className="mt-6 shrink-0 border-t border-hairline pt-4">
        <NavLink
          to="/wallet"
          className="block rounded-inset px-3 py-2 transition-colors hover:bg-panel"
        >
          <span className="label-money block">Balance</span>
          <span className="mt-0.5 block text-lg font-semibold text-green">
            {formatCurrency(wallet?.available_cents ?? 0)}
          </span>
        </NavLink>
        <NavLink
          to="/profile"
          className="mt-1 flex min-w-0 items-center gap-3 rounded-inset px-3 py-2 transition-colors hover:bg-panel"
        >
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-panel-raised text-sm font-semibold">
            {username.slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-sm text-text-secondary">{username}</span>
        </NavLink>
      </div>
    </nav>
  );
}
