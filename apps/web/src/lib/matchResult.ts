import type { MatchView, Termination } from '../hooks/useMatchmaking';

export type MatchOutcome = 'win' | 'loss' | 'draw' | 'refund';

/** How a settled head-to-head ended for the viewer; null while it is still on. */
export function matchOutcome(match: MatchView): MatchOutcome | null {
  if (match.state === 'PUSHED') return 'draw';
  if (match.state === 'CANCELED') return 'refund';
  if (match.state !== 'SETTLED') return null;
  const you = match.players.find((p) => p.is_you);
  return you && match.winner_user_id === you.user_id ? 'win' : 'loss';
}

/**
 * The real ending, as Lichess reported it: "by checkmate", "on time". Null when
 * Lichess didn't say, so we never invent one.
 */
export function terminationPhrase(
  termination: Termination | null | undefined,
): string | null {
  switch (termination) {
    case 'checkmate':
      return 'by checkmate';
    case 'resignation':
      return 'by resignation';
    case 'time':
      return 'on time';
    case 'stalemate':
      return 'by stalemate';
    case 'abandoned':
      return 'by abandonment';
    case 'aborted':
      return 'game aborted';
    default:
      return null;
  }
}

/** "you won by resignation", "draw by stalemate", "you lost on time". */
export function resultLine(
  result: 'you' | 'opp' | 'draw' | null | undefined,
  termination?: Termination | null,
): string {
  const how = terminationPhrase(termination);
  if (result === 'draw')
    return termination === 'stalemate' ? 'draw by stalemate' : 'draw';
  const base =
    result === 'you' ? 'you won' : result === 'opp' ? 'you lost' : 'game over';
  return how && result ? `${base} ${how}` : base;
}

/** "38s", "2m 05s", "1h 04m". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`;
}

/** Seconds from the game ending on Lichess to our settlement, when both are known. */
export function settleSeconds(
  gameEndedAt: string | null | undefined,
  resolvedAt: string | null | undefined,
): number | null {
  if (!gameEndedAt || !resolvedAt) return null;
  const ended = Date.parse(gameEndedAt);
  const settled = Date.parse(resolvedAt);
  if (!Number.isFinite(ended) || !Number.isFinite(settled) || settled < ended)
    return null;
  return (settled - ended) / 1000;
}

/** The game on Lichess, from your side of the board. */
export function lichessGameUrl(
  gameId: string | null | undefined,
  color?: string | null,
): string | null {
  if (!gameId) return null;
  return `https://lichess.org/${gameId}${color === 'black' ? '/black' : ''}`;
}
