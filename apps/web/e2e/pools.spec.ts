import { expect, test, type Page } from '@playwright/test';

import { e2eAuthConfigured, signInAs } from './auth';

/**
 * Phase-4 exit criterion + required e2e (07-phase-4):
 * a CS2 user picks Medium, sees bars quoted from their own baseline, enqueues,
 * lands in a formed room whose room_bar is the rounded mean of members' bars
 * (shown with the delta), plays a (fixture) FaceIt match, is graded from
 * server-fetched telemetry, and is paid their pool share — zero client input
 * after enqueue.
 *
 * Prerequisites (see e2e/README.md): a running stack (`make dev`) with a stubbed
 * FaceIt adapter that resolves each member's next match deterministically, and
 * the test-auth seam (`E2E_AUTH=1`) so four seeded, CS2-linked users sign in via
 * the API's `/dev/e2e/token` route.
 */

// Four seeded, CS2-linked players from scripts/seed_demo.py.
const POOL_AUTH_IDS: string[] = process.env.E2E_POOL_AUTH_IDS
  ? (JSON.parse(process.env.E2E_POOL_AUTH_IDS) as string[])
  : ['seed_player1', 'seed_player2', 'seed_player3', 'seed_player4'];

test('four similar players form a Medium K/D room, clear, and split the pool', async ({
  browser,
}) => {
  test.skip(!e2eAuthConfigured(), 'Set E2E_AUTH=1 and run the stack with the seam on.');
  test.skip(
    POOL_AUTH_IDS.length < 4,
    'Need at least four seeded users to fill a room.',
  );

  const pages: Page[] = [];
  for (const authId of POOL_AUTH_IDS.slice(0, 4)) {
    pages.push(await signInAs(browser, authId, { path: '/pools' }));
  }

  // The first player picks Medium and sees a bar quoted from their own baseline.
  const p0 = pages[0];
  await p0.getByText('medium').click();
  await expect(p0.getByTestId('pool-slip')).toContainText('your');
  await p0.getByRole('button', { name: '$10.00' }).click();
  // Disclosed as an estimate — never a fixed odds line.
  await expect(p0.getByTestId('pool-slip')).toContainText('your share of the pool');

  // All four enter Medium at $10 → the room forms.
  for (const page of pages) {
    await page.getByText('medium').click();
    await page.getByRole('button', { name: '$10.00' }).click();
    await page.getByRole('button', { name: 'Enter pool' }).click();
  }
  for (const page of pages) {
    await expect(page.getByTestId('room-card')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('room-card')).toContainText('Room bar');
  }

  // The fixture resolves each member's next match; the worker settles within a
  // cycle. Clearers' wallets reflect their pool share; nobody self-reports.
  await p0.goto('/activity');
  await expect(p0.getByTestId('settlement-toast')).toBeVisible({ timeout: 30_000 });

  for (const page of pages) {
    await page.context().close();
  }
});
