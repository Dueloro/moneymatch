import { Link } from 'react-router-dom';

import { useMe } from '../hooks/useMe';

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

  return (
    <div className="mb-6 rounded-2xl border border-hairline bg-panel p-4">
      <p className="label-mono">Getting started</p>
      <ul className="mt-2 flex flex-col gap-2">
        {steps.map((step) => (
          <li key={step.label} className="flex items-center gap-3 text-sm">
            <span
              aria-hidden
              className={[
                'grid h-5 w-5 shrink-0 place-items-center rounded-full border text-bg',
                step.done ? 'border-green bg-green' : 'border-hairline',
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
              <span className="text-text-secondary line-through">{step.label}</span>
            ) : (
              <Link to={step.to} className="text-text hover:underline">
                {step.label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
