import { useState, type ReactNode } from 'react';

import {
  useLeaveTournament,
  type TournamentGame,
  type TournamentView,
} from '../../hooks/useTournaments';
import { formatCurrency } from '../../lib/format';
import { AmountText } from '../ui/AmountText';
import { Card } from '../ui/Card';
import { GameBadge } from '../ui/GameBadge';
import { ChevronDownIcon } from '../ui/icons';
import { ListRow } from '../ui/ListRow';
import { PillButton } from '../ui/PillButton';

/**
 * Your current (or just-finished) tournament: the field, and the log of your
 * games we fetched with whether each one counted.
 *
 * It lives in the right rail (`RailTournamentCard`), collapsible, so joining a
 * tournament no longer pushes the browse grid down the page. Below `xl` there
 * is no rail, so TournamentPage keeps the inline `TournamentPanel` there.
 */

function clockTime(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(2);
}

function isLive(t: TournamentView): boolean {
  return t.state === 'OPEN' || t.state === 'LOCKED';
}

function stateLine(t: TournamentView): string {
  if (t.state === 'OPEN') {
    return `Open to join until ${clockTime(t.join_closes_at)} · ends ${clockTime(t.window_ends_at)}`;
  }
  if (t.state === 'LOCKED')
    return `Joining closed · ends ${clockTime(t.window_ends_at)}`;
  if (t.state === 'CANCELED') {
    if (t.outcome_reason === 'not_enough_players') {
      return t.players <= 1
        ? 'You were the only player, so your entry was refunded in full.'
        : 'Not enough players, so every entry was refunded in full.';
    }
    if (t.outcome_reason === 'no_scores') {
      return 'Nobody had a counted game, so every entry was refunded in full.';
    }
    return 'Canceled. Your entry was refunded.';
  }
  return 'Final standings';
}

/** A toggle remembered per browser. Storage can be unavailable (private
 * windows), so every access is guarded and the default still renders. */
function useRememberedToggle(key: string, initial: boolean): [boolean, () => void] {
  const storageKey = `mm.tournament-panel.${key}`;
  const [open, setOpen] = useState<boolean>(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      return raw == null ? initial : raw === '1';
    } catch {
      return initial;
    }
  });
  const toggle = () =>
    setOpen((was) => {
      const next = !was;
      try {
        window.localStorage.setItem(storageKey, next ? '1' : '0');
      } catch {
        // Not remembered; still toggles for this visit.
      }
      return next;
    });
  return [open, toggle];
}

function Chevron({ open }: { open: boolean }) {
  return (
    <ChevronDownIcon
      className={[
        'h-4 w-4 shrink-0 text-text-tertiary transition-transform',
        open ? 'rotate-180' : '',
      ].join(' ')}
    />
  );
}

function LiveDot() {
  return (
    <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-live" aria-hidden />
  );
}

/** Every player in the field, ranked. */
function Standings({ t }: { t: TournamentView }) {
  const settled = t.state === 'SETTLED';
  return (
    <div>
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
              ? `${formatScore(row.score)} · ${row.matches} of ${t.score_matches} games`
              : 'No counted game yet'
          }
          right={
            settled && row.payout_cents > 0 ? (
              <AmountText cents={row.payout_cents} win />
            ) : undefined
          }
        />
      ))}
    </div>
  );
}

/** Every game of yours we fetched around the tournament, and whether/why it
 * counted. */
function YourGames({ games }: { games: TournamentGame[] }) {
  if (games.length === 0) {
    return (
      <p className="py-2 text-xs text-text-secondary">
        Your games show up here a few minutes after they finish.
      </p>
    );
  }
  return (
    <div data-testid="your-games">
      {games.map((g) => (
        <ListRow
          key={g.host_match_id}
          title={
            <span>
              {clockTime(g.started_at)} · {g.mode ?? 'game'}
              {g.result ? ` · ${g.result}` : ''}
            </span>
          }
          subline={g.reason_text}
          right={
            g.value != null ? (
              <span
                className={
                  g.reason === 'COUNTED'
                    ? 'text-sm font-semibold text-text'
                    : 'text-sm text-text-tertiary'
                }
              >
                {formatScore(g.value)}
              </span>
            ) : undefined
          }
        />
      ))}
    </div>
  );
}

function LeaveButton({ t }: { t: TournamentView }) {
  const leave = useLeaveTournament();
  if (!(t.state === 'OPEN' && t.players <= 1)) return null;
  return (
    <PillButton
      variant="text"
      size="sm"
      className="px-0"
      onClick={() => leave.mutate()}
      disabled={leave.isPending}
    >
      Leave and get my entry back
    </PillButton>
  );
}

