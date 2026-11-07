import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { LICHESS_A, availableCents, linkedA } from './fixtures';

test('join a pool through the confirm step, then leave with the balance untouched', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(!LICHESS_A, 'Set E2E_LICHESS_A to link a player.');

  const a = await linkedA();
  const before = await availableCents(a);
  const page = await signInAs(browser, a.authId, { path: '/pools' });

  const card = page
    .locator('.rounded-card')
    .filter({ has: page.getByRole('button', { name: 'Join pool' }) })
    .first();
  await card.getByRole('tab', { name: '$10.00' }).click();
  await expect(card.getByText(/platform fee/)).toBeVisible();

  await card.getByRole('button', { name: 'Join pool' }).click();
  await card.getByRole('button', { name: 'Confirm · $10.00' }).click();

  const queued = page
    .getByTestId('pool-status')
    .or(page.getByTestId('rail-pool-status'));
  const shown = queued.filter({ visible: true }).first();
  await expect(shown).toBeVisible();
  // Escrow waits for the room to form, so queuing holds nothing yet.
  expect(await availableCents(a)).toBe(before);

  await shown.getByRole('button', { name: 'Cancel' }).click();
  await expect(queued.filter({ visible: true })).toHaveCount(0);
  await expect.poll(() => availableCents(a)).toBe(before);

  await page.context().close();
});
