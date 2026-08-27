/* eslint-disable react-refresh/only-export-components -- config module: exports
   the gameMeta helper alongside internal icon components. */
import type { FC } from 'react';

/** Per-game presentation: a clean display name (no acronyms), a compact label,
 * an accent color, and a small icon. Keyed by the host game id. */
export interface GameMeta {
  id: string;
  name: string;
  short: string;
  accent: string;
  Icon: FC<{ className?: string }>;
}

const ChessIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <path d="M4 9.2 7.6 12 12 5l4.4 7L20 9.2V16H4V9.2Z" />
    <rect x="5.5" y="17.2" width="13" height="2.4" rx="1" />
  </svg>
);

const CrosshairIcon: FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 24 24"
    className={className}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    aria-hidden
  >
    <circle cx="12" cy="12" r="7" />
    <path d="M12 2.5v3.5M12 18v3.5M2.5 12H6M18 12h3.5" strokeLinecap="round" />
  </svg>
);

const ShieldIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <path d="M12 2.5 20 5v5.5c0 5-3.4 8.4-8 10.5-4.6-2.1-8-5.5-8-10.5V5l8-2.5Z" />
  </svg>
);

const DotIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <circle cx="12" cy="12" r="6" />
  </svg>
);

const PubgIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <path d="M3 7.5 12 4l9 3.5-2 2.2-7-2.7-7 2.7L3 7.5Z" />
    <path d="M6.5 12.2 12 10l5.5 2.2-1.4 6.3L12 20l-4.1-1.5-1.4-6.3Z" />
  </svg>
);

const GAMES: Record<string, GameMeta> = {
  'chess.lichess': {
    id: 'chess.lichess',
    name: 'Chess',
    short: 'Chess',
    accent: '#e6c65c',
    Icon: ChessIcon,
  },
  'cs2.steam': {
    id: 'cs2.steam',
    name: 'Counter-Strike 2',
    short: 'CS2',
    accent: '#f0883e',
    Icon: CrosshairIcon,
  },
  'dota2.opendota': {
    id: 'dota2.opendota',
    name: 'Dota 2',
    short: 'Dota 2',
    accent: '#e15b4c',
    Icon: ShieldIcon,
  },
  'pubg.steam': {
    id: 'pubg.steam',
    name: 'PUBG',
    short: 'PUBG',
    accent: '#e8a13a',
    Icon: PubgIcon,
  },
};

/** Presentation for a game id. Falls back to a passed-in display name (with the
 * host suffix stripped) for any game not in the map. */
/**
 * Games that no longer exist but still appear in settled history.
 *
 * A contest that paid out keeps the game id it settled under -- rewriting it
 * would claim it settled somewhere it did not. But a row reading 'cs2.faceit'
 * is not a label, it is a leaked database value, so retired ids keep a display
 * name here. Nothing else about them survives: there is no adapter, no market
 * and no way to enter one.
 */
const RETIRED_GAMES: Record<string, { name: string; short: string }> = {
  'cs2.faceit': { name: 'Counter-Strike 2', short: 'CS2' },
};

export function gameMeta(id: string, fallbackName?: string): GameMeta {
  const known = GAMES[id];
  if (known) return known;

  const retired = RETIRED_GAMES[id];
  if (retired) {
    return {
      id,
      name: retired.name,
      short: retired.short,
      accent: 'var(--text-secondary)',
      Icon: CrosshairIcon,
    };
  }

  const name = (fallbackName ?? id).split(/[·—-]/)[0].trim() || id;
  return { id, name, short: name, accent: 'var(--text-secondary)', Icon: DotIcon };
}

/**
 * Games in the catalog but not yet linkable/playable (no adapter). The server is
 * the source of truth via the `COMING_SOON` link status; this mirror lets the
 * switcher and Play screens flag a game without waiting on a /links round-trip.
 */
const COMING_SOON_GAMES = new Set<string>([]);

export function isComingSoon(id: string): boolean {
  return COMING_SOON_GAMES.has(id);
}

// --------------------------------------------------------------------------- //
// Game-select onboarding config — the ONE table driving the selection overlay,
// app-wide gating, and Profile add-back, in both demo and production.
//
// Demo vs. prod is a *context*, not a fork in the UI: every surface reads this
// table and its own context, so flipping a game from prod-locked to prod-live is
// a one-line change here (move its `production` row from OFF to ON). Nothing else
// changes. Availability has two axes: `selectable` (can it be toggled) and
// `color` (full color vs. grayscale). Grayscale-but-selectable is deliberate —
// Dota in demo keeps its "coming soon" look while still being clickable.
// --------------------------------------------------------------------------- //

export type OnboardingContext = 'demo' | 'production';

export interface GameAvailability {
  /** Clickable / toggleable in this context. */
  selectable: boolean;
  /** Rendered in full color (vs. grayscale). */
  color: boolean;
}

export interface GameOnboardingConfig {
  id: string;
  /** Badge under the icon, or none. */
  badge: 'BETA' | 'SOON' | null;
  /** Pre-selected and required — cannot be deselected. Chess only. */
  preselected: boolean;
  demo: GameAvailability;
  production: GameAvailability;
}

const ON: GameAvailability = { selectable: true, color: true };
const GRAY_ON: GameAvailability = { selectable: true, color: false };
const OFF: GameAvailability = { selectable: false, color: false };

/** Display order in the overlay (Chess first — it is the launch game). */
export const ONBOARDING_GAME_ORDER = [
  'chess.lichess',
  'cs2.steam',
  'pubg.steam',
  'dota2.opendota',
] as const;

const ONBOARDING: Record<string, GameOnboardingConfig> = {
  'chess.lichess': {
    id: 'chess.lichess',
    badge: null,
    preselected: true,
    demo: ON,
    production: ON,
  },
  'cs2.steam': {
    id: 'cs2.steam',
    badge: 'BETA',
    preselected: false,
    demo: ON,
    production: OFF,
  },
  'pubg.steam': {
    id: 'pubg.steam',
    badge: 'BETA',
    preselected: false,
    demo: ON,
    production: OFF,
  },
  'dota2.opendota': {
    id: 'dota2.opendota',
    badge: 'SOON',
    preselected: false,
    // Demo: clickable but keeps the muted SOON look (grayscale, selectable).
    demo: GRAY_ON,
    production: OFF,
  },
};

/** The overlay's game configs, in display order. */
export function onboardingGames(): GameOnboardingConfig[] {
  return ONBOARDING_GAME_ORDER.map((id) => ONBOARDING[id]);
}

export function gameOnboarding(id: string): GameOnboardingConfig | undefined {
  return ONBOARDING[id];
}

/** Availability of a game in a given context (unknown games are locked off). */
export function availabilityFor(id: string, ctx: OnboardingContext): GameAvailability {
  const cfg = ONBOARDING[id];
  if (!cfg) return OFF;
  return ctx === 'demo' ? cfg.demo : cfg.production;
}

/** Games that can be added/kept in a given context (drives Profile add-back). */
export function selectableGames(ctx: OnboardingContext): string[] {
  return ONBOARDING_GAME_ORDER.filter((id) => availabilityFor(id, ctx).selectable);
}

/** The brand lime used for the filled selection circle (design guidelines). */
export const SELECT_FILL = '#c6f440';
