// Primary consumer navigation, shared by the desktop sidebar and the mobile
// bottom tab bar so the two stay in sync.
export const NAV = [
  { to: '/play', label: 'Head-to-Head' },
  { to: '/pools', label: 'Solo Pools' },
  { to: '/tournament', label: 'Tournament' },
  { to: '/activity', label: 'Activity' },
  { to: '/social', label: 'Social' },
  { to: '/wallet', label: 'Wallet' },
] as const;
