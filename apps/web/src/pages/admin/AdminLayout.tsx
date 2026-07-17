import { NavLink, Outlet } from 'react-router-dom';

import { styles } from './adminStyles';

const TABS = [
  ['users', 'Users'],
  ['contests', 'Contests'],
  ['queue', 'Queue'],
  ['flags', 'Flags'],
  ['reconciliation', 'Reconciliation'],
  ['risk', 'Risk'],
] as const;

export function AdminLayout() {
  return (
    <div style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>
      <nav
        style={{
          display: 'flex',
          gap: 4,
          padding: '8px 16px',
          borderBottom: '2px solid #333',
          background: '#fafafa',
          alignItems: 'center',
        }}
      >
        <strong style={{ marginRight: 12 }}>MoneyMatch Admin</strong>
        {TABS.map(([path, label]) => (
          <NavLink
            key={path}
            to={`/admin/${path}`}
            style={({ isActive }) => ({
              ...styles.button,
              background: isActive ? '#333' : '#eee',
              color: isActive ? '#fff' : '#000',
              textDecoration: 'none',
            })}
          >
            {label}
          </NavLink>
        ))}
        <NavLink to="/play" style={{ marginLeft: 'auto', fontSize: 12 }}>
          ← back to app
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
