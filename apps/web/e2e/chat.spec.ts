import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';

/**
 * Inbox messaging (14-inbox-messaging), driven as a real user pair:
 * A befriends B → A messages B from the Friends tab → B's bell lights **from
 * another page** and the thread carries the line → B replies → A sends a
 * head-to-head invite from the composer → B accepts the card in chat → a real
 * PENDING match exists on /play.
 *
 * This is the part unit tests can't prove: two independent sessions, the poll
 * loop, the unread cursor, and the fact that a chat invite is the same binding
 * aggregate as the Inbox Respond pill.
 *
 * Prerequisites (see e2e/README.md): a running stack, the seeded cohort
 * (`make seed` → `player1`, `player2`, CS2-linked), and the test-auth seam
 * (`E2E_AUTH=1`).
 */

const A = process.env.E2E_AUTH_ID_A ?? 'seed_player1';
const B = process.env.E2E_AUTH_ID_B ?? 'seed_player2';
// Usernames as seeded by scripts/seed_demo.py (auth_id `seed_<handle>`).
const A_NAME = process.env.E2E_USERNAME_A ?? 'player1';
const B_NAME = process.env.E2E_USERNAME_B ?? 'player2';

// The poll cadence is 15 s for the list and 6 s for an open thread, so the
// cross-session assertions get a generous window.
const POLL = { timeout: 30_000 };

test('friends → DM → unread badge → invite card in chat → PENDING match', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');

  const pageA = await signInAs(browser, A, { path: '/social?tab=friends' });
  const pageB = await signInAs(browser, B, { path: '/social?tab=friends' });

  // --- Messaging follows friendship, so establish it first. ---------------- //
  await pageA.getByLabel('Add friend by username or code').fill(B_NAME);
  await pageA.getByRole('button', { name: 'Add' }).click();

  await pageB.reload();
  await pageB.getByRole('tab', { name: 'Friends' }).click();
  await pageB.getByRole('button', { name: 'Accept' }).first().click(POLL);
  await expect(pageB.getByText(A_NAME).first()).toBeVisible(POLL);

  // --- A opens the DM straight from the friend row. ------------------------ //
  await pageA.reload();
  await pageA.getByRole('tab', { name: 'Friends' }).click();
  await pageA.getByRole('button', { name: 'Message' }).first().click(POLL);
  // Landed in the thread (the deep link opened it and stripped `?dm=`).
  await expect(pageA.getByLabel(`Chat with ${B_NAME}`)).toBeVisible(POLL);
  await expect(pageA).toHaveURL(/tab=inbox/);

  await pageA.getByLabel('Message').fill('run it back?');
  await pageA.getByLabel('Message').press('Enter');
  await expect(pageA.getByText('run it back?')).toBeVisible();

  // --- B is on a different page entirely; the bell must still light. ------- //
  await pageB.goto('/wallet');
  await expect(pageB.getByTestId('inbox-unread-dot').first()).toBeVisible(POLL);

  // Opening the thread clears the badge and shows the line.
  await pageB.goto('/social?tab=inbox');
  // The DM row for A in the left rail (the Inbox is the default Social tab).
  await pageB.getByRole('button').filter({ hasText: A_NAME }).first().click(POLL);
  const threadB = pageB.getByLabel(`Chat with ${A_NAME}`);
  await expect(threadB.getByText('run it back?')).toBeVisible(POLL);
  await expect(pageB.getByTestId('inbox-unread-dot')).toHaveCount(0, POLL);

  await pageB.getByLabel('Message').fill('yeah, $10 K/D');
  await pageB.getByLabel('Message').press('Enter');
  await expect(pageA.getByText('yeah, $10 K/D')).toBeVisible(POLL);

  // --- A sends a head-to-head invite from inside the chat. ----------------- //
  await pageA.getByRole('button', { name: 'Send an invite' }).click();
  await pageA.getByRole('menuitem', { name: /Head-to-head/ }).click();
  // The composer reuses ChallengeDialog, pre-targeted at the peer.
  await pageA.getByText('K/D ratio').click();
  await pageA.getByRole('button', { name: '$10.00' }).click();
  await pageA.getByRole('button', { name: /Send challenge/i }).click();
  await expect(pageA.getByTestId('invite-card').last()).toBeVisible(POLL);

  // --- B accepts the card in chat → a real PENDING match forms. ------------ //
  const cardB = threadB.getByTestId('invite-card').last();
  await expect(cardB).toBeVisible(POLL);
  await cardB.getByRole('button', { name: 'Accept' }).click();

  // Accepting navigates to the formed match, and it is a genuine one.
  await expect(pageB).toHaveURL(/\/play\?match=/, POLL);
  await expect(pageB.getByRole('button', { name: /Confirm & stake/ })).toBeVisible(
    POLL,
  );
  // The sender's copy of the card is stamped too (no stale pending invite).
  await expect(pageA.getByTestId('invite-card').last()).toContainText(
    /accepted/i,
    POLL,
  );

  await pageA.context().close();
  await pageB.context().close();
});
