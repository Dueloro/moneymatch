import { expect, test } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';
import {
  ensureFriends,
  ensurePlayer,
  lichessConfigured,
  linkedA,
  linkedB,
  runId,
} from './fixtures';

/**
 * Inbox messaging, driven as a real user pair: A befriends B → A messages B
 * from the Friends tab → B's bell lights **from another page** → B replies.
 * Then, for two linked players, a head-to-head invite sent from the chat
 * composer is accepted on the card and forms a real PENDING match.
 *
 * The part unit tests can't prove: two independent sessions, the poll loop,
 * the unread cursor, and a chat invite being the same binding aggregate as the
 * Inbox Respond pill.
 */

// The poll cadence is 15 s for the list and 6 s for an open thread, so the
// cross-session assertions get a generous window.
const POLL = { timeout: 30_000 };

test('friends → DM → unread badge → reply', async ({ browser }) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');

  // Fresh players each run, so the friendship is always new.
  const id = runId();
  const a = await ensurePlayer({
    authId: `e2e_chat_a_${id}`,
    username: `chat_a_${id}`,
  });
  const b = await ensurePlayer({
    authId: `e2e_chat_b_${id}`,
    username: `chat_b_${id}`,
  });

  const pageA = await signInAs(browser, a.authId, { path: '/social?tab=friends' });
  const pageB = await signInAs(browser, b.authId, { path: '/social?tab=friends' });

  // --- Messaging follows friendship, so establish it first. ---------------- //
  await pageA.getByLabel('Add friend by username or code').fill(b.username);
  await pageA.getByRole('button', { name: 'Add' }).click();

  await pageB.reload();
  await pageB.getByRole('tab', { name: 'Friends' }).click();
  await pageB.getByRole('button', { name: 'Accept' }).first().click(POLL);
  await expect(pageB.getByText(a.username).first()).toBeVisible(POLL);

  // --- A opens the DM straight from the friend row. ------------------------ //
  await pageA.reload();
  await pageA.getByRole('tab', { name: 'Friends' }).click();
  await pageA.getByRole('button', { name: 'Message' }).first().click(POLL);
  await expect(pageA.getByLabel(`Chat with ${b.username}`)).toBeVisible(POLL);
  await expect(pageA).toHaveURL(/tab=inbox/);

  await pageA.getByLabel('Message').fill('run it back?');
  await pageA.getByLabel('Message').press('Enter');
  await expect(pageA.getByText('run it back?')).toBeVisible();

  // --- B is on a different page entirely; the bell must still light. ------- //
  await pageB.goto('/wallet');
  await expect(pageB.getByTestId('inbox-unread-dot').first()).toBeVisible(POLL);

  // Opening the thread clears the badge and shows the line.
  await pageB.goto('/social?tab=inbox');
  await pageB.getByRole('button').filter({ hasText: a.username }).first().click(POLL);
  const threadB = pageB.getByLabel(`Chat with ${a.username}`);
  await expect(threadB.getByText('run it back?')).toBeVisible(POLL);
  await expect(pageB.getByTestId('inbox-unread-dot')).toHaveCount(0, POLL);

  await pageB.getByLabel('Message').fill('yeah, $10 blitz');
  await pageB.getByLabel('Message').press('Enter');
  await expect(pageA.getByText('yeah, $10 blitz')).toBeVisible(POLL);

  await pageA.context().close();
  await pageB.context().close();
});

test('head-to-head invite from chat → accept → PENDING match', async ({ browser }) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(
    !lichessConfigured(),
    'Set E2E_LICHESS_A and E2E_LICHESS_B to link players.',
  );

  const a = await linkedA();
  const b = await linkedB();
  await ensureFriends(a, b);

  const pageA = await signInAs(browser, a.authId, { path: '/social?tab=friends' });
  const pageB = await signInAs(browser, b.authId, { path: '/social?tab=inbox' });

  await pageA.getByRole('button', { name: 'Message' }).first().click(POLL);
  await expect(pageA.getByLabel(`Chat with ${b.username}`)).toBeVisible(POLL);

  // The composer reuses ChallengeDialog, pre-targeted at the peer.
  await pageA.getByRole('button', { name: 'Send an invite' }).click();
  await pageA.getByRole('menuitem', { name: /Head-to-head/ }).click();
  await pageA.getByRole('button', { name: 'blitz' }).click();
  await pageA.getByRole('button', { name: '$10.00' }).click();
  await pageA.getByRole('button', { name: /Send challenge/i }).click();
  await expect(pageA.getByTestId('invite-card').last()).toBeVisible(POLL);

  await pageB.getByRole('button').filter({ hasText: a.username }).first().click(POLL);
  const cardB = pageB
    .getByLabel(`Chat with ${a.username}`)
    .getByTestId('invite-card')
    .last();
  await expect(cardB).toBeVisible(POLL);
  await cardB.getByRole('button', { name: 'Accept' }).click();

  // Accepting navigates to the formed match, and it is a genuine one.
  await expect(pageB).toHaveURL(/\/play\?match=/, POLL);
  await expect(pageB.getByRole('button', { name: /Confirm & stake/ })).toBeVisible(
    POLL,
  );
  await expect(pageA.getByTestId('invite-card').last()).toContainText(
    /accepted/i,
    POLL,
  );

  await pageA.context().close();
  await pageB.context().close();
});
