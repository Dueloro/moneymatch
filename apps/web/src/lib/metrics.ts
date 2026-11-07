const LOWER_IS_BETTER = new Set(['chess_moves']);

const REQUIRES_WIN = new Set(['chess_moves']);

export function isLowerBetter(metric: string): boolean {
  return LOWER_IS_BETTER.has(metric);
}

export function requiresWin(metric: string): boolean {
  return REQUIRES_WIN.has(metric);
}

const UNITS: Record<string, string> = { chess_moves: 'moves' };

export function metricUnit(metric: string): string | undefined {
  return UNITS[metric];
}

export function barPhrase(metric: string, bar: number): string {
  const unit = metricUnit(metric);
  const n = unit ? `${bar} ${unit}` : String(bar);
  if (isLowerBetter(metric)) {
    return `${requiresWin(metric) ? 'win in' : 'get'} ${n} or fewer`;
  }
  return requiresWin(metric) ? `win with ${n} or more` : `clear ${n}`;
}

export function barTitle(metric: string, bar: number): string {
  const phrase = barPhrase(metric, bar);
  return phrase.charAt(0).toUpperCase() + phrase.slice(1);
}

const TOURNAMENT_RULES: Record<string, string> = {
  chess_wins: 'Most wins across your games in the window ranks first.',
  chess_win_streak:
    'Longest run of wins in a row ranks first. A loss or a draw ends the run.',
  chess_fastest_win: 'Fewest moves in a single win ranks first.',
};

export function tournamentRule(metric: string, label: string): string {
  return TOURNAMENT_RULES[metric] ?? `Ranked by ${label.toLowerCase()} in the window.`;
}
