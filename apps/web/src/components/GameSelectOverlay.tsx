import {
  IconChessKnight,
  IconCrosshair,
  IconParachute,
  IconSwords,
  type Icon,
} from '@tabler/icons-react';
import type { CSSProperties } from 'react';
import { useState } from 'react';

import {
  SELECT_FILL,
  availabilityFor,
  gameMeta,
  isBetaGated,
  onboardingGames,
  type OnboardingContext,
} from '../lib/games';

/**
 * Full-screen game-selection overlay shown after sign-up — the product's front
 * door. Four game tiles, each a card with an accent-tinted glow behind an
 * original filled game motif that lifts to a lime-ringed "selected" state.
 *
 * Selection rules (context-driven, config in `../lib/games`):
 *  - Live (Chess) and BETA (CS2, PUBG) tiles are freely selectable/deselectable.
 *    Nothing is force-checked or locked-on; Chess starts checked as a default.
 *  - "Coming soon" (Dota 2) is non-interactive in production; demo keeps it
 *    selectable (the original demo exception), just visually muted.
 *  - Continue is gated by two independent, distinctly-messaged checks: at least
 *    one game must be selected (empty), and any selected BETA game requires beta
 *    access, which no production user has yet (see `isBetaGated` / `hasBetaAccess`).
 *
 * Accessibility: each tile is a real `<button>` with `aria-pressed`, keyboard
 * focus + activation, a visible lime focus ring, and a label naming the game,
 * its badge, and its state. Only genuinely non-interactive tiles are
 * `aria-disabled`. The validation message is a `role="alert"`. Hover lift/scale
 * respects `prefers-reduced-motion`; the selected ring is static state.
 */
export function GameSelectOverlay({
  context,
  initialSelected,
  onConfirm,
  busy = false,
  title = 'What games do you play?',
  subtitle = 'Pick the games you want to wager on.',
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
  const defaults = games.filter((g) => g.preselected).map((g) => g.id);

  const [selected, setSelected] = useState<string[]>(() => {
    const seed = new Set([...(initialSelected ?? []), ...defaults]);
    // Only keep games that are actually selectable in this context.
    return [...seed].filter((id) => availabilityFor(id, context).selectable);
  });

  const toggle = (id: string) => {
    if (!availabilityFor(id, context).selectable) return; // non-interactive tile
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  // Two independent validation states, each with its own message.
  const betaSelected = selected.filter((id) => isBetaGated(id, context));
  const emptyError = selected.length === 0;
  const betaError = betaSelected.length > 0;

  const validationMessage = betaError
    ? betaGateMessage(betaSelected.map((id) => gameMeta(id).short))
    : emptyError
      ? 'Pick at least one game to continue.'
      : null;

  const canProceed = !busy && !emptyError && !betaError;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="mm-grid-surface fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-bg px-6 py-10"
    >
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1.5 max-w-sm text-sm text-text-secondary">{subtitle}</p>
      </div>

      <div className="grid w-full max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        {games.map((cfg) => {
          const meta = gameMeta(cfg.id);
          const avail = availabilityFor(cfg.id, context);
          const active = selected.includes(cfg.id);
          const disabled = !avail.selectable;
          const muted = disabled || !avail.color;
          const Art = TILE_ART[cfg.id];
          const displayName = TILE_LABEL[cfg.id] ?? meta.name;
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
            <div key={cfg.id} className="flex flex-col items-center">
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
                  'group relative flex aspect-square w-full flex-col items-center justify-center overflow-hidden rounded-card border bg-panel',
                  'transition-[transform,border-color] duration-200 ease-[cubic-bezier(0.2,0.8,0.2,1)]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
                  disabled
                    ? 'cursor-not-allowed border-hairline'
                    : 'border-hairline hover:border-line-strong motion-safe:hover:-translate-y-1 motion-safe:hover:scale-[1.03] motion-safe:active:translate-y-0 motion-safe:active:scale-[0.99]',
                  active ? 'bg-panel-raised' : '',
                ].join(' ')}
              >
                {/* Accent glow, brighter on hover/active, muted when locked. */}
                <span
                  aria-hidden
                  className={[
                    'pointer-events-none absolute inset-0 transition-opacity duration-200',
                    muted
                      ? 'opacity-40 grayscale'
                      : 'motion-safe:group-hover:opacity-90',
                  ].join(' ')}
                  style={{
                    background: `radial-gradient(120% 92% at 50% 4%, ${withAlpha(
                      meta.accent,
                      active ? 0.24 : 0.15,
                    )} 0%, ${withAlpha(meta.accent, 0.04)} 44%, transparent 74%)`,
                  }}
                />

                {/* Hover sheen: a soft diagonal light sweep (skip locked tiles).
                    Gated by motion-safe, so reduced-motion users never see it. */}
                {!disabled && (
                  <span
                    aria-hidden
                    className="pointer-events-none absolute inset-0 -translate-x-[120%] skew-x-12 bg-gradient-to-r from-transparent via-white/10 to-transparent transition-transform duration-700 ease-out motion-safe:group-hover:translate-x-[120%]"
                  />
                )}

                {/* Icon: subtle hover lift + scale (parallax). */}
                <span
                  aria-hidden
                  className={[
                    'relative transition-transform duration-200 ease-[cubic-bezier(0.2,0.8,0.2,1)]',
                    'motion-safe:group-hover:-translate-y-0.5 motion-safe:group-hover:scale-110',
                    muted ? 'opacity-55 grayscale' : '',
                  ].join(' ')}
                  style={{ color: muted ? 'var(--text-secondary)' : meta.accent }}
                >
                  {Art ? (
                    <Art className="h-12 w-12 sm:h-14 sm:w-14" stroke={1.75} />
                  ) : (
                    <meta.Icon className="h-12 w-12 sm:h-14 sm:w-14" />
                  )}
                </span>

                {/* Selection ring — always mounted; fades in on select and back
                    out on deselect (clean reverse, not an instant vanish). */}
                <span
                  aria-hidden
                  className={[
                    'pointer-events-none absolute inset-0 rounded-card transition-opacity duration-300 ease-out',
                    active ? 'opacity-100' : 'opacity-0',
                  ].join(' ')}
                  style={{
                    boxShadow: `inset 0 0 0 1.5px ${SELECT_FILL}, 0 10px 30px -16px ${withAlpha(
                      SELECT_FILL,
                      0.6,
                    )}`,
                  }}
                />

                {/* Corner check — pops in with a slight overshoot on select and
                    scales back out on deselect. Always mounted so both directions
                    animate; under reduced-motion it just appears/disappears. */}
                <span
                  aria-hidden
                  className={[
                    'absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full shadow-sm',
                    'transition-[transform,opacity] duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)]',
                    active ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                  ].join(' ')}
                  style={{ backgroundColor: SELECT_FILL }}
                >
                  <CheckIcon className="h-3 w-3 text-bg" />
                </span>

                {/* Badge in-tile (bottom-left, clear of the top-right check) so
                    the full name below never has to share a line with it. */}
                {cfg.badge && (
                  <span className="absolute bottom-2 left-2 rounded-pill bg-panel/80 px-2 py-0.5 text-micro font-semibold uppercase tracking-wide text-text-secondary backdrop-blur-sm">
                    {cfg.badge}
                  </span>
                )}

                {/* Locked-but-designed: a lock affordance, not a broken asset. */}
                {disabled && (
                  <span
                    aria-hidden
                    className="absolute bottom-2 right-2 text-text-tertiary"
                  >
                    <LockIcon className="h-4 w-4" />
                  </span>
                )}
              </button>

              {/* Full game name below the tile (item 1). aria-hidden: the button's
                  aria-label already names the game and its state, so this is
                  visual reinforcement only and must not double-announce. */}
              <span
                aria-hidden
                className={[
                  'mt-2.5 text-center text-xs font-medium',
                  muted ? 'text-text-secondary' : 'text-text',
                ].join(' ')}
              >
                {displayName}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex w-full max-w-2xl flex-col gap-3">
        {validationMessage && (
          <p role="alert" className="text-center text-xs text-red">
            {validationMessage}
          </p>
        )}
        <button
          type="button"
          disabled={!canProceed}
          onClick={() => canProceed && onConfirm(selected)}
          className="w-full rounded-pill bg-action px-6 py-3 text-sm font-semibold text-bg transition disabled:opacity-40"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}

