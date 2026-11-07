import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { LICHESS_A, availableCents, linkedA } from './fixtures';

/**
 * Tournaments, one player: the fee is shown before committing, joining puts you
 * in the field queue, and leaving before the field forms costs nothing: the
 * entry is only escrowed once the field forms.
 *
 * A formed field and its payout need a full field of linked players with games
 * played on Lichess, which the API has no seam to seed.
 */

test('join a tournament, then leave with the balance untouched', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(!LICHESS_A, 'Set E2E_LICHESS_A to link a player.');

  const a = await linkedA();
  const before = await availableCents(a);
  const page = await signInAs(browser, a.authId, { path: '/tournament' });

  const card = page
    .locator('.rounded-card')
    .filter({ has: page.getByRole('button', { name: 'Join tournament' }) })
    .first();
  await card.getByRole('tab', { name: '$10.00' }).click();
  await expect(card.getByText(/platform fee/)).toBeVisible();
  await card.getByRole('button', { name: 'Join tournament' }).click();

  const queued = page
    .getByTestId('tournament-status')
    .or(page.getByTestId('rail-tournament-status'));
  // Shown inline below xl and in the side rail from xl up; use whichever is on screen.
  const shown = queued.filter({ visible: true }).first();
  await expect(shown).toBeVisible();
  // Escrow waits for the field to form, so queuing holds nothing yet.
  expect(await availableCents(a)).toBe(before);

  await shown.getByRole('button', { name: 'Cancel' }).click();
  await expect(queued.filter({ visible: true })).toHaveCount(0);
  await expect.poll(() => availableCents(a)).toBe(before);

  await page.context().close();
});
