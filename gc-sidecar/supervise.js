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

function log(event, extra) {
  process.stdout.write(
    JSON.stringify({ ts: new Date().toISOString(), event, ...extra }) + '\n',
  );
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

    setTimeout(start, delay);
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

log('supervisor.start', { server: SERVER });
start();
