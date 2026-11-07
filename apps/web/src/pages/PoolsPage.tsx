import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { GettingStarted } from '../components/GettingStarted';
import { PlayHeader } from '../components/PlayHeader';
import { Card } from '../components/ui/Card';
import { CardGrid } from '../components/ui/CardGrid';
import { ClearBar } from '../components/ui/ClearBar';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatPoints } from '../lib/format';
import {
  formatMetric,
  formatMetricNumber,
  isLowerBetter,
  metricUnit,
  poolCardTitle,
} from '../lib/metrics';
import { feeOnNetWinnings, platformFeeNote } from '../lib/rake';
import {
  estPrize,
  useEnterPool,
  useLeavePool,
  usePoolMarkets,
  usePoolStatus,
  type PoolView,
} from '../hooks/usePools';

const DIFFICULTY_ORDER = ['easy', 'medium', 'hard'];

export function PoolsPage() {
  usePageTitle('Solo pools');
  const {
    data: markets,
    isError: marketsError,
    isLoading: marketsLoading,
    refetch: refetchMarkets,
  } = usePoolMarkets();
  const { data: status } = usePoolStatus();
  const enter = useEnterPool();

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
    <PlayHeader
      id="pools"
      how="You get a bar set from your own recent games. Win your next Lichess game inside it to take a share of the pot."
    />
  );

  if (marketsError) {
    return (
      <div>
        {header}
        <ErrorState
          title="Could not load pools"
          subline="The connection dropped. Try again."
          onRetry={() => refetchMarkets()}
        />
      </div>
    );
  }

  if (markets && !markets.linked) {
    return (
      <div>
        {header}
        <EmptyState
          title="Link your Lichess account"
          subline="Pools settle from your Lichess games, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link Lichess</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  const busy = status?.status === 'searching' || status?.status === 'formed';

  return (
    <div>
      {header}

      <GettingStarted />

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
        <EmptyState title="No pools open right now" subline="Check back shortly." />
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
                  {m.cards.map((c) => {
                    const key = `${m.metric}:${c.difficulty}`;
                    return (
                      <WagerCard
                        key={key}
                        title={poolCardTitle(m.metric, c.difficulty)}
                        target={c.bar}
                        clearRate={c.clear_rate}
                        lowerIsBetter={isLowerBetter(m.metric)}
                        targetUnit={metricUnit(m.metric)}
                        entryOptions={presets}
                        payoutFor={(entry) => estPrize(entry, c.est_multiplier_bps)}
                        payoutLabel="Est. win"
                        feeNote={(entry) =>
                          platformFeeNote(
                            feeOnNetWinnings(estPrize(entry, c.est_multiplier_bps)),
                          )
                        }
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
  const lower = isLowerBetter(pool.metric);
  const unit = metricUnit(pool.metric);
  return (
    <Card className="mb-6 p-5" data-testid="room-card">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <p className="flex items-center gap-2 text-sm font-medium text-text">
          <span className="h-2 w-2 rounded-full bg-live" aria-hidden />
          Room formed
        </p>
        <p className="text-xs text-text-secondary">
          {pool.room_size} {pool.room_size === 1 ? 'player' : 'players'} · pot{' '}
          <span className="text-green">{formatPoints(pool.pot_cents)}</span>
        </p>
      </div>
      <p className="mt-4 text-xs text-text-secondary">
        {poolCardTitle(pool.metric, pool.difficulty)}
      </p>
      <h2 className="mt-1 flex items-baseline gap-2">
        <span className="num text-3xl font-semibold text-text">
          {formatMetricNumber(pool.room_bar)}
        </span>
        <span className="text-sm text-text-secondary">
          {unit ? `${unit} ` : ''}
          {lower ? 'or fewer' : 'or better'}
        </span>
      </h2>
      <div className="mt-4">
        <ClearBar
          current={pool.your_bar}
          target={pool.room_bar}
          label="your bar"
          lowerIsBetter={lower}
          format={(n) => formatMetric(pool.metric, n)}
        />
      </div>
      <p className="mt-4 text-sm text-text" data-testid="room-play-cue">
        Your {formatPoints(pool.entry_cents)} is in escrow. Play your next game on
        Lichess.
      </p>
    </Card>
  );
}
