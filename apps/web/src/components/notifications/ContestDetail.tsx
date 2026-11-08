import { usePool, type PoolMember } from '../../hooks/usePools';
import { useTournament } from '../../hooks/useTournaments';
import { formatPoints } from '../../lib/format';
import { formatMetric, isLowerBetter } from '../../lib/metrics';
import { AmountText } from '../ui/AmountText';
import { ErrorState } from '../ui/ErrorState';
import { ListRow } from '../ui/ListRow';
import { Skeleton } from '../ui/Skeleton';

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-2" data-testid="detail-skeleton">
      <Skeleton className="h-3.5 w-48" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}

function Line({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-text-secondary">{children}</p>;
}

export function PoolDetail({ poolId }: { poolId: string }) {
  const { data: pool, isPending, isError, refetch } = usePool(poolId);

  if (isPending) return <DetailSkeleton />;
  if (isError || !pool)
    return (
      <ErrorState
        title="Couldn't load this room"
        subline="Try again in a moment."
        onRetry={() => void refetch()}
      />
    );

  const settled = pool.state === 'SETTLED' || pool.state === 'CANCELED';
  const lower = isLowerBetter(pool.metric);
  const stat = (n: number | null | undefined) => formatMetric(pool.metric, n);

  const members: PoolMember[] = settled
    ? [...pool.members].sort((a, b) => rankOf(a) - rankOf(b))
    : pool.members;

  return (
    <div>
      <Line>
        {pool.metric_label} · {pool.difficulty} · room bar{' '}
        <span className="text-text">{stat(pool.room_bar)}</span> ·{' '}
        {formatPoints(pool.entry_cents)} each
      </Line>

      <div className="mt-2">
        {members.map((m) => (
          <ListRow
            key={m.user_id}
            title={
              <span className={m.is_you ? 'font-semibold text-text' : undefined}>
                {m.username ?? 'Player'}
                {m.is_you ? ' (you)' : ''}
              </span>
            }
            subline={memberSubline(m, settled, lower, stat)}
            right={
              settled ? (
                <span className="flex items-center gap-2">
                  <Outcome status={m.status} />
                  {m.payout_cents > 0 && <AmountText cents={m.payout_cents} win />}
                </span>
              ) : (
                <span className="tabular-nums text-text-secondary">
                  {stat(m.personal_bar)}
                </span>
              )
            }
          />
        ))}
      </div>

      {!settled && (
        <Line>
          Everyone is playing their own bar. Clear yours to take a share of{' '}
          {formatPoints(pool.pot_cents)}.
        </Line>
      )}
    </div>
  );
}

/** Cleared first, then missed, then refunded. */
function rankOf(m: PoolMember): number {
  if (m.status === 'CLEARED') return 0;
  if (m.status === 'MISSED') return 1;
  return 2;
}

function memberSubline(
  m: PoolMember,
  settled: boolean,
  lower: boolean,
  stat: (n: number) => string,
): string {
  const bar = `bar ${stat(m.personal_bar)}`;
  if (!settled) return bar;
  if (m.result_value == null) {
    return m.status === 'REFUNDED' ? `${bar} · no qualifying game` : bar;
  }
  const verb = lower ? 'in' : 'hit';
  return `${verb} ${stat(m.result_value)} · ${bar}`;
}

function Outcome({ status }: { status: string }) {
  const label =
    status === 'CLEARED'
      ? 'Cleared'
      : status === 'MISSED'
        ? 'Missed'
        : status === 'REFUNDED'
          ? 'Refunded'
          : status;
  const tone =
    status === 'CLEARED'
      ? 'text-green'
      : status === 'MISSED'
        ? 'text-text-secondary'
        : 'text-text-tertiary';
  return <span className={`text-xs ${tone}`}>{label}</span>;
}

export function TournamentDetail({ tournamentId }: { tournamentId: string }) {
  const { data: t, isPending, isError, refetch } = useTournament(tournamentId);

  if (isPending) return <DetailSkeleton />;
  if (isError || !t)
    return (
      <ErrorState
        title="Couldn't load this tournament"
        subline="Try again in a moment."
        onRetry={() => void refetch()}
      />
    );

  const settled = t.state === 'SETTLED' || t.state === 'CANCELED';
  const stat = (n: number) => formatMetric(t.metric, n);

  return (
    <div>
      <Line>
        {t.metric_label} · {t.standings.length} entrants · {formatPoints(t.entry_cents)}{' '}
        each · {settled ? 'final' : 'live'} standings
      </Line>

      <div className="mt-2 tabular-nums">
        {t.standings.map((row) => (
          <ListRow
            key={row.user_id}
            title={
              <span className={row.is_you ? 'font-semibold text-text' : undefined}>
                {row.rank ? `#${row.rank}` : '-'} {row.username ?? 'Player'}
                {row.is_you ? ' (you)' : ''}
              </span>
            }
            subline={
              row.score != null
                ? `${stat(row.score)} · ${row.matches} ${
                    row.matches === 1 ? 'game' : 'games'
                  }`
                : 'No qualifying game yet'
            }
            right={
              row.payout_cents > 0 ? (
                <AmountText cents={row.payout_cents} win />
              ) : undefined
            }
          />
        ))}
      </div>

      {!settled && (
        <Line>
          Prizes are paid when the window closes. Pot {formatPoints(t.pot_cents)}.
        </Line>
      )}
    </div>
  );
}
