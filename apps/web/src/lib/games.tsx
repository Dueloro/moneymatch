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

const GAMES: Record<string, GameMeta> = {
  'chess.lichess': {
    id: 'chess.lichess',
    name: 'Chess',
    short: 'Chess',
    accent: '#e6c65c',
    Icon: ChessIcon,
  },
  'cs2.faceit': {
    id: 'cs2.faceit',
    name: 'Counter Strike 2',
    short: 'Counter Strike',
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
};

/** Presentation for a game id. Falls back to a passed-in display name (with the
 * host suffix stripped) for any game not in the map. */
export function gameMeta(id: string, fallbackName?: string): GameMeta {
  const known = GAMES[id];
  if (known) return known;
  const name = (fallbackName ?? id).split(/[·—-]/)[0].trim() || id;
  return { id, name, short: name, accent: 'var(--text-secondary)', Icon: DotIcon };
}
