import { useState } from 'react';

import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
  type ProfileSnapshot,
} from '../hooks/useLinks';
import { CHESS, gameMeta } from '../lib/games';
import { TextInput } from './ui/Field';
import { SkeletonList } from './ui/Skeleton';
import { PillButton } from './ui/PillButton';

/** A row for a game we have no link record for yet (unlinked default). */
function unlinkedLink(id: string): GameLink {
  return {
    game: id,
    display_name: gameMeta(id).name,
    status: 'UNLINKED',
    host_username: null,
    linked_at: null,
    profile: null,
    win_streak: 0,
  };
}

/** The best rating for a snapshot: the primary speed's, else any. */
function skillBadge(p: ProfileSnapshot): string | null {
  const rating =
    p.rating ??
    p.formats.find((f) => f.speed === p.primary_speed)?.rating ??
    p.formats[0]?.rating ??
    null;
  return rating != null ? `Rating ${rating}` : null;
}

/**
 * The linked-account editor: one row per game the server offers (row →
 * username input → server verify → LINKED). Reused by Profile and the
 * onboarding link step.
 */
export function LinkGames() {
  const links = useLinks();

  if (links.isLoading) {
    return <SkeletonList rows={1} />;
  }
  if (links.isError || !links.data) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-sm text-red">Couldn't load your linked account.</p>
        <button
          type="button"
          className="text-sm text-text-secondary underline hover:text-text"
          onClick={() => void links.refetch()}
        >
          Try again
        </button>
      </div>
    );
  }

  const rows = links.data.games.length > 0 ? links.data.games : [unlinkedLink(CHESS)];

  return (
    <div className="divide-y divide-hairline border-y border-hairline">
      {rows.map((link) => (
        <GameRow key={link.game} link={link} />
      ))}
    </div>
  );
}

function GameRow({ link }: { link: GameLink }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const create = useCreateLink();
  const refresh = useRefreshLink();
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const meta = gameMeta(link.game, link.display_name);

  const { Icon } = meta;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!confirming) {
      setConfirming(true);
      return;
    }
    create.mutate(
      { game: link.game, username: username.trim() },
      {
        onSuccess: () => {
          setEditing(false);
          setConfirming(false);
          setUsername('');
        },
        onError: (err: Error) => {
          setError(err.message);
          setConfirming(false);
        },
      },
    );
  };

  return (
    <div className="py-3">
      <div className="flex items-center gap-3">
        <span className="shrink-0" style={{ color: meta.accent }}>
          <Icon className="h-5 w-5" />
        </span>

        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-text">{meta.name}</span>
          <div className="truncate text-xs text-text-secondary">
            {link.status === 'LINKED'
              ? link.profile
                ? `${link.host_username} · ${link.profile.total_games.toLocaleString('en-US')} games`
                : (link.host_username ?? 'Linked')
              : link.status === 'BLOCKED'
                ? 'Unavailable right now'
                : 'Link it to play'}
          </div>
          {link.status === 'LINKED' && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {link.profile && skillBadge(link.profile) && (
                <span
                  className="rounded-pill px-2 py-0.5 text-micro font-semibold"
                  style={{ color: meta.accent, backgroundColor: `${meta.accent}1f` }}
                >
                  {skillBadge(link.profile)}
                </span>
              )}
              {link.win_streak > 0 && (
                <span className="rounded-pill bg-panel-raised px-2 py-0.5 text-micro font-semibold text-text">
                  {link.win_streak} win streak
                </span>
              )}
            </div>
          )}
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
              <span className="text-xs font-semibold uppercase tracking-wide text-live">
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
          {!confirming ? (
            <>
              <div className="flex items-center gap-2">
                <TextInput
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-label={`Your ${meta.name} username`}
                  placeholder="Your Lichess username"
                />
                <PillButton
                  type="submit"
                  variant="primary"
                  disabled={!username.trim() || create.isPending}
                >
                  Verify
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
              <p className="text-xs text-text-secondary">
                Find yours at{' '}
                <a
                  href="https://lichess.org"
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-text"
                >
                  lichess.org
                </a>
              </p>
            </>
          ) : (
            <>
              <p className="text-xs text-text-secondary">
                This permanently links{' '}
                <span className="font-medium text-text">{username}</span> to your
                account. Contact support if you ever need to change it.
              </p>
              <div className="flex items-center gap-2">
                <PillButton type="submit" variant="primary" disabled={create.isPending}>
                  {create.isPending ? 'Linking…' : 'Link account'}
                </PillButton>
                <PillButton
                  type="button"
                  variant="text"
                  onClick={() => setConfirming(false)}
                >
                  Back
                </PillButton>
              </div>
            </>
          )}
          {error && <p className="text-xs text-red">{error}</p>}
        </form>
      )}
    </div>
  );
}
