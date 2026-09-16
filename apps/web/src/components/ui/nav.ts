// Primary consumer navigation, shared by the desktop sidebar and the mobile
// bottom tab bar so the two stay in sync.
//
// Four items, down from six. Solo Pools, Tournament and Head-to-Head are three
// modes of one act, so they collapse into "Play" with a mode switcher at the top
// of that surface (16-ui-revamp-plan §5). Every route still exists and every
// mode is one tap away; the mobile bar goes from six ~62px tabs to four ~94px
// ones, which clears the 44px touch-target floor with room to spare.
export const NAV = [
  { to: '/play', label: 'Play' },
  { to: '/activity', label: 'Activity' },
  { to: '/social', label: 'Social' },
  { to: '/wallet', label: 'Wallet' },
] as const;

// The product is peer-to-peer only (IMPLEMENTATION_PHASES.md): winners are paid
// from the pot, never against a bar we set. So the two contest modes are the
// head-to-head duel and the tournament. Solo Pools and the bucketing bar-wager
// (both "beat a number we set") have been removed from the product.
export const PLAY_MODES = [
  { to: '/play', label: 'Head-to-head' },
  { to: '/tournament', label: 'Tournament' },
] as const;

const PLAY_PATHS = new Set<string>(PLAY_MODES.map((m) => m.to));

/** True when a pathname belongs to the Play surface (any contest mode). */
export function isPlayPath(pathname: string): boolean {
  return PLAY_PATHS.has(pathname);
}
