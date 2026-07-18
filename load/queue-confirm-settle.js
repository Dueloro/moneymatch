// MoneyMatch load sanity (10-phase-7 §2).
//
// Drives ~50 concurrent users through the money path — markets → queue →
// confirm — against a staging deployment, asserting p95 API latency < 300 ms
// and zero non-2xx/3xx write failures. The settlement half is host-verified and
// asynchronous (the worker settles once a real host game lands), so this script
// exercises the synchronous request path; a companion reconciliation check
// (`GET /api/v1/admin/reconciliation`, admin token) confirms
// `sum(payouts) + rake == sum(entries)` held under load with no violations.
//
// Auth: every virtual user needs a real Supabase JWT. Until the dev/e2e
// sign-in bypass lands (BACKLOG · "Browser e2e test-auth seam"), mint tokens
// out of band and pass them as a JSON array:
//
//   BASE_URL=https://staging.api.moneymatch... \
//   TOKENS='["<jwt1>","<jwt2>", ...]' \
//   k6 run load/queue-confirm-settle.js
//
// VUs pair off, so provide at least as many tokens as VUs (50).

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const TOKENS = JSON.parse(__ENV.TOKENS || '[]');

const writeErrors = new Rate('write_errors');

export const options = {
  scenarios: {
    money_path: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },
        { duration: '2m', target: 50 },
        { duration: '30s', target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'], // §2 load-sanity bar
    write_errors: ['rate==0'], // no invariant-touching write may fail
    checks: ['rate>0.99'],
  },
};

function authHeaders() {
  const token = TOKENS[(__VU - 1) % TOKENS.length];
  return {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };
}

const GAME = 'cs2.faceit';

export default function () {
  const auth = authHeaders();

  const markets = http.get(`${BASE_URL}/api/v1/play/markets?game=${GAME}`, auth);
  check(markets, { 'markets 200': (r) => r.status === 200 });

  const queue = http.post(
    `${BASE_URL}/api/v1/play/queue`,
    JSON.stringify({ game: GAME, market: 'kd_ratio', entry_preset_cents: 1000 }),
    auth,
  );
  const queued = check(queue, { 'queue accepted': (r) => r.status === 200 });
  writeErrors.add(!queued);

  // Poll for a pairing, then confirm if matched (best-effort under load).
  for (let i = 0; i < 3; i++) {
    const status = http.get(`${BASE_URL}/api/v1/play/queue/status`, auth);
    if (status.status === 200 && status.json('status') === 'matched') {
      const matchId = status.json('match.id');
      const confirm = http.post(
        `${BASE_URL}/api/v1/play/matches/${matchId}/confirm`,
        null,
        auth,
      );
      check(confirm, { 'confirm ok': (r) => r.status === 200 });
      break;
    }
    sleep(1);
  }

  sleep(1);
}
