import { Chess, type Square } from 'chess.js';

export interface Position {
  board: ReturnType<Chess['board']>;
  last: { from: Square; to: Square; san: string } | null;
  plies: number;
}

/** Replays the SAN list; stops at the first move it can't read rather than failing. */
export function replay(san: string[]): Position {
  const chess = new Chess();
  let last: Position['last'] = null;
  let plies = 0;
  for (const move of san) {
    try {
      const m = chess.move(move);
      last = { from: m.from, to: m.to, san: m.san };
      plies += 1;
    } catch {
      break;
    }
  }
  return { board: chess.board(), last, plies };
}
