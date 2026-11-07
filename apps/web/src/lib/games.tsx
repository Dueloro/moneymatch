/* eslint-disable react-refresh/only-export-components -- config module: exports
   the gameMeta helper alongside internal icon components. */
import type { FC } from 'react';

export interface GameMeta {
  id: string;
  name: string;
  accent: string;
  Icon: FC<{ className?: string }>;
}

const ChessIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <path d="M4 9.2 7.6 12 12 5l4.4 7L20 9.2V16H4V9.2Z" />
    <rect x="5.5" y="17.2" width="13" height="2.4" rx="1" />
  </svg>
);

const DotIcon: FC<{ className?: string }> = ({ className }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
    <circle cx="12" cy="12" r="6" />
  </svg>
);

export const CHESS = 'chess.lichess';

const GAMES: Record<string, GameMeta> = {
  [CHESS]: {
    id: CHESS,
    name: 'Chess',
    accent: '#e6c65c',
    Icon: ChessIcon,
  },
};

export function gameMeta(id: string, fallbackName?: string): GameMeta {
  const known = GAMES[id];
  if (known) return known;
  const name = (fallbackName ?? id).split(/[·—-]/)[0].trim() || id;
  return { id, name, accent: 'var(--text-secondary)', Icon: DotIcon };
}
