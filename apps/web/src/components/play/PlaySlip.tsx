import { PillButton } from '../ui/PillButton';
import { VersusCard } from './VersusCard';
import { dashless, formatPoints } from '../../lib/format';
import { timeControlLabel } from '../../lib/timeControl';
import {
  prizeForEntry,
  useConfirmMatch,
  useDeclineMatch,
  useLeaveQueue,
  type MatchView,
  type QueueStatus,
} from '../../hooks/useMatchmaking';

export function PlaySlip({ status }: { status: QueueStatus | undefined }) {
  if (status?.status === 'matched' && status.match) {
    return <MatchedSlip match={status.match} />;
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
  const leave = useLeaveQueue();

  return (
    <SlipShell>
      <div className="flex items-center gap-3">
        <span
          className="h-3 w-3 animate-pulse rounded-full bg-live"
          data-testid="searching-dot"
        />
        <p className="text-sm font-semibold text-text">Searching…</p>
      </div>
      <p className="mt-2 text-xs text-text-secondary">
        Matching you with someone at your skill level…
      </p>
      {status.waited_seconds != null && (
        <p className="mt-1 text-xs tabular-nums text-text-secondary">
          Waiting {status.waited_seconds}s
        </p>
      )}
      <div className="mt-5">
        <PillButton
          variant="text"
          onClick={() => leave.mutate()}
          disabled={leave.isPending}
        >
          Cancel search
        </PillButton>
      </div>
    </SlipShell>
  );
}

function MatchedSlip({ match }: { match: MatchView }) {
  const confirm = useConfirmMatch();
  const decline = useDeclineMatch();
  const you = match.players.find((p) => p.is_you);
  const opponent = match.players.find((p) => !p.is_you);
  const active = match.state === 'ACTIVE' || match.state === 'AWAITING_RESULT';

  return (
    <SlipShell>
      <VersusCard
        marketLabel={timeControlLabel(match.speed) || match.market_label}
        status={active ? 'Match on' : 'Opponent found'}
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

      {active ? (
        <GoPlay match={match} />
      ) : (
        <div className="mt-5 space-y-2">
          {match.you_confirmed ? (
            <p className="text-xs text-text-secondary">
              Waiting for {opponent?.username ?? 'your opponent'} to confirm…
            </p>
          ) : (
            <PillButton
              fullWidth
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
      )}
    </SlipShell>
  );
}

function GoPlay({ match }: { match: MatchView }) {
  if (match.your_play_url) {
    return (
      <div className="mt-5">
        <a href={match.your_play_url} target="_blank" rel="noreferrer">
          <PillButton fullWidth>Go play your game ↗</PillButton>
        </a>
        <p className="mt-2 text-xs text-text-secondary">
          Only you and your opponent can take these seats. We settle this exact game
          automatically.
        </p>
      </div>
    );
  }
  return (
    <div className="mt-5 rounded-inset bg-bg p-3">
      <p className="text-sm font-medium text-text">Game link unavailable</p>
      <p className="mt-1 text-xs text-text-secondary">
        Your entry is held safely and the link should arrive shortly. Contact support
        with your match ID if this persists.
      </p>
    </div>
  );
}
