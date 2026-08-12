# GC sidecar

Turns a CS2 share code into a scoreboard. The API calls this; nothing else
should be able to.

A share code carries three ids and nothing more. The scoreboard and demo URL
come from Valve's Game Coordinator, which speaks protobuf over the Steam
network rather than HTTP and has no maintained Python client. Hence a small
Node service.

## Setup

```bash
cd gc-sidecar
npm install

# One-time: get a refresh token. Not a password and a Guard code, which expire
# in ~30 seconds and will not survive a restart.
npm run token          # scan a QR code with the Steam mobile app
npm run token:creds    # or username + password + Guard code
```

`npm run token` prints a QR code in the terminal. Open the Steam mobile app ->
Steam Guard -> the QR button, and scan it. No password is typed anywhere; what
comes back is a token, not a credential.

(`npx steam-session` does not work: it is a library, not a CLI.)

The token is a login to your Steam account. Keep it in `.env`, which is
gitignored, and treat it like a password.

Then set, in the repo `.env`:

```
GC_REFRESH_TOKEN=<the token steam-session printed>
GC_SHARED_SECRET=<any long random string>
GC_SIDECAR_URL=http://127.0.0.1:8787
```

Run it:

```bash
GC_REFRESH_TOKEN=... GC_SHARED_SECRET=... npm start
curl -s localhost:8787/health          # { "ready": true, "queueDepth": 0 }
```

`ready: false` means the process is up but not yet attached to the GC. That is
normal for a few seconds after start, and after any Steam hiccup.

## The account it logs in as

It must have **played CS2**. A brand-new account is *limited* and may never
attach to the GC. If yours is new, spend the $5 to unlock it before relying on
this.

**Give it its own account.** Attaching to the Game Coordinator means telling
Steam you are playing CS2, and an account can only do that in one place at a
time. Run this on the account you play on and the two sessions evict each
other: you get `LoggedInElsewhere` and the sidecar exits.

For a quick test you can quit Steam on your PC while the sidecar runs. For
anything ongoing, a second Steam account that owns CS2 is the answer, and it
resolves *anyone's* share code, so it does not need to have played the match.

## Rules that are not tuning knobs

- **One request in flight, ~1.2s apart.** The GC is stateful and rate limited.
  Concurrent requests get throttled, dropped, or answered with another
  request's data, which on a wager product means grading the wrong match.
- **Loopback only, shared secret required.** This can read match data for
  arbitrary Steam users. It must never face the internet.
- **Exit on a Steam error** rather than limping half-connected. A process that
  is up but cannot answer is worse than one that is visibly down, because
  callers keep waiting on it.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/resolve` | `{ shareCode }` -> scoreboard. 404 if Valve does not know it, 503 while reconnecting |
| POST | `/recent` | `{ steamId }` -> last few matches. Opportunistic; Valve has restricted this and failure is normal |
| GET | `/health` | `{ ready, queueDepth }`. No secret required, so a status page can poll it |

`expired: true` with `demoUrl: null` is expected on matches older than about a
month. **It does not block settlement** — the scoreboard is still there. Only
ADR and the other parse-only metrics are lost with the demo.
