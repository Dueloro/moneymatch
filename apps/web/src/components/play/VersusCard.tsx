import { formatCurrency } from '../../lib/format';

interface Side {
  name: string;
  rating?: number | null;
  you?: boolean;
}

/**
 * Head-to-head duel card: the emotional core of a match. Both players, the pot,
 * and what you take home. Used for the matched slip state and the landing hero.
 */
export function VersusCard({
  marketLabel,
  you,
  opponent,
  potCents,
  prizeCents,
  status,
}: {
  marketLabel: string;
  you: Side;
  opponent: Side;
  potCents: number;
  prizeCents: number;
  status?: string;
}) {
  return (
    <div className="animate-rise rounded-2xl border border-hairline bg-panel-raised p-5">
      <div className="flex items-center justify-between">
        <span className="label-mono">{status ?? 'Opponent found'}</span>
        <span className="label-mono">{marketLabel}</span>
      </div>

      <div className="mt-4 flex items-stretch gap-3">
        <Player side={{ ...you, you: true }} />
        <div className="flex flex-col items-center justify-center">
          <span className="rounded-pill border border-hairline px-2.5 py-1 text-xs font-bold text-text-secondary">
            VS
          </span>
        </div>
        <Player side={opponent} align="right" />
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-hairline pt-4">
        <div>
          <div className="label-mono">Pot</div>
          <div className="text-lg font-bold tabular-nums">
            {formatCurrency(potCents)}
          </div>
        </div>
        <div className="text-right">
          <div className="label-mono">You&apos;d win</div>
          <div className="text-lg font-bold tabular-nums text-green">
            {formatCurrency(prizeCents)}
          </div>
        </div>
      </div>
    </div>
  );
}

function Player({ side, align = 'left' }: { side: Side; align?: 'left' | 'right' }) {
  const right = align === 'right';
  return (
    <div
      className={[
        'flex min-w-0 flex-1 flex-col gap-2 rounded-xl border p-3',
        side.you ? 'border-green/40 bg-green/5' : 'border-hairline',
        right ? 'items-end text-right' : 'items-start',
      ].join(' ')}
    >
      <span
        className={[
          'grid h-9 w-9 place-items-center rounded-full text-sm font-bold',
          side.you ? 'bg-green text-black' : 'bg-panel text-text',
        ].join(' ')}
      >
        {(side.name || '?').slice(0, 1).toUpperCase()}
      </span>
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold">
          {side.you ? 'You' : side.name || 'Opponent'}
        </div>
        <div className="text-xs tabular-nums text-text-secondary">
          {side.rating != null ? side.rating : '—'}
        </div>
      </div>
    </div>
  );
}
