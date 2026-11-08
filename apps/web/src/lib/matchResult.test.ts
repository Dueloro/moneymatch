import { describe, expect, it } from 'vitest';

import { liveClocks, formatClock } from '../hooks/useLiveClocks';
import { replay } from '../components/play/board/replay';
import {
  formatDuration,
  lichessGameUrl,
  resultLine,
  settleSeconds,
  terminationPhrase,
} from './matchResult';

describe('match result copy', () => {
  it('names the real ending and never invents one', () => {
    expect(terminationPhrase('checkmate')).toBe('by checkmate');
    expect(terminationPhrase('time')).toBe('on time');
    expect(terminationPhrase('other')).toBeNull();
    expect(terminationPhrase(null)).toBeNull();
    expect(resultLine('you', 'resignation')).toBe('you won by resignation');
    expect(resultLine('opp', 'time')).toBe('you lost on time');
    expect(resultLine('opp')).toBe('you lost');
    expect(resultLine('draw', 'stalemate')).toBe('draw by stalemate');
    expect(resultLine('draw', 'draw')).toBe('draw');
  });

  it('claims a settle time only when both ends are known', () => {
    expect(settleSeconds('2026-01-01T10:00:00Z', '2026-01-01T10:00:38Z')).toBe(38);
    expect(settleSeconds(null, '2026-01-01T10:00:38Z')).toBeNull();
    expect(settleSeconds('2026-01-01T10:01:00Z', '2026-01-01T10:00:38Z')).toBeNull();
    expect(formatDuration(38)).toBe('38s');
    expect(formatDuration(125)).toBe('2m 05s');
    expect(formatDuration(3840)).toBe('1h 04m');
  });

  it('links to the game from your side', () => {
    expect(lichessGameUrl('abcd1234', 'black')).toBe(
      'https://lichess.org/abcd1234/black',
    );
    expect(lichessGameUrl('abcd1234', 'white')).toBe('https://lichess.org/abcd1234');
    expect(lichessGameUrl(null)).toBeNull();
  });
});

describe('live clocks', () => {
  const base = {
    kind: 'match' as const,
    format: 'chess' as const,
    status: 'live' as const,
    your_color: 'white' as const,
    clocks: { white_ms: 200_000, black_ms: 180_000 },
    last_move_at: '2026-01-01T10:00:00Z',
  };
  const t0 = Date.parse('2026-01-01T10:00:00Z');

  it('runs only the side to move, from the last move', () => {
    const c = liveClocks({ ...base, san: ['e4', 'e5'], turn: 'you' }, t0 + 4_000);
    expect(c).toEqual({ you: 196_000, opp: 180_000, running: 'you' });
  });

  it('holds both clocks before both sides have moved, and once it is over', () => {
    expect(
      liveClocks({ ...base, san: ['e4'], turn: 'opp' }, t0 + 4_000)?.running,
    ).toBeNull();
    expect(
      liveClocks(
        { ...base, status: 'finished', san: ['e4', 'e5'], turn: null },
        t0 + 9e9,
      )?.you,
    ).toBe(200_000);
  });

  it('formats like a chess clock', () => {
    expect(formatClock(245_000)).toBe('4:05');
    expect(formatClock(8_440)).toBe('0:08.4');
    expect(formatClock(3_725_000)).toBe('1:02:05');
  });
});

describe('board replay', () => {
  it('replays SAN to a position and stops at the first unreadable move', () => {
    const p = replay(['e4', 'e5', 'Nf3', 'Zz9', 'Nc6']);
    expect(p.plies).toBe(3);
    expect(p.last).toMatchObject({ from: 'g1', to: 'f3', san: 'Nf3' });
    expect(p.board[5][5]).toMatchObject({ type: 'n', color: 'w' });
  });
});
