const LOWER_IS_BETTER = new Set(['chess_moves']);

const REQUIRES_WIN = new Set(['chess_moves']);

export function isLowerBetter(metric: string): boolean {
  return LOWER_IS_BETTER.has(metric);
}

export function requiresWin(metric: string): boolean {
  return REQUIRES_WIN.has(metric);
}

const UNITS: Record<string, string> = { chess_moves: 'moves' };

type Unit = { one: string; many: string } | { suffix: string };

const METRIC_UNITS: Record<string, Unit> = {
  chess_moves: { one: 'move', many: 'moves' },
  chess_fastest_win: { one: 'move', many: 'moves' },
  chess_wins: { one: 'win', many: 'wins' },
  chess_win_streak: { one: 'in a row', many: 'in a row' },
  chess_accuracy: { suffix: '%' },
};

/** A metric value as a bare number: integers stay integers, others trim to 1 dp. */
export function formatMetricNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString('en-US');
  return String(Math.round(value * 10) / 10);
}

/** "31 moves", "4 wins", "3 in a row", "86.4%"; a bare number if unknown. */
export function formatMetric(metric: string, value: number | null | undefined): string {
  if (value == null) return '-';
  const n = formatMetricNumber(value);
  const unit = METRIC_UNITS[metric];
  if (!unit) return n;
  if ('suffix' in unit) return `${n}${unit.suffix}`;
  return `${n} ${value === 1 ? unit.one : unit.many}`;
}

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

/** A pool card's title: difficulty, plus the rule the big figure can't carry. */
export function poolCardTitle(metric: string, difficulty: string): string {
  const d = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
  return requiresWin(metric) ? `${d} · wins only` : d;
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
