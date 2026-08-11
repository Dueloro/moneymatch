import { useState } from 'react';

import {
  useGcHealth,
  useSteamLoginUrl,
  useSubmitShareCode,
  type SubmittedMatch,
} from '../../hooks/useCs2';
import { Card } from '../ui/Card';
import { PillButton } from '../ui/PillButton';

/**
 * Paste the share code from your last CS2 match.
 *
 * This is the whole CS2 intake path. CS2 has no public per-match stats API, so
 * the share code is the only artifact a player can copy out of the game, and
 * pasting one is what turns a match you played into a wager that settles.
 *
 * The copy tells you where to find it, because the most common failure is
 * looking in the wrong place. Second most common: playing Casual, which
 * produces no share code at all.
 */
export function SubmitMatchCard({ linked = true }: { linked?: boolean }) {
  const [code, setCode] = useState('');
  const [result, setResult] = useState<SubmittedMatch | null>(null);
  const submit = useSubmitShareCode();
  const { data: health } = useGcHealth();
  const { data: loginUrl } = useSteamLoginUrl();

  if (!linked) {
    return (
      <Card className="p-5" data-testid="cs2-submit-card">
        <h3 className="text-sm font-semibold text-text">Submit a CS2 match</h3>
        <p className="mt-2 text-xs text-text-secondary">
          Sign in through Steam first. Your SteamID is what ties a match to you.
        </p>
        {loginUrl && (
          <a
            href={loginUrl}
            className="mt-3 inline-block rounded-pill bg-action px-4 py-2 text-sm font-semibold text-bg"
          >
            Sign in through Steam
          </a>
        )}
      </Card>
    );
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setResult(null);
    const match = await submit.mutateAsync(code.trim());
    setResult(match);
    setCode('');
  }

  return (
    <Card className="p-5" data-testid="cs2-submit-card">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-text">Submit a CS2 match</h3>
        {health && !health.ready && (
          <span className="text-xs text-text-tertiary" data-testid="gc-offline">
            Match service offline
          </span>
        )}
      </div>

      <p className="mt-2 text-xs text-text-secondary">
        In CS2: <span className="text-text">Watch</span> →{' '}
        <span className="text-text">Your Matches</span> → copy the share code for the
        match you just played.
      </p>

      <form onSubmit={onSubmit} className="mt-3 flex flex-col gap-2">
        <label htmlFor="cs2-share-code" className="sr-only">
          CS2 share code
        </label>
        <input
          id="cs2-share-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx"
          autoComplete="off"
          spellCheck={false}
          className="w-full rounded-inset border border-hairline bg-panel px-3 py-2 font-mono text-sm text-text placeholder:text-text-tertiary"
        />
        <div className="flex items-center gap-2">
          <PillButton
            type="submit"
            disabled={submit.isPending || code.trim().length < 10}
          >
            {submit.isPending ? 'Checking…' : 'Submit match'}
          </PillButton>
          {/* Only Premier, Competitive and Wingman generate a code at all. */}
          <span className="text-xs text-text-tertiary">
            Premier, Competitive or Wingman only
          </span>
        </div>
      </form>

      {submit.isError && (
        <p
          className="mt-3 text-xs text-red"
          role="alert"
          data-testid="cs2-submit-error"
        >
          {(submit.error as Error).message}
        </p>
      )}

      {result && (
        <div
          className="mt-4 border-t border-hairline pt-3"
          data-testid="cs2-submit-result"
        >
          <p className="text-xs text-text-secondary">
            {result.map_name ?? 'Match'} · {result.score} · {result.rounds} rounds
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {Object.entries(result.your_metrics).map(([metric, value]) => (
              <span key={metric} className="tabular-nums text-text">
                {LABELS[metric] ?? metric}{' '}
                <span className="font-semibold">{value}</span>
              </span>
            ))}
          </div>
          {result.demo_expired && (
            <p className="mt-2 text-xs text-text-tertiary">
              The demo file has expired, which is normal after about a month. The
              scoreboard is what settles a wager, so this still counts.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

const LABELS: Record<string, string> = {
  cs2_kd_ratio: 'K/D',
  cs2_headshot_pct: 'HS%',
  cs2_kills: 'Kills',
};
