// Primary consumer navigation, shared by the desktop sidebar and the mobile
// bottom tab bar so the two stay in sync.
//
// Four items, down from six. Solo Pools, Tournament and Head-to-Head are three
// modes of one act, so they collapse into "Play" with a mode switcher at the top
// of that surface (16-ui-revamp-plan §5). Every route still exists and every
// mode is one tap away; the mobile bar goes from six ~62px tabs to four ~94px
// ones, which clears the 44px touch-target floor with room to spare.
export const NAV = [
  { to: '/pools', label: 'Play' },
  { to: '/activity', label: 'Activity' },
  { to: '/social', label: 'Social' },
  { to: '/wallet', label: 'Wallet' },
] as const;

/** The three contest modes that live under "Play". */
export const PLAY_MODES = [
  { to: '/pools', label: 'Solo pools' },
  { to: '/tournament', label: 'Tournament' },
  { to: '/play', label: 'Head-to-head' },
] as const;

const PLAY_PATHS = new Set<string>(PLAY_MODES.map((m) => m.to));

/** True when a pathname belongs to the Play surface (any contest mode). */
export function isPlayPath(pathname: string): boolean {
  return PLAY_PATHS.has(pathname);
}
