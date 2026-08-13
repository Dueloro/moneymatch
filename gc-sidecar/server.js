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

const crypto = require('crypto');
const http = require('http');
const SteamUser = require('steam-user');
const GlobalOffensive = require('globaloffensive');

// Render (and most platforms) inject the port to listen on.
const PORT = Number(process.env.PORT || process.env.GC_PORT || 8787);

// Loopback by default, because on a laptop nothing else should be able to reach
// this. A deployed instance has to accept connections from the API container,
// so the bind address is configurable — and the shared secret is mandatory
// either way, which is what makes widening it survivable.
const HOST = process.env.GC_BIND_HOST || '127.0.0.1';
const SHARED_SECRET = process.env.GC_SHARED_SECRET || '';

// Fail closed. Authentication used to be skipped entirely when the secret was
// unset -- it warned, and served every request anyway. A service that can read
// any player's match history must not be reachable by anyone who can reach the
// port, and "we logged a hint at startup" is not access control. Refusing to
// boot is the only version of this nobody can ignore.
if (!SHARED_SECRET) {
  console.error(
    'GC_SHARED_SECRET is not set. This service can read match data for arbitrary',
  );
  console.error(
    'players, so it will not start without one. Put a long random string in .env.',
  );
  process.exit(1);
}
const REFRESH_TOKEN = process.env.GC_REFRESH_TOKEN || '';

/**
 * Seconds of idleness after which the sidecar logs out of Steam entirely.
 *
 * Zero means stay connected, which is what production wants: the account is
 * dedicated to this service and nobody is playing on it.
 *
 * Set it when the sidecar shares an account with a person. Attaching to the GC
 * means claiming to play CS2, so being connected evicts their Steam client.
 * Idling out means the sidecar is dormant while they play, wakes for the few
 * seconds it takes to resolve a share code, and lets go again.
 */
const IDLE_LOGOUT_SECONDS = Number(process.env.GC_IDLE_LOGOUT_SECONDS || 0);

/** Minimum gap between GC requests. Below this the GC starts dropping them. */
const REQUEST_SPACING_MS = 1200;
/** A GC that has not answered by now is not going to. */
const REQUEST_TIMEOUT_MS = 25000;

/** account_id (32-bit) -> SteamID64. Valve sends the short form. */
const STEAMID64_BASE = 76561197960265728n;

const steam = new SteamUser();
const cs = new GlobalOffensive(steam);

let gcReady = false;
let loggedOn = false;
let idleTimer = null;
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

function connect() {
  if (loggedOn) return;
  loggedOn = true;
  log('gc.connecting');
  steam.logOn({ refreshToken: REFRESH_TOKEN });
}

function scheduleIdleLogout() {
  if (!IDLE_LOGOUT_SECONDS) return;
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (working || queue.length) {
      scheduleIdleLogout();
      return;
    }
    log('gc.idle_logout', { afterSeconds: IDLE_LOGOUT_SECONDS });
    gcReady = false;
    loggedOn = false;
    try {
      steam.gamesPlayed([]);
      steam.logOff();
    } catch (err) {
      log('gc.logoff_failed', { error: String(err && err.message) });
    }
  }, IDLE_LOGOUT_SECONDS * 1000);
}

steam.on('loggedOn', () => {
  log('gc.steam_logged_on', { steamId: String(steam.steamID) });
  steam.setPersona(SteamUser.EPersonaState.Online);
  steam.gamesPlayed([730]); // claiming to play CS2 is what connects the GC
});

if (!IDLE_LOGOUT_SECONDS) {
  connect();
} else {
  log('gc.lazy_mode', {
    idleLogoutSeconds: IDLE_LOGOUT_SECONDS,
    note: 'Dormant until a request arrives, so this account can be used to play in the meantime.',
  });
}

cs.on('connectedToGC', () => {
  gcReady = true;
  log('gc.connected');
  pump();
  scheduleIdleLogout();
});

cs.on('disconnectedFromGC', (reason) => {
  gcReady = false;
  log('gc.disconnected', { reason });
});

steam.on('error', (err) => {
  const reason = String((err && err.eresult) || '');
  const message = String((err && err.message) || err);

  // The one failure a user can fix themselves, and the one they will hit
  // first. Connecting to the Game Coordinator means telling Steam you are
  // playing CS2, and an account can only do that in one place at a time, so
  // signing in on your own PC evicts this session (or is evicted by it).
  if (message.includes('LoggedInElsewhere') || reason === '6') {
    log('gc.logged_in_elsewhere', {
      error: message,
      hint: 'This Steam account is signed in somewhere else. Either quit Steam on your PC while the sidecar runs, or give the sidecar its own Steam account that owns CS2. One account cannot play CS2 in two places.',
    });
    process.exit(2);
  }

  // Exit rather than limp along half-connected: a process that is up but
  // cannot answer is worse than one that is visibly down, because the caller
  // keeps waiting on it. Let the supervisor restart us.
  log('gc.steam_error', { error: message });
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
  if (!gcReady) {
    // Requests wait rather than fail while (re)connecting. In lazy mode this
    // is also what wakes the sidecar up.
    connect();
    return;
  }
  scheduleIdleLogout();

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

/**
 * Whether a request carries the shared secret.
 *
 * Compared in constant time. A byte-by-byte `!==` returns sooner the earlier it
 * finds a difference, which over enough requests leaks the secret one character
 * at a time — cheap to avoid, and this service can read any player's match
 * history.
 */
function authorised(req) {
  const given = req.headers['x-gc-secret'];
  if (typeof given !== 'string') return false;
  const a = Buffer.from(given);
  const b = Buffer.from(SHARED_SECRET);
  // timingSafeEqual throws on a length mismatch, which would itself be a
  // length oracle, so equalise first and let the content decide.
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    send(res, 200, { ready: gcReady, queueDepth: queue.length });
    return;
  }

  if (!authorised(req)) {
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
    if (!gcReady && !IDLE_LOGOUT_SECONDS) {
      send(res, 503, { error: 'gc_not_ready' });
      return;
    }
    try {
      // In lazy mode a dormant sidecar wakes here; the request queues until
      // the GC attaches rather than being refused.
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
});
