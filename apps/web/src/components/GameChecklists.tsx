import { Link } from 'react-router-dom';

import { useLinks } from '../hooks/useLinks';
import { useMe, useSetDismissedChecklists } from '../hooks/useMe';
import { gameMeta } from '../lib/games';
import { Card } from './ui/Card';

interface Step {
  done: boolean;
  label: string;
  to: string;
}

/**
 * Per-game onboarding checklist for the Play tab. One card per game in the
 * player's active set that hasn't been dismissed (and isn't already complete),
 * walking them from linking that game's account to their first contest. The X
 * dismisses the card server-side (`dismissed_checklists`), so it stays gone
 * across reload and devices — never localStorage.
 *
 * Both steps are per-game: linked from `/links`, first-contest from the account's
 * `contested_games` (the games it has actually entered a contest for) — so a
 * chess veteran who just added CS2 sees CS2's contest step still open.
 */
export function GameChecklists() {
  const me = useMe();
  const links = useLinks();
  const setDismissed = useSetDismissedChecklists();

  const user = me.data?.user;
  if (!user) return null;

  const active = user.active_games ?? [];
  const dismissed = new Set(user.dismissed_checklists ?? []);
  const contested = new Set(me.data?.contested_games ?? []);
  const linkedGames = new Set(
    (links.data?.games ?? []).filter((g) => g.status === 'LINKED').map((g) => g.game),
  );

  const cards = active
    .filter((game) => !dismissed.has(game))
    .map((game) => {
      const name = gameMeta(game).name;
      const steps: Step[] = [
        {
          done: linkedGames.has(game),
          label: `Link your ${name} account`,
          to: '/profile',
        },
        {
          done: contested.has(game),
          label: `Join your first ${name} contest`,
          to: '/pools',
        },
      ];
      return { game, name, steps };
    })
    .filter((c) => !c.steps.every((s) => s.done));

  if (cards.length === 0) return null;

  // The hook computes the full server list from the freshest cache, so we only
  // pass the one game being dismissed (no stale-closure append here).
  const dismiss = (game: string) => setDismissed.mutate(game);

  return (
    <div className="mb-6 flex flex-col gap-3">
      {cards.map((c) => (
        <ChecklistCard
          key={c.game}
          name={c.name}
          steps={c.steps}
          onDismiss={() => dismiss(c.game)}
        />
      ))}
    </div>
  );
}

function ChecklistCard({
  name,
  steps,
  onDismiss,
}: {
  name: string;
  steps: Step[];
  onDismiss: () => void;
}) {
  const done = steps.filter((s) => s.done).length;
  return (
    <Card className="relative p-4">
      <button
        type="button"
        onClick={onDismiss}
        aria-label={`Dismiss ${name} checklist`}
        className="absolute right-3 top-3 grid h-6 w-6 place-items-center rounded-full text-text-tertiary transition hover:bg-panel hover:text-text focus-visible:outline-none focus-visible:ring-2"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
          <path
            d="M6 6l12 12M18 6L6 18"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
          />
        </svg>
      </button>

      <p className="text-sm font-semibold text-text">
        Get started with {name}{' '}
        <span className="font-normal text-text-tertiary">
          {done} of {steps.length}
        </span>
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {steps.map((step) => (
          <li key={step.label} className="flex items-center gap-3 text-sm">
            <span
              aria-hidden
              className={[
                'grid h-5 w-5 shrink-0 place-items-center rounded-full border text-bg',
                step.done ? 'border-action bg-action' : 'border-hairline',
              ].join(' ')}
            >
              {step.done && (
                <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" aria-hidden>
                  <path
                    d="M5 12.5 10 17l9-10"
                    stroke="currentColor"
                    strokeWidth={3}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </span>
            {step.done ? (
              <span className="text-text-tertiary line-through">{step.label}</span>
            ) : (
              <Link
                to={step.to}
                className="text-text underline-offset-4 hover:underline"
              >
                {step.label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
