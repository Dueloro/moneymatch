import { expect, test, type Browser, type Page } from '@playwright/test';

import { mintToken } from './auth';
import { ensureFriends, ensurePlayer } from './fixtures';

const TOKEN_KEY = 'mm.e2e.access_token';
const AUTH_ID = 'release_audit';

const routes = [
  '/play',
  '/pools',
  '/tournament',
  '/activity',
  '/social?tab=friends',
  '/social?tab=inbox',
  '/wallet',
  '/profile',
  '/admin/users',
  '/admin/contests',
  '/admin/disputes',
  '/admin/support',
  '/admin/queue',
  '/admin/flags',
  '/admin/reconciliation',
  '/admin/risk',
] as const;

const viewports = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 1000 },
] as const;

let token: string;

test.beforeAll(async () => {
  token = await mintToken(AUTH_ID, 'audit@example.com');
});

async function authenticatedPage(
  browser: Browser,
  viewport: { width: number; height: number },
  accessToken = token,
): Promise<Page> {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block' });
  await context.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
      // The route matrix creates dozens of short-lived contexts. Disable the live
      // stream so their 15-second disconnect checks cannot exhaust local Postgres.
      Object.defineProperty(window, 'EventSource', { value: undefined });
    },
    { key: TOKEN_KEY, value: accessToken },
  );
  return context.newPage();
}

const activeMatch = {
  id: 'audit-match',
  game: 'chess.lichess',
  market: 'win_h2h',
  market_label: 'Match winner',
  kind: 'win_h2h',
  speed: 'blitz',
  entry_cents: 1000,
  pot_cents: 2000,
  prize_cents: 1800,
  rake_cents: 200,
  multiplier_bps: 18000,
  state: 'ACTIVE',
  host_game_id: 'auditgame',
  matched_at: '2026-11-09T03:00:00Z',
  window_ends_at: '2026-11-09T04:00:00Z',
  players: [
    {
      user_id: 'release_audit',
      username: 'release_audit',
      rating: 1512,
      color: 'white',
      confirmed: true,
      payout_cents: 0,
      stat_line: null,
      is_you: true,
    },
    {
      user_id: 'audit_opponent',
      username: 'knight_shift',
      rating: 1538,
      color: 'black',
      confirmed: true,
      payout_cents: 0,
      stat_line: null,
      is_you: false,
    },
  ],
  you_confirmed: true,
  your_play_url: 'https://lichess.org/auditgame',
  forecast: { you_win_prob: 0.47, label: 'Even match' },
  winner_user_id: null,
  friendly: false,
  termination: null,
  game_ended_at: null,
  resolved_at: null,
  live: {
    kind: 'match',
    format: 'chess',
    status: 'live',
    moves: 6,
    your_color: 'white',
    turn: 'you',
    result: null,
    termination: null,
    san: ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6'],
    clocks: { white_ms: 261000, black_ms: 254000 },
    clock: { limit: 300, increment: 0 },
    last_move_at: '2026-11-09T03:05:00Z',
  },
};

async function mockMatchStage(page: Page, settled: boolean): Promise<void> {
  const match = settled
    ? {
        ...activeMatch,
        state: 'SETTLED',
        winner_user_id: 'release_audit',
        termination: 'checkmate',
        game_ended_at: '2026-11-09T03:10:00Z',
        resolved_at: '2026-11-09T03:10:12Z',
        players: activeMatch.players.map((player) => ({
          ...player,
          payout_cents: player.is_you ? 1800 : 0,
        })),
        live: {
          ...activeMatch.live,
          status: 'finished',
          result: 'you',
          termination: 'checkmate',
        },
      }
    : activeMatch;

  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    if (path === '/api/v1/links') {
      await json({
        games: [
          {
            game: 'chess.lichess',
            status: 'LINKED',
            host_username: 'release_audit',
            win_streak: 2,
            profile: {
              username: 'release_audit',
              rating: 1512,
              total_games: 80,
              formats: [
                { speed: 'blitz', rating: 1512, games: 80, provisional: false },
              ],
            },
          },
        ],
      });
      return;
    }
    if (path === '/api/v1/play/markets') {
      await json({
        game: 'chess.lichess',
        linked: true,
        entry_presets_cents: [500, 1000, 2000],
        markets: [
          {
            key: 'win_h2h',
            label: 'Match winner',
            kind: 'win_h2h',
            requires_speed: true,
            speeds: ['blitz'],
            clocks: [{ speed: 'blitz', limit_seconds: 300, increment_seconds: 0 }],
            multiplier_bps: 18000,
            queue_depth: 1,
            resolution_note: 'Winner takes the pot.',
          },
        ],
      });
      return;
    }
    if (path === '/api/v1/play/queue/status') {
      await json({
        status: 'matched',
        match,
        waited_seconds: null,
        can_cancel: false,
      });
      return;
    }
    if (path === '/api/v1/play/matches/audit-match') {
      await json(match);
      return;
    }
    if (path === '/api/v1/play/waiting') {
      await json({ waiting: [] });
      return;
    }
    await route.continue();
  });
}

async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(overflow, JSON.stringify(overflow)).toEqual({
    viewport: overflow.viewport,
    document: overflow.viewport,
    body: overflow.viewport,
  });
}

async function expectWithinViewport(page: Page, selector: string): Promise<void> {
  const box = await page.locator(selector).boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
}