function SoloNote({ t }: { t: TournamentView }) {
  if (!(isLive(t) && t.players <= 1)) return null;
  return (
    <p className="text-xs text-text-secondary">
      You&apos;re first in. Others who pick this stat and entry join you. Your games
      count from the moment you joined. If nobody else joins, the tournament still runs
      and your entry is refunded in full when it ends.
    </p>
  );
}

/** The inline panel, for screens without the rail. */
export function TournamentPanel({ tournament: t }: { tournament: TournamentView }) {
  const live = isLive(t);
  const settled = t.state === 'SETTLED';
  return (
    <Card className="mb-6 p-5" data-testid="standings-panel">
      <div className="flex items-center gap-2">
        {live && <LiveDot />}
        <p
          className={[
            'text-xs font-semibold uppercase tracking-wide',
            live ? 'text-live' : 'text-text-tertiary',
          ].join(' ')}
        >
          {live ? 'Your tournament' : settled ? 'Final standings' : 'Last tournament'}
        </p>
      </div>
      <h2 className="mt-2 text-xl font-semibold text-text">{t.metric_label}</h2>
      <p className="mt-1 text-sm text-text-secondary">
        {t.players} of {t.field_size} players · pot {formatCurrency(t.pot_cents)} ·{' '}
        {stateLine(t)}
      </p>
      <div className="mt-2">
        <SoloNote t={t} />
      </div>
      <div className="mt-3">
        <Standings t={t} />
      </div>
      <div className="mt-5">
        <p className="label-money mb-1">Your games</p>
        <YourGames games={t.your_games ?? []} />
      </div>
      <div className="mt-4">
        <LeaveButton t={t} />
      </div>
    </Card>
  );
}

/** A collapsible sub-section inside the rail card. */
function Section({
  id,
  title,
  count,
  children,
  testId,
}: {
  id: string;
  title: string;
  count?: number;
  children: ReactNode;
  testId: string;
}) {
  const [open, toggle] = useRememberedToggle(id, true);
  const bodyId = `rail-tournament-${id}`;
  return (
    <div className="mt-3 border-t border-hairline pt-2">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={bodyId}
        data-testid={testId}
        className="flex w-full items-center gap-2 py-1 text-left"
      >
        <span className="label-money flex-1">
          {title}
          {count != null && <span className="ml-1 text-text-tertiary">({count})</span>}
        </span>
        <Chevron open={open} />
      </button>
      {open && <div id={bodyId}>{children}</div>}
    </div>
  );
}

/** Your tournament in the right rail: a one-line summary that expands into the
 * field and your game log. */
export function RailTournamentCard({ tournament: t }: { tournament: TournamentView }) {
  const [open, toggle] = useRememberedToggle('card', true);
  const live = isLive(t);
  const you = t.standings.find((r) => r.is_you);
  const settled = t.state === 'SETTLED';

  let summary: ReactNode;
  if (t.state === 'CANCELED') {
    summary = 'Refunded in full';
  } else if (you?.score != null) {
    summary = (
      <>
        You: <span className="font-semibold text-text">#{you.rank}</span> ·{' '}
        {formatScore(you.score)} · {you.matches} of {t.score_matches} games
      </>
    );
  } else {
    summary = 'No counted game yet';
  }

  return (
    <Card className="p-3" data-testid="rail-tournament-card">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="rail-tournament-body"
        className="flex w-full items-center gap-2 text-left"
      >
        {live && <LiveDot />}
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-text">
          {t.metric_label} tournament
        </p>
        <GameBadge game={t.game} />
        <Chevron open={open} />
      </button>
      <p className="mt-0.5 text-xs text-text-secondary">
        {t.players} of {t.field_size} players · pot {formatCurrency(t.pot_cents)}
        {live ? ` · ends ${clockTime(t.window_ends_at)}` : settled ? ' · final' : ''}
      </p>
      <div className="mt-2 flex items-baseline justify-between gap-2 text-xs text-text-secondary">
        <span className="min-w-0 truncate" data-testid="rail-tournament-summary">
          {summary}
        </span>
        {settled && (you?.payout_cents ?? 0) > 0 && (
          <AmountText cents={you!.payout_cents} win />
        )}
      </div>

      {open && (
        <div id="rail-tournament-body">
          {t.state === 'CANCELED' && (
            <p className="mt-2 text-xs text-text-secondary">{stateLine(t)}</p>
          )}
          <div className="mt-2">
            <SoloNote t={t} />
          </div>
          <Section
            id="players"
            title="Players"
            count={t.players}
            testId="rail-tournament-players"
          >
            <Standings t={t} />
          </Section>
          <Section
            id="games"
            title="Your games"
            count={(t.your_games ?? []).length}
            testId="rail-tournament-games"
          >
            <YourGames games={t.your_games ?? []} />
          </Section>
          <div className="mt-2">
            <LeaveButton t={t} />
          </div>
        </div>
      )}
    </Card>
  );
}
