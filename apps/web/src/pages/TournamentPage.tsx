import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ModeSwitcher } from '../components/ModeSwitcher';
import { AmountText } from '../components/ui/AmountText';
import { Card } from '../components/ui/Card';
import { CardGrid } from '../components/ui/CardGrid';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { GameTabs } from '../components/ui/GameTabs';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatCurrency } from '../lib/format';
import { gameMeta, isComingSoon } from '../lib/games';
import { platformFeeNote, rakeOnPot } from '../lib/rake';
import { filledSpots } from '../lib/spots';
import { useAuth } from '../auth/useAuth';
import { useGameSelection } from '../hooks/useGameSelection';
import {
  useEnterTournament,
  useLeaveTournament,
  useTournamentMarkets,
  useTournamentStatus,
  type TournamentView,
} from '../hooks/useTournaments';

/** The Tournament section: browse joinable skill fields as cards. */
export function TournamentPage() {
  usePageTitle('Tournament');
  const { isDemo } = useAuth();
  const { games, selected: game, select: setGame } = useGameSelection();
  const playableGame = game && !isComingSoon(game) ? game : undefined;
  const {
    data: markets,
    isError: marketsUnavailable,
    isLoading: marketsLoading,
  } = useTournamentMarkets(playableGame);
  const { data: status } = useTournamentStatus();
  const enter = useEnterTournament();

  const [metricFilter, setMetricFilter] = useState<string>(ALL);

  const places = markets?.prize_split.length ?? 3;
  const scoreN = markets?.score_matches ?? 3;

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="tournament">
            A field of similar-skill players all chase the same stat. Your best {scoreN}{' '}
            matches inside the window are scored automatically, and the top {places}{' '}
            split the pot. No reporting, no brackets, just play.
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

  // The markets endpoint 404s for a game that doesn't offer tournaments yet.
  if (game && marketsUnavailable) {
    return (
      <div>
        {header}
        <EmptyState
          title={`No tournaments on ${gameMeta(game).name} yet`}
          subline="Tournaments are Counter Strike 2 only for now. More games are coming."
          action={
            <Link to="/pools">
              <PillButton>Browse solo pools</PillButton>
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
          subline="Tournaments score your best matches automatically, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link a game</PillButton>
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
          title="No tournaments on this game yet"
          subline="Play a match on it and they appear here."
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
                const key = `${game}:${m.metric}`;
                return (
                  <WagerCard
                    key={key}
                    gameName={`${fieldSize} players`}
                    tag={`top ${places} paid`}
                    title={m.label}
                    subtitle={`Your best ${scoreN} matches in the window are scored automatically.`}
                    entryOptions={presets}
                    payoutFor={(entry) => entry * fieldSize}
                    payoutLabel="Pot if full"
                    // Rake is taken off the full pot before the top places split
                    // it (money_math.split_by_weights).
                    feeNote={(entry) => platformFeeNote(rakeOnPot(entry * fieldSize))}
                    capacity={fieldSize}
                    filled={isDemo ? filledSpots(key, fieldSize) : undefined}
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

/** In-flight tournament: forming banner (with cancel) or live/final standings. */
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
      <div className="mt-3">
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
                ? `${row.score.toFixed(2)} · ${row.matches} matches`
                : 'No qualifying match yet'
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
        Pot {formatCurrency(tournament.pot_cents)} · the window closes automatically.
      </p>
    </Card>
  );
}
