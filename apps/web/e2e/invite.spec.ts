import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import { createInviteLink, lichessConfigured, linkedA, linkedB } from './fixtures';

/**
 * Invite link: A mints a $10 blitz challenge link, B opens the public preview,
 * accepts, both confirm, and both get the Lichess game set up for them.
 *
 * B is prepared by the fixture (onboarded + linked) because a Lichess handle
 * binds to one account, so a fresh signup per run cannot link the same handle
 * again. Settlement needs the game played on Lichess and is not driven here.
 */

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

  // --- B opens the preview and accepts. ------------------------------------ //
  const pageB = await signInAs(browser, b.authId, { path: invitePath });
  await expect(pageB.getByText(`${a.username} challenged you`)).toBeVisible();
  await expect(pageB.getByText('$10.00')).toBeVisible();
  await pageB.getByRole('button', { name: 'Accept challenge' }).click();
  await expect(pageB).toHaveURL(/\/play\?match=/);

  // --- Both confirm → the match goes live with a game link. ---------------- //
  const confirm = { name: /Confirm & stake \$10\.00/ };
  await pageB.getByRole('button', confirm).click();

  // A challenge match is not in the queue status, so A opens it by id.
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
