import { NavLink, Outlet } from 'react-router-dom';

import { INK, PAPER, styles } from './adminStyles';

const TABS = [
  ['users', 'Users'],
  ['contests', 'Contests'],
  ['disputes', 'Disputes'],
  ['support', 'Support'],
  ['queue', 'Queue'],
  ['flags', 'Flags'],
  ['reconciliation', 'Reconciliation'],
  ['risk', 'Risk'],
] as const;

export function AdminLayout() {
  return (
    <div style={styles.root} data-testid="admin-root">
      <nav
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          padding: '10px 16px',
          borderBottom: `2px solid ${INK}`,
          background: '#f4f4f5',
          alignItems: 'center',
        }}
      >
        <strong style={{ marginRight: 12, fontSize: 14 }}>Money Match admin</strong>
        {TABS.map(([path, label]) => (
          <NavLink
            key={path}
            to={`/admin/${path}`}
            style={({ isActive }) => ({
              ...styles.button,
              borderColor: isActive ? INK : '#52525b',
              background: isActive ? INK : PAPER,
              color: isActive ? PAPER : INK,
              textDecoration: 'none',
            })}
          >
            {label}
          </NavLink>
        ))}
        <NavLink
          to="/play"
          style={{
            marginLeft: 'auto',
            fontSize: 12,
            color: INK,
            textDecoration: 'underline',
          }}
        >
          ← back to app
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
