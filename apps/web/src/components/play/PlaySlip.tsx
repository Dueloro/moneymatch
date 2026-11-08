import { PillButton } from '../ui/PillButton';
import { SkillBandRuler } from './SkillBandRuler';
import { VersusCard } from './VersusCard';
import { useWaitedSeconds } from '../../hooks/useWaitedSeconds';
import { bandAt, bandRange, formatWaited, MAX_BAND } from '../../lib/skillBand';
import { dashless, formatPoints } from '../../lib/format';
import { clockFor, timeControlLabel, type SpeedClock } from '../../lib/timeControl';
import {
  prizeForEntry,
  useConfirmMatch,
  useDeclineMatch,
  useLeaveQueue,
  type MatchView,
  type QueueStatus,
} from '../../hooks/useMatchmaking';

/** Searching, then the confirm card. Once both confirm, the match stage takes over. */
export function PlaySlip({
  status,
  clocks,
}: {
  status: QueueStatus | undefined;
  clocks?: SpeedClock[];
}) {
  if (status?.status === 'matched' && status.match) {
    return <MatchedSlip match={status.match} clocks={clocks} />;
  }
  if (status?.status === 'searching') {
    return <SearchingSlip status={status} />;
  }
  return null;
}

function SlipShell({ children }: { children: React.ReactNode }) {
  return (
    <aside
      className="w-full rounded-card border border-hairline bg-panel p-5 md:p-6"
      data-testid="play-slip"
    >
      {children}
    </aside>
  );
}

function RakeLine({
  entryCents,
  multiplierBps,
}: {
  entryCents: number;
  multiplierBps: number;
}) {
  const prize = prizeForEntry(entryCents, multiplierBps);
  const fee = entryCents * 2 - prize;
  return (
    <p className="mt-3 text-xs text-text-secondary">
      Both stake {formatPoints(entryCents)} · winner takes {formatPoints(prize)} · fee{' '}
      {formatPoints(fee)}
    </p>
  );
}

function SearchingSlip({ status }: { status: QueueStatus }) {
  const ticket = status.ticket ?? null;
  const leave = useLeaveQueue();
  const seconds = useWaitedSeconds(status.waited_seconds);
  const rating = ticket?.rating ?? null;
  const band = bandAt(seconds);
  const recap = ticket
    ? [
        timeControlLabel(ticket.speed, ticket.clock),
        `${formatPoints(ticket.entry_cents)} stake`,
      ]
        .filter(Boolean)
        .join(' · ')
    : null;

  return (
    <SlipShell>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="h-2 w-2 animate-pulse rounded-full bg-live"
              data-testid="searching-dot"
            />
            <p className="text-sm font-semibold text-text">Searching</p>
          </div>
          {recap && <p className="mt-1 text-xs text-text-secondary">{recap}</p>}
        </div>
        <p
          className="num text-sm text-text-secondary"
          aria-label={`Waited ${seconds} seconds`}
          data-testid="waited"
        >
          {formatWaited(seconds)}
        </p>
      </div>

      <div className="mt-6">
        <p className="num text-2xl font-semibold text-text" data-testid="band-range">
          {rating != null ? bandRange(rating, seconds).join('–') : `±${band}`}
        </p>
        <p className="label-neutral mt-0.5">
          {band >= MAX_BAND ? 'Widest range' : 'Your range'}
          {rating != null ? ` · ±${band}` : ''}
        </p>
      </div>

      <div className="mt-4">
        <SkillBandRuler rating={rating} seconds={seconds} />
      </div>

      <div className="mt-6 flex items-center justify-between gap-4 border-t border-hairline pt-4">
        <p className="text-xs text-text-tertiary">
          {band >= MAX_BAND
            ? 'Matched with the closest rating in range'
            : `Widens as you wait, up to ±${MAX_BAND}`}
        </p>
        <PillButton
          variant="text"
          className="shrink-0 whitespace-nowrap"
          onClick={() => leave.mutate()}
          disabled={leave.isPending}
        >
          Cancel search
        </PillButton>
      </div>
    </SlipShell>
  );
}

function MatchedSlip({ match, clocks }: { match: MatchView; clocks?: SpeedClock[] }) {
  const confirm = useConfirmMatch();
  const decline = useDeclineMatch();
  const you = match.players.find((p) => p.is_you);
  const opponent = match.players.find((p) => !p.is_you);

  return (
    <SlipShell>
      <VersusCard
        marketLabel={
          timeControlLabel(match.speed, clockFor(match.speed, clocks)) ||
          match.market_label
        }
        status="Opponent found"
        you={{ name: you?.username ?? 'You', rating: you?.rating }}
        opponent={{ name: opponent?.username ?? 'Opponent', rating: opponent?.rating }}
        potCents={match.pot_cents}
        prizeCents={match.prize_cents}
      />

      {match.forecast && (
        <p className="mt-3 text-xs text-text-secondary" data-testid="forecast">
          {dashless(match.forecast.label)}
        </p>
      )}

      <RakeLine entryCents={match.entry_cents} multiplierBps={match.multiplier_bps} />

      <div className="mt-5 space-y-2">
        {match.you_confirmed ? (
          <p className="text-xs text-text-secondary">
            Waiting for {opponent?.username ?? 'your opponent'} to confirm…
          </p>
        ) : (
          <PillButton
            fullWidth
            size="lg"
            onClick={() => confirm.mutate(match.id)}
            disabled={confirm.isPending}
          >
            Confirm &amp; stake {formatPoints(match.entry_cents)}
          </PillButton>
        )}
        <PillButton
          variant="text"
          fullWidth
          onClick={() => decline.mutate(match.id)}
          disabled={decline.isPending}
        >
          Decline
        </PillButton>
      </div>
    </SlipShell>
  );
}
