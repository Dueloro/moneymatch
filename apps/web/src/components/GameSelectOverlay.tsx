import type { CSSProperties } from 'react';
import { useState } from 'react';

import {
  SELECT_FILL,
  availabilityFor,
  gameMeta,
  onboardingGames,
  type OnboardingContext,
} from '../lib/games';

/**
 * Full-screen game-selection overlay shown after sign-up. Four rounded-square
 * tiles (Chess, CS2, PUBG, Dota 2), each a toggle that fills a lime circle when
 * selected. Availability (color / grayscale, selectable / disabled) is driven
 * entirely by `../lib/games` for the given `context`, so demo vs. production is a
 * config change, not a UI fork.
 *
 * Accessibility: each tile is a real `<button>` with `aria-pressed`, keyboard
 * focus + activation, a visible lime focus ring, and a label that names the game,
 * its badge, and its state. Locked tiles are `aria-disabled` with a caption/title
 * explaining why. Hover scale respects `prefers-reduced-motion` (motion-safe).
 */
export function GameSelectOverlay({
  context,
  initialSelected,
  onConfirm,
  busy = false,
  title = 'Choose your games',
  subtitle = 'Pick what you want to play. You can change this any time in your profile.',
  confirmLabel = 'Continue',
}: {
  context: OnboardingContext;
  initialSelected?: string[];
  onConfirm: (games: string[]) => void;
  busy?: boolean;
  title?: string;
  subtitle?: string;
  confirmLabel?: string;
}) {
  const games = onboardingGames();
  const required = games.filter((g) => g.preselected).map((g) => g.id);

  const [selected, setSelected] = useState<string[]>(() => {
    const seed = new Set([...(initialSelected ?? []), ...required]);
    // Only keep games that are actually selectable in this context.
    return [...seed].filter((id) => availabilityFor(id, context).selectable);
  });

  const toggle = (id: string) => {
    const cfg = games.find((g) => g.id === id);
    if (!cfg || cfg.preselected) return; // required — cannot be turned off
    if (!availabilityFor(id, context).selectable) return;
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const canProceed = selected.length > 0 && !busy;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-bg px-6 py-10"
    >
      <div className="text-center">
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="mt-1 max-w-sm text-sm text-text-secondary">{subtitle}</p>
      </div>

      <div className="grid w-full max-w-md grid-cols-2 gap-4">
        {games.map((cfg) => {
          const meta = gameMeta(cfg.id);
          const avail = availabilityFor(cfg.id, context);
          const active = selected.includes(cfg.id);
          const disabled = !avail.selectable;
          const { Icon } = meta;
          const reason =
            cfg.badge === 'SOON' ? 'Coming soon' : 'Available after launch';
          const label = [
            meta.name,
            cfg.badge ? `(${cfg.badge})` : null,
            disabled ? 'coming soon' : active ? 'selected' : 'not selected',
          ]
            .filter(Boolean)
            .join(', ');

          return (
            <div key={cfg.id} className="flex flex-col items-center gap-3">
              <button
                type="button"
                aria-pressed={active}
                aria-disabled={disabled || undefined}
                aria-label={label}
                title={disabled ? reason : undefined}
                disabled={disabled}
                onClick={() => toggle(cfg.id)}
                style={{ '--tw-ring-color': SELECT_FILL } as CSSProperties}
                className={[
                  'relative grid aspect-square w-full place-items-center rounded-card border transition',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
                  disabled
                    ? 'cursor-not-allowed border-hairline opacity-40 grayscale'
                    : 'border-hairline hover:border-text-secondary/60 motion-safe:hover:scale-105',
                  !avail.color && !disabled ? 'grayscale' : '',
                  active ? 'bg-panel-raised' : '',
                ].join(' ')}
              >
                <span
                  style={{
                    color: avail.color ? meta.accent : 'var(--text-secondary)',
                  }}
                >
                  <Icon className="h-14 w-14" />
                </span>
                {cfg.badge && (
                  <span className="absolute bottom-2 rounded-pill bg-panel px-2 py-0.5 text-micro font-semibold uppercase tracking-wide text-text-secondary">
                    {cfg.badge}
                  </span>
                )}
              </button>

              <span
                aria-hidden
                className="grid h-6 w-6 place-items-center rounded-full border transition"
                style={
                  active
                    ? { backgroundColor: SELECT_FILL, borderColor: SELECT_FILL }
                    : { borderColor: 'var(--hairline)' }
                }
              >
                {active && <CheckIcon className="h-3.5 w-3.5 text-bg" />}
              </span>

              {disabled && (
                <span className="text-micro text-text-secondary">{reason}</span>
              )}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        disabled={!canProceed}
        onClick={() => onConfirm(selected)}
        className="w-full max-w-md rounded-pill bg-text px-6 py-3 text-sm font-semibold text-bg transition disabled:opacity-40"
      >
        {confirmLabel}
      </button>
    </div>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <path
        d="M5 12.5 10 17l9-10"
        stroke="currentColor"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
