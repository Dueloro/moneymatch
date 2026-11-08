import {
  useLinks,
  useRefreshLink,
  type GameLink,
  type ProfileSnapshot,
} from '../hooks/useLinks';
import { CHESS, gameMeta } from '../lib/games';
import { ConnectLichessButton, NotAffiliated } from './ConnectLichess';
import { SkeletonList } from './ui/Skeleton';

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

function skillBadge(p: ProfileSnapshot): string | null {
  const rating =
    p.rating ??
    p.formats.find((f) => f.speed === p.primary_speed)?.rating ??
    p.formats[0]?.rating ??
    null;
  return rating != null ? `Rating ${rating}` : null;
}

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
          className="inline-flex touch:min-h-11 items-center text-sm text-text-secondary underline hover:text-text"
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
  const refresh = useRefreshLink();
  const meta = gameMeta(link.game, link.display_name);

  const { Icon } = meta;

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
                className="inline-flex touch:min-h-11 items-center text-xs text-text-secondary hover:text-text disabled:opacity-40"
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
          {link.status === 'UNLINKED' && <ConnectLichessButton size="sm" />}
        </div>
      </div>

      {link.status === 'UNLINKED' && (
        <div className="mt-2 flex flex-col gap-0.5">
          <p className="text-xs text-text-secondary">
            We read your games from Lichess to settle matches.
          </p>
          <NotAffiliated />
        </div>
      )}
    </div>
  );
}
