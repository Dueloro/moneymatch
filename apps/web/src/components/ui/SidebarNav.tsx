import { Link, NavLink, useLocation } from 'react-router-dom';

import { useInboxUnread } from '../../hooks/useChat';
import { useDisplayBalance } from '../../hooks/useDisplayBalance';
import { useMe } from '../../hooks/useMe';
import { AnimatedBalance } from './AnimatedBalance';
import { Badge } from './Badge';
import { Logo } from './brand';
import { NavIcon } from './icons';
import { NAV, isPlayPath } from './nav';

export function SidebarNav() {
  const me = useMe();
  const available = useDisplayBalance();
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
        <Link to="/play" aria-label="Money Match home" className="inline-flex">
          <Logo />
        </Link>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
        {NAV.map((item) => {
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
            <AnimatedBalance cents={available} testId="sidebar-balance" />
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
