import { Link, useSearchParams } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { PlaySlip } from '../components/play/PlaySlip';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { GameTabs } from '../components/ui/GameTabs';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatCurrency } from '../lib/format';
import { gameMeta, isComingSoon } from '../lib/games';
import { useGameSelection } from '../hooks/useGameSelection';
import {
  prizeForEntry,
  useJoinQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
  type MarketRow,
  type QueueStatus,
} from '../hooks/useMatchmaking';

/** The market's headline resolution note (the part before the first "·"). */
function marketHeadline(market: MarketRow): string {
  return market.resolution_note.split('·')[0]?.trim() ?? '';
}

/** Default speed for a speed-gated market (chess): the middle option if present. */
function defaultSpeed(market: MarketRow): string | undefined {
  if (!market.requires_speed) return undefined;
  return market.speeds[1] ?? market.speeds[0] ?? undefined;
}

// States where the slip should show the confirm/active card for a deep-linked
// match; a terminal match falls through to the normal slip (reachable via Activity).
const DEEP_LINK_STATES = new Set(['PENDING', 'ACTIVE', 'AWAITING_RESULT']);

export function PlayPage() {
  const { games, selected: game, select: setGame } = useGameSelection();
  // Coming-soon games have no markets endpoint — don't fetch for them.
  const playableGame = game && !isComingSoon(game) ? game : undefined;

  const {
    data: markets,
    isLoading: marketsLoading,
    isError: marketsError,
    refetch: refetchMarkets,
  } = useMarkets(playableGame);

  // Inbox "Respond" lands here as /play?match=<id>; open that match's slip
  // directly (it isn't in the viewer's queue status when it came from a challenge).
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
          tolerance_stage: null,
          can_cancel: false,
        }
      : liveStatus;

  const waiting = useWaiting(playableGame);
  const join = useJoinQueue();
  const take = useTakeWaiting();

  const selectGame = games.find((g) => g.game === game);
  const linked = markets?.linked ?? false;
  const meta = game ? gameMeta(game, selectGame?.display_name) : null;
  const presets = markets?.entry_presets_cents ?? [];
  // A match is in flight — surface the slip and freeze new joins.
  const inFlight = status?.status === 'searching' || status?.status === 'matched';

  const header = (
    <div className="mb-6 flex items-center gap-4">
      <GameTabs games={games} selected={game} onSelect={setGame} />
      <BalanceHeader />
    </div>
  );

  if (game && isComingSoon(game)) {
    return (
      <div>
        {header}
        <ComingSoonPanel name={gameMeta(game, selectGame?.display_name).name} />
      </div>
    );
  }

  return (
    <div>
      {header}

      {marketsLoading ? (
        <SkeletonList rows={4} />
      ) : marketsError ? (
        <ErrorState title="Could not load markets" onRetry={() => refetchMarkets()} />
      ) : !linked ? (
        <EmptyState
          title={`Link your ${meta?.name ?? 'game'} account`}
          subline="Link a game account to play head-to-head for real payouts."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
            </Link>
          }
        />
      ) : (
        <>
          <p className="mb-6 max-w-2xl text-sm text-text-secondary">
            Head-to-head puts you 1v1 against an evenly-matched opponent for a preset
            stake. Pick what to wager on and we&apos;ll find your match.
          </p>

          {inFlight && (
            <div className="mb-8">
              <PlaySlip
                status={status}
                market={null}
                entryCents={null}
                presetsCents={presets}
                onSelectEntry={() => {}}
                onFindMatch={() => {}}
                finding={false}
              />
            </div>
          )}

          {!inFlight && (
            <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(markets?.markets ?? [])
                .filter((m) => !m.provisional)
                .flatMap((m) => {
                  const speed = defaultSpeed(m);
                  const speedTag = speed ? speed.toUpperCase() : undefined;
                  return presets.map((entry) => {
                    const key = `${game}:${m.key}:${speed ?? ''}:${entry}`;
                    return (
                      <WagerCard
                        key={key}
                        accent={meta?.accent ?? 'var(--text-secondary)'}
                        gameName={meta?.short ?? 'Game'}
                        tag={speedTag}
                        title={m.label}
                        subtitle={marketHeadline(m)}
                        entryCents={entry}
                        capacity={2}
                        filled={1}
                        oneVsOne
                        footnote={`You'd win ≈ ${formatCurrency(
                          prizeForEntry(entry, m.multiplier_bps),
                        )}`}
                        buttonLabel="Find Match"
                        joining={join.isPending}
                        onJoin={() =>
                          join.mutate({
                            game: game!,
                            market: m.key,
                            speed,
                            entry_preset_cents: entry,
                          })
                        }
                      />
                    );
                  });
                })}
            </div>
          )}

          <h2 className="mb-3 label-mono">Waiting to play</h2>
          {waiting.data && waiting.data.waiting.length > 0 ? (
            waiting.data.waiting.map((w) => (
              <ListRow
                key={w.ticket_id}
                title={w.username ?? 'Player'}
                subline={`${w.market_label} · ${formatCurrency(w.entry_cents)}`}
                right={
                  <PillButton
                    variant="secondary"
                    onClick={() => take.mutate(w.ticket_id)}
                    disabled={take.isPending || inFlight}
                  >
                    Match
                  </PillButton>
                }
              />
            ))
          ) : (
            <p className="py-4 text-sm text-text-secondary">
              No one waiting yet. Start a search and we&apos;ll pair you.
            </p>
          )}
        </>
      )}
    </div>
  );
}
