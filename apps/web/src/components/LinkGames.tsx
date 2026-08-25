import { useState } from 'react';

import { useMe, useSetActiveGames } from '../hooks/useMe';
import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
  type ProfileSnapshot,
} from '../hooks/useLinks';
import { gameMeta, isComingSoon } from '../lib/games';
import { TextInput } from './ui/Field';
import { SkeletonList } from './ui/Skeleton';
import { PillButton } from './ui/PillButton';

/** The single best skill descriptor for a snapshot: a rank label, else a
 * rating. Drives the per-game skill badge. */
function skillBadge(p: ProfileSnapshot): string | null {
  const rating =
    p.rating ??
    p.formats.find((f) => f.speed === p.primary_speed)?.rating ??
    p.formats[0]?.rating ??
    null;
  return p.rank_label ?? (rating != null ? `Rating ${rating}` : null);
}

/**
 * Games section (design PDF p.12): the full catalog, one row per game. A left
 * checkmark toggles the game in the player's play set (what shows in the
 * switcher) independent of linking; the right side carries the link flow
 * (row → username input → server verify → LINKED) or a "coming soon" note for
 * games without an adapter yet. Reused by Profile and the onboarding link step.
 *
 * `onlyActive` narrows the list to the player's chosen games (used in
 * onboarding, where they've just picked); it falls back to the full catalog
 * when nothing is chosen yet.
 */
export function LinkGames({ onlyActive = false }: { onlyActive?: boolean }) {
  const links = useLinks();
  const me = useMe();
  const setActiveGames = useSetActiveGames();

  if (links.isLoading) {
    return <SkeletonList rows={3} />;
  }
  if (links.isError || !links.data) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-sm text-red">Couldn't load your games.</p>
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

  // An empty play set means "not chosen yet" — the switcher falls back to every
  // playable game, so we show those as the effective selection here too. That
  // keeps the checkmarks in sync with the bar and makes the first edit additive
  // (checking a new game adds to the visible set rather than replacing it).
  const stored = me.data?.user.active_games ?? [];
  const registeredIds = links.data.games
    .filter((g) => !isComingSoon(g.game))
    .map((g) => g.game);
  const active = stored.length > 0 ? stored : registeredIds;
  const activeSet = new Set(active);

  const setSelected = (game: string, on: boolean) => {
    const next = on ? [...active, game] : active.filter((g) => g !== game);
    setActiveGames.mutate(next);
  };

  const rows =
    onlyActive && stored.length > 0
      ? links.data.games.filter((g) => activeSet.has(g.game))
      : links.data.games;

  return (
    <div className="divide-y divide-hairline border-y border-hairline">
      {rows.map((g) => (
        <GameRow
          key={g.game}
          link={g}
          selected={activeSet.has(g.game)}
          onToggleSelect={() => setSelected(g.game, !activeSet.has(g.game))}
          onLinked={() => {
            if (!activeSet.has(g.game)) setSelected(g.game, true);
          }}
        />
      ))}
    </div>
  );
}

function GameRow({
  link,
  selected,
  onToggleSelect,
  onLinked,
}: {
  link: GameLink;
  selected: boolean;
  onToggleSelect: () => void;
  onLinked: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const create = useCreateLink();
  const refresh = useRefreshLink();
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const meta = gameMeta(link.game, link.display_name);
  const soon = link.status === 'COMING_SOON' || isComingSoon(link.game);

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
          onLinked();
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
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-label={selected ? `Remove ${meta.name}` : `Add ${meta.name}`}
          onClick={onToggleSelect}
          className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-bg transition"
          style={
            selected
              ? { backgroundColor: meta.accent, borderColor: meta.accent }
              : { borderColor: 'var(--hairline)' }
          }
        >
          {selected && <CheckIcon className="h-3 w-3" />}
        </button>

        <div className="min-w-0 flex-1">
          {/* meta.name, not display_name: the server sends "CS2 — FACEIT" and
           * the copy rules ban the em dash. */}
          <div className="text-sm font-medium text-text">{meta.name}</div>
          <div className="truncate text-xs text-text-secondary">
            {soon
              ? 'Linking coming soon'
              : link.status === 'LINKED'
                ? link.profile
                  ? `${link.host_username} · ${link.profile.total_games.toLocaleString('en-US')} games`
                  : (link.host_username ?? 'Linked')
                : link.status === 'BLOCKED'
                  ? 'Unavailable right now'
                  : selected
                    ? 'Link it to play'
                    : 'Not linked'}
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
          {soon && (
            <span className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Soon
            </span>
          )}
          {!soon && link.status === 'LINKED' && (
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
          {!soon && link.status === 'BLOCKED' && (
            <span className="text-xs font-semibold uppercase tracking-wide text-red">
              Blocked
            </span>
          )}
          {!soon && link.status === 'UNLINKED' && !editing && (
            <PillButton variant="outline" onClick={() => setEditing(true)}>
              Link
            </PillButton>
          )}
        </div>
      </div>

      {!soon && link.status === 'UNLINKED' && editing && (
        <form className="mt-3 flex flex-col gap-2" onSubmit={submit}>
          {!confirming ? (
            <>
              <div className="flex items-center gap-2">
                <TextInput
                  autoFocus
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-label={`Your ${meta.name} username`}
                  placeholder={
                    link.game === 'chess.lichess'
                      ? 'Your Lichess username'
                      : link.game === 'dota2.opendota'
                        ? 'Steam name or ID'
                        : 'Your username'
                  }
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
              {link.game === 'chess.lichess' && (
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
              )}
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

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <path
        d="M5 12.5 10 17l9-10"
        stroke="currentColor"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
