import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { ModeSwitcher } from '../components/ModeSwitcher';
import { PlaySlip } from '../components/play/PlaySlip';
import { CardGrid } from '../components/ui/CardGrid';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { GameTabs } from '../components/ui/GameTabs';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { dashless, formatCurrency } from '../lib/format';
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

/** The market's headline resolution note (the part before the first separator). */
function marketHeadline(market: MarketRow): string {
  return dashless(market.resolution_note).split('·')[0]?.trim() ?? '';
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
  usePageTitle('Head to head');
  const { games, selected: game, select: setGame } = useGameSelection();
  // Coming-soon games have no markets endpoint, so don't fetch for them.
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

  const [marketFilter, setMarketFilter] = useState<string>(ALL);
  const [speedByMarket, setSpeedByMarket] = useState<Record<string, string>>({});

  const selectGame = games.find((g) => g.game === game);
  const linked = markets?.linked ?? false;
  const meta = game ? gameMeta(game, selectGame?.display_name) : null;
  const presets = markets?.entry_presets_cents ?? [];
  // A match is in flight: surface the slip and freeze new joins.
  const inFlight = status?.status === 'searching' || status?.status === 'matched';

  // Only markets you can actually wager on are browsable.
  const openMarkets = useMemo(
    () => (markets?.markets ?? []).filter((m) => !m.provisional),
    [markets],
  );
  const filteredMarkets = openMarkets.filter(
    (m) => marketFilter === ALL || m.key === marketFilter,
  );
  const activeCount = marketFilter !== ALL ? 1 : 0;
  const hasResults = filteredMarkets.length > 0 && presets.length > 0;

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="play">
            You go 1v1 with an evenly matched opponent for the same stake. Both of you
            play your own next match, we read the result from the game, and the better
            stat line takes the pot.
          </HowItWorks>
        </div>
      </div>
      <GameTabs games={games} selected={game} onSelect={setGame} />
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
        <SkeletonList rows={3} />
      ) : marketsError ? (
        <ErrorState
          title="Could not load markets"
          subline="The connection dropped. Try again."
          onRetry={() => refetchMarkets()}
        />
      ) : !linked ? (
        <EmptyState
          title={`Link your ${meta?.name ?? 'game'} account`}
          subline="Head to head is graded from your real matches, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
            </Link>
          }
        />
      ) : (
        <>
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
            <>
              <SectionHeader
                level="page"
                action={
                  openMarkets.length > 1 && (
                    <FilterBar
                      testId="play-filters"
                      activeCount={activeCount}
                      onClear={() => setMarketFilter(ALL)}
                    >
                      <FilterChips
                        label="Market"
                        options={openMarkets.map((m) => m.key)}
                        selected={marketFilter}
                        onSelect={(v) => setMarketFilter(v as string)}
                        format={(k) =>
                          openMarkets.find((m) => m.key === k)?.label ?? String(k)
                        }
                      />
                    </FilterBar>
                  )
                }
              >
                Head to head
              </SectionHeader>

              {hasResults ? (
                <CardGrid count={filteredMarkets.length}>
                  {filteredMarkets.map((m) => {
                    const speed = speedByMarket[m.key] ?? defaultSpeed(m);
                    const key = `${game}:${m.key}:${speed ?? ''}`;
                    return (
                      <WagerCard
                        key={key}
                        gameName={meta?.name ?? 'Game'}
                        tag={speed?.toUpperCase()}
                        title={m.label}
                        subtitle={marketHeadline(m)}
                        speedOptions={m.requires_speed ? m.speeds : undefined}
                        selectedSpeed={speed}
                        onSpeedChange={
                          m.requires_speed
                            ? (s) =>
                                setSpeedByMarket((prev) => ({ ...prev, [m.key]: s }))
                            : undefined
                        }
                        entryOptions={presets}
                        payoutFor={(entry) => prizeForEntry(entry, m.multiplier_bps)}
                        payoutLabel="You win"
                        capacity={2}
                        oneVsOne
                        buttonLabel="Find match"
                        joining={join.isPending}
                        onJoin={(entry) =>
                          join.mutate({
                            game: game!,
                            market: m.key,
                            speed,
                            entry_preset_cents: entry,
                          })
                        }
                      />
                    );
                  })}
                </CardGrid>
              ) : (
                <EmptyState
                  title="Nothing matches those filters"
                  subline="Clear them to see every open market."
                />
              )}
            </>
          )}

          {waiting.data && waiting.data.waiting.length > 0 && (
            <section className="mt-10">
              <SectionHeader
                level="section"
                hint="Take one of these and you skip the queue."
              >
                Waiting to play
              </SectionHeader>
              {waiting.data.waiting.map((w) => (
                <ListRow
                  key={w.ticket_id}
                  left={
                    <span
                      aria-hidden
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-live"
                    />
                  }
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
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}
