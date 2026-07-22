// Primary consumer navigation, shared by the desktop sidebar and the mobile
// bottom tab bar so the two stay in sync.
export const NAV = [
  { to: '/play', label: 'Play' },
  { to: '/pools', label: 'Pools' },
  { to: '/tournament', label: 'Tournament' },
  { to: '/activity', label: 'Activity' },
  { to: '/wallet', label: 'Wallet' },
] as const;