/** "CS2 is …" / "CS2 and PUBG are …" — grammatical, names the gated picks. */
function betaGateMessage(shorts: string[]): string {
  const names =
    shorts.length <= 1
      ? (shorts[0] ?? 'This game')
      : `${shorts.slice(0, -1).join(', ')} and ${shorts[shorts.length - 1]}`;
  const verb = shorts.length > 1 ? 'are' : 'is';
  return `${names} ${verb} only available in an invite-only beta.`;
}

/** `#rrggbb` → `rgba(r,g,b,a)` for accent glows. Passes non-hex values through. */
function withAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/**
 * Overlay-local tile motifs.
 *
 * ⚠️ PLACEHOLDER ICONS — NOT FINAL. These are licensed stock icons from Tabler
 * Icons (@tabler/icons-react, MIT license — free for commercial use, no
 * attribution required: https://github.com/tabler/tabler-icons/blob/main/LICENSE).
 * They were chosen as a genre-appropriate, stylistically-consistent set (one
 * 2px line-art family) to look more professional than the earlier hand-drawn
 * attempt — none reproduce trademarked game logos, only generic genre marks
 * (chess piece / tactical crosshair / parachute airdrop / crossed swords).
 *
 * TODO(brand-icons): before launch, commission or design BESPOKE per-game icons
 * matching Money Match's own visual identity, and remove this Tabler dependency.
 * "Good enough for now" is not "done" — this is a stopgap, not the final art.
 *
 * Kept here (not in the shared `gameMeta`) so this restyle doesn't change the
 * compact icons used elsewhere (game tabs, invite cards).
 */
const TILE_ART: Record<string, Icon> = {
  'chess.lichess': IconChessKnight,
  'cs2.steam': IconCrosshair, // tactical shooter
  'pubg.steam': IconParachute, // battle-royale airdrop
  'dota2.opendota': IconSwords, // MOBA
};

/**
 * Full game names for the visible tile label (item 1). Kept separate from
 * `gameMeta.name`, which stays the a11y/aria source of truth (and what tests
 * assert), so the visible label can read the full "PUBG: Battlegrounds" without
 * changing the accessible name.
 */
const TILE_LABEL: Record<string, string> = {
  'chess.lichess': 'Chess',
  'cs2.steam': 'Counter-Strike 2',
  'pubg.steam': 'PUBG: Battlegrounds',
  'dota2.opendota': 'Dota 2',
};

function LockIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <rect
        x="5"
        y="10.5"
        width="14"
        height="9.5"
        rx="2"
        fill="currentColor"
        opacity="0.9"
      />
      <path
        d="M8 10.5V8a4 4 0 0 1 8 0v2.5"
        stroke="currentColor"
        strokeWidth={1.8}
        fill="none"
      />
    </svg>
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
