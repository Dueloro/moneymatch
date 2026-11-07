export const NAV = [
  { to: '/pools', label: 'Play' },
  { to: '/activity', label: 'Activity' },
  { to: '/social', label: 'Social' },
  { to: '/wallet', label: 'Wallet' },
] as const;

export const PLAY_MODES = [
  { to: '/pools', label: 'Solo pools' },
  { to: '/tournament', label: 'Tournament' },
  { to: '/play', label: 'Head-to-head' },
] as const;

const PLAY_PATHS = new Set<string>(PLAY_MODES.map((m) => m.to));

export function isPlayPath(pathname: string): boolean {
  return PLAY_PATHS.has(pathname);
}
