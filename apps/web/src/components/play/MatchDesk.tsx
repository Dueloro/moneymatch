import { useState } from 'react';

import { prizeForEntry, type MarketRow } from '../../hooks/useMatchmaking';
import type { ProfileSnapshot } from '../../hooks/useLinks';
import { middlePreset } from '../../lib/stake';
import { defaultSpeed, ratingForSpeed, speedName } from '../../lib/timeControl';
import { ConnectLichessButton, NotAffiliated } from '../ConnectLichess';
import { PointsFigure } from '../ui/AmountText';
import { Card } from '../ui/Card';
import { PillButton } from '../ui/PillButton';
import { PayoutSummary, StakeChoice, TimeControlChoice } from '../ui/MatchChoices';

const CHOICE_KEY = 'mm.h2h.desk';

function readChoice(): { speed?: string; entry?: number } {
  try {
    return JSON.parse(window.localStorage.getItem(CHOICE_KEY) ?? '{}') ?? {};
  } catch {
    return {};
  }
}

function saveChoice(choice: { speed?: string; entry: number }) {
  try {
    window.localStorage.setItem(CHOICE_KEY, JSON.stringify(choice));
  } catch {
    /* per-viewer convenience only */
  }
}

/** The head-to-head desk: time control, stake, your rating, the payout and fee, one action. */
export function MatchDesk({
  market,
  presets,
  profile,
  username,
  joining,
  onFind,
}: {
  market: MarketRow;
  presets: number[];
  profile: ProfileSnapshot | null | undefined;
  username: string | null | undefined;
  joining: boolean;
  onFind: (choice: { speed?: string; entry: number }) => void;
}) {
  const [saved] = useState(readChoice);
  const speeds = market.requires_speed ? market.speeds : [];
  const [speedPick, setSpeed] = useState(saved.speed);
  const [entryPick, setEntry] = useState(saved.entry);

  const speed =
    speedPick && speeds.includes(speedPick) ? speedPick : defaultSpeed(speeds);
  const entry =
    entryPick != null && presets.includes(entryPick)
      ? entryPick
      : middlePreset(presets);

  const prize = prizeForEntry(entry, market.multiplier_bps);
  const fee = entry * 2 - prize;
  const rating = ratingForSpeed(profile, speed);
  const name = profile?.username ?? username ?? 'You';

  return (
    <Card as="section" aria-label="Find a head to head match" data-testid="match-desk">
      <div className="flex items-center gap-3 border-b border-hairline px-5 py-4 md:px-6">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-panel-raised text-sm font-bold text-text">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-text">{name}</p>
          <p className="text-xs text-text-secondary">
            Matched with someone at your skill level
          </p>
        </div>
        {rating && (
          <div className="shrink-0 text-right" data-testid="desk-rating">
            <p className="num text-xl font-semibold text-text">
              {rating.rating}
              {rating.provisional ? '?' : ''}
            </p>
            <p className="label-neutral">
              {rating.from && rating.from !== speed
                ? `From ${rating.from}`
                : `${speed ? speedName(speed) : 'Lichess'} rating`}
            </p>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-5 px-5 py-5 md:px-6">
        {speed && speeds.length > 1 && (
          <TimeControlChoice
            speeds={speeds}
            clocks={market.clocks}
            value={speed}
            onChange={(s) => {
              setSpeed(s);
              saveChoice({ speed: s, entry });
            }}
          />
        )}

        <StakeChoice
          presets={presets}
          value={entry}
          onChange={(cents) => {
            setEntry(cents);
            saveChoice({ speed, entry: cents });
          }}
        />
      </div>

      <div className="flex flex-col gap-4 border-t border-hairline px-5 py-5 md:flex-row md:items-end md:justify-between md:px-6">
        <PayoutSummary prize={prize} fee={fee} />
        <PillButton
          className="mm-glow md:min-w-64"
          size="lg"
          disabled={joining || entry == null}
          onClick={() => onFind({ speed, entry })}
        >
          {joining ? (
            'Finding…'
          ) : (
            <>
              Find match ·{' '}
              <span className="num">
                <PointsFigure cents={entry} />
              </span>
            </>
          )}
        </PillButton>
      </div>
    </Card>
  );
}

/** The desk before Lichess is linked: same frame, one action. */
export function LinkLichessDesk() {
  return (
    <Card as="section" data-testid="match-desk-unlinked">
      <div className="flex flex-col items-start gap-4 px-5 py-6 md:flex-row md:items-center md:justify-between md:px-6">
        <div>
          <p className="text-base font-semibold text-text">Link Lichess to play</p>
          <p className="mt-1 max-w-md text-sm text-text-secondary">
            Games settle from your Lichess account, and your rating there sets who
            you&apos;re matched with.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-1 md:items-end">
          <ConnectLichessButton size="lg" />
          <NotAffiliated />
        </div>
      </div>
    </Card>
  );
}
