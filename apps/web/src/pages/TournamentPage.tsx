import { useState } from 'react';
import { Link } from 'react-router-dom';

import { ModeSwitcher } from '../components/ModeSwitcher';
import { TournamentPanel } from '../components/tournament/TournamentPanel';
import { CardGrid } from '../components/ui/CardGrid';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { ALL, FilterBar, FilterChips } from '../components/ui/FilterBar';
import { GameTabs } from '../components/ui/GameTabs';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { gameMeta, isComingSoon } from '../lib/games';
import { platformFeeNote, rakeOnPot } from '../lib/rake';
import { useGameSelection } from '../hooks/useGameSelection';
import {
  useEnterTournament,
  useTournamentMarkets,
  useTournamentStatus,
} from '../hooks/useTournaments';

function hours(seconds: number): string {
  const h = seconds / 3600;
  return Number.isInteger(h)
    ? `${h} hour${h === 1 ? '' : 's'}`
    : `${h.toFixed(1)} hours`;
}

/** The Tournament section: pick a stat tournament and you're in. */
export function TournamentPage() {
  usePageTitle('Tournament');
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

  const scoreN = markets?.score_matches ?? 3;
  const split = markets?.prize_split ?? [60, 25, 15];

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="tournament">
            Pick a stat and you&apos;re in. The tournament starts as soon as a second
            player joins and runs {hours(markets?.duration_seconds ?? 10800)} from then;
            others can join until it ends (up to {markets?.field_size ?? 10} players).
            Until it starts you can leave for a full refund. Your first {scoreN}{' '}
            qualifying games after it starts (and after you join) are scored
            automatically, and the top places split the pot {split.join('/')}.
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
          subline="More games are coming."
          action={
            <Link to="/play">
              <PillButton>Play head-to-head</PillButton>
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
          subline="Tournaments score your games automatically, so we need to know which account is yours."
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
  const metrics = markets?.metrics ?? [];
  const fieldSize = markets?.field_size ?? 10;
  const inOne = status?.status === 'formed';

  const filteredMetrics = metrics.filter(
    (m) => metricFilter === ALL || m.metric === metricFilter,
  );
  const activeCount = metricFilter !== ALL ? 1 : 0;

  return (
    <div>
      {header}

      {/* From xl up your tournament lives in the right rail (collapsible), so
       * it stops pushing the cards down. Narrower screens have no rail. */}
      <div className="xl:hidden">
        {inOne && status?.tournament && (
          <TournamentPanel tournament={status.tournament} />
        )}
      </div>

      <SectionHeader
        level="page"
        action={
          !marketsLoading &&
          metrics.length > 1 && (
            <FilterBar
              testId="tournament-filters"
              activeCount={activeCount}
              onClear={() => setMetricFilter(ALL)}
            >
              <FilterChips
                label="Stat"
                options={metrics.map((m) => m.metric)}
                selected={metricFilter}
                onSelect={(v) => setMetricFilter(v as string)}
                format={(m) => metrics.find((x) => x.metric === m)?.label ?? String(m)}
              />
            </FilterBar>
          )
        }
      >
        Tournaments
      </SectionHeader>

      {enter.isError && (
        <p className="mb-4 text-sm text-red" role="alert">
          {(enter.error as Error).message}
        </p>
      )}

      {marketsLoading ? (
        <SkeletonList rows={3} />
      ) : filteredMetrics.length === 0 || presets.length === 0 ? (
        <EmptyState
          title="No tournaments on this game yet"
          subline="Check back soon."
        />
      ) : (
        <CardGrid count={filteredMetrics.length}>
          {filteredMetrics.map((m) => {
            const inNow = (entry: number) =>
              (m.open_tables ?? []).find((t) => t.entry_cents === entry)?.players ?? 0;
            return (
              <WagerCard
                key={`${game}:${m.metric}`}
                gameName={game ? gameMeta(game).name : ''}
                tag={`top ${split.length} paid`}
                title={m.label}
                subtitle={m.rules}
                entryOptions={presets}
                payoutFor={(entry) => entry * fieldSize}
                payoutLabel="Pot if full"
                // Rake comes off the whole pot before the places split it.
                feeNote={(entry) => platformFeeNote(rakeOnPot(entry * fieldSize))}
                capacity={fieldSize}
                filledFor={inNow}
                buttonLabel={inOne ? "You're in a tournament" : 'Join tournament'}
                // Once anyone else joins, your entry is final.
                requireConfirm
                disabled={inOne}
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
    </div>
  );
}
