/**
 * Game Coordinator sidecar.
 *
 * A CS2 share code contains three ids and nothing else. The scoreboard and the
 * demo URL come from Valve's Game Coordinator, which speaks protobuf over the
 * Steam network rather than HTTP, and has no maintained Python client. This is
 * the bridge: a Steam bot account logs in, and one HTTP endpoint turns a share
 * code into a scoreboard.
 *
 *   POST /resolve  { shareCode }  -> { matchId, matchTime, scores, players[], demoUrl }
 *   POST /recent   { steamId }    -> { matches: [...] }   opportunistic only
 *   GET  /health                  -> { ready, queueDepth }
 *
 * Three rules that are not tuning knobs:
 *
 * 1. **One GC request in flight at a time, spaced out.** The GC is stateful and
 *    rate limited. Concurrent requests get throttled, dropped, or answered with
 *    another request's data, which on a wager product means grading the wrong
 *    match.
 * 2. **Loopback only, behind a shared secret.** This service can read match data
 *    for arbitrary Steam users. It must never face the internet.
 * 3. **Refresh token, not a password.** Steam Guard codes expire in about 30
 *    seconds and will not survive a restart.
 */

'use strict';

const http = require('http');
const SteamUser = require('steam-user');
const GlobalOffensive = require('globaloffensive');

const PORT = Number(process.env.GC_PORT || 8787);
const HOST = '127.0.0.1';
const SHARED_SECRET = process.env.GC_SHARED_SECRET || '';
const REFRESH_TOKEN = process.env.GC_REFRESH_TOKEN || '';

/** Minimum gap between GC requests. Below this the GC starts dropping them. */
const REQUEST_SPACING_MS = 1200;
/** A GC that has not answered by now is not going to. */
const REQUEST_TIMEOUT_MS = 25000;

/** account_id (32-bit) -> SteamID64. Valve sends the short form. */
const STEAMID64_BASE = 76561197960265728n;

const steam = new SteamUser();
const cs = new GlobalOffensive(steam);

let gcReady = false;
const queue = [];
let working = false;
let lastRequestAt = 0;

function log(event, fields = {}) {
  // One JSON object per line, so it reads the same as the Python side.
  console.log(JSON.stringify({ ts: new Date().toISOString(), event, ...fields }));
}

// --------------------------------------------------------------------------
// Steam connection
// --------------------------------------------------------------------------

if (!REFRESH_TOKEN) {
  log('gc.no_refresh_token', {
    hint: 'Run `npx steam-session` once and set GC_REFRESH_TOKEN. A password plus a Steam Guard code cannot survive a restart.',
  });
  process.exit(1);
}

steam.logOn({ refreshToken: REFRESH_TOKEN });

steam.on('loggedOn', () => {
  log('gc.steam_logged_on', { steamId: String(steam.steamID) });
  steam.setPersona(SteamUser.EPersonaState.Online);
  steam.gamesPlayed([730]); // launching CS2 is what connects the GC
});

cs.on('connectedToGC', () => {
  gcReady = true;
  log('gc.connected');
  pump();
});

cs.on('disconnectedFromGC', (reason) => {
  gcReady = false;
  log('gc.disconnected', { reason });
});

steam.on('error', (err) => {
  // Exit rather than limp along half-connected: a process that is up but
  // cannot answer is worse than one that is visibly down, because the caller
  // keeps waiting on it. Let the supervisor restart us.
  log('gc.steam_error', { error: String(err && err.message) });
  process.exit(1);
});

// --------------------------------------------------------------------------
// Serialised GC access
// --------------------------------------------------------------------------

function enqueue(task) {
  return new Promise((resolve, reject) => {
    queue.push({ task, resolve, reject });
    pump();
  });
}

function pump() {
  if (working || queue.length === 0) return;
  if (!gcReady) return; // requests wait rather than fail while reconnecting

  working = true;
  const { task, resolve, reject } = queue.shift();
  const wait = Math.max(0, REQUEST_SPACING_MS - (Date.now() - lastRequestAt));

  setTimeout(() => {
    lastRequestAt = Date.now();
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      working = false;
      reject(new Error('The Game Coordinator did not answer in time.'));
      pump();
    }, REQUEST_TIMEOUT_MS);

    task()
      .then((value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        working = false;
        resolve(value);
        pump();
      })
      .catch((err) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        working = false;
        reject(err);
        pump();
      });
  }, wait);
}

/** Ask the GC for one match and wait for the matching `matchList` event. */
function requestMatch(shareCode) {
  return new Promise((resolve, reject) => {
    const onMatchList = (matches) => {
      cs.removeListener('matchList', onMatchList);
      if (!matches || matches.length === 0) {
        reject(new Error('not_found'));
        return;
      }
      resolve(matches[0]);
    };
    cs.on('matchList', onMatchList);
    try {
      cs.requestGame(shareCode);
    } catch (err) {
      cs.removeListener('matchList', onMatchList);
      reject(err);
    }
  });
}

