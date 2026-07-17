import { useState } from 'react';

import { useCreateChallenge } from '../hooks/useChallenges';
import { useMarkets, type MarketRow } from '../hooks/useMatchmaking';
import { formatCurrency } from '../lib/format';
import { PillButton } from './ui/PillButton';
import { PresetSelector } from './ui/PresetSelector';

const GAMES = [
  { id: 'cs2.faceit', label: 'CS2' },
  { id: 'chess.lichess', label: 'Chess' },
  { id: 'dota2.opendota', label: 'Dota 2' },
];

/**
 * Create a challenge (design p.3 "Invite friend"): pick game + market + entry,
 * then either challenge a specific friend or mint a shareable invite link. The
 * server owns entry cents and the friendly/pair-cap decision.
 */
export function ChallengeDialog({
  friend,
  onClose,
  onSent,
}: {
  friend?: { user_id: string; username: string | null } | null;
  onClose: () => void;
  onSent?: () => void;
}) {
  const [game, setGame] = useState(GAMES[0].id);
  const [marketKey, setMarketKey] = useState<string | null>(null);
  const [speed, setSpeed] = useState<string | null>(null);
  const [entryCents, setEntryCents] = useState<number | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: markets } = useMarkets(game);
  const create = useCreateChallenge();

  const market: MarketRow | null =
    markets?.markets.find((m) => m.key === marketKey) ?? markets?.markets[0] ?? null;
  const requiresSpeed = market?.requires_speed ?? false;
  const ready =
    market != null && entryCents != null && (!requiresSpeed || speed != null);

  function baseVars() {
    return {
      game,
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
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md rounded-2xl bg-panel p-6"
        data-testid="challenge-dialog"
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-text">
            {friend ? `Challenge ${friend.username ?? 'friend'}` : 'Invite a friend'}
          </h3>
          <PillButton variant="text" onClick={onClose}>
            Close
          </PillButton>
        </div>

        <div className="mb-4 flex gap-2">
          {GAMES.map((g) => (
            <button
              key={g.id}
              onClick={() => {
                setGame(g.id);
                setMarketKey(null);
                setSpeed(null);
              }}
              className={[
                'rounded-pill px-3 py-1 text-xs font-semibold transition',
                g.id === game
                  ? 'bg-text text-black'
                  : 'border border-hairline text-text-secondary hover:text-text',
              ].join(' ')}
            >
              {g.label}
            </button>
          ))}
        </div>

        {markets && !markets.linked ? (
          <p className="text-sm text-text-secondary">
            Link your {GAMES.find((g) => g.id === game)?.label} account first (Profile).
          </p>
        ) : (
          <>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
              Market
            </p>
            <div className="mb-4 max-h-40 overflow-y-auto">
              {markets?.markets.map((m) => (
                <label
                  key={`${m.key}-${m.label}`}
                  className="flex cursor-pointer items-center gap-3 border-b border-hairline py-2 last:border-b-0"
                >
                  <input
                    type="radio"
                    name="challenge-market"
                    checked={m.key === (market?.key ?? '')}
                    onChange={() => setMarketKey(m.key)}
                  />
                  <span className="text-sm text-text">{m.label}</span>
                </label>
              ))}
            </div>

            {requiresSpeed && (
              <div className="mb-4 flex flex-wrap gap-2">
                {(market?.speeds ?? []).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSpeed(s)}
                    className={[
                      'rounded-pill border px-3 py-1 text-xs transition',
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
                  Share this link — it&apos;s single-use and expires in 24h.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    value={inviteUrl}
                    className="min-w-0 flex-1 rounded-lg border border-hairline bg-bg px-3 py-2 text-xs text-text"
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
                Both stake {formatCurrency(entryCents!)} · winner takes the pot minus
                the platform fee.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
