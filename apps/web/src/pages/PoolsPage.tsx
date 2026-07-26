import { Link } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { GettingStarted } from '../components/GettingStarted';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { EmptyState } from '../components/ui/EmptyState';
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

export function PoolsPage() {
  const { games, selected: game, select: setGame } = useGameSelection();
  const playableGame = game && !isComingSoon(game) ? game : undefined;
  const { data: markets } = usePoolMarkets(playableGame);
  const { data: status } = usePoolStatus();
  const enter = useEnterPool();

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
        <ComingSoonPanel name={gameMeta(game).name} />
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
  const presets = markets?.entry_presets_cents ?? [];
  const openMetrics = markets?.metrics.filter((m) => !m.provisional) ?? [];
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
          No pools on this game yet — play a match on it and its pools appear here.
        </p>
      ) : (
        openMetrics.map((m) => (
          <section key={m.metric} className="mb-8">
            <h2 className="mb-3 label-mono">{m.label}</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {m.cards.flatMap((c) =>
                presets.map((entry) => {
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
  return (
    <div className="mb-6 rounded-2xl bg-panel p-4" data-testid="room-card">
      <p className="label-mono">Room formed</p>
      <h3 className="mt-1 text-lg font-bold capitalize text-text">
        {pool.difficulty} {pool.metric_label} · bar {pool.room_bar}
      </h3>
      <p className="mt-1 text-xs text-text-secondary">
        {pool.room_size} players · pot {formatCurrency(pool.pot_cents)}. Clear the room
        bar in your next match to take a share.
      </p>
    </div>
  );
}
