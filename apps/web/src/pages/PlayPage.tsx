import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { PlaySlip } from '../components/play/PlaySlip';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
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

  // Filters — trim the market × entry browse grid down to what you want.
  const [marketFilter, setMarketFilter] = useState<string>(ALL);
  const [entryFilter, setEntryFilter] = useState<number | typeof ALL>(ALL);

  const selectGame = games.find((g) => g.game === game);
  const linked = markets?.linked ?? false;
  const meta = game ? gameMeta(game, selectGame?.display_name) : null;
  const presets = markets?.entry_presets_cents ?? [];
  // A match is in flight — surface the slip and freeze new joins.
  const inFlight = status?.status === 'searching' || status?.status === 'matched';

  // Only markets you can actually wager on are browsable — mirror that in the
  // filter options, then apply the active filters to the market × entry grid.
  const openMarkets = useMemo(
    () => (markets?.markets ?? []).filter((m) => !m.provisional),
    [markets],
  );
  const filteredMarkets = openMarkets.filter(
    (m) => marketFilter === ALL || m.key === marketFilter,
  );
  const filteredPresets = presets.filter(
    (e) => entryFilter === ALL || e === entryFilter,
  );
  const activeCount = (marketFilter !== ALL ? 1 : 0) + (entryFilter !== ALL ? 1 : 0);
  const filterable = openMarkets.length > 1 || presets.length > 1;
  const hasResults = filteredMarkets.length > 0 && filteredPresets.length > 0;

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

          {!inFlight && filterable && (
            <FilterBar
              testId="play-filters"
              activeCount={activeCount}
              onClear={() => {
                setMarketFilter(ALL);
                setEntryFilter(ALL);
              }}
            >
              {openMarkets.length > 1 && (
                <FilterChips
                  label="Market"
                  options={openMarkets.map((m) => m.key)}
                  selected={marketFilter}
                  onSelect={(v) => setMarketFilter(v as string)}
                  format={(k) =>
                    openMarkets.find((m) => m.key === k)?.label ?? String(k)
                  }
                />
              )}
              {presets.length > 1 && (
                <FilterChips
                  label="Entry"
                  options={presets}
                  selected={entryFilter}
                  onSelect={setEntryFilter}
                  format={(cents) => formatCurrency(cents)}
                />
              )}
            </FilterBar>
          )}

          {!inFlight &&
            (hasResults ? (
              <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {filteredMarkets.flatMap((m) => {
                  const speed = defaultSpeed(m);
                  const speedTag = speed ? speed.toUpperCase() : undefined;
                  return filteredPresets.map((entry) => {
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
            ) : (
              <p className="mb-8 py-8 text-sm text-text-secondary">
                No matches fit these filters.
              </p>
            ))}

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
