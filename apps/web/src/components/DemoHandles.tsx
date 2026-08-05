import { useState } from 'react';

import { useDemoRelink, useLinks, type GameLink } from '../hooks/useLinks';
import { gameMeta, isComingSoon } from '../lib/games';
import { PillButton } from './ui/PillButton';

/** The single best skill descriptor for a snapshot — a rank label, else a
 * rating. Mirrors LinkGames so a real profile reads the same in both places. */
function skillBadge(link: GameLink): string | null {
  const p = link.profile;
  if (!p) return null;
  const rating =
    p.rating ??
    p.formats.find((f) => f.speed === p.primary_speed)?.rating ??
    p.formats[0]?.rating ??
    null;
  return p.rank_label ?? (rating != null ? `Rating ${rating}` : null);
}

/**
 * Demo-only handle swap. The shared demo user is auto-linked to every game with
 * the placeholder handle "demo"; this panel points a game at a *real* account so
 * the live adapter verifies it and the real profile + skill land. One row per
 * playable game: current handle → real-username input → Save. Rendered on Profile
 * only when `isDemo`. Not shown to real users, whose bindings are immutable.
 */
export function DemoHandles() {
  const links = useLinks();

  if (links.isLoading) {
    return <p className="text-sm text-text-secondary">Loading games…</p>;
  }
  if (links.isError || !links.data) {
    return <p className="text-sm text-red">Couldn't load your games.</p>;
  }

  const rows = links.data.games.filter(
    (g) => g.status !== 'COMING_SOON' && !isComingSoon(g.game),
  );

  return (
    <div className="divide-y divide-hairline border-y border-hairline">
      {rows.map((g) => (
        <HandleRow key={g.game} link={g} />
      ))}
    </div>
  );
}

function HandleRow({ link }: { link: GameLink }) {
  const relink = useDemoRelink();
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const meta = gameMeta(link.game, link.display_name);
  const badge = skillBadge(link);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const handle = username.trim();
    if (!handle) return;
    setError(null);
    setSaved(false);
    relink.mutate(
      { game: link.game, username: handle },
      {
        onSuccess: () => {
          setUsername('');
          setSaved(true);
        },
        onError: (err: Error) => setError(err.message),
      },
    );
  };

  return (
    <form onSubmit={submit} className="py-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" style={{ color: meta.accent }}>
            {meta.name}
          </p>
          <p className="truncate text-xs text-text-secondary">
            {link.host_username ? `@${link.host_username}` : 'not linked'}
            {badge ? ` · ${badge}` : ''}
          </p>
        </div>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="real username"
          aria-label={`Real ${meta.name} username`}
          className="w-36 rounded-full border border-hairline bg-transparent px-3 py-1 text-sm"
        />
        <PillButton type="submit" disabled={relink.isPending || !username.trim()}>
          {relink.isPending ? 'Saving…' : 'Save'}
        </PillButton>
      </div>
      {error && <p className="mt-1 text-xs text-red">{error}</p>}
      {saved && !error && (
        <p className="mt-1 text-xs text-text-secondary">Linked — pulling real stats.</p>
      )}
    </form>
  );
}
