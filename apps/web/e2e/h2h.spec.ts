import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { lichessConfigured, linkedA, linkedB } from './fixtures';

/**
 * Head to head, through the UI: two linked players queue the same blitz market
 * at $10, get paired on rating, both confirm, and the slip hands each of them
 * the Lichess game set up for them.
 *
 * Settlement is not driven here: it needs the game played to a result
 * on Lichess, and the API has no seam to finish one. The money math is covered
 * by the API suite (`apps/api/tests/test_settlement_worker.py`).
 */

test('two linked players queue blitz at $10, match, confirm, and get the game', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(
    !lichessConfigured(),
    'Set E2E_LICHESS_A and E2E_LICHESS_B to link players.',
  );
  // The rating band widens for up to a minute before two distant ratings pair.
  test.setTimeout(150_000);

  const a = await linkedA();
  const b = await linkedB();

  const pageA = await signInAs(browser, a.authId, { path: '/play' });
  const pageB = await signInAs(browser, b.authId, { path: '/play' });

  for (const page of [pageA, pageB]) {
    await page.getByRole('button', { name: 'blitz' }).click();
    await page.getByRole('tab', { name: '$10.00' }).click();
    await page.getByRole('button', { name: 'Find match' }).click();
  }
  await expect(
    pageA.getByText('Searching…').or(pageA.getByText('Opponent found')),
  ).toBeVisible();

  const confirm = { name: /Confirm & stake \$10\.00/ };
  await expect(pageA.getByRole('button', confirm)).toBeVisible({ timeout: 90_000 });
  await expect(pageB.getByRole('button', confirm)).toBeVisible({ timeout: 30_000 });

  await pageA.getByRole('button', confirm).click();
  await pageB.getByRole('button', confirm).click();

  // Active: each side gets the seat link for the Lichess game set up for them.
  for (const page of [pageA, pageB]) {
    await expect(page.getByRole('link', { name: /Go play your game/ })).toHaveAttribute(
      'href',
      /lichess\.org\//,
    );
  }

  await pageA.context().close();
  await pageB.context().close();
});
