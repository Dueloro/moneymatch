import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { BalanceHeader } from '../components/BalanceHeader';
import { GettingStarted } from '../components/GettingStarted';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { GameTabs } from '../components/ui/GameTabs';
import { PillButton } from '../components/ui/PillButton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatCurrency, formatPct } from '../lib/format';
import { gameMeta, isComingSoon } from '../lib/games';
import { filledSpots } from '../lib/spots';
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

// Difficulty chips read easiest → hardest regardless of API order.
const DIFFICULTY_ORDER = ['easy', 'medium', 'hard'];

export function PoolsPage() {
  const { games, selected: game, select: setGame } = useGameSelection();
  const playableGame = game && !isComingSoon(game) ? game : undefined;
  const {
    data: markets,
    isError: marketsUnavailable,
    isLoading: marketsLoading,
  } = usePoolMarkets(playableGame);
  const { data: status } = usePoolStatus();
  const enter = useEnterPool();

  // Filters — trim the metric × difficulty × entry grid down to what you want.
  // Tucked behind a hamburger toggle so they don't eat screen space by default.
  const [metricFilter, setMetricFilter] = useState<string>(ALL);
  const [difficultyFilter, setDifficultyFilter] = useState<string>(ALL);
  const [entryFilter, setEntryFilter] = useState<number | typeof ALL>(ALL);

  const header = (
    <div className="mb-6 flex items-center gap-4">
      <GameTabs games={games} selected={game} onSelect={setGame} />
      <BalanceHeader />
    </div>
  );

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

  // Apply the active filters to the metric → cards → entries fan-out.
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
  const filteredPresets = presets.filter(
    (e) => entryFilter === ALL || e === entryFilter,
  );
  const activeCount =
    (metricFilter !== ALL ? 1 : 0) +
    (difficultyFilter !== ALL ? 1 : 0) +
    (entryFilter !== ALL ? 1 : 0);
  const hasResults = filteredMetrics.length > 0 && filteredPresets.length > 0;

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
          title={`Pools aren't available for ${gameMeta(game).name} yet`}
          subline="Solo pools are Counter-Strike 2 only for now — more games soon."
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
          subline="Pools are graded from your real matches. Link to play."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  const meta = game ? gameMeta(game, undefined) : null;
  // One pool in flight at a time — freeze joins while searching or formed.
  const busy = status?.status === 'searching' || status?.status === 'formed';

  return (
    <div>
      {header}

      <GettingStarted />

      <p className="mb-6 max-w-2xl text-sm text-text-secondary">
        Solo pools put 3–4 similar-skill players against a personal bar quoted from your
        own baseline. Clear your bar in your next match to take a share of the pot. Pick
        a pool below and join.
      </p>

      {status && (status.status === 'searching' || status.status === 'formed') && (
        <PoolStatusBanner status={status} />
      )}

      {openMetrics.length === 0 ? (
        <p className="py-8 text-sm text-text-secondary">
          {marketsLoading
            ? 'Loading pools…'
            : 'No pools on this game yet — play a match on it and its pools appear here.'}
        </p>
      ) : (
        <>
          <FilterBar
            testId="pool-filters"
            activeCount={activeCount}
            onClear={() => {
              setMetricFilter(ALL);
              setDifficultyFilter(ALL);
              setEntryFilter(ALL);
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

          {!hasResults ? (
            <p className="py-8 text-sm text-text-secondary">
              No pools match these filters.
            </p>
          ) : (
            filteredMetrics.map((m) => (
              <section key={m.metric} className="mb-8">
                <h2 className="mb-3 label-mono">{m.label}</h2>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {m.cards.flatMap((c) =>
                    filteredPresets.map((entry) => {
                      const key = `${game}:${m.metric}:${c.difficulty}:${entry}`;
                      return (
                        <WagerCard
                          key={key}
                          accent={meta?.accent ?? 'var(--text-secondary)'}
                          gameName={meta?.short ?? 'Game'}
                          tag={c.difficulty}
                          title={`${m.label} ≥ ${c.bar}`}
                          subtitle={`Clears ≈ ${formatPct(c.clear_rate)} of the time`}
                          entryCents={entry}
                          capacity={POOL_CAPACITY}
                          filled={filledSpots(key, POOL_CAPACITY)}
                          footnote={`Est. payout ≈ ${formatCurrency(
                            estPrize(entry, c.est_multiplier_bps),
                          )}`}
                          buttonLabel="Join Pool"
                          disabled={busy}
                          joining={enter.isPending}
                          onJoin={() =>
                            enter.mutate({
                              game: markets!.game,
                              metric: m.metric,
                              difficulty: c.difficulty,
                              entry_preset_cents: entry,
                            })
                          }
                        />
                      );
                    }),
                  )}
                </div>
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
    <div
      className="mb-6 flex items-center justify-between gap-4 rounded-2xl bg-panel p-4"
      data-testid="pool-status"
    >
      <div className="flex items-center gap-3">
        <span className="h-3 w-3 animate-pulse rounded-full bg-green" />
        <div>
          <p className="text-sm font-semibold text-text">Forming your room…</p>
          <p className="text-xs text-text-secondary">
            Matching you with similar-stat players.
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
    </div>
  );
}

function RoomBanner({ pool }: { pool: PoolView }) {
  const { isDemo } = useAuth();
  const leave = useLeavePool();
  const gameName = gameMeta(pool.game).name;
  return (
    <div className="mb-6 rounded-2xl bg-panel p-4" data-testid="room-card">
      <p className="label-mono">Room formed</p>
      <h3 className="mt-1 text-lg font-bold capitalize text-text">
        {pool.difficulty} {pool.metric_label} · bar {pool.room_bar}
      </h3>
      <p className="mt-1 text-xs text-text-secondary">
        {pool.room_size} {pool.room_size === 1 ? 'player' : 'players'} · pot{' '}
        {formatCurrency(pool.pot_cents)}.
      </p>
      <p className="mt-2 text-sm font-semibold text-green" data-testid="room-play-cue">
        ✓ Your {formatCurrency(pool.entry_cents)} is locked in escrow — you can now play
        your {gameName} game. Clear the room bar in your next match to take your share.
      </p>
      {isDemo && (
        <div className="mt-3">
          <PillButton
            variant="outline"
            onClick={() => leave.mutate()}
            disabled={leave.isPending}
          >
            New pool
          </PillButton>
        </div>
      )}
    </div>
  );
}
