import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { createInviteLink, lichessConfigured, linkedA, linkedB } from './fixtures';

test('invite link → preview → accept → both confirm → game link', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(
    !lichessConfigured(),
    'Set E2E_LICHESS_A and E2E_LICHESS_B to link players.',
  );

  const a = await linkedA();
  const b = await linkedB();
  const invitePath = await createInviteLink(a, { speed: 'blitz', entryCents: 1000 });
  expect(invitePath).toContain('/i/');

  const pageB = await signInAs(browser, b.authId, { path: invitePath });
  await expect(pageB.getByText(`${a.username} challenged you`)).toBeVisible();
  await expect(pageB.getByText('$10.00')).toBeVisible();
  await pageB.getByRole('button', { name: 'Accept challenge' }).click();
  await expect(pageB).toHaveURL(/\/play\?match=/);

  const confirm = { name: /Confirm & stake \$10\.00/ };
  await pageB.getByRole('button', confirm).click();

  const matchPath = new URL(pageB.url()).pathname + new URL(pageB.url()).search;
  const pageA = await signInAs(browser, a.authId, { path: matchPath });
  await pageA.getByRole('button', confirm).click();

  for (const page of [pageA, pageB]) {
    await expect(page.getByRole('link', { name: /Go play your game/ })).toHaveAttribute(
      'href',
      /lichess\.org\//,
    );
  }

  await pageA.context().close();
  await pageB.context().close();
});
