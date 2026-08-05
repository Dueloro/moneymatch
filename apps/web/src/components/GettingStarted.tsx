import { Link } from 'react-router-dom';

import { useMe } from '../hooks/useMe';
import { Card } from './ui/Card';

/**
 * First-match funnel nudge: a compact checklist that walks a new player from
 * picking games to linking an account to placing their first wager. Renders
 * nothing once every step is done (or before /me loads).
 */
export function GettingStarted() {
  const me = useMe();
  const gs = me.data?.getting_started;
  if (!gs || gs.complete) return null;

  const steps = [
    { done: gs.picked_games, label: 'Pick the games you play', to: '/profile' },
    { done: gs.linked_game, label: 'Link a game account', to: '/profile' },
    { done: gs.placed_wager, label: 'Join your first pool', to: '/pools' },
  ];

  const done = steps.filter((s) => s.done).length;

  return (
    <Card className="mb-6 p-4">
      <p className="text-sm font-semibold text-text">
        Getting started{' '}
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
