// k6 sanity for markets -> queue -> confirm: p95 < 300 ms, no write failures.
// Usage: BASE_URL=https://... TOKENS='["<jwt>", ...]' k6 run load/queue-confirm-settle.js

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
    http_req_duration: ['p(95)<300'],
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
