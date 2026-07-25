import { useLayoutEffect, useRef } from 'react';

import type { GameLink } from '../../hooks/useLinks';
import { gameMeta } from '../../lib/games';

/** Shared game switcher: icon + coloured name per game, recency-ordered by the
 * caller. Used by Head-to-Head, Solo Pools, and Tournament. Selecting a game
 * shuffles it to the front; `useFlipReorder` animates that swap so pills glide
 * to their new spot instead of jumping. */
export function GameTabs({
  games,
  selected,
  onSelect,
}: {
  games: GameLink[];
  selected: string | undefined;
  onSelect: (id: string) => void;
}) {
  const registerTab = useFlipReorder();

  if (games.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2" role="tablist">
      {games.map((g) => {
        const meta = gameMeta(g.game, g.display_name);
        const active = g.game === selected;
        const { Icon } = meta;
        return (
          <button
            key={g.game}
            ref={registerTab(g.game)}
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

/**
 * FLIP reordering: when the keyed children change order, glide each element
 * from where it was to where it now is. Returns a `ref` factory keyed by id.
 * Honours prefers-reduced-motion and no-ops where the Web Animations API is
 * unavailable (e.g. jsdom in tests).
 */
function useFlipReorder() {
  const els = useRef(new Map<string, HTMLElement>());
  const prevPos = useRef(new Map<string, { left: number; top: number }>());
  const anims = useRef(new Map<string, Animation>());

  // Runs after every commit: measure the settled layout and glide any pill
  // whose position changed since the last render. We read offsetLeft/offsetTop
  // (transform-immune) rather than getBoundingClientRect, so a re-render that
  // fires mid-glide measures the true destination and leaves the running
  // animation untouched instead of cancelling every pill on each commit.
  useLayoutEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    els.current.forEach((el, id) => {
      const next = { left: el.offsetLeft, top: el.offsetTop };
      const prev = prevPos.current.get(id);
      prevPos.current.set(id, next);
      if (!prev || reduce || typeof el.animate !== 'function') return;
      const dx = prev.left - next.left;
      const dy = prev.top - next.top;
      if (!dx && !dy) return;
      // Moved again — restart this pill's glide from the new offset.
      anims.current.get(id)?.cancel();
      anims.current.set(
        id,
        el.animate(
          [
            { transform: `translate(${dx}px, ${dy}px)` },
            { transform: 'translate(0px, 0px)' },
          ],
          { duration: 260, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' },
        ),
      );
    });
    // Drop bookkeeping for ids no longer rendered.
    prevPos.current.forEach((_, id) => {
      if (!els.current.has(id)) {
        prevPos.current.delete(id);
        anims.current.delete(id);
      }
    });
  });

  return (id: string) => (el: HTMLElement | null) => {
    if (el) els.current.set(id, el);
    else els.current.delete(id);
  };
}
