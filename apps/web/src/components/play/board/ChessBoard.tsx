import { useId, useMemo } from 'react';

import { PIECES } from './pieces';
import { replay } from './replay';

const FILES = 'abcdefgh';

const isLight = (file: number, rank: number) => (file + rank) % 2 === 1;

/**
 * A view-only board: SVG squares, the Cburnett pieces, and the last move washed
 * in cyan while the game is on (neutral once it's over). Orientation is yours.
 */
export default function ChessBoard({
  san,
  orientation = 'white',
  state = 'live',
}: {
  san: string[];
  orientation?: 'white' | 'black';
  state?: 'waiting' | 'live' | 'finished';
}) {
  const uid = useId().replace(/:/g, '');
  const { board, last, plies } = useMemo(() => replay(san), [san]);
  const flip = orientation === 'black';
  const at = (file: number, rank: number) => ({
    x: flip ? 7 - file : file,
    y: flip ? rank : 7 - rank,
  });

  const defs = useMemo(
    () =>
      Object.entries(PIECES)
        .map(
          ([k, inner]) =>
            `<symbol id="${uid}${k}" viewBox="0 0 45 45">${inner}</symbol>`,
        )
        .join(''),
    [uid],
  );

  const moveNo = Math.ceil(plies / 2);
  const label = last
    ? `Board after ${moveNo}${plies % 2 ? '.' : '...'} ${last.san}`
    : 'Board at the starting position';

  const lastSquares = last ? [last.from, last.to] : [];

  return (
    <svg
      viewBox="0 0 8 8"
      role="img"
      aria-label={label}
      className="block h-full w-full select-none"
      data-testid="chess-board"
      data-state={state}
    >
      <defs dangerouslySetInnerHTML={{ __html: defs }} />
      {Array.from({ length: 64 }, (_, i) => {
        const file = i % 8;
        const rank = Math.floor(i / 8);
        const { x, y } = at(file, rank);
        const light = isLight(file, rank);
        return (
          <rect
            key={i}
            x={x}
            y={y}
            width={1}
            height={1}
            style={{ fill: light ? 'var(--board-light)' : 'var(--board-dark)' }}
          />
        );
      })}
      {lastSquares.map((sq) => {
        const { x, y } = at(FILES.indexOf(sq[0]), Number(sq[1]) - 1);
        return (
          <rect
            key={`last-${sq}`}
            x={x}
            y={y}
            width={1}
            height={1}
            className="mm-last-move"
            style={{
              fill: state === 'finished' ? 'var(--text)' : 'var(--live)',
              opacity: state === 'finished' ? 0.16 : 0.34,
            }}
          />
        );
      })}
      {Array.from({ length: 8 }, (_, n) => {
        const bottomFile = flip ? 7 - n : n;
        const leftRank = flip ? n : 7 - n;
        const ink = (file: number, rank: number) =>
          isLight(file, rank) ? 'var(--board-dark)' : 'var(--board-light)';
        return (
          <g key={`c${n}`} aria-hidden style={{ fontSize: 0.2, fontWeight: 600 }}>
            <text
              x={n + 0.92}
              y={7.93}
              textAnchor="end"
              style={{ fill: ink(bottomFile, flip ? 7 : 0) }}
            >
              {FILES[bottomFile]}
            </text>
            <text x={0.06} y={n + 0.22} style={{ fill: ink(flip ? 7 : 0, leftRank) }}>
              {leftRank + 1}
            </text>
          </g>
        );
      })}
      {board.flatMap((row, r) =>
        row.map((piece, f) => {
          if (!piece) return null;
          const { x, y } = at(f, 7 - r);
          return (
            <use
              key={`${piece.square}`}
              href={`#${uid}${piece.color}${piece.type}`}
              x={x}
              y={y}
              width={1}
              height={1}
            />
          );
        }),
      )}
    </svg>
  );
}
