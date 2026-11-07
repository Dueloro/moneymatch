import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { ModeSwitcher } from '../components/ModeSwitcher';
import { PlaySlip } from '../components/play/PlaySlip';
import { CardGrid } from '../components/ui/CardGrid';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { ListRow } from '../components/ui/ListRow';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { SkeletonList } from '../components/ui/Skeleton';
import { WagerCard } from '../components/ui/WagerCard';
import { dashless, formatCurrency } from '../lib/format';
import { CHESS, gameMeta } from '../lib/games';
import { platformFeeNote } from '../lib/rake';
import {
  prizeForEntry,
  useJoinQueue,
  useMarkets,
  useMatch,
  useQueueStatus,
  useTakeWaiting,
  useWaiting,
  type MarketRow,
  type QueueStatus,
} from '../hooks/useMatchmaking';

/** The market's headline resolution note (the part before the first separator). */
function marketHeadline(market: MarketRow): string {
  return dashless(market.resolution_note).split('·')[0]?.trim() ?? '';
}

/** Default speed for a speed-gated market: the middle option if present. */
function defaultSpeed(market: MarketRow): string | undefined {
  if (!market.requires_speed) return undefined;
  return market.speeds[1] ?? market.speeds[0] ?? undefined;
}

// States where the slip should show the confirm/active card for a deep-linked
// match; a terminal match falls through to the normal slip (reachable via Activity).
const DEEP_LINK_STATES = new Set(['PENDING', 'ACTIVE', 'AWAITING_RESULT']);

export function PlayPage() {
  usePageTitle('Head to head');
  const {
    data: markets,
    isLoading: marketsLoading,
    isError: marketsError,
    refetch: refetchMarkets,
  } = useMarkets(CHESS);

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
          can_cancel: false,
        }
      : liveStatus;

  const waiting = useWaiting(CHESS);
  const join = useJoinQueue();
  const take = useTakeWaiting();

  const [speedByMarket, setSpeedByMarket] = useState<Record<string, string>>({});

  const linked = markets?.linked ?? false;
  const gameName = gameMeta(CHESS).name;
  const presets = markets?.entry_presets_cents ?? [];
  // A match is in flight: surface the slip and freeze new joins.
  const inFlight = status?.status === 'searching' || status?.status === 'matched';

  const openMarkets = markets?.markets ?? [];
  const hasResults = openMarkets.length > 0 && presets.length > 0;

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="play">
            You play one game of chess on Lichess against an opponent at your skill
            level, for the same stake. We read the result from Lichess and the winner
            takes the pot. A draw refunds both stakes.
          </HowItWorks>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      {header}

      {marketsLoading ? (
        <SkeletonList rows={3} />
      ) : marketsError ? (
        <ErrorState
          title="Could not load markets"
          subline="The connection dropped. Try again."
          onRetry={() => refetchMarkets()}
        />
      ) : !linked ? (
        <EmptyState
          title="Link your Lichess account"
          subline="Head to head settles from your Lichess games, so we need to know which account is yours."
          action={
            <Link to="/profile">
              <PillButton>Link Lichess</PillButton>
            </Link>
          }
        />
      ) : (
        <>
          {inFlight && (
            <div className="mb-8">
              <PlaySlip status={status} />
            </div>
          )}

          {!inFlight && (
            <>
              <SectionHeader level="page">Head to head</SectionHeader>

              {hasResults ? (
                <CardGrid count={openMarkets.length}>
                  {openMarkets.map((m) => {
                    const speed = speedByMarket[m.key] ?? defaultSpeed(m);
                    const key = `${m.key}:${speed ?? ''}`;
                    return (
                      <WagerCard
                        key={key}
                        gameName={gameName}
                        tag={speed?.toUpperCase()}
                        title={m.label}
                        subtitle={marketHeadline(m)}
                        speedOptions={m.requires_speed ? m.speeds : undefined}
                        selectedSpeed={speed}
                        onSpeedChange={
                          m.requires_speed
                            ? (s) =>
                                setSpeedByMarket((prev) => ({ ...prev, [m.key]: s }))
                            : undefined
                        }
                        entryOptions={presets}
                        payoutFor={(entry) => prizeForEntry(entry, m.multiplier_bps)}
                        payoutLabel="You win"
                        // Pot is both stakes (1v1); the fee is what the winner
                        // doesn't take. Matches PlaySlip's confirm-step RakeLine.
                        feeNote={(entry) =>
                          platformFeeNote(
                            entry * 2 - prizeForEntry(entry, m.multiplier_bps),
                          )
                        }
                        oneVsOne
                        buttonLabel="Find match"
                        joining={join.isPending}
                        onJoin={(entry) =>
                          join.mutate({
                            game: CHESS,
                            market: m.key,
                            speed,
                            entry_preset_cents: entry,
                          })
                        }
                      />
                    );
                  })}
                </CardGrid>
              ) : (
                <EmptyState
                  title="No head to head markets right now"
                  subline="Check back shortly."
                />
              )}
            </>
          )}

          {waiting.data && waiting.data.waiting.length > 0 && (
            <section className="mt-10">
              <SectionHeader
                level="section"
                hint="Take one of these and you skip the queue."
              >
                Waiting to play
              </SectionHeader>
              {waiting.data.waiting.map((w) => (
                <ListRow
                  key={w.ticket_id}
                  left={
                    <span
                      aria-hidden
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-live"
                    />
                  }
                  title={w.username ?? 'Player'}
                  subline={`${w.market_label} · ${formatCurrency(w.entry_cents)}`}
                  right={
                    <PillButton
                      variant="secondary"
                      onClick={() => take.mutate(w.ticket_id)}
                      disabled={take.isPending || inFlight}
                    >
                      Match
                    </PillButton>
                  }
                />
              ))}
            </section>
          )}
        </>
      )}
    </div>
  );
}