// --------------------------------------------------------------------------
// Shaping the reply
// --------------------------------------------------------------------------

function toSteamId64(accountId) {
  return String(BigInt(accountId) + STEAMID64_BASE);
}

/**
 * Turn a GC match into the flat scoreboard the API stores.
 *
 * The per-player arrays are positional: index i in `kills` belongs to index i
 * in `reservation.account_ids`. Getting that wrong silently attributes one
 * player's stats to another, so the arrays are read by index and never zipped
 * through anything reordered.
 */
function shapeMatch(match) {
  const rounds = match.roundstatsall || [];
  const final = rounds[rounds.length - 1] || {};
  const accountIds = (final.reservation && final.reservation.account_ids) || [];

  const kills = final.kills || [];
  const deaths = final.deaths || [];
  const assists = final.assists || [];
  const headshots = final.enemy_headshots || [];
  const mvps = final.mvps || [];
  const scores = final.scores || [];
  const teamScores = final.team_scores || [];

  const half = Math.ceil(accountIds.length / 2);
  const players = accountIds.map((accountId, i) => ({
    steamid: toSteamId64(accountId),
    // The GC does not label sides; the roster is ordered team A then team B.
    team: i < half ? 'a' : 'b',
    kills: kills[i] || 0,
    deaths: deaths[i] || 0,
    assists: assists[i] || 0,
    headshots: headshots[i] || 0,
    mvps: mvps[i] || 0,
    score: scores[i] || 0,
  }));

  const demoUrl = final.map || null; // Valve puts the demo URL in `map`
  const isDemoUrl = typeof demoUrl === 'string' && demoUrl.startsWith('http');

  return {
    matchId: String(match.matchid),
    matchTime: match.matchtime,
    scores: { a: teamScores[0] || 0, b: teamScores[1] || 0 },
    players,
    // Absent after about a month, which is normal and does not block
    // settlement: the scoreboard is what a wager grades on.
    demoUrl: isDemoUrl ? demoUrl : null,
    expired: !isDemoUrl,
  };
}

// --------------------------------------------------------------------------
// HTTP
// --------------------------------------------------------------------------

function send(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 8192) reject(new Error('body too large'));
    });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    send(res, 200, { ready: gcReady, queueDepth: queue.length });
    return;
  }

  if (SHARED_SECRET && req.headers['x-gc-secret'] !== SHARED_SECRET) {
    log('gc.rejected_unauthenticated', { url: req.url });
    send(res, 401, { error: 'unauthorized' });
    return;
  }

  let body;
  try {
    body = await readJson(req);
  } catch (err) {
    send(res, 400, { error: 'bad_json', detail: String(err.message) });
    return;
  }

  if (req.method === 'POST' && req.url === '/resolve') {
    const shareCode = String(body.shareCode || '').trim();
    if (!shareCode) {
      send(res, 400, { error: 'shareCode is required' });
      return;
    }
    if (!gcReady) {
      send(res, 503, { error: 'gc_not_ready' });
      return;
    }
    try {
      const match = await enqueue(() => requestMatch(shareCode));
      const shaped = shapeMatch(match);
      log('gc.resolved', {
        shareCode,
        matchId: shaped.matchId,
        players: shaped.players.length,
        expired: shaped.expired,
      });
      send(res, 200, shaped);
    } catch (err) {
      const message = String((err && err.message) || err);
      if (message === 'not_found') {
        log('gc.match_not_found', { shareCode });
        send(res, 404, { error: 'match_not_found' });
        return;
      }
      log('gc.resolve_failed', { shareCode, error: message });
      send(res, 502, { error: 'gc_error', detail: message });
    }
    return;
  }

  if (req.method === 'POST' && req.url === '/recent') {
    // Opportunistic. Valve has restricted this over time; a failure here is
    // normal and the caller treats an empty list as "no answer".
    if (!gcReady) {
      send(res, 503, { error: 'gc_not_ready' });
      return;
    }
    try {
      const matches = await enqueue(
        () =>
          new Promise((resolve, reject) => {
            const onList = (list) => {
              cs.removeListener('matchList', onList);
              resolve(list || []);
            };
            cs.on('matchList', onList);
            try {
              cs.requestRecentGames();
            } catch (err) {
              cs.removeListener('matchList', onList);
              reject(err);
            }
          }),
      );
      send(res, 200, { matches: matches.map(shapeMatch) });
    } catch (err) {
      log('gc.recent_failed', { error: String(err && err.message) });
      send(res, 200, { matches: [] });
    }
    return;
  }

  send(res, 404, { error: 'not_found' });
});

server.listen(PORT, HOST, () => {
  log('gc.listening', { host: HOST, port: PORT, authenticated: Boolean(SHARED_SECRET) });
  if (!SHARED_SECRET) {
    log('gc.no_shared_secret', {
      hint: 'Set GC_SHARED_SECRET. This service can read match data for arbitrary users.',
    });
  }
});
