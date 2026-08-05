import { gameMeta, isComingSoon } from '../lib/games';
import { useLinks } from '../hooks/useLinks';
import { SkeletonList } from './ui/Skeleton';

/**
 * Controlled multi-select grid of the game catalog. Tapping a card toggles the
 * game in/out of the play set; coming-soon games are selectable too (they show
 * a "Soon" badge and light up in the switcher once their adapter lands). Used by
 * onboarding and anywhere a quick play-set edit is useful.
 */
export function GameSelectGrid({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const links = useLinks();

  if (links.isLoading) {
    return <SkeletonList rows={2} />;
  }
  if (links.isError || !links.data) {
    return <p className="text-sm text-red">Couldn't load games.</p>;
  }

  const toggle = (game: string) => {
    onChange(
      selected.includes(game)
        ? selected.filter((g) => g !== game)
        : [...selected, game],
    );
  };

  return (
    <div className="grid grid-cols-2 gap-3">
      {links.data.games.map((g) => {
        const meta = gameMeta(g.game, g.display_name);
        const active = selected.includes(g.game);
        const soon = isComingSoon(g.game);
        const { Icon } = meta;
        return (
          <button
            key={g.game}
            type="button"
            role="checkbox"
            aria-checked={active}
            onClick={() => toggle(g.game)}
            style={active ? { borderColor: meta.accent } : undefined}
            className={[
              'relative flex flex-col items-start gap-3 rounded-card border p-4 text-left transition',
              active
                ? 'bg-panel-raised'
                : 'border-hairline hover:border-text-secondary/60',
            ].join(' ')}
          >
            <span
              className="absolute right-3 top-3 grid h-5 w-5 place-items-center rounded-full border text-bg transition"
              style={
                active
                  ? { backgroundColor: meta.accent, borderColor: meta.accent }
                  : { borderColor: 'var(--hairline)' }
              }
              aria-hidden
            >
              {active && <CheckIcon className="h-3 w-3" />}
            </span>
            <span style={{ color: meta.accent }}>
              <Icon className="h-6 w-6" />
            </span>
            <span className="text-sm font-semibold">{meta.name}</span>
            {soon && (
              <span className="rounded-pill bg-panel px-2 py-0.5 text-micro font-semibold uppercase tracking-wide text-text-secondary">
                Soon
              </span>
            )}
          </button>
        );
      })}
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
