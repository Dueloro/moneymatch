import { useState } from 'react';
import { Link } from 'react-router-dom';

import { PlayHeader } from '../components/PlayHeader';
import { AmountText } from '../components/ui/AmountText';
import { Card } from '../components/ui/Card';
import { CardGrid } from '../components/ui/CardGrid';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatPoints, formatTimeLeft } from '../lib/format';
import { formatMetric, tournamentRule } from '../lib/metrics';
import { platformFeeNote, rakeOnPot } from '../lib/rake';
import {
  useEnterTournament,
  useLeaveTournament,
  useTournamentMarkets,
  useTournamentStatus,
  type TournamentView,
} from '../hooks/useTournaments';

export function TournamentPage() {
  usePageTitle('Tournament');
  const {
    data: markets,
    isError: marketsError,
    isLoading: marketsLoading,
    refetch: refetchMarkets,
  } = useTournamentMarkets();
  const { data: status } = useTournamentStatus();
  const enter = useEnterTournament();

  const [metricFilter, setMetricFilter] = useState<string>(ALL);

  const places = markets?.prize_split.length ?? 3;

  const header = (
    <PlayHeader
      id="tournament"
      how={`Every rated Lichess game you finish in the window counts. The top ${places} split the pot.`}
    />
  );

  if (marketsError) {
    return (
      <div>
        {header}
        <ErrorState
          title="Could not load tournaments"
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
          subline="Tournaments score your Lichess games automatically, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link Lichess</PillButton>
            </Link>
          }
        />
      </div>
    );
  }

  const presets = markets?.entry_presets_cents ?? [];
  const openMetrics = markets?.metrics.filter((m) => !m.provisional) ?? [];
  const fieldSize = markets?.field_size ?? 16;
  const busy = status?.status === 'searching' || status?.status === 'formed';
  const split = markets?.prize_split ?? [];
  const splitTotal = split.reduce((a, b) => a + b, 0);
  const firstPlace = (pot: number) =>
    splitTotal > 0 ? Math.floor(((pot - rakeOnPot(pot)) * split[0]) / splitTotal) : 0;

  const filteredMetrics = openMetrics.filter(
    (m) => metricFilter === ALL || m.metric === metricFilter,
  );
  const activeCount = metricFilter !== ALL ? 1 : 0;
  const hasResults = filteredMetrics.length > 0 && presets.length > 0;

  return (
    <div>
      {header}

      {status && (status.status === 'searching' || status.status === 'formed') && (
        <TournamentStatusBanner status={status} />
      )}

      <SectionHeader
        level="page"
        action={
          !marketsLoading &&
          openMetrics.length > 1 && (
            <FilterBar
              testId="tournament-filters"
              activeCount={activeCount}
              onClear={() => setMetricFilter(ALL)}
            >
              <FilterChips
                label="Metric"
                options={openMetrics.map((m) => m.metric)}
                selected={metricFilter}
                onSelect={(v) => setMetricFilter(v as string)}
                format={(m) =>
                  openMetrics.find((x) => x.metric === m)?.label ?? String(m)
                }
              />
            </FilterBar>
          )
        }
      >
        Tournaments
      </SectionHeader>

      {marketsLoading ? (
        <SkeletonList rows={3} />
      ) : openMetrics.length === 0 ? (
        <EmptyState
          title="No tournaments open right now"
          subline="Check back shortly."
        />
      ) : (
        <>
          {!hasResults ? (
            <EmptyState
              title="Nothing matches those filters"
              subline="Clear them to see every open tournament."
            />
          ) : (
            <CardGrid count={filteredMetrics.length}>
              {filteredMetrics.map((m) => {
                const key = m.metric;
                return (
                  <WagerCard
                    key={key}
                    gameName={`${fieldSize} players`}
                    tag={`top ${places} paid`}
                    title={m.label}
                    subtitle={tournamentRule(m.metric, m.label)}
                    entryOptions={presets}
                    payoutFor={(entry) => firstPlace(entry * fieldSize)}
                    payoutLabel="1st place if full"
                    // Rake is taken off the full pot before the top places
                    // split it (money_math.split_by_weights).
                    feeNote={(entry) => platformFeeNote(rakeOnPot(entry * fieldSize))}
                    buttonLabel="Join tournament"
                    disabled={busy}
                    joining={enter.isPending}
                    onJoin={(entry) =>
                      enter.mutate({
                        game: markets!.game,
                        metric: m.metric,
                        entry_preset_cents: entry,
                      })
                    }
                  />
                );
              })}
            </CardGrid>
          )}
        </>
      )}
    </div>
  );
}

function TournamentStatusBanner({
  status,
}: {
  status: NonNullable<ReturnType<typeof useTournamentStatus>['data']>;
}) {
  const leave = useLeaveTournament();

  if (status.status === 'formed' && status.tournament) {
    return <StandingsPanel tournament={status.tournament} />;
  }

  return (
    <Card
      className="mb-6 flex items-center justify-between gap-4 p-4"
      data-testid="tournament-status"
    >
      <div className="flex items-center gap-3">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-live" />
        <div>
          <p className="text-sm font-medium text-text">Finding your field</p>
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

function closesIn(endsAt: string): string {
  const left = formatTimeLeft(endsAt);
  return left ? `closes in ${left}` : 'closing now';
}

function StandingsPanel({ tournament }: { tournament: TournamentView }) {
  const settled = tournament.state === 'SETTLED';
  return (
    <Card className="mb-6 p-5" data-testid="standings-panel">
      <div className="flex items-center gap-2">
        {!settled && <span className="h-2 w-2 rounded-full bg-live" aria-hidden />}
        <p
          className={[
            'text-xs font-semibold uppercase tracking-wide',
            settled ? 'text-text-tertiary' : 'text-live',
          ].join(' ')}
        >
          {settled ? 'Final standings' : 'Live standings'}
        </p>
      </div>
      <h2 className="mt-2 text-xl font-semibold text-text">
        {tournament.metric_label}
      </h2>
      <p className="mt-1 text-xs text-text-secondary">
        {tournamentRule(tournament.metric, tournament.metric_label)}
      </p>
      <div className="mt-3 tabular-nums">
        {tournament.standings.map((row) => (
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
                ? `${formatMetric(tournament.metric, row.score)} · ${row.matches} ${row.matches === 1 ? 'game' : 'games'}`
                : 'No qualifying game yet'
            }
            right={
              settled && row.payout_cents > 0 ? (
                <AmountText cents={row.payout_cents} win />
              ) : undefined
            }
          />
        ))}
      </div>
      <p className="mt-3 text-xs text-text-secondary">
        Pot {formatPoints(tournament.pot_cents)}
        {!settled && ` · ${closesIn(tournament.window_ends_at)}`}
      </p>
    </Card>
  );
}
