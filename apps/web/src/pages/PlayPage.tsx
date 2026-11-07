import { useSearchParams } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { PlayHeader } from '../components/PlayHeader';
import { LinkLichessDesk, MatchDesk } from '../components/play/MatchDesk';
import { PlaySlip } from '../components/play/PlaySlip';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { Skeleton } from '../components/ui/Skeleton';
import { usePageTitle } from '../hooks/usePageTitle';
import { useLinks } from '../hooks/useLinks';
import { formatPoints } from '../lib/format';
import { CHESS } from '../lib/games';
import { recallTicket, rememberTicket } from '../lib/h2hTicket';
import { timeControlLabel } from '../lib/timeControl';
import {
  useJoinQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
  type QueueStatus,
} from '../hooks/useMatchmaking';

const DEEP_LINK_STATES = new Set(['PENDING', 'ACTIVE', 'AWAITING_RESULT']);

export function PlayPage() {
  usePageTitle('Head to head');
  const {
    data: markets,
    isLoading: marketsLoading,
    isError: marketsError,
    refetch: refetchMarkets,
  } = useMarkets(CHESS);
  const { session } = useAuth();
  const userId = session?.user.id;
  const { data: links } = useLinks();
  const chessLink = links?.games.find((g) => g.game === CHESS);

  const [searchParams] = useSearchParams();
  const deepLinkMatchId = searchParams.get('match') ?? undefined;
  const { data: deepLinkMatch } = useMatch(deepLinkMatchId);

  const { data: liveStatus } = useQueueStatus();
  const status: QueueStatus | undefined =
    deepLinkMatch && DEEP_LINK_STATES.has(deepLinkMatch.state)
      ? {
          status: 'matched',
          match: deepLinkMatch,
          waited_seconds: null,
          can_cancel: false,
        }
      : liveStatus;

  const waiting = useWaiting(CHESS);
  const join = useJoinQueue();
  const take = useTakeWaiting();

  const linked = markets?.linked ?? false;
  const presets = markets?.entry_presets_cents ?? [];
  const inFlight = status?.status === 'searching' || status?.status === 'matched';
  const market =
    markets?.markets.find((m) => m.kind === 'win_h2h') ?? markets?.markets[0];
  const open = waiting.data?.waiting ?? [];

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PlayHeader
        id="play"
        how="One Lichess game against a player at your level. Winner takes the pot, draws are refunded."
      />

      {marketsLoading ? (
        <Skeleton className="h-80 w-full rounded-card" />
      ) : marketsError ? (
        <ErrorState
          title="Could not load markets"
          subline="The connection dropped. Try again."
          onRetry={() => refetchMarkets()}
        />
      ) : !linked ? (
        <LinkLichessDesk />
      ) : inFlight ? (
        <PlaySlip
          status={status}
          ticket={status?.status === 'searching' ? recallTicket(userId) : null}
        />
      ) : market && presets.length > 0 ? (
        <MatchDesk
          market={market}
          presets={presets}
          profile={chessLink?.profile}
          username={chessLink?.host_username}
          joining={join.isPending}
          onFind={({ speed, entry, rating }) => {
            rememberTicket(userId, {
              speed: speed ?? null,
              entry_cents: entry,
              rating,
              at: Date.now(),
            });
            join.mutate({
              game: CHESS,
              market: market.key,
              speed,
              entry_preset_cents: entry,
            });
          }}
        />
      ) : (
        <EmptyState
          title="Head to head is paused"
          subline="Check back shortly."
          action={
            <PillButton variant="secondary" onClick={() => refetchMarkets()}>
              Refresh
            </PillButton>
          }
        />
      )}

      {linked && !inFlight && open.length > 0 && (
        <section className="mt-10" aria-label="Waiting to play">
          <SectionHeader level="sub" hint="Take a seat and skip the queue.">
            Waiting to play
          </SectionHeader>
          {open.map((w) => (
            <ListRow
              key={w.ticket_id}
              left={
                <span
                  aria-hidden
                  className="h-1.5 w-1.5 shrink-0 rounded-full bg-live"
                />
              }
              title={
                <>
                  {w.username ?? 'Player'}
                  {w.rating != null && (
                    <span className="num ml-2 text-xs font-normal text-text-tertiary">
                      {w.rating}
                    </span>
                  )}
                </>
              }
              subline={[timeControlLabel(w.speed), formatPoints(w.entry_cents)]
                .filter(Boolean)
                .join(' · ')}
              right={
                <PillButton
                  variant="secondary"
                  onClick={() => take.mutate(w.ticket_id)}
                  disabled={take.isPending}
                >
                  Match
                </PillButton>
              }
            />
          ))}
        </section>
      )}
    </div>
  );
}
