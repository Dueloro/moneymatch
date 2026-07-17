import { NavLink } from 'react-router-dom';

import { useMe } from '../../hooks/useMe';

const NAV = [
  { to: '/play', label: 'Play' },
  { to: '/pools', label: 'Pools' },
  { to: '/tournament', label: 'Tournament' },
  { to: '/activity', label: 'Activity' },
  { to: '/wallet', label: 'Wallet' },
];

/** Left sidebar (~184px): logo, primary nav, bottom bell + avatar chip. */
export function SidebarNav() {
  const me = useMe();
  const username = me.data?.user.username ?? '…';
  const unread = me.data?.unread_notifications ?? 0;

  return (
    <nav className="flex h-full w-[184px] shrink-0 flex-col bg-bg px-3 py-5">
      <div className="mb-8 flex items-center gap-2 px-2">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-green text-black">
          <span className="text-sm font-bold">M</span>
        </div>
        <span className="text-sm font-semibold">Money Match</span>
      </div>

      <div className="flex flex-1 flex-col gap-1">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'rounded-lg px-3 py-2 text-sm transition',
                isActive
                  ? 'bg-panel-raised text-text'
                  : 'text-text-secondary hover:text-text',
              ].join(' ')
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 px-1">
        <NavLink
          to="/inbox"
          aria-label={unread > 0 ? `Inbox (${unread} unread)` : 'Inbox'}
          className="relative grid h-8 w-8 place-items-center rounded-lg text-text-secondary hover:text-text"
        >
          <span aria-hidden>🔔</span>
          {unread > 0 && (
            <span
              data-testid="inbox-unread-dot"
              className="absolute right-1 top-1 h-2 w-2 rounded-full bg-green"
            />
          )}
        </NavLink>
        <NavLink
          to="/profile"
          className="flex min-w-0 items-center gap-2 rounded-lg px-1 py-1 hover:bg-panel-raised"
        >
          <span className="grid h-7 w-7 place-items-center rounded-full bg-panel-raised text-xs">
            {username.slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-sm text-text-secondary">{username}</span>
        </NavLink>
      </div>
    </nav>
  );
}
