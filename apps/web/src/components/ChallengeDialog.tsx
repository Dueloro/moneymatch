import { useEffect, useRef, useState } from 'react';

import { useCreateChallenge } from '../hooks/useChallenges';
import { prizeForEntry, useMarkets, type MarketRow } from '../hooks/useMatchmaking';
import { copyText } from '../lib/clipboard';
import { CHESS } from '../lib/games';
import { middlePreset } from '../lib/stake';
import { defaultSpeed } from '../lib/timeControl';
import { PointsFigure } from './ui/AmountText';
import { Dialog } from './ui/Dialog';
import { RadioRow } from './ui/Field';
import { PayoutSummary, StakeChoice, TimeControlChoice } from './ui/MatchChoices';
import { PillButton } from './ui/PillButton';

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
  const [speedPick, setSpeed] = useState<string | null>(null);
  const [entryPick, setEntry] = useState<number | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timer = useRef<number>();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const { data: markets } = useMarkets(CHESS);
  const create = useCreateChallenge();

  const market: MarketRow | null =
    markets?.markets.find((m) => m.key === marketKey) ?? markets?.markets[0] ?? null;
  const speeds = market?.requires_speed ? market.speeds : [];
  const speed =
    speedPick && speeds.includes(speedPick) ? speedPick : defaultSpeed(speeds);
  const presets = markets?.entry_presets_cents ?? [];
  const entry =
    entryPick != null && presets.includes(entryPick)
      ? entryPick
      : presets.length
        ? middlePreset(presets)
        : null;
  const ready = market != null && entry != null && (speeds.length === 0 || !!speed);
  const prize = ready ? prizeForEntry(entry, market.multiplier_bps) : 0;
  const busy = create.isPending;

  function baseVars() {
    return {
      game: CHESS,
      market: market!.key,
      entry_preset_cents: entry!,
      ...(speeds.length && speed ? { speed } : {}),
    };
  }

  async function sendDirect() {
    if (!ready || !friend) return;
    await create.mutateAsync({ challengee_id: friend.user_id, ...baseVars() });
    onSent?.();
    onClose();
  }

  async function copyLink(url: string) {
    if (!(await copyText(url))) return;
    setCopied(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 2000);
  }

  async function createInvite() {
    if (!ready) return;
    const res = inviteUrl ? null : await create.mutateAsync(baseVars());
    const url =
      inviteUrl ??
      (res?.invite_path ? `${window.location.origin}${res.invite_path}` : null);
    if (!url) return;
    setInviteUrl(url);
    await copyLink(url);
  }

  const name = friend?.username ?? 'friend';

  return (
    <Dialog
      title={friend ? `Challenge ${name}` : 'Invite a friend'}
      onClose={onClose}
      testId="challenge-dialog"
    >
      {markets && !markets.linked ? (
        <p className="px-5 pb-6 pt-4 text-sm text-text-secondary md:px-6">
          Link your Lichess account first (Profile).
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-5 overflow-y-auto px-5 py-5 md:px-6">
            {(markets?.markets.length ?? 0) > 1 && (
              <div>
                <p className="label-neutral mb-2">Market</p>
                <div className="max-h-40 overflow-y-auto">
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
              </div>
            )}

            {speed && speeds.length > 1 && (
              <TimeControlChoice
                speeds={speeds}
                clocks={market?.clocks}
                value={speed}
                onChange={setSpeed}
              />
            )}

            {entry != null && (
              <StakeChoice presets={presets} value={entry} onChange={setEntry} />
            )}

            {create.error && (
              <p className="text-xs text-red">{(create.error as Error).message}</p>
            )}

            {inviteUrl && (
              <div>
                <p className="mb-2 text-xs text-text-secondary">
                  Share this link. It&apos;s single-use and expires in 24h.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    aria-label="Invite link"
                    value={inviteUrl}
                    className="min-w-0 flex-1 rounded-inset border border-hairline bg-bg px-3 py-2 text-xs text-text"
                  />
                  <span role="status" className="w-14 text-xs text-green">
                    {copied ? 'Copied' : ''}
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4 border-t border-hairline px-5 py-5 md:px-6">
            {ready && <PayoutSummary prize={prize} fee={entry * 2 - prize} />}
            <div className="flex flex-col gap-2 md:flex-row-reverse">
              {friend && (
                <PillButton
                  size="lg"
                  className="mm-glow md:flex-1"
                  disabled={!ready || busy}
                  onClick={sendDirect}
                >
                  {busy ? (
                    'Sending…'
                  ) : (
                    <>
                      Challenge {name}
                      {ready && (
                        <>
                          {' '}
                          · <PointsFigure cents={entry} />
                        </>
                      )}
                    </>
                  )}
                </PillButton>
              )}
              <PillButton
                size="lg"
                variant={friend ? 'outline' : 'primary'}
                className={friend ? 'md:flex-1' : 'mm-glow flex-1'}
                disabled={!ready || busy}
                onClick={createInvite}
              >
                {copied ? 'Copied' : 'Copy invite link'}
              </PillButton>
            </div>
          </div>
        </>
      )}
    </Dialog>
  );
}
