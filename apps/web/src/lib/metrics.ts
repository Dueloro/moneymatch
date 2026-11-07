/**
 * Which stats are won by a *smaller* number. Mirrors `METRIC_LOWER_IS_BETTER`
 * in the API's `constants.py`; the server places and grades the bar, this only
 * words the card ("win in 14 moves or fewer" rather than "clear 14").
 */
const LOWER_IS_BETTER = new Set(['chess_moves']);

/**
 * Metrics that only count when you *won* the match. Mirrors
 * `METRIC_REQUIRES_WIN` in the API's `constants.py`. The server grades a loss
 * as a miss, so the card has to say win.
 */
const REQUIRES_WIN = new Set(['chess_moves']);

export function isLowerBetter(metric: string): boolean {
  return LOWER_IS_BETTER.has(metric);
}

export function requiresWin(metric: string): boolean {
  return REQUIRES_WIN.has(metric);
}

/** What clearing a bar takes, mid-sentence: "win in 14 moves or fewer". */
export function barPhrase(metric: string, bar: number): string {
  if (metric === 'chess_moves') return `win in ${bar} moves or fewer`;
  return `clear ${bar}`;
}

/** The pool card's heading for a bar. */
export function barTitle(metric: string, bar: number): string {
  const phrase = barPhrase(metric, bar);
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}

/** What a tournament metric ranks, in one sentence. Mirrors the aggregate
 * metrics in the API's `services/aggregate_metrics.py`. */
const TOURNAMENT_RULES: Record<string, string> = {
  chess_wins: 'Most wins across your games in the window ranks first.',
  chess_win_streak:
    'Longest run of wins in a row ranks first. A loss or a draw ends the run.',
  chess_fastest_win: 'Fewest moves in a single win ranks first.',
};

export function tournamentRule(metric: string, label: string): string {
  return TOURNAMENT_RULES[metric] ?? `Ranked by ${label.toLowerCase()} in the window.`;
}
