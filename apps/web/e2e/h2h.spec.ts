import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { lichessConfigured, linkedA, linkedB } from './fixtures';

test('two linked players queue blitz at $10, match, confirm, and get the game', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(
    !lichessConfigured(),
    'Set E2E_LICHESS_A and E2E_LICHESS_B to link players.',
  );
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

  for (const page of [pageA, pageB]) {
    await expect(page.getByRole('link', { name: /Go play your game/ })).toHaveAttribute(
      'href',
      /lichess\.org\//,
    );
  }

  await pageA.context().close();
  await pageB.context().close();
});
