import { useState } from 'react';

import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
  type ProfileSnapshot,
} from '../hooks/useLinks';
import { PillButton } from './ui/PillButton';

/** Best single skill descriptor for a snapshot row (rank, else rating). */
function profileSummary(p: ProfileSnapshot): string {
  const rating =
    p.rating ??
    p.formats.find((f) => f.speed === p.primary_speed)?.rating ??
    p.formats[0]?.rating ??
    null;
  const parts = [
    p.rank_label ?? (rating != null ? `Rating ${rating}` : null),
    `${p.total_games.toLocaleString('en-US')} games`,
  ].filter(Boolean);
  return parts.join(' · ');
}

/**
 * Linked-games section (design PDF p.12): a row per game showing LINKED / BLOCKED
 * status, with the link flow (row → username input → server verify → LINKED).
 * Reused by Profile and onboarding step 3.
 */
export function LinkGames() {
  const links = useLinks();

  if (links.isLoading) {
    return <p className="text-sm text-text-secondary">Loading games…</p>;
  }
  if (links.isError || !links.data) {
    return <p className="text-sm text-red">Couldn't load your games.</p>;
  }

  return (
    <div className="divide-y divide-hairline border-y border-hairline">
      {links.data.games.map((g) => (
        <GameRow key={g.game} link={g} />
      ))}
    </div>
  );
}

function GameRow({ link }: { link: GameLink }) {
  const [editing, setEditing] = useState(false);
  const create = useCreateLink();
  const refresh = useRefreshLink();
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    create.mutate(
      { game: link.game, username: username.trim() },
      {
        onSuccess: () => {
          setEditing(false);
          setUsername('');
        },
        onError: (err: Error) => setError(err.message),
      },
    );
  };

  return (
    <div className="py-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-text">{link.display_name}</div>
          <div className="truncate text-xs text-text-secondary">
            {link.status === 'LINKED' && link.profile
              ? `${link.host_username} · ${profileSummary(link.profile)}`
              : link.status === 'BLOCKED'
                ? 'Unavailable right now'
                : 'Not linked'}
          </div>
        </div>

        <div className="shrink-0">
          {link.status === 'LINKED' && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => refresh.mutate(link.game)}
                disabled={refresh.isPending}
                className="text-xs text-text-secondary hover:text-text disabled:opacity-40"
              >
                {refresh.isPending ? 'Refreshing…' : 'Refresh'}
              </button>
              <span className="text-xs font-semibold uppercase tracking-wide text-green">
                Linked
              </span>
            </div>
          )}
          {link.status === 'BLOCKED' && (
            <span className="text-xs font-semibold uppercase tracking-wide text-red">
              Blocked
            </span>
          )}
          {link.status === 'UNLINKED' && !editing && (
            <PillButton variant="outline" onClick={() => setEditing(true)}>
              Link
            </PillButton>
          )}
        </div>
      </div>

      {link.status === 'UNLINKED' && editing && (
        <form className="mt-3 flex flex-col gap-2" onSubmit={submit}>
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={
                link.game === 'dota2.opendota' ? 'Steam name or ID' : 'Your username'
              }
              className="min-w-0 flex-1 rounded-pill border border-hairline bg-panel px-4 py-2 text-sm outline-none focus:border-text-secondary"
            />
            <PillButton
              type="submit"
              variant="primary"
              disabled={!username.trim() || create.isPending}
            >
              {create.isPending ? 'Verifying…' : 'Verify'}
            </PillButton>
            <PillButton
              type="button"
              variant="text"
              onClick={() => {
                setEditing(false);
                setError(null);
              }}
            >
              Cancel
            </PillButton>
          </div>
          {error && <p className="text-xs text-red">{error}</p>}
        </form>
      )}
    </div>
  );
}
