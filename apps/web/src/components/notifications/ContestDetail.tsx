import { usePool, type PoolMember } from '../../hooks/usePools';
import { useTournament } from '../../hooks/useTournaments';
import { formatCurrency } from '../../lib/format';
import { isLowerBetter } from '../../lib/metrics';
import { AmountText } from '../ui/AmountText';
import { ListRow } from '../ui/ListRow';

/**
 * The body behind a contest notification.
 *
 * A notification used to be a dead end: "Your pool room filled" told you a room
 * existed but not who was in it, and "A contest settled" told you something
 * finished but not what happened or to whom. Both of those are answerable from
 * data the API already returns, so opening the row answers them in place rather
 * than sending you off to hunt through Activity.
 *
 * Fetching lives here, not in the row, because `ExpandableCard` only mounts its
 * children once opened. A feed of fifty notifications therefore costs zero
 * requests until something is actually opened.
 */

function Line({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-text-secondary">{children}</p>;
}

/** Value formatting shared by both panels: whole numbers stay whole. */
function stat(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function PoolDetail({ poolId }: { poolId: string }) {
  const { data: pool, isPending, isError } = usePool(poolId);

  if (isPending) return <Line>Loading the room…</Line>;
  if (isError || !pool) return <Line>Could not load this room.</Line>;

  const settled = pool.state === 'SETTLED' || pool.state === 'CANCELED';
  const lower = isLowerBetter(pool.metric);

  // Once settled, lead with whoever cleared: the outcome is the point of
  // opening a settled contest. While it is live, order is meaningless, so
  // keep the room's own order and just mark yourself.
  const members: PoolMember[] = settled
    ? [...pool.members].sort((a, b) => rankOf(a) - rankOf(b))
    : pool.members;

  return (
    <div>
      <Line>
        {pool.metric_label} · {pool.difficulty} · room bar{' '}
        <span className="text-text">{stat(pool.room_bar)}</span> ·{' '}
        {formatCurrency(pool.entry_cents)} each
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
            subline={memberSubline(m, settled, lower)}
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
          {formatCurrency(pool.pot_cents)}.
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

function memberSubline(m: PoolMember, settled: boolean, lower: boolean): string {
  const bar = `bar ${stat(m.personal_bar)}`;
  if (!settled) return bar;
  if (m.result_value == null) {
    return m.status === 'REFUNDED' ? `${bar} · no qualifying match` : bar;
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
  const { data: t, isPending, isError } = useTournament(tournamentId);

  if (isPending) return <Line>Loading standings…</Line>;
  if (isError || !t) return <Line>Could not load this tournament.</Line>;

  const settled = t.state === 'SETTLED' || t.state === 'CANCELED';

  return (
    <div>
      <Line>
        {t.metric_label} · {t.standings.length} entrants ·{' '}
        {formatCurrency(t.entry_cents)} each · {settled ? 'final' : 'live'} standings
      </Line>

      <div className="mt-2">
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
                    row.matches === 1 ? 'match' : 'matches'
                  }`
                : 'No qualifying match'
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
          Prizes are paid when the window closes. Pot {formatCurrency(t.pot_cents)}.
        </Line>
      )}
    </div>
  );
}
