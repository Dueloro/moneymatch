import { useState } from 'react';

import { useMe, useSetActiveGames } from '../hooks/useMe';
import {
  useCreateLink,
  useLinks,
  useRefreshLink,
  type GameLink,
  type ProfileSnapshot,
} from '../hooks/useLinks';
import {
  availabilityFor,
  gameMeta,
  gameOnboarding,
  isBetaGated,
  onboardingGames,
  type OnboardingContext,
} from '../lib/games';
import { TextInput } from './ui/Field';
import { SkeletonList } from './ui/Skeleton';
import { PillButton } from './ui/PillButton';

/** A row for a catalog game we have no link record for yet (unlinked default). */
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
 * Games section (design PDF p.12): the add/remove editor for the play set. One
 * row per game, in the onboarding order. A left checkmark toggles the game in
 * the player's play set (what gates the whole app) independent of linking; the
 * right side carries the link flow (row → username input → server verify →
 * LINKED). Reused by Profile and the onboarding link step.
 *
 * Availability is driven by the shared C2 config (`lib/games`) for the given
 * `context`, so demo vs. production is one table, not logic duplicated here:
 * - **Add** a game only if it's `selectable` in this context. In production
 *   that's Chess only; CS2/PUBG/Dota render grayscale + disabled with their
 *   badge until launch flips their `production` availability.
 * - **Remove** any currently-active game (except Chess, which is required) — it
 *   drops out of `active_games` and disappears from every play surface, but its
 *   linked account and history are untouched (nothing is deleted).
 *
 * Fail-closed: an empty play set is treated as Chess-only (matching the switcher
 * and the backfill), so editing never starts from an accidental "all games".
 *
 * `onlyActive` narrows the list to the player's chosen games (onboarding, right
 * after they picked).
 */
export function LinkGames({
  onlyActive = false,
  context = 'production',
}: {
  onlyActive?: boolean;
  context?: OnboardingContext;
}) {
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

  // Fail-closed: an empty set is Chess-only, never "every game". Mutations base
  // off this real set (not a fallback-expanded one) so a single edit can never
  // accidentally persist the whole catalog.
  const stored = me.data?.user.active_games ?? [];
  const activeList = stored.length > 0 ? stored : ['chess.lichess'];
  const activeSet = new Set(activeList);
  const byGame = new Map(links.data.games.map((g) => [g.game, g]));

  const setSelected = (game: string, on: boolean) => {
    // Chess is required — never toggles off. Every other gate (locked/not-yet
    // addable) is enforced by the row's disabled toggle, so this only runs for
    // genuinely allowed edits.
    if (gameOnboarding(game)?.preselected) return;
    const next = on ? [...activeList, game] : activeList.filter((g) => g !== game);
    setActiveGames.mutate(next);
  };

  const configs = onlyActive
    ? onboardingGames().filter((c) => activeSet.has(c.id))
    : onboardingGames();

  return (
    <div className="divide-y divide-hairline border-y border-hairline">
      {configs.map((cfg) => (
        <GameRow
          key={cfg.id}
          link={byGame.get(cfg.id) ?? unlinkedLink(cfg.id)}
          context={context}
          selected={activeSet.has(cfg.id)}
          onToggleSelect={() => setSelected(cfg.id, !activeSet.has(cfg.id))}
          onLinked={() => {
            if (!activeSet.has(cfg.id)) setSelected(cfg.id, true);
          }}
        />
      ))}
    </div>
  );
}

function GameRow({
  link,
  context,
  selected,
  onToggleSelect,
  onLinked,
}: {
  link: GameLink;
  context: OnboardingContext;
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

  const cfg = gameOnboarding(link.game);
  const avail = availabilityFor(link.game, context);
  const preselected = cfg?.preselected ?? false;
  const hasBinding = link.status === 'LINKED' || link.status === 'BLOCKED';
  // "Locked" = can't be added yet in this context (e.g. Dota in prod, or a
  // beta-gated CS2/PUBG for a user without a beta invite) AND has no real
  // binding of its own. A game already in the play set, or one the player has
  // actually linked, always renders normally (removable/visible) — the launch
  // gate only hides games that are neither yours nor addable yet.
  //
  // NB: CS2/PUBG are now `selectable` in production config (so the onboarding
  // overlay can present them as real tiles), so `isBetaGated` — not
  // `avail.selectable` — is what keeps them locked here. Without it, Profile
  // would silently let a production user add a beta game the overlay blocks.
  const locked =
    !preselected &&
    !selected &&
    !hasBinding &&
    (!avail.selectable ||
      isBetaGated(link.game, context) ||
      link.status === 'COMING_SOON');
  const grayscale = locked || (!selected && !avail.color);
  const toggleDisabled = preselected || locked;
  const lockReason = cfg?.badge === 'SOON' ? 'Coming soon' : 'Available after launch';
  const toggleLabel = preselected
    ? `${meta.name} (always on)`
    : locked
      ? `${meta.name} (${lockReason.toLowerCase()})`
      : selected
        ? `Remove ${meta.name}`
        : `Add ${meta.name}`;

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
    <div className={`py-3 ${grayscale ? 'opacity-50 grayscale' : ''}`}>
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-disabled={toggleDisabled || undefined}
          disabled={toggleDisabled}
          aria-label={toggleLabel}
          title={locked ? lockReason : undefined}
          onClick={onToggleSelect}
          className="grid h-5 w-5 shrink-0 place-items-center rounded-full border text-bg transition disabled:cursor-not-allowed"
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
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-text">{meta.name}</span>
            {cfg?.badge && (
              <span className="rounded-pill bg-panel px-1.5 py-0.5 text-micro font-semibold uppercase tracking-wide text-text-secondary">
                {cfg.badge}
              </span>
            )}
          </div>
          <div className="truncate text-xs text-text-secondary">
            {locked
              ? lockReason
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
          {!locked && link.status === 'LINKED' && (
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
          {!locked && link.status === 'BLOCKED' && (
            <span className="text-xs font-semibold uppercase tracking-wide text-red">
              Blocked
            </span>
          )}
          {!locked && link.status === 'UNLINKED' && !editing && (
            <PillButton variant="outline" onClick={() => setEditing(true)}>
              Link
            </PillButton>
          )}
        </div>
      </div>

      {!locked && link.status === 'UNLINKED' && editing && (
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
