// AI recommendation signal for a joinable contest: red / yellow / green based on
// the player's skill vs. the contest. Heuristic today (a model swaps in later).

export type RecLevel = 'green' | 'yellow' | 'red' | 'gray';

export interface Recommendation {
  level: RecLevel;
  label: string;
  reason: string;
}

const GRAY: (game: string) => Recommendation = (game) => ({
  level: 'gray',
  label: 'No read',
  reason: `Link your ${game} account for a recommendation on this contest.`,
});

function levelFromEdge(edge: number): RecLevel {
  if (edge >= 0.12) return 'green';
  if (edge <= -0.12) return 'red';
  return 'yellow';
}

const LABEL: Record<RecLevel, string> = {
  green: 'Good pick',
  yellow: 'Toss-up',
  red: 'Long shot',
  gray: 'No read',
};

/** ELO win expectancy that A beats B. */
function expectancy(a: number, b: number): number {
  return 1 / (1 + Math.pow(10, (b - a) / 400));
}

/** Head-to-head: recommendation from ELO win-expectancy vs. the opponent. */
export function recommendVsOpponent(userRating: number, oppRating: number): Recommendation {
  const p = expectancy(userRating, oppRating);
  const level = levelFromEdge((p - 0.5) * 2);
  const pct = Math.round(p * 100);
  const reason =
    `AI estimates a ~${pct}% chance you win — your rating ${userRating} vs. the opponent's ${oppRating}. ` +
    (level === 'green' ? 'The matchup favors you.' : level === 'yellow' ? 'It’s close to even.' : 'The opponent is favored.');
  return { level, label: LABEL[level], reason };
}

/**
 * Pooled tournaments / solo: recommendation from the player's win rate for this
 * game vs. the stake (a rough proxy for field strength — higher stakes draw
 * tougher fields). ``winRate`` null ⇒ the game isn't linked, so no read.
 */
export function recommendVsField(
  gameName: string,
  winRate: number | null,
  entry: number,
  kind: 'pool' | 'tournament',
): Recommendation {
  if (winRate == null) return GRAY(gameName);
  const difficulty = Math.min(0.6, entry / 50); // $5 → 0.1, $25 → 0.5
  const edge = winRate - 0.5 - (difficulty - 0.2);
  const level = levelFromEdge(edge);
  const pct = Math.round(winRate * 100);
  const field = kind === 'pool' ? 'pool' : 'field';
  const reason =
    level === 'green'
      ? `AI likes this: your ~${pct}% win rate is strong for the ${field} at this stake.`
      : level === 'yellow'
        ? `AI says it's competitive: your ~${pct}% win rate is about even for this stake.`
        : `AI is cautious: this stake tends to draw a tougher ${field} than your ~${pct}% win rate.`;
  return { level, label: LABEL[level], reason };
}
