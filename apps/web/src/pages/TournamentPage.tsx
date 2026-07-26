import { Link } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { AmountText } from '../components/ui/AmountText';
import { ComingSoonPanel } from '../components/ui/ComingSoonPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { GameTabs } from '../components/ui/GameTabs';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { WagerCard } from '../components/ui/WagerCard';
import { formatCurrency } from '../lib/format';
import { gameMeta, isComingSoon } from '../lib/games';
import { filledSpots } from '../lib/spots';
import { useGameSelection } from '../hooks/useGameSelection';
import {
  useEnterTournament,
  useLeaveTournament,
  useTournamentMarkets,
  useTournamentStatus,
  type TournamentView,
} from '../hooks/useTournaments';

// Advertised field sizes (10–20 players). The backend forms a real field on
// join; these give the browse cards a realistic range of tournament sizes.
const FIELD_SIZES = [10, 16, 20];

/** The Tournament section: browse joinable skill fields as cards. */
export function TournamentPage() {
  const { games, selected: game, select: setGame } = useGameSelection();
  const playableGame = game && !isComingSoon(game) ? game : undefined;
  const {
    data: markets,
    isError: marketsUnavailable,
    isLoading: marketsLoading,
  } = useTournamentMarkets(playableGame);
  const { data: status } = useTournamentStatus();
  const enter = useEnterTournament();

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

  // The markets endpoint 404s for a game that doesn't offer tournaments yet.
  if (game && marketsUnavailable) {
    return (
      <div>
        {header}
        <EmptyState
          title={`Tournaments aren't available for ${gameMeta(game).name} yet`}
          subline="Tournaments are Counter-Strike 2 only for now — more games soon."
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
          subline="Tournaments record your best matches automatically. Link to play."
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
  const places = markets?.prize_split.length ?? 3;
  const scoreN = markets?.score_matches ?? 3;
  const busy = status?.status === 'searching' || status?.status === 'formed';

  return (
    <div>
      {header}

      <p className="mb-6 max-w-2xl text-sm text-text-secondary">
        Tournaments field 10–20 similar-skill players. Your best {scoreN} matches over
        the window are scored automatically — no reporting — and the top {places} split
        the pot. Pick a tournament and join.
      </p>

      {status && (status.status === 'searching' || status.status === 'formed') && (
        <TournamentStatusBanner status={status} />
      )}

      {openMetrics.length === 0 ? (
        <p className="py-8 text-sm text-text-secondary">
          {marketsLoading
            ? 'Loading tournaments…'
            : 'No tournaments on this game yet — play a match on it and they appear here.'}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {openMetrics.flatMap((m) =>
            presets.map((entry, i) => {
              const size = FIELD_SIZES[i % FIELD_SIZES.length];
              const key = `${game}:${m.metric}:${entry}:${size}`;
              return (
                <WagerCard
                  key={key}
                  accent={meta?.accent ?? 'var(--text-secondary)'}
                  gameName={meta?.short ?? 'Game'}
                  tag={`${size} players`}
                  title={m.label}
                  subtitle={`Best ${scoreN} matches · top ${places} split the pot`}
                  entryCents={entry}
                  capacity={size}
                  filled={filledSpots(key, size)}
                  footnote={`Top ${places} paid`}
                  buttonLabel="Join Tournament"
                  disabled={busy}
                  joining={enter.isPending}
                  onJoin={() =>
                    enter.mutate({
                      game: markets!.game,
                      metric: m.metric,
                      entry_preset_cents: entry,
                    })
                  }
                />
              );
            }),
          )}
        </div>
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
    <div
      className="mb-6 flex items-center justify-between gap-4 rounded-2xl bg-panel p-4"
      data-testid="tournament-status"
    >
      <div className="flex items-center gap-3">
        <span className="h-3 w-3 animate-pulse rounded-full bg-green" />
        <div>
          <p className="text-sm font-semibold text-text">Forming a field…</p>
          <p className="text-xs text-text-secondary">
            Matching you with similar-skill players under the dispersion cap.
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

function StandingsPanel({ tournament }: { tournament: TournamentView }) {
  const settled = tournament.state === 'SETTLED';
  return (
    <div className="mb-6 rounded-2xl bg-panel p-6" data-testid="standings-panel">
      <p className="label-mono">{settled ? 'Final standings' : 'Live standings'}</p>
      <h3 className="text-lg font-bold text-text">{tournament.metric_label}</h3>
      <div className="mt-3">
        {tournament.standings.map((row) => (
          <ListRow
            key={row.user_id}
            title={
              <span className={row.is_you ? 'text-green' : undefined}>
                {row.rank ? `#${row.rank}` : '—'} {row.username ?? 'Player'}
                {row.is_you ? ' (you)' : ''}
              </span>
            }
            subline={
              row.score != null
                ? `${row.score.toFixed(2)} · ${row.matches} matches`
                : 'no qualifying match yet'
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
        Pot {formatCurrency(tournament.pot_cents)} · window closes automatically.
      </p>
    </div>
  );
}
