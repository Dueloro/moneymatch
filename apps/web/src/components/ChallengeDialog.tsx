import { useState } from 'react';

import { useCreateChallenge } from '../hooks/useChallenges';
import { prizeForEntry, useMarkets, type MarketRow } from '../hooks/useMatchmaking';
import { formatPoints } from '../lib/format';
import { CHESS } from '../lib/games';
import { Dialog } from './ui/Dialog';
import { RadioRow } from './ui/Field';
import { PillButton } from './ui/PillButton';
import { PresetSelector } from './ui/PresetSelector';

function feeLine(entry: number, multiplierBps: number): string {
  const prize = prizeForEntry(entry, multiplierBps);
  return `Both stake ${formatPoints(entry)} · winner takes ${formatPoints(prize)} · fee ${formatPoints(entry * 2 - prize)}`;
}

/** The server owns entry cents and the friendly/pair-cap decision. */
export function ChallengeDialog({
  friend,
  onClose,
  onSent,
}: {
  friend?: { user_id: string; username: string | null } | null;
  onClose: () => void;
  onSent?: () => void;
}) {
  const [marketKey, setMarketKey] = useState<string | null>(null);
  const [speed, setSpeed] = useState<string | null>(null);
  const [entryCents, setEntryCents] = useState<number | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: markets } = useMarkets(CHESS);
  const create = useCreateChallenge();

  const market: MarketRow | null =
    markets?.markets.find((m) => m.key === marketKey) ?? markets?.markets[0] ?? null;
  const requiresSpeed = market?.requires_speed ?? false;
  const ready =
    market != null && entryCents != null && (!requiresSpeed || speed != null);

  function baseVars() {
    return {
      game: CHESS,
      market: market!.key,
      entry_preset_cents: entryCents!,
      ...(requiresSpeed && speed ? { speed } : {}),
    };
  }

  async function sendDirect() {
    if (!ready || !friend) return;
    await create.mutateAsync({ challengee_id: friend.user_id, ...baseVars() });
    onSent?.();
    onClose();
  }

  async function createInvite() {
    if (!ready) return;
    const res = await create.mutateAsync(baseVars());
    if (res.invite_path) {
      setInviteUrl(`${window.location.origin}${res.invite_path}`);
    }
  }

  async function copyLink() {
    if (!inviteUrl) return;
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
  }

  return (
    <Dialog
      title={friend ? `Challenge ${friend.username ?? 'friend'}` : 'Invite a friend'}
      onClose={onClose}
      testId="challenge-dialog"
    >
      <div className="overflow-y-auto px-5 pb-5 pt-4 md:px-6 md:pb-6">
        {markets && !markets.linked ? (
          <p className="text-sm text-text-secondary">
            Link your Lichess account first (Profile).
          </p>
        ) : (
          <>
            {(markets?.markets.length ?? 0) > 1 && (
              <>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                  Market
                </p>
                <div className="mb-4 max-h-40 overflow-y-auto">
                  {markets?.markets.map((m) => (
                    <RadioRow
                      key={`${m.key}-${m.label}`}
                      name="challenge-market"
                      checked={m.key === (market?.key ?? '')}
                      onSelect={() => setMarketKey(m.key)}
                    >
                      {m.label}
                    </RadioRow>
                  ))}
                </div>
              </>
            )}

            {requiresSpeed && (
              <div className="mb-4 flex flex-wrap gap-2">
                {(market?.speeds ?? []).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSpeed(s)}
                    className={[
                      'rounded-pill border px-3 py-1 text-xs transition',
                      s === speed
                        ? 'border-line-strong bg-panel-raised text-text'
                        : 'border-hairline text-text-secondary hover:text-text',
                    ].join(' ')}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Entry
            </p>
            <PresetSelector
              presetsCents={markets?.entry_presets_cents ?? []}
              selectedCents={entryCents}
              onSelect={setEntryCents}
            />

            {create.error && (
              <p className="mt-3 text-xs text-red">{(create.error as Error).message}</p>
            )}

            {inviteUrl ? (
              <div className="mt-5">
                <p className="mb-2 text-xs text-text-secondary">
                  Share this link. It&apos;s single-use and expires in 24h.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    value={inviteUrl}
                    className="min-w-0 flex-1 rounded-inset border border-hairline bg-bg px-3 py-2 text-xs text-text"
                  />
                  <PillButton onClick={copyLink}>
                    {copied ? 'Copied' : 'Copy'}
                  </PillButton>
                </div>
              </div>
            ) : (
              <div className="mt-5 flex gap-2">
                {friend && (
                  <PillButton
                    disabled={!ready || create.isPending}
                    onClick={sendDirect}
                  >
                    {create.isPending ? 'Sending…' : 'Send challenge'}
                  </PillButton>
                )}
                <PillButton
                  variant="outline"
                  disabled={!ready || create.isPending}
                  onClick={createInvite}
                >
                  Copy invite link
                </PillButton>
              </div>
            )}

            {ready && market && (
              <p className="mt-3 text-xs text-text-secondary">
                {feeLine(entryCents!, market.multiplier_bps)}
              </p>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
