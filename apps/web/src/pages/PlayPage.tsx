import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

import { PlayHeader } from '../components/PlayHeader';
import { LinkLichessDesk, MatchDesk } from '../components/play/MatchDesk';
import { MatchStage } from '../components/play/MatchStage';
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
import { clockFor, timeControlLabel } from '../lib/timeControl';
import { toast } from '../lib/toast';
import {
  useJoinQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
  type MatchView,
} from '../hooks/useMatchmaking';

const STAGE_STATES = new Set(['ACTIVE', 'AWAITING_RESULT', 'SETTLED', 'PUSHED']);

/** Both staked and then nothing could be graded: the stage shows the refund. */
const refundedAfterStart = (m: MatchView) =>
  m.state === 'CANCELED' && m.players.length > 0 && m.players.every((p) => p.confirmed);

export function PlayPage() {
  usePageTitle('Head to head');
  const {
    data: markets,
    isLoading: marketsLoading,
    isError: marketsError,
    refetch: refetchMarkets,
  } = useMarkets(CHESS);
  const { data: links } = useLinks();
  const chessLink = links?.games.find((g) => g.game === CHESS);

  // The match you're in is pinned to the URL, so its result stays on screen after
  // the queue goes idle (and survives a refresh) until you choose to play again.
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: liveStatus } = useQueueStatus();
  const queued = liveStatus?.status === 'matched' ? liveStatus.match : null;
  const pinnedId = searchParams.get('match') ?? undefined;
  const matchId = pinnedId ?? queued?.id;
  const { data: fetched } = useMatch(matchId);
  const match = fetched ?? (queued?.id === matchId ? queued : undefined);

  useEffect(() => {
    if (!pinnedId && queued) setSearchParams({ match: queued.id }, { replace: true });
  }, [pinnedId, queued, setSearchParams]);

  const seenPending = useRef(new Set<string>());
  const dropped = match?.state === 'CANCELED' && !refundedAfterStart(match);
  useEffect(() => {
    if (!match) return;
    if (match.state === 'PENDING') seenPending.current.add(match.id);
    if (dropped) {
      if (seenPending.current.has(match.id))
        toast.neutral(
          match.you_confirmed ? 'Match canceled · stake refunded' : 'Match canceled',
        );
      setSearchParams({}, { replace: true });
    }
  }, [match, dropped, setSearchParams]);

  const onStage = match && (STAGE_STATES.has(match.state) || refundedAfterStart(match));
  const confirming = match?.state === 'PENDING';
  const playAgain = () => setSearchParams({}, { replace: true });

  const waiting = useWaiting(CHESS);
  const join = useJoinQueue();
  const take = useTakeWaiting();

  const linked = markets?.linked ?? false;
  const presets = markets?.entry_presets_cents ?? [];
  const searching = liveStatus?.status === 'searching';
  const inFlight = !!onStage || confirming || searching;
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
      ) : onStage && match ? (
        <MatchStage match={match} clocks={market?.clocks} onPlayAgain={playAgain} />
      ) : confirming && match ? (
        <PlaySlip
          status={{ status: 'matched', match, waited_seconds: null, can_cancel: false }}
          clocks={market?.clocks}
        />
      ) : searching ? (
        <PlaySlip status={liveStatus} />
      ) : market && presets.length > 0 ? (
        <MatchDesk
          market={market}
          presets={presets}
          profile={chessLink?.profile}
          username={chessLink?.host_username}
          joining={join.isPending}
          onFind={({ speed, entry }) => {
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
              subline={[
                timeControlLabel(w.speed, clockFor(w.speed, market?.clocks)),
                formatPoints(w.entry_cents),
              ]
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
