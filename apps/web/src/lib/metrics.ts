/**
 * Which stats are won by a *smaller* number.
 *
 * Mirrors `METRIC_LOWER_IS_BETTER` in the API's `constants.py`. The server is
 * the authority: it places the bar at µ − k·σ and grades `value <= bar`. This
 * copy exists only so the card can word itself correctly ("win in 14 moves or
 * fewer" rather than "clear 14"), and should be replaced by a `lower_is_better`
 * field on the markets response the next time the API client is regenerated.
 */
const LOWER_IS_BETTER = new Set(['chess_moves']);

/**
 * Metrics that only count when you *won* the match. Mirrors
 * `METRIC_REQUIRES_WIN` in the API's `constants.py`.
 *
 * This has to reach the card. "14 moves or fewer" reads as though a short game
 * of any kind counts, and a player who loses in ten would fairly expect to have
 * cleared it. The server grades a loss as a miss, so the card has to say win.
 */
const REQUIRES_WIN = new Set(['chess_moves']);

export function isLowerBetter(metric: string): boolean {
  return LOWER_IS_BETTER.has(metric);
}

export function requiresWin(metric: string): boolean {
  return REQUIRES_WIN.has(metric);
}

/** The headline on a contest card: what you have to do to clear the bar. */
export function barHeadline(metric: string, bar: number, unit: string): string {
  const n = Number.isInteger(bar) ? bar : bar.toFixed(2);
  if (requiresWin(metric)) return `Win in ${n} ${unit} or fewer`;
  return isLowerBetter(metric) ? `${n} ${unit} or fewer` : `${n} ${unit} or better`;
}
