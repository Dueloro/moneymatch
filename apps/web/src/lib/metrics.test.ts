import { describe, expect, it } from 'vitest';

import { barPhrase, barTitle, tournamentRule } from './metrics';

describe('barPhrase / barTitle', () => {
  it('words moves-to-win as a win in that many moves or fewer', () => {
    expect(barPhrase('chess_moves', 28)).toBe('win in 28 moves or fewer');
    expect(barTitle('chess_moves', 28)).toBe('Win in 28 moves or fewer');
  });

  it('words a higher-is-better stat as a number to clear', () => {
    expect(barPhrase('chess_accuracy', 85)).toBe('clear 85');
    expect(barTitle('chess_accuracy', 85)).toBe('Clear 85');
  });
});

describe('tournamentRule', () => {
  it('says what each chess metric ranks', () => {
    expect(tournamentRule('chess_wins', 'Total wins')).toMatch(/most wins/i);
    expect(tournamentRule('chess_win_streak', 'Longest win streak')).toMatch(
      /in a row.*loss or a draw ends/i,
    );
    expect(tournamentRule('chess_fastest_win', 'Fastest win')).toMatch(
      /fewest moves in a single win/i,
    );
  });

  it('falls back to the label for a metric it does not know', () => {
    expect(tournamentRule('new_metric', 'New Metric')).toBe(
      'Ranked by new metric in the window.',
    );
  });
});
