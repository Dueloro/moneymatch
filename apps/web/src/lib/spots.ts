// Deterministic "spots filled" for a joinable card. Pools/tournaments form via
// matchmaking, so there's no literal roster to read; this gives each card a
// stable, plausible fill (always at least one open seat so the card is joinable)
// derived from its key, so the same card shows the same number across renders.
//
// DEMO-ONLY. This is a synthetic count, not a real roster. It must only be shown
// in the demo, never in authenticated production — call sites gate it on
// `isDemo` and omit the `filled` prop otherwise (see WagerCard). Showing it to
// real users would be fabricated social proof on a money product.

function hash(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * A stable filled-seat count in [floor(capacity/2), capacity − 1] for the given
 * key — populated enough to feel live, never full (so "Join" always works).
 */
export function filledSpots(key: string, capacity: number): number {
  if (capacity <= 1) return 0;
  const min = Math.floor(capacity / 2);
  const span = capacity - 1 - min; // inclusive upper bound is capacity - 1
  if (span <= 0) return min;
  return min + (hash(key) % (span + 1));
}
