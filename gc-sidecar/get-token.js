/**
 * Print a Steam refresh token for the sidecar to log in with.
 *
 * Two ways in, and QR is the default because it is the one where no password
 * is typed anywhere: Steam shows the approval on your phone, and what comes
 * back here is a token, not a credential.
 *
 *   node get-token.js          # scan a QR code with the Steam mobile app
 *   node get-token.js --creds  # username + password + Guard code
 *
 * A refresh token, rather than a password and a Guard code, because Guard codes
 * expire in about 30 seconds and will not survive a service restart. This token
 * lasts for months.
 *
 * Treat the output like a password: it is a login to your Steam account. Put it
 * in `.env` as GC_REFRESH_TOKEN and do not commit it (`.env` is gitignored).
 */

'use strict';

const { LoginSession, EAuthTokenPlatformType } = require('steam-session');

const useCreds = process.argv.includes('--creds');

function printToken(session) {
  console.log('\n' + '='.repeat(72));
  console.log('Signed in as:', session.accountName || String(session.steamID));
  console.log('\nGC_REFRESH_TOKEN=' + session.refreshToken);
  console.log('='.repeat(72));
  console.log('\nPaste that line into the repo .env, replacing the empty one.');
  console.log('Then: npm start');
  process.exit(0);
}

function wire(session) {
  session.on('authenticated', () => printToken(session));
  session.on('timeout', () => {
    console.error('\nTimed out waiting for approval. Run it again.');
    process.exit(1);
  });
  session.on('error', (err) => {
    console.error('\nSteam refused the sign-in:', err.message);
    process.exit(1);
  });
}

async function viaQr() {
  // SteamClient, not WebBrowser: only a client-platform token can talk to the
  // Game Coordinator, which is the whole point of this token.
  const session = new LoginSession(EAuthTokenPlatformType.SteamClient);
  wire(session);

  const started = await session.startWithQR();
  console.log('Open the Steam mobile app, go to the Steam Guard tab, tap the');
  console.log('QR button, and scan this:\n');

  try {
    // Optional: a scannable code right in the terminal.
    const qrcode = require('qrcode-terminal');
    qrcode.generate(started.qrChallengeUrl, { small: true });
  } catch {
    console.log('(install qrcode-terminal to render it here)');
  }
  console.log('\nOr open this URL on your phone:\n' + started.qrChallengeUrl);
  console.log('\nWaiting for you to approve it…');
}

async function viaCredentials() {
  const readline = require('readline');
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = (q, hide = false) =>
    new Promise((resolve) => {
      if (!hide) return rl.question(q, resolve);
      // Do not echo the password back to the terminal.
      const onData = (char) => {
        if (['\n', '\r', ''].includes(String(char))) {
          process.stdin.removeListener('data', onData);
        } else {
          process.stdout.write('\x1B[2K\x1B[200D' + q + '*'.repeat(rl.line.length));
        }
      };
      process.stdin.on('data', onData);
      rl.question(q, (value) => {
        process.stdout.write('\n');
        resolve(value);
      });
    });

  const accountName = await ask('Steam username: ');
  const password = await ask('Steam password: ', true);

  const session = new LoginSession(EAuthTokenPlatformType.SteamClient);
  wire(session);

  const started = await session.startWithCredentials({ accountName, password });
  if (started.actionRequired) {
    const code = await ask('Steam Guard code: ');
    await session.submitSteamGuardCode(code.trim());
  }
  rl.close();
  console.log('\nWaiting for Steam…');
}

(useCreds ? viaCredentials() : viaQr()).catch((err) => {
  console.error('\nFailed:', err.message);
  process.exit(1);
});
