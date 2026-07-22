import type { GameLink } from '../../hooks/useLinks';
import { gameMeta } from '../../lib/games';

/** Shared game switcher: icon + coloured name per game, recency-ordered by the
 * caller. Used by Head-to-Head, Solo Pools, and Tournament. */
export function GameTabs({
  games,
  selected,
  onSelect,
}: {
  games: GameLink[];
  selected: string | undefined;
  onSelect: (id: string) => void;
}) {
  if (games.length === 0) return null;

  return (
    <div className="mb-6 flex flex-wrap gap-2" role="tablist">
      {games.map((g) => {
        const meta = gameMeta(g.game, g.display_name);
        const active = g.game === selected;
        const { Icon } = meta;
        return (
          <button
            key={g.game}
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(g.game)}
            style={active ? { borderColor: meta.accent } : undefined}
            className={[
              'inline-flex items-center gap-2 rounded-pill border px-4 py-1.5 text-sm font-semibold transition',
              active
                ? 'bg-panel-raised text-text'
                : 'border-hairline text-text-secondary hover:text-text',
            ].join(' ')}
          >
            <span style={{ color: meta.accent }}>
              <Icon className="h-4 w-4" />
            </span>
            {meta.name}
          </button>
        );
      })}
    </div>
  );
}
