import { useState } from 'react';
import { Link } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { PillButton } from '../components/ui/PillButton';
import { PresetSelector } from '../components/ui/PresetSelector';
import { formatCurrency, formatPct } from '../lib/format';
import {
  estPrize,
  useEnterPool,
  useLeavePool,
  usePoolMarkets,
  usePoolStatus,
  type DifficultyCard,
  type PoolMetric,
  type PoolView,
} from '../hooks/usePools';

function multiplierLabel(bps: number): string {
  return `≈ ×${(bps / 10000).toFixed(2)}`;
}

export function PoolsPage() {
  const { data: markets } = usePoolMarkets();
  const { data: status } = usePoolStatus();
  const enter = useEnterPool();

  const [metricKey, setMetricKey] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<string | null>(null);
  const [entryCents, setEntryCents] = useState<number | null>(null);

  const metric: PoolMetric | null =
    markets?.metrics.find((m) => m.metric === metricKey) ?? markets?.metrics[0] ?? null;
  const card: DifficultyCard | null =
    metric?.cards.find((c) => c.difficulty === difficulty) ?? null;

  function enterPool() {
    if (!markets || !metric || !difficulty || entryCents == null) return;
    enter.mutate({
      game: markets.game,
      metric: metric.metric,
      difficulty,
      entry_preset_cents: entryCents,
    });
  }

  if (markets && !markets.linked) {
    return (
      <div>
        <div className="mb-6">
          <BalanceHeader />
        </div>
        <EmptyState
          title="Link your CS2 account"
          subline="Pools are graded from your real FACEIT matches — link to play."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <BalanceHeader />
      </div>

      {/* Metric tabs */}
      <div className="mb-6 flex gap-2" role="tablist">
        {markets?.metrics.map((m) => (
          <button
            key={m.metric}
            role="tab"
            aria-selected={m.metric === (metric?.metric ?? '')}
            onClick={() => {
              setMetricKey(m.metric);
              setDifficulty(null);
            }}
            className={[
              'rounded-pill px-4 py-1.5 text-sm font-semibold transition',
              m.metric === (metric?.metric ?? '')
                ? 'bg-text text-black'
                : 'border border-hairline text-text-secondary hover:text-text',
            ].join(' ')}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="flex gap-8">
        <div className="min-w-0 flex-1">
          {metric?.provisional ? (
            <p className="py-6 text-sm text-text-secondary">
              Play a few more {metric.label} matches to unlock pools on this stat.
            </p>
          ) : (
            <>
              <h2 className="mb-2 text-sm font-semibold text-text-secondary">
                Difficulty — bars from your baseline
              </h2>
              <div className="grid grid-cols-3 gap-3">
                {metric?.cards.map((c) => {
                  const selected = c.difficulty === difficulty;
                  return (
                    <button
                      key={c.difficulty}
                      onClick={() => setDifficulty(c.difficulty)}
                      className={[
                        'rounded-2xl border p-4 text-left transition',
                        selected
                          ? 'border-green'
                          : 'border-hairline hover:border-text-secondary',
                      ].join(' ')}
                    >
                      <div className="text-xs uppercase tracking-wide text-text-secondary">
                        {c.difficulty}
                      </div>
                      <div className="mt-1 text-2xl font-bold tabular-nums">
                        {c.bar}
                      </div>
                      <div className="mt-1 text-xs text-text-secondary">
                        clears ≈ {formatPct(c.clear_rate)}
                      </div>
                      <div className="mt-1 text-xs text-green">
                        {multiplierLabel(c.est_multiplier_bps)}
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        <PoolSlip
          status={status}
          metricLabel={metric?.label ?? ''}
          card={card}
          presetsCents={markets?.entry_presets_cents ?? []}
          entryCents={entryCents}
          onSelectEntry={setEntryCents}
          onEnter={enterPool}
          entering={enter.isPending}
        />
      </div>
    </div>
  );
}

function PoolSlip({
  status,
  metricLabel,
  card,
  presetsCents,
  entryCents,
  onSelectEntry,
  onEnter,
  entering,
}: {
  status: ReturnType<typeof usePoolStatus>['data'];
  metricLabel: string;
  card: DifficultyCard | null;
  presetsCents: number[];
  entryCents: number | null;
  onSelectEntry: (cents: number) => void;
  onEnter: () => void;
  entering: boolean;
}) {
  const leave = useLeavePool();

  if (status?.status === 'formed' && status.pool) {
    return <RoomCard pool={status.pool} />;
  }

  return (
    <aside
      className="w-[354px] shrink-0 rounded-2xl bg-panel p-6"
      data-testid="pool-slip"
    >
      {status?.status === 'searching' ? (
        <>
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 animate-pulse rounded-full bg-green" />
            <p className="text-sm font-semibold text-text">Forming a room…</p>
          </div>
          <p className="mt-2 text-xs text-text-secondary">
            Matching you with similar-stat players.
          </p>
          <div className="mt-5">
            <PillButton
              variant="text"
              onClick={() => leave.mutate()}
              disabled={leave.isPending}
            >
              Cancel
            </PillButton>
          </div>
        </>
      ) : card ? (
        <>
          <p className="text-xs uppercase tracking-wide text-text-secondary">
            Clear it and win
          </p>
          <h3 className="text-lg font-bold capitalize text-text">
            {card.difficulty} {metricLabel}
          </h3>
          <p className="mt-1 text-sm text-text">
            Beat <span className="font-bold tabular-nums">{card.bar}</span> in your next
            match
          </p>

          <p className="mt-4 mb-2 text-xs font-semibold text-text-secondary">Entry</p>
          <PresetSelector
            presetsCents={presetsCents}
            selectedCents={entryCents}
            onSelect={onSelectEntry}
          />

          {entryCents != null && (
            <p className="mt-4 text-sm text-text">
              Estimated payout{' '}
              <span className="font-bold text-green">
                {formatCurrency(estPrize(entryCents, card.est_multiplier_bps))}
              </span>
            </p>
          )}
          <p className="mt-2 text-xs text-text-secondary">
            Estimated — your actual payout is your share of the pool minus rake.
          </p>

          <div className="mt-5">
            <PillButton
              fullWidth
              disabled={entryCents == null || entering}
              onClick={onEnter}
            >
              {entering ? 'Entering…' : 'Enter pool'}
            </PillButton>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm font-semibold text-text">Pick a difficulty</p>
          <p className="mt-1 text-xs text-text-secondary">
            Each bar is quoted from your own baseline. Clear it in your next match to
            win a share of the pool.
          </p>
        </>
      )}
    </aside>
  );
}

function RoomCard({ pool }: { pool: PoolView }) {
  return (
    <aside
      className="w-[354px] shrink-0 rounded-2xl bg-panel p-6"
      data-testid="room-card"
    >
      <p className="text-xs uppercase tracking-wide text-text-secondary">Room formed</p>
      <h3 className="text-lg font-bold capitalize text-text">
        {pool.difficulty} {pool.metric_label}
      </h3>
      <div className="mt-3 rounded-lg bg-bg p-3">
        <p className="text-sm text-text">
          Room bar <span className="font-bold tabular-nums">{pool.room_bar}</span>
        </p>
        {pool.your_bar != null && (
          <p className="mt-1 text-xs text-text-secondary">
            Your bar was {pool.your_bar}
            {pool.bar_delta != null && (
              <>
                {' '}
                · delta {pool.bar_delta > 0 ? '+' : ''}
                {pool.bar_delta.toFixed(2)}
              </>
            )}
          </p>
        )}
      </div>
      <p className="mt-3 text-xs text-text-secondary">
        {pool.room_size} players · pot {formatCurrency(pool.pot_cents)}. Clear the room
        bar in your next match to take a share.
      </p>
    </aside>
  );
}
