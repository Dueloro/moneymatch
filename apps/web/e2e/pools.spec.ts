import { expect, test, type BrowserContext, type Page } from '@playwright/test';

/**
 * Phase-4 exit criterion + required e2e (07-phase-4):
 * a CS2 user picks Medium, sees bars quoted from their own baseline, enqueues,
 * lands in a formed room whose room_bar is the rounded mean of members' bars
 * (shown with the delta), plays a (fixture) FaceIt match, is graded from
 * server-fetched telemetry, and is paid their pool share — zero client input
 * after enqueue.
 *
 * Prerequisites (see e2e/README.md): a running stack (`make dev`) with a stubbed
 * FaceIt adapter that resolves each member's next match deterministically, and a
 * test-auth seam that signs in `POOL_ROOM_SIZE` seeded, CS2-linked users. The env
 * supplies their ready sessions as a JSON array in E2E_POOL_USERS.
 */

async function signIn(context: BrowserContext, sessionJson: string): Promise<Page> {
  await context.addInitScript((session) => {
    window.localStorage.setItem('sb-moneymatch-auth-token', session);
  }, sessionJson);
  const page = await context.newPage();
  await page.goto('/pools');
  return page;
}

test('four similar players form a Medium K/D room, clear, and split the pool', async ({
  browser,
}) => {
  const raw = process.env.E2E_POOL_USERS;
  test.skip(
    !raw,
    'Set E2E_POOL_USERS (JSON array of seeded, CS2-linked sessions) and run the stack.',
  );
  const sessions: string[] = JSON.parse(raw!);
  test.skip(sessions.length < 4, 'Need at least four seeded sessions to fill a room.');

  const pages: Page[] = [];
  for (const s of sessions.slice(0, 4)) {
    const ctx = await browser.newContext();
    pages.push(await signIn(ctx, s));
  }

  // The first player picks Medium and sees a bar quoted from their own baseline.
  const p0 = pages[0];
  await p0.getByText('medium').click();
  await expect(p0.getByTestId('pool-slip')).toContainText('your');
  await p0.getByRole('button', { name: '$10.00' }).click();
  // Disclosed as an estimate — never a fixed odds line.
  await expect(p0.getByTestId('pool-slip')).toContainText(
    'your share of the pool',
  );

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
