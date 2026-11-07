import { Link } from 'react-router-dom';

import { useMe, useSetDismissedChecklists } from '../hooks/useMe';
import { CHESS } from '../lib/games';
import { Card } from './ui/Card';

interface Step {
  done: boolean;
  label: string;
  to: string;
}

/**
 * The new-player checklist: link Lichess, then play a first match. Progress is
 * the server's `getting_started`; the X dismisses it server-side
 * (`dismissed_checklists`), so it stays gone across reloads and devices.
 */
export function GettingStarted() {
  const me = useMe();
  const setDismissed = useSetDismissedChecklists();

  const user = me.data?.user;
  const progress = me.data?.getting_started;
  if (!user || !progress || progress.complete) return null;
  if ((user.dismissed_checklists ?? []).includes(CHESS)) return null;

  const steps: Step[] = [
    { done: progress.linked_game, label: 'Link your Lichess account', to: '/profile' },
    { done: progress.placed_wager, label: 'Play your first match', to: '/play' },
  ];

  return (
    <div className="mb-6">
      <ChecklistCard steps={steps} onDismiss={() => setDismissed.mutate(CHESS)} />
    </div>
  );
}

function ChecklistCard({ steps, onDismiss }: { steps: Step[]; onDismiss: () => void }) {
  const done = steps.filter((s) => s.done).length;
  return (
    <Card className="relative p-4">
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss checklist"
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
        Get started{' '}
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
