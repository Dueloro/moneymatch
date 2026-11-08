import { useLocation } from 'react-router-dom';

import { useLinks } from '../hooks/useLinks';
import { useMe, useSetDismissedChecklists } from '../hooks/useMe';
import { CHESS } from '../lib/games';
import { ConnectLichessButton } from './ConnectLichess';
import { isPlayPath } from './ui/nav';

/** Play routes and Profile already lead with Connect Lichess. */
function pageOffersConnect(pathname: string): boolean {
  return isPlayPath(pathname) || pathname === '/profile';
}

export function ConnectPrompt() {
  const { pathname } = useLocation();
  const me = useMe();
  const links = useLinks();
  const dismiss = useSetDismissedChecklists();

  if (!links.data || !me.data) return null;
  if (links.data.games.some((g) => g.status === 'LINKED')) return null;
  if ((me.data.user.dismissed_checklists ?? []).includes(CHESS)) return null;
  if (pageOffersConnect(pathname)) return null;

  return (
    <div
      data-testid="connect-prompt"
      className="mb-6 flex items-center gap-3 rounded-card border border-hairline bg-panel py-2 pl-4 pr-2"
    >
      <p className="min-w-0 flex-1 text-sm text-text-secondary">
        Connect Lichess to play.
      </p>
      <ConnectLichessButton size="sm" />
      <button
        type="button"
        onClick={() => dismiss.mutate(CHESS)}
        aria-label="Dismiss"
        className="grid h-8 w-8 shrink-0 touch:h-11 touch:w-11 place-items-center rounded-full text-text-tertiary transition hover:bg-panel-raised hover:text-text focus-visible:outline-none focus-visible:ring-2"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
          <path
            d="M6 6l12 12M18 6L6 18"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}
