import { useCallback, useEffect, useMemo, useState } from 'react';

import { useLinks, type GameLink } from './useLinks';

// The current game and the recency order are shared across Head-to-Head, Solo
// Pools, and Tournament (persisted), so a pick carries between sections and the
// most recently used games shuffle to the front of the switcher.
const ORDER_KEY = 'mm.games.order';
const SELECTED_KEY = 'mm.games.selected';

function readList(key: string): string[] {
  try {
    const v = window.localStorage.getItem(key);
    const parsed = v ? (JSON.parse(v) as unknown) : [];
    return Array.isArray(parsed)
      ? (parsed.filter((x) => typeof x === 'string') as string[])
      : [];
  } catch {
    return [];
  }
}

function readStr(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function useGameSelection(): {
  games: GameLink[];
  selected: string | undefined;
  select: (id: string) => void;
} {
  const { data } = useLinks();
  const games = useMemo(() => data?.games ?? [], [data]);
  const [order, setOrder] = useState<string[]>(() => readList(ORDER_KEY));
  const [selected, setSelected] = useState<string | null>(() => readStr(SELECTED_KEY));

  // Default the selection once games load (first linked, else first game).
  useEffect(() => {
    if (games.length === 0) return;
    const ids = games.map((g) => g.game);
    if (!selected || !ids.includes(selected)) {
      const firstLinked = games.find((g) => g.status === 'LINKED');
      setSelected((firstLinked ?? games[0]).game);
    }
  }, [games, selected]);

  useEffect(() => {
    if (selected) {
      try {
        window.localStorage.setItem(SELECTED_KEY, selected);
      } catch {
        /* ignore */
      }
    }
  }, [selected]);

  useEffect(() => {
    try {
      window.localStorage.setItem(ORDER_KEY, JSON.stringify(order));
    } catch {
      /* ignore */
    }
  }, [order]);

  const select = useCallback((id: string) => {
    setSelected(id);
    setOrder((prev) => [id, ...prev.filter((x) => x !== id)]);
  }, []);

  // Recency-first: games in `order` (that still exist), then the rest.
  const orderedIds = [
    ...order.filter((id) => games.some((g) => g.game === id)),
    ...games.map((g) => g.game).filter((id) => !order.includes(id)),
  ];
  const orderedGames = orderedIds
    .map((id) => games.find((g) => g.game === id))
    .filter((g): g is GameLink => g != null);

  return { games: orderedGames, selected: selected ?? undefined, select };
}
