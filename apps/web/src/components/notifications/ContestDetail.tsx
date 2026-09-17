import { useTournament } from '../../hooks/useTournaments';
import { formatCurrency, formatStat as stat } from '../../lib/format';
import { AmountText } from '../ui/AmountText';
import { ListRow } from '../ui/ListRow';

/**
 * The body behind a contest notification.
 *
 * A notification used to be a dead end: "A contest settled" told you something
 * finished but not what happened or to whom. That is answerable from data the
 * API already returns, so opening the row answers it in place rather than
 * sending you off to hunt through Activity.
 *
 * Fetching lives here, not in the row, because `ExpandableCard` only mounts its
 * children once opened. A feed of fifty notifications therefore costs zero
 * requests until something is actually opened.
 */

function Line({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-text-secondary">{children}</p>;
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