for (const viewport of viewports) {
  test.describe(`${viewport.name} ${viewport.width}px`, () => {
    for (const route of routes) {
      test(`${route} renders without overflow or browser errors`, async ({
        browser,
      }) => {
        const page = await authenticatedPage(browser, viewport);
        const errors: string[] = [];
        page.on('console', (message) => {
          if (message.type() === 'error') errors.push(message.text());
        });
        page.on('pageerror', (error) => errors.push(error.message));

        await page.goto(route, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(500);
        await expect(page.locator('body')).not.toBeEmpty();
        await expectNoDocumentOverflow(page);
        expect(errors).toEqual([]);

        const name = route.replace(/[/?=&]+/g, '-').replace(/^-|-$/g, '');
        await page.screenshot({
          path: `test-results/release-audit/${viewport.name}-${name}.png`,
          fullPage: true,
        });
        await page.context().close();
      });
    }
  });
}

test('signed-out users cannot enter protected routes', async ({ page }) => {
  for (const route of routes) {
    await page.goto(route);
    await expect(page).toHaveURL(/\/signin$/);
  }
});

test('unknown routes resolve to the signed-in home', async ({ browser }) => {
  const page = await authenticatedPage(browser, viewports[0]);
  await page.goto('/not-a-real-route');
  await expect(page).toHaveURL(/\/play$/);
  await page.context().close();
});

test('invalid invite has a recoverable error at phone width', async ({ page }) => {
  await page.setViewportSize(viewports[0]);
  await page.goto('/i/not-a-real-invite');
  await expect(page.getByText(/invalid or expired/i)).toBeVisible();
  await expectNoDocumentOverflow(page);
});

test('cancelled Lichess callback has a recoverable error', async ({ browser }) => {
  const page = await authenticatedPage(browser, viewports[0]);
  await page.goto('/link/lichess/callback?error=access_denied&state=audit');
  await expect(page.getByText(/cancelled/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /back/i })).toBeVisible();
  await expectNoDocumentOverflow(page);
  await page.context().close();
});

for (const route of routes) {
  test(`${route} survives a downstream API failure`, async ({ browser }) => {
    const page = await authenticatedPage(browser, viewports[0]);
    await page.route('**/api/v1/**', async (request) => {
      if (new URL(request.request().url()).pathname === '/api/v1/me') {
        await request.continue();
        return;
      }
      await request.fulfill({
        status: 503,
        contentType: 'application/problem+json',
        body: JSON.stringify({ detail: 'Release audit outage' }),
      });
    });
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    await expect(page.locator('body')).toContainText(
      /couldn't|could not|failed|try again|unavailable/i,
    );
    await expectNoDocumentOverflow(page);
    await page.context().close();
  });
}

for (const route of ['/play', '/social?tab=inbox', '/wallet', '/profile']) {
  test(`${route} has a stable phone loading state`, async ({ browser }) => {
    const page = await authenticatedPage(browser, viewports[0]);
    await page.route('**/api/v1/**', async (request) => {
      if (new URL(request.request().url()).pathname !== '/api/v1/me') {
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
      await request.continue();
    });
    await page.goto(route);
    await page.waitForTimeout(300);
    await expect(page.locator('body')).not.toBeEmpty();
    await expectNoDocumentOverflow(page);
    await page.context().close();
  });
}

for (const viewport of [viewports[0], viewports[1]]) {
  for (const settled of [false, true]) {
    test(`${settled ? 'settled' : 'live'} match stage fits ${viewport.name}`, async ({
      browser,
    }) => {
      const page = await authenticatedPage(browser, viewport);
      await mockMatchStage(page, settled);
      await page.goto('/play?match=audit-match');
      const stage = page.getByTestId('match-stage');
      await expect(stage).toBeVisible();
      await expect(stage).toHaveAttribute('data-state', settled ? 'win' : 'live');
      if (settled) await expect(page.getByTestId('result-headline')).toBeVisible();
      await expectNoDocumentOverflow(page);
      await expectWithinViewport(page, '[data-testid="match-stage"]');
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: `test-results/release-audit/${viewport.name}-match-${settled ? 'settled' : 'live'}.png`,
        fullPage: true,
      });
      await page.context().close();
    });
  }
}

for (const viewport of [viewports[0], viewports[1]]) {
  test(`open chat thread fits ${viewport.name}`, async ({ browser }) => {
    const a = await ensurePlayer({
      authId: 'release_chat_a',
      username: 'release_chat_a',
    });
    const b = await ensurePlayer({
      authId: 'release_chat_b',
      username: 'release_chat_b',
    });
    await ensureFriends(a, b);
    const chatToken = await mintToken(a.authId);
    const page = await authenticatedPage(browser, viewport, chatToken);
    await page.goto('/social?tab=friends');
    await page.getByRole('button', { name: 'Message' }).first().click();
    await expect(page.getByLabel(`Chat with ${b.username}`)).toBeVisible();
    await expectNoDocumentOverflow(page);
    await expectWithinViewport(page, `[aria-label="Chat with ${b.username}"]`);
    if (viewport.name === 'phone') {
      const composer = await page.getByLabel('Message').boundingBox();
      const navigation = await page
        .getByRole('navigation', { name: 'Primary' })
        .boundingBox();
      expect(composer).not.toBeNull();
      expect(navigation).not.toBeNull();
      expect(composer!.y + composer!.height).toBeLessThanOrEqual(navigation!.y);
    }
    await page.screenshot({
      path: `test-results/release-audit/${viewport.name}-chat-thread.png`,
      fullPage: true,
    });
    await page.context().close();
  });
}
