import { useState } from 'react';
import { Link } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { FriendsPanel } from '../components/FriendsPanel';
import { LeaderboardPanel } from '../components/LeaderboardPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { PresetSelector } from '../components/ui/PresetSelector';
import { SubTabs } from '../components/ui/SubTabs';
import { AmountText } from '../components/ui/AmountText';
import { formatCurrency } from '../lib/format';
import {
  useEnterTournament,
  useLeaveTournament,
  useTournamentMarkets,
  useTournamentStatus,
  type TournamentMetric,
  type TournamentView,
} from '../hooks/useTournaments';

type SectionTab = 'tournaments' | 'leaderboard' | 'friends';

/** The Tournament section: sub-tabs across Tournaments / Leaderboard / Friends
 * (design p.6, p.7, p.8). */
export function TournamentPage() {
  const [tab, setTab] = useState<SectionTab>('tournaments');
  return (
    <div>
      <div className="mb-6">
        <SubTabs<SectionTab>
          tabs={[
            { key: 'tournaments', label: 'Tournaments' },
            { key: 'leaderboard', label: 'Leaderboard' },
            { key: 'friends', label: 'Friends' },
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>
      {tab === 'tournaments' && <TournamentsTab />}
      {tab === 'leaderboard' && <LeaderboardPanel />}
      {tab === 'friends' && <FriendsPanel />}
    </div>
  );
}

function TournamentsTab() {
  const { data: markets } = useTournamentMarkets();
  const { data: status } = useTournamentStatus();
  const enter = useEnterTournament();

  const [metricKey, setMetricKey] = useState<string | null>(null);
  const [entryCents, setEntryCents] = useState<number | null>(null);

  const metric: TournamentMetric | null =
    markets?.metrics.find((m) => m.metric === metricKey) ?? markets?.metrics[0] ?? null;

  function enterField() {
    if (!markets || !metric || entryCents == null) return;
    enter.mutate({
      game: markets.game,
      metric: metric.metric,
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
          subline="Tournaments record your best matches automatically — link to play."
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

      <div className="mb-6 flex gap-2" role="tablist">
        {markets?.metrics.map((m) => (
          <button
            key={m.metric}
            role="tab"
            aria-selected={m.metric === (metric?.metric ?? '')}
            onClick={() => setMetricKey(m.metric)}
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
          <ListRow
            title={`Best ${metric?.label ?? ''} — first ${markets?.score_matches ?? 3} matches`}
            subline={`Field of ${markets?.field_size ?? 10} · top 3 split ${(markets?.prize_split ?? [50, 30, 20]).join('/')}`}
            right={
              <span className="text-xs text-text-secondary">
                Play your normal matches during the window
              </span>
            }
          />
          <p className="mt-4 text-xs text-text-secondary">
            Your best stat over the window is recorded automatically — no reporting. The
            field is matched on similar skill.
          </p>
        </div>

        <TournamentSlip
          status={status}
          metricLabel={metric?.label ?? ''}
          provisional={metric?.provisional ?? false}
          presetsCents={markets?.entry_presets_cents ?? []}
          entryCents={entryCents}
          onSelectEntry={setEntryCents}
          onEnter={enterField}
          entering={enter.isPending}
        />
      </div>
    </div>
  );
}

function TournamentSlip({
  status,
  metricLabel,
  provisional,
  presetsCents,
  entryCents,
  onSelectEntry,
  onEnter,
  entering,
}: {
  status: ReturnType<typeof useTournamentStatus>['data'];
  metricLabel: string;
  provisional: boolean;
  presetsCents: number[];
  entryCents: number | null;
  onSelectEntry: (cents: number) => void;
  onEnter: () => void;
  entering: boolean;
}) {
  const leave = useLeaveTournament();

  if (status?.status === 'formed' && status.tournament) {
    return <StandingsPanel tournament={status.tournament} />;
  }

  return (
    <aside
      className="w-[354px] shrink-0 rounded-2xl bg-panel p-6"
      data-testid="tournament-slip"
    >
      {status?.status === 'searching' ? (
        <>
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 animate-pulse rounded-full bg-green" />
            <p className="text-sm font-semibold text-text">Forming a field…</p>
          </div>
          <p className="mt-2 text-xs text-text-secondary">
            Matching you with similar-skill players under the dispersion cap.
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
      ) : provisional ? (
        <p className="text-xs text-text-secondary">
          Play a few more {metricLabel} matches to enter a tournament on this stat.
        </p>
      ) : (
        <>
          <p className="text-xs uppercase tracking-wide text-text-secondary">
            Enter tournament
          </p>
          <h3 className="text-lg font-bold text-text">Best {metricLabel}</h3>
          <p className="mt-4 mb-2 text-xs font-semibold text-text-secondary">Entry</p>
          <PresetSelector
            presetsCents={presetsCents}
            selectedCents={entryCents}
            onSelect={onSelectEntry}
          />
          <p className="mt-3 text-xs text-text-secondary">
            Top 3 split the pool minus rake. Prize is entrants&apos; pooled entries only
            — never house-funded.
          </p>
          <div className="mt-5">
            <PillButton
              fullWidth
              disabled={entryCents == null || entering}
              onClick={onEnter}
            >
              {entering ? 'Entering…' : 'Enter'}
            </PillButton>
          </div>
        </>
      )}
    </aside>
  );
}

function StandingsPanel({ tournament }: { tournament: TournamentView }) {
  const settled = tournament.state === 'SETTLED';
  return (
    <aside
      className="w-[354px] shrink-0 rounded-2xl bg-panel p-6"
      data-testid="standings-panel"
    >
      <p className="text-xs uppercase tracking-wide text-text-secondary">
        {settled ? 'Final standings' : 'Live standings'}
      </p>
      <h3 className="text-lg font-bold text-text">{tournament.metric_label}</h3>
      {tournament.field_mu_low != null && tournament.field_mu_high != null && (
        <p className="mt-1 text-xs text-text-secondary">
          Field: {tournament.metric_label} {tournament.field_mu_low}–
          {tournament.field_mu_high}
        </p>
      )}
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
    </aside>
  );
}
