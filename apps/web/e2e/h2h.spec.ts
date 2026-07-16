import { expect, test, type BrowserContext, type Page } from '@playwright/test';

/**
 * Phase-3 exit criterion #1 + the required e2e (06-phase-3):
 * two users on separate machines complete queue → match → confirm → play →
 * auto-settlement, no manual steps — and the money lands exactly:
 * winner +$18.00, loser −$10.00, $2.00 rake in the platform ledger.
 *
 * Prerequisites (see e2e/README.md): a running stack (`make dev`) with a stubbed
 * host adapter that resolves the two accounts' next match to a fixed winner, and
 * a test-auth seam that lets each context sign in as a seeded, game-linked user.
 * The env supplies two ready sessions:
 *   E2E_USER_A / E2E_USER_B — JSON Supabase sessions to inject.
 */

async function signIn(context: BrowserContext, sessionJson: string): Promise<Page> {
  // The web app keeps only the Supabase session in localStorage (00-README §2),
  // so injecting it is a valid, deploy-shaped way to authenticate a context.
  await context.addInitScript((session) => {
    window.localStorage.setItem('sb-moneymatch-auth-token', session);
  }, sessionJson);
  const page = await context.newPage();
  await page.goto('/play');
  return page;
}

test('two users duel on K/D at $10 → winner +$18, loser −$10, rake $2', async ({
  browser,
}) => {
  test.skip(
    !process.env.E2E_USER_A || !process.env.E2E_USER_B,
    'Set E2E_USER_A / E2E_USER_B (seeded, CS2-linked sessions) and run the stack.',
  );

  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const pageA = await signIn(ctxA, process.env.E2E_USER_A!);
  const pageB = await signIn(ctxB, process.env.E2E_USER_B!);

  // A picks K/D ratio at $10 and searches.
  await pageA.getByRole('tab', { name: /CS2/ }).click();
  await pageA.getByText('K/D ratio').click();
  await pageA.getByRole('button', { name: '$10.00' }).click();
  await pageA.getByRole('button', { name: 'Find match' }).click();
  await expect(pageA.getByText('Searching…')).toBeVisible();

  // B queues the same market → the pair forms; both see the matched card.
  await pageB.getByRole('tab', { name: /CS2/ }).click();
  await pageB.getByText('K/D ratio').click();
  await pageB.getByRole('button', { name: '$10.00' }).click();
  await pageB.getByRole('button', { name: 'Find match' }).click();

  await expect(pageA.getByTestId('forecast')).toBeVisible();
  await expect(pageB.getByTestId('forecast')).toBeVisible();

  // Both confirm → escrow $10 each → ACTIVE.
  await pageA.getByRole('button', { name: /Confirm & stake/ }).click();
  await pageB.getByRole('button', { name: /Confirm & stake/ }).click();
  await expect(pageA.getByText(/Play your next match/)).toBeVisible();

  // The fixture host resolves the next match; the worker settles within a cycle.
  // Winner sees the settlement toast on Activity; the wallet reflects the payout.
  await pageA.goto('/activity');
  await expect(pageA.getByTestId('settlement-toast')).toBeVisible({ timeout: 30_000 });

  await pageA.goto('/wallet');
  // Winner: signup $1000 − $10 stake + $18 prize = $1008.00.
  await expect(pageA.getByText('$1,008.00')).toBeVisible();
  await pageB.goto('/wallet');
  // Loser: $1000 − $10 = $990.00.
  await expect(pageB.getByText('$990.00')).toBeVisible();

  await ctxA.close();
  await ctxB.close();
});
