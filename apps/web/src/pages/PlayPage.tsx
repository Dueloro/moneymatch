import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { BalanceHeader } from '../components/BalanceHeader';
import { PlaySlip } from '../components/play/PlaySlip';
import { EmptyState } from '../components/ui/EmptyState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { formatCurrency } from '../lib/format';
import { useLinks } from '../hooks/useLinks';
import {
  useJoinQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
  type MarketRow,
  type QueueStatus,
} from '../hooks/useMatchmaking';

function formatMultiplier(bps: number): string {
  return `×${(bps / 10000).toFixed(2)}`;
}

// States where the slip should show the confirm/active card for a deep-linked
// match; a terminal match falls through to the normal slip (reachable via Activity).
const DEEP_LINK_STATES = new Set(['PENDING', 'ACTIVE', 'AWAITING_RESULT']);

export function PlayPage() {
  const { data: links } = useLinks();
  const games = useMemo(() => links?.games ?? [], [links]);
  const [game, setGame] = useState<string | undefined>(undefined);

  // Default to the first linked game (else the first game) once links load.
  useEffect(() => {
    if (game || games.length === 0) return;
    const firstLinked = games.find((g) => g.status === 'LINKED');
    setGame((firstLinked ?? games[0]).game);
  }, [games, game]);

  const { data: markets } = useMarkets(game);

  // Inbox "Respond" lands here as /play?match=<id>; open that match's slip
  // directly (it isn't in the viewer's queue status when it came from a challenge).
  const [searchParams] = useSearchParams();
  const deepLinkMatchId = searchParams.get('match') ?? undefined;
  const { data: deepLinkMatch } = useMatch(deepLinkMatchId);

  const { data: liveStatus } = useQueueStatus();
  const status: QueueStatus | undefined =
    deepLinkMatch && DEEP_LINK_STATES.has(deepLinkMatch.state)
      ? {
          status: 'matched',
          match: deepLinkMatch,
          waited_seconds: null,
          tolerance_stage: null,
          can_cancel: false,
        }
      : liveStatus;

  const waiting = useWaiting(game);
  const join = useJoinQueue();
  const take = useTakeWaiting();

  const [marketKey, setMarketKey] = useState<string | null>(null);
  const [speed, setSpeed] = useState<string | null>(null);
  const [entryCents, setEntryCents] = useState<number | null>(null);

  // Reset the local slip selection when the game changes.
  useEffect(() => {
    setMarketKey(null);
    setSpeed(null);
    setEntryCents(null);
  }, [game]);

  const selectedMarket: MarketRow | null =
    markets?.markets.find((m) => m.key === marketKey) ?? null;

  const selectGame = games.find((g) => g.game === game);
  const linked = markets?.linked ?? false;

  function selectMarket(m: MarketRow) {
    setMarketKey(m.key);
    setSpeed(m.requires_speed ? (m.speeds[1] ?? m.speeds[0] ?? null) : null);
  }

  function findMatch() {
    if (!game || !selectedMarket || entryCents == null) return;
    join.mutate({
      game,
      market: selectedMarket.key,
      speed: selectedMarket.requires_speed ? (speed ?? undefined) : undefined,
      entry_preset_cents: entryCents,
    });
  }

  return (
    <div>
      <div className="mb-6">
        <BalanceHeader />
      </div>

      {/* Game tabs */}
      <div className="mb-6 flex gap-2" role="tablist">
        {games.map((g) => (
          <button
            key={g.game}
            role="tab"
            aria-selected={g.game === game}
            onClick={() => setGame(g.game)}
            className={[
              'rounded-pill px-4 py-1.5 text-sm font-semibold transition',
              g.game === game
                ? 'bg-text text-black'
                : 'border border-hairline text-text-secondary hover:text-text',
            ].join(' ')}
          >
            {g.display_name}
          </button>
        ))}
      </div>

      <div className="flex gap-8">
        <div className="min-w-0 flex-1">
          {!linked ? (
            <EmptyState
              title={`Link your ${selectGame?.display_name ?? 'game'} account`}
              subline="Link a game account to play head-to-head for real payouts."
              action={
                <Link to="/profile">
                  <PillButton>Link a game</PillButton>
                </Link>
              }
            />
          ) : (
            <>
              <h2 className="mb-2 text-sm font-semibold text-text-secondary">
                Markets
              </h2>
              <div className="mb-8">
                {markets?.markets.map((m) => {
                  const selected = m.key === marketKey;
                  return (
                    <button
                      key={m.key}
                      onClick={() => selectMarket(m)}
                      className="block w-full text-left"
                    >
                      <ListRow
                        left={
                          <span
                            aria-hidden
                            className={[
                              'grid h-4 w-4 place-items-center rounded-full border',
                              selected ? 'border-green' : 'border-hairline',
                            ].join(' ')}
                          >
                            {selected && (
                              <span className="h-2 w-2 rounded-full bg-green" />
                            )}
                          </span>
                        }
                        title={m.label}
                        subline={
                          m.queue_depth > 0
                            ? `${m.resolution_note.split('·')[0].trim()} · ${m.queue_depth} waiting`
                            : m.resolution_note.split('·')[0].trim()
                        }
                        right={
                          <span className="font-semibold text-text">
                            {formatMultiplier(m.multiplier_bps)}
                          </span>
                        }
                      />
                    </button>
                  );
                })}
              </div>

              {/* Speed sub-selector for chess */}
              {selectedMarket?.requires_speed && (
                <div className="mb-8 flex gap-2">
                  {selectedMarket.speeds.map((s) => (
                    <button
                      key={s}
                      onClick={() => setSpeed(s)}
                      className={[
                        'rounded-pill border px-3 py-1 text-xs font-semibold capitalize',
                        s === speed
                          ? 'border-green text-green'
                          : 'border-hairline text-text-secondary hover:text-text',
                      ].join(' ')}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}

              <h2 className="mb-2 text-sm font-semibold text-text-secondary">
                Waiting to play
              </h2>
              {waiting.data && waiting.data.waiting.length > 0 ? (
                waiting.data.waiting.map((w) => (
                  <ListRow
                    key={w.ticket_id}
                    title={w.username ?? 'Player'}
                    subline={`${w.market_label} · ${formatCurrency(w.entry_cents)}`}
                    right={
                      <PillButton
                        variant="secondary"
                        onClick={() => take.mutate(w.ticket_id)}
                        disabled={take.isPending || status?.status === 'matched'}
                      >
                        Match
                      </PillButton>
                    }
                  />
                ))
              ) : (
                <p className="py-4 text-sm text-text-secondary">
                  No one waiting yet — start a search and we&apos;ll pair you.
                </p>
              )}
            </>
          )}
        </div>

        <PlaySlip
          status={status}
          market={selectedMarket}
          entryCents={entryCents}
          presetsCents={markets?.entry_presets_cents ?? []}
          onSelectEntry={setEntryCents}
          onFindMatch={findMatch}
          finding={join.isPending}
        />
      </div>
    </div>
  );
}
