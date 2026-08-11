import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { GettingStarted } from '../components/GettingStarted';
import { ModeSwitcher } from '../components/ModeSwitcher';
import { Card } from '../components/ui/Card';
import { CardGrid } from '../components/ui/CardGrid';
import { ClearBar } from '../components/ui/ClearBar';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { GameTabs } from '../components/ui/GameTabs';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatCurrency } from '../lib/format';
import { gameMeta, isComingSoon } from '../lib/games';
import { barTitle, isLowerBetter, requiresWin } from '../lib/metrics';
import { filledSpots } from '../lib/spots';
import { useAuth } from '../auth/useAuth';
import { useGameSelection } from '../hooks/useGameSelection';
import {
  estPrize,
  useEnterPool,
  useLeavePool,
  usePoolMarkets,
  usePoolStatus,
  type PoolView,
} from '../hooks/usePools';

// A full pool is POOL_ROOM_SIZE (backend); we advertise the target on each card.
const POOL_CAPACITY = 4;

// Difficulty chips read easiest to hardest regardless of API order.
const DIFFICULTY_ORDER = ['easy', 'medium', 'hard'];

export function PoolsPage() {
  const { isDemo } = useAuth();
  const { games, selected: game, select: setGame } = useGameSelection();
  const playableGame = game && !isComingSoon(game) ? game : undefined;
  const {
    data: markets,
    isError: marketsUnavailable,
    isLoading: marketsLoading,
  } = usePoolMarkets(playableGame);
  const { data: status } = usePoolStatus();
  const enter = useEnterPool();

  // Filters trim the metric × difficulty grid. Entry is no longer a filter
  // dimension: it lives inside each card as a control, so filtering by it would
  // hide contests rather than narrow them.
  const [metricFilter, setMetricFilter] = useState<string>(ALL);
  const [difficultyFilter, setDifficultyFilter] = useState<string>(ALL);

  const presets = markets?.entry_presets_cents ?? [];
  const openMetrics = useMemo(
    () => markets?.metrics.filter((m) => !m.provisional) ?? [],
    [markets],
  );
  const difficulties = useMemo(() => {
    const seen = new Set<string>();
    for (const m of openMetrics) for (const c of m.cards) seen.add(c.difficulty);
    return DIFFICULTY_ORDER.filter((d) => seen.has(d));
  }, [openMetrics]);

  const filteredMetrics = useMemo(() => {
    return openMetrics
      .filter((m) => metricFilter === ALL || m.metric === metricFilter)
      .map((m) => ({
        ...m,
        cards: m.cards.filter(
          (c) => difficultyFilter === ALL || c.difficulty === difficultyFilter,
        ),
      }))
      .filter((m) => m.cards.length > 0);
  }, [openMetrics, metricFilter, difficultyFilter]);
  const activeCount =
    (metricFilter !== ALL ? 1 : 0) + (difficultyFilter !== ALL ? 1 : 0);
  const hasResults = filteredMetrics.length > 0 && presets.length > 0;

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="pools">
            Three or four similar-skill players each get a personal bar quoted from
            their own baseline. Clear your bar in your next match and you take a share
            of the pot. You are playing the number, not the other players.
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
        <ComingSoonPanel name={gameMeta(game).name} />
      </div>
    );
  }

  // The markets endpoint 404s for a game that doesn't offer pools yet.
  if (game && marketsUnavailable) {
    return (
      <div>
        {header}
        <EmptyState
          title={`No pools on ${gameMeta(game).name} yet`}
          subline="Solo pools are Counter Strike 2 only for now. More games are coming."
          action={
            <Link to="/play">
              <PillButton>Play head to head</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  if (markets && !markets.linked) {
    return (
      <div>
        {header}
        <EmptyState
          title={`Link your ${game ? gameMeta(game).name : 'game'} account`}
          subline="Pools are graded from your real matches, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  // One pool in flight at a time, so joins freeze while searching or formed.
  const busy = status?.status === 'searching' || status?.status === 'formed';

  return (
    <div>
      {header}

      <GettingStarted />

      {/* From xl up the rail's "Room formed" section owns this, so a formed room
       * stops pushing the grid down. Below xl there is no rail, so keep it here
       * — it is the only place to see the room or leave the queue. */}
      {status && (status.status === 'searching' || status.status === 'formed') && (
        <div className="xl:hidden">
          <PoolStatusBanner status={status} />
        </div>
      )}

      <SectionHeader
        level="page"
        action={
          !marketsLoading &&
          openMetrics.length > 0 && (
            <FilterBar
              testId="pool-filters"
              activeCount={activeCount}
              onClear={() => {
                setMetricFilter(ALL);
                setDifficultyFilter(ALL);
              }}
            >
              {openMetrics.length > 1 && (
                <FilterChips
                  label="Metric"
                  options={openMetrics.map((m) => m.metric)}
                  selected={metricFilter}
                  onSelect={(v) => setMetricFilter(v as string)}
                  format={(m) =>
                    openMetrics.find((x) => x.metric === m)?.label ?? String(m)
                  }
                />
              )}
              {difficulties.length > 1 && (
                <FilterChips
                  label="Difficulty"
                  options={difficulties}
                  selected={difficultyFilter}
                  onSelect={(v) => setDifficultyFilter(v as string)}
                />
              )}
            </FilterBar>
          )
        }
      >
        Solo pools
      </SectionHeader>

      {marketsLoading ? (
        <SkeletonList rows={3} />
      ) : openMetrics.length === 0 ? (
        <EmptyState
          title="No pools on this game yet"
          subline="Play a match on it and its pools appear here."
        />
      ) : (
        <>
          {!hasResults ? (
            <EmptyState
              title="Nothing matches those filters"
              subline="Clear them to see every open pool."
            />
          ) : (
            filteredMetrics.map((m) => (
              <section key={m.metric} className="mb-8">
                {filteredMetrics.length > 1 && (
                  <SectionHeader level="section">{m.label}</SectionHeader>
                )}
                <CardGrid count={m.cards.length}>
                  {/* One card per bar. Entry is a control inside it, so a
                   * three-difficulty metric is three cards, not nine. */}
                  {m.cards.map((c) => {
                    const key = `${game}:${m.metric}:${c.difficulty}`;
                    return (
                      <WagerCard
                        key={key}
                        gameName={m.label}
                        tag={c.difficulty}
                        title={barTitle(m.metric, c.bar)}
                        target={c.bar}
                        clearRate={c.clear_rate}
                        lowerIsBetter={isLowerBetter(m.metric)}
                        targetUnit={isLowerBetter(m.metric) ? 'moves' : undefined}
                        targetNote={
                          requiresWin(m.metric)
                            ? 'Wins only. A loss or a draw does not count.'
                            : undefined
                        }
                        entryOptions={presets}
                        payoutFor={(entry) => estPrize(entry, c.est_multiplier_bps)}
                        payoutLabel="Est. win"
                        capacity={POOL_CAPACITY}
                        filled={isDemo ? filledSpots(key, POOL_CAPACITY) : undefined}
                        buttonLabel="Join pool"
                        disabled={busy}
                        joining={enter.isPending}
                        requireConfirm
                        onJoin={(entry) =>
                          enter.mutate({
                            game: markets!.game,
                            metric: m.metric,
                            difficulty: c.difficulty,
                            entry_preset_cents: entry,
                          })
                        }
                      />
                    );
                  })}
                </CardGrid>
              </section>
            ))
          )}
        </>
      )}
    </div>
  );
}

/** Compact top banner for an in-flight pool: forming (with cancel) or formed. */
function PoolStatusBanner({
  status,
}: {
  status: NonNullable<ReturnType<typeof usePoolStatus>['data']>;
}) {
  const leave = useLeavePool();

  if (status.status === 'formed' && status.pool) {
    return <RoomBanner pool={status.pool} />;
  }

  return (
    <Card
      className="mb-6 flex items-center justify-between gap-4 p-4"
      data-testid="pool-status"
    >
      <div className="flex items-center gap-3">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-live" />
        <div>
          <p className="text-sm font-medium text-text">Finding your room</p>
          <p className="text-xs text-text-secondary">
            Matching you with players of a similar standard.
          </p>
        </div>
      </div>
      <PillButton
        variant="text"
        onClick={() => leave.mutate()}
        disabled={leave.isPending}
      >
        Cancel
      </PillButton>
    </Card>
  );
}

function RoomBanner({ pool }: { pool: PoolView }) {
  const gameName = gameMeta(pool.game).name;
  return (
    <Card className="mb-6 p-5" data-testid="room-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-live" aria-hidden />
            <p className="text-xs font-semibold uppercase tracking-wide text-live">
              Room formed
            </p>
          </div>
          <h2 className="mt-2 text-xl font-semibold capitalize text-text">
            {pool.difficulty} {pool.metric_label} · bar {pool.room_bar}
          </h2>
          <p className="mt-1 text-xs text-text-secondary">
            {pool.room_size} {pool.room_size === 1 ? 'player' : 'players'} · pot{' '}
            {formatCurrency(pool.pot_cents)}
          </p>
        </div>
        <div className="w-full max-w-xs">
          <ClearBar current={pool.your_bar} target={pool.room_bar} label="your avg" />
        </div>
      </div>
      <p className="mt-4 text-sm text-text" data-testid="room-play-cue">
        Your {formatCurrency(pool.entry_cents)} is in escrow, so you can now play your{' '}
        {gameName} game. Clear the room bar in your next match to take your share.
      </p>
    </Card>
  );
}
