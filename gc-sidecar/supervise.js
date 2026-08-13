/**
 * Keep the sidecar up, without fighting you for the Steam account.
 *
 * `server.js` exits rather than limping along half-connected, on the reasoning
 * that a process which is up but cannot answer is worse than one that is
 * visibly down. That is only true if something restarts it. Nothing did, so a
 * sidecar that died at 3am took every CS2 settlement with it until a human
 * noticed — and the way we noticed was a player asking why their wager had not
 * paid out.
 *
 * The one restart policy that matters here is the CS2 account conflict. An
 * account can only tell Steam it is playing CS2 in one place at a time, so the
 * moment you launch the game the sidecar is evicted (exit code 2). That is not
 * a fault and must not be retried hard: it would race your game client and lose
 * repeatedly. It is retried *patiently* instead, so the sidecar comes back on
 * its own the moment you quit, with nobody having to remember to restart it.
 *
 *     npm start          # supervised (this file) — the normal way to run it
 *     npm run start:once # one process, exits on failure — for debugging
 */

'use strict';

const { spawn } = require('child_process');
const path = require('path');

const STEAM_API_KEY = process.env.STEAM_API_KEY || '';
const STEAM_ID = process.env.GC_STEAM_ID || '';

/** Valve's appid for CS2. `gameid` equals this while the account is in a match. */
const CS2_APPID = '730';

/** How often to ask Steam whether you have finished playing. */
const PLAYING_POLL_MS = Number(process.env.GC_PLAYING_POLL_MS || 20_000);

// Overridable so the restart policy itself can be exercised against a stub
// that exits on demand. Testing it by actually launching CS2 is not a test
// anyone will re-run.
const SERVER = process.env.GC_SUPERVISE_ENTRY || path.join(__dirname, 'server.js');

/** Exit code `server.js` uses for "this account is playing CS2 elsewhere". */
const EXIT_PLAYING = 2;

/**
 * How long to wait before trying again while you are playing.
 *
 * Long, deliberately. A tight loop would spend the whole match losing a race
 * against your game client, and every attempt tells Steam this account is
 * launching CS2 — which is exactly the noise that gets a session throttled.
 * A match is tens of minutes; checking every half minute is plenty.
 */
const PLAYING_RETRY_MS = Number(process.env.GC_PLAYING_RETRY_MS || 30_000);

/** Backoff for real failures: quick at first, then patient. */
const MIN_BACKOFF_MS = 2_000;
const MAX_BACKOFF_MS = 60_000;

/**
 * A run this long counts as healthy, so the next failure starts from a short
 * delay again. Without it, a service that is up for hours and then hits one
 * blip inherits the backoff from a bad patch last week.
 */
const HEALTHY_AFTER_MS = 60_000;

let backoff = MIN_BACKOFF_MS;
let child = null;
let stopping = false;
// One retry per decision, so a flaky API delays the sidecar rather than
// keeping it down indefinitely.
let recheckedUnknown = false;

function log(event, extra) {
  process.stdout.write(
    JSON.stringify({ ts: new Date().toISOString(), event, ...extra }) + '\n',
  );
}

/**
 * Is the sidecar's Steam account in CS2 right now?
 *
 * Asked over the Web API, which is a plain read: it does not sign in, does not
 * announce a game, and cannot evict anyone. That distinction is the whole point
 * of this function. Connecting to the Game Coordinator means *telling Steam you
 * are playing CS2*, so a supervisor that blindly retries while you are in a
 * match does not merely fail — it throws you out of the game it exists to
 * grade, and then does it again 30 seconds later.
 *
 * One subtlety that makes this readable at all: while the sidecar is connected,
 * Steam reports *this same account* as in CS2, because from Steam's side the
 * sidecar is playing it. So the answer only distinguishes you from us when the
 * sidecar is down -- which is exactly, and only, when it is asked.
 *
 * Returns null when the answer is unknown (no key, no id, API down, profile
 * hidden).
 */
async function accountIsInGame() {
  if (!STEAM_API_KEY || !STEAM_ID) return null;
  const url =
    (process.env.GC_STEAM_API_BASE ||
      'https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/') +
    `?key=${encodeURIComponent(STEAM_API_KEY)}&steamids=${encodeURIComponent(STEAM_ID)}`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    if (!res.ok) return null;
    const player = (await res.json())?.response?.players?.[0];
    if (!player) return null;
    return String(player.gameid || '') === CS2_APPID;
  } catch {
    // Never let a failed status check kill the supervisor.
    return null;
  }
}

/** Spawn the server, but only once the account is actually free. */
async function startWhenFree() {
  if (stopping) return;
  const inGame = await accountIsInGame();

  if (inGame === true) {
    log('supervisor.account_in_game', {
      recheckInMs: PLAYING_POLL_MS,
      note: 'You are in CS2 on this account. Not connecting: doing so would evict you from your own match. Waiting for you to finish.',
    });
    setTimeout(startWhenFree, PLAYING_POLL_MS);
    return;
  }

  if (inGame === null) {
    // Unknown. On a shared account, connecting blind can throw you out of a
    // match, so give the check one more go before deciding. Staying down
    // forever because Steam's API is having a bad minute is its own failure,
    // so after a single retry it proceeds.
    if (!STEAM_API_KEY || !STEAM_ID) {
      log('supervisor.cannot_check_account', {
        note: 'Set STEAM_API_KEY and GC_STEAM_ID so the supervisor can wait for you to stop playing instead of racing you for the account.',
      });
    } else if (!recheckedUnknown) {
      recheckedUnknown = true;
      log('supervisor.account_state_unknown', { recheckInMs: PLAYING_POLL_MS });
      setTimeout(startWhenFree, PLAYING_POLL_MS);
      return;
    }
  }

  recheckedUnknown = false;
  start();
}

function start() {
  const startedAt = Date.now();
  // `inherit`: the child's own structured logs are the useful ones, and
  // re-encoding them here would only make them harder to grep.
  child = spawn(process.execPath, [SERVER], { stdio: 'inherit' });

  child.on('exit', (code, signal) => {
    child = null;
    if (stopping) return;

    const ranFor = Date.now() - startedAt;
    if (ranFor >= HEALTHY_AFTER_MS) backoff = MIN_BACKOFF_MS;

    // A clean exit is someone shutting it down on purpose. Respect that, or
    // there is no way to stop the thing.
    if (code === 0) {
      log('supervisor.stopped', { reason: 'clean exit' });
      process.exit(0);
    }

    let delay;
    if (code === EXIT_PLAYING) {
      delay = PLAYING_RETRY_MS;
      log('supervisor.waiting_for_you_to_stop_playing', {
        retryInMs: delay,
        note: 'Your Steam account is in CS2, which evicts the sidecar. It will come back on its own once you quit; nothing to do.',
      });
    } else {
      delay = backoff;
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      log('supervisor.restarting', { exitCode: code, signal, retryInMs: delay });
    }

    setTimeout(startWhenFree, delay);
  });
}

function stop(signal) {
  stopping = true;
  log('supervisor.shutting_down', { signal });
  if (child) child.kill(signal);
  // Do not wait forever on a child that will not die.
  setTimeout(() => process.exit(0), 2_000).unref();
}

process.on('SIGINT', () => stop('SIGINT'));
process.on('SIGTERM', () => stop('SIGTERM'));

log('supervisor.start', {
  server: SERVER,
  canDetectPlaying: Boolean(STEAM_API_KEY && STEAM_ID),
});
startWhenFree();
