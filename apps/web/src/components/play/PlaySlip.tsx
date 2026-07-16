import { PillButton } from '../ui/PillButton';
import { PresetSelector } from '../ui/PresetSelector';
import { formatCurrency, formatPct } from '../../lib/format';
import {
  prizeForEntry,
  useConfirmMatch,
  useDeclineMatch,
  useLeaveQueue,
  type MarketRow,
  type MatchView,
  type QueueStatus,
} from '../../hooks/useMatchmaking';

/**
 * The right slip panel's state machine (design PDF p.1–2):
 *   pick → presets + "You'd win" → Find match → searching (band + cancel)
 *        → matched (opponent card + Confirm) → active ("Go play").
 *
 * The live queue status is server-authoritative, so once a match forms the slip
 * follows it regardless of local selection.
 */
export function PlaySlip({
  status,
  market,
  entryCents,
  presetsCents,
  onSelectEntry,
  onFindMatch,
  finding,
}: {
  status: QueueStatus | undefined;
  market: MarketRow | null;
  entryCents: number | null;
  presetsCents: number[];
  onSelectEntry: (cents: number) => void;
  onFindMatch: () => void;
  finding: boolean;
}) {
  if (status?.status === 'matched' && status.match) {
    return <MatchedSlip match={status.match} />;
  }
  if (status?.status === 'searching') {
    return <SearchingSlip status={status} />;
  }
  if (market) {
    return (
      <WagerSlip
        market={market}
        entryCents={entryCents}
        presetsCents={presetsCents}
        onSelectEntry={onSelectEntry}
        onFindMatch={onFindMatch}
        finding={finding}
      />
    );
  }
  return (
    <SlipShell>
      <p className="text-sm font-semibold text-text">Pick a stat to start</p>
      <p className="mt-1 text-xs text-text-secondary">
        Choose a market on the left, set your entry, and we&apos;ll find a fair,
        evenly-matched opponent.
      </p>
    </SlipShell>
  );
}

function SlipShell({ children }: { children: React.ReactNode }) {
  return (
    <aside
      className="w-[354px] shrink-0 rounded-2xl bg-panel p-6"
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
      Both stake {formatCurrency(entryCents)} · winner takes {formatCurrency(prize)} ·{' '}
      {formatCurrency(fee)} platform fee
    </p>
  );
}

function WagerSlip({
  market,
  entryCents,
  presetsCents,
  onSelectEntry,
  onFindMatch,
  finding,
}: {
  market: MarketRow;
  entryCents: number | null;
  presetsCents: number[];
  onSelectEntry: (cents: number) => void;
  onFindMatch: () => void;
  finding: boolean;
}) {
  const canFind = entryCents != null && !market.provisional && !finding;
  const prize =
    entryCents != null ? prizeForEntry(entryCents, market.multiplier_bps) : 0;

  return (
    <SlipShell>
      <p className="text-xs uppercase tracking-wide text-text-secondary">Wagering on</p>
      <h3 className="text-lg font-bold text-text">{market.label}</h3>

      {market.provisional ? (
        <p className="mt-3 rounded-lg bg-bg p-3 text-xs text-text-secondary">
          You need more recent matches on this stat before you can duel it. Play a few
          and check back.
        </p>
      ) : (
        <>
          <p className="mt-4 mb-2 text-xs font-semibold text-text-secondary">Entry</p>
          <PresetSelector
            presetsCents={presetsCents}
            selectedCents={entryCents}
            onSelect={onSelectEntry}
          />

          {entryCents != null && (
            <>
              <p className="mt-4 text-sm text-text">
                You&apos;d win{' '}
                <span className="font-bold text-green">{formatCurrency(prize)}</span> on
                a {formatCurrency(entryCents)} wager
              </p>
              <RakeLine entryCents={entryCents} multiplierBps={market.multiplier_bps} />
            </>
          )}

          <p className="mt-3 text-xs text-text-secondary">{market.resolution_note}</p>

          <div className="mt-5">
            <PillButton fullWidth disabled={!canFind} onClick={onFindMatch}>
              {finding ? 'Finding…' : 'Find match'}
            </PillButton>
          </div>
        </>
      )}
    </SlipShell>
  );
}

function SearchingSlip({ status }: { status: QueueStatus }) {
  const leave = useLeaveQueue();
  const stage = status.tolerance_stage ?? 0;
  const bandCopy =
    stage === 0
      ? 'Matching you tightly on skill…'
      : `Widening the search for a fair match (stage ${stage + 1})…`;

  return (
    <SlipShell>
      <div className="flex items-center gap-3">
        <span
          className="h-3 w-3 animate-pulse rounded-full bg-green"
          data-testid="searching-dot"
        />
        <p className="text-sm font-semibold text-text">Searching…</p>
      </div>
      <p className="mt-2 text-xs text-text-secondary">{bandCopy}</p>
      {status.waited_seconds != null && (
        <p className="mt-1 text-xs text-text-secondary">
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
  const opponent = match.players.find((p) => !p.is_you);
  const active = match.state === 'ACTIVE' || match.state === 'AWAITING_RESULT';

  return (
    <SlipShell>
      <p className="text-xs uppercase tracking-wide text-text-secondary">
        {active ? 'Match on' : 'Opponent found'}
      </p>
      <h3 className="text-lg font-bold text-text">{match.market_label}</h3>

      <div className="mt-3 rounded-lg bg-bg p-3">
        <p className="text-sm font-medium text-text">
          vs {opponent?.username ?? 'opponent'}
          {opponent?.rating != null && (
            <span className="text-text-secondary"> · {opponent.rating}</span>
          )}
        </p>
        {match.forecast && (
          <p className="mt-1 text-xs text-green" data-testid="forecast">
            {match.forecast.label}
          </p>
        )}
      </div>

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
              Confirm &amp; stake {formatCurrency(match.entry_cents)}
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
  if (match.brokered && match.your_play_url) {
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
    <div className="mt-5 rounded-lg bg-bg p-3">
      <p className="text-sm font-medium text-text">Play your next match now</p>
      <p className="mt-1 text-xs text-text-secondary">
        Jump into {match.game.split('.')[0].toUpperCase()} and play. We grade your next
        finished match automatically — no reporting needed.
      </p>
      {match.forecast && (
        <p className="mt-2 text-xs text-text-secondary">
          Even-duel forecast: {formatPct(match.forecast.you_win_prob)} you.
        </p>
      )}
    </div>
  );
}
