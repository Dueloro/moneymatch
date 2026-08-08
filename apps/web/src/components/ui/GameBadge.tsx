import { gameMeta } from '../../lib/games';

/**
 * A compact game chip: the host game's icon + short name, tinted with its accent.
 *
 * Cards like the Activity rows and the rail's In play / Queue lists were
 * game-ambiguous — a "$10 · vs Alex" line never said whether it was Chess or CS2.
 * This names the game at a glance without re-introducing an accent per card the
 * way the browse grids deliberately dropped (the badge is the only coloured mark).
 */
export function GameBadge({
  game,
  fallbackName,
  className = '',
}: {
  game: string;
  fallbackName?: string;
  className?: string;
}) {
  const meta = gameMeta(game, fallbackName);
  const { Icon } = meta;
  return (
    <span
      className={[
        'inline-flex shrink-0 items-center gap-1 rounded-pill border border-hairline',
        'px-1.5 py-0.5 text-micro font-semibold text-text-secondary',
        className,
      ].join(' ')}
    >
      <span style={{ color: meta.accent }} aria-hidden>
        <Icon className="h-3 w-3" />
      </span>
      {meta.short}
    </span>
  );
}
