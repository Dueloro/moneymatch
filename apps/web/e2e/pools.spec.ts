import { test } from '@playwright/test';

/**
 * Solo pools: four similar-rated linked players join Medium `chess_moves`, a
 * room forms, each wins their next Lichess game in N moves or fewer, and the
 * pool splits from server-fetched games.
 */

test('four similar players form a Medium moves-to-win room and split the pool', () => {
  test.skip(
    true,
    'Needs four linked Lichess accounts of similar rating and finished wins on Lichess; the API has no seam to seed either.',
  );
});
