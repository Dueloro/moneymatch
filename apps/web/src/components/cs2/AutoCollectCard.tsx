import { useState } from 'react';

import { useChainStatus, useConnectChain, useSyncChain } from '../../hooks/useCs2';

/**
 * Automatic match collection, so a player never pastes a share code again.
 *
 * Valve stores a player's matches as a linked list: given one code they own,
 * the API returns the next. So this is a one-time setup, and after it every
 * match arrives on its own.
 *
 * The authentication code is the part people get stuck on — it lives several
 * clicks deep in Steam support. The button below deep-links straight to it
 * rather than describing where to navigate.
 */

const AUTH_CODE_URL =
  'https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128';

export function AutoCollectCard({ linked = true }: { linked?: boolean }) {
  const { data: status } = useChainStatus();
  const connect = useConnectChain();
  const sync = useSyncChain();
  const [authCode, setAuthCode] = useState('');
  const [knownCode, setKnownCode] = useState('');

  if (!linked) return null;

  const connected = status?.connected && status.state === 'active';
  // A broken chain is not a failure to hide: it has stopped collecting, and it
  // stays stopped until the player reconnects it.
  const broken = status?.connected && status.state !== 'active';

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-100">Automatic match collection</h3>
          <p className="text-sm text-slate-400">
            {connected
              ? 'Connected. New matches are picked up on their own.'
              : 'Connect once and you will never paste a share code again.'}
          </p>
        </div>
        {connected ? (
          <span className="rounded-full bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-300">
            On
          </span>
        ) : null}
      </header>

      {broken ? (
        <p className="mb-3 rounded border border-amber-600/40 bg-amber-500/10 p-2 text-sm text-amber-200">
          {status?.last_error ?? 'Collection stopped. Reconnect below.'}
        </p>
      ) : null}

      {connected ? (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
            className="rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-100 hover:bg-slate-600 disabled:opacity-50"
          >
            {sync.isPending ? 'Checking…' : 'Check for new matches'}
          </button>
          {sync.isSuccess ? (
            <span className="text-sm text-slate-400">
              {sync.data.collected === 0
                ? 'Up to date.'
                : `Collected ${sync.data.collected} match${sync.data.collected === 1 ? '' : 'es'}.`}
            </span>
          ) : null}
          {sync.isError ? (
            <span className="text-sm text-rose-300">{(sync.error as Error).message}</span>
          ) : null}
        </div>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            connect.mutate({ authCode, knownCode });
          }}
        >
          <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-300">
            <li>
              <a
                href={AUTH_CODE_URL}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 underline"
              >
                Create an authentication code
              </a>{' '}
              on Steam, then paste it here.
            </li>
            <li>Paste any share code from a match on this account, to start from.</li>
          </ol>

          <input
            value={authCode}
            onChange={(event) => setAuthCode(event.target.value.trim())}
            placeholder="Authentication code"
            aria-label="Steam authentication code"
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
          />
          <input
            value={knownCode}
            onChange={(event) => setKnownCode(event.target.value.trim())}
            placeholder="CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx"
            aria-label="Starting share code"
            className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100"
          />

          {connect.isError ? (
            <p className="text-sm text-rose-300">{(connect.error as Error).message}</p>
          ) : null}

          <button
            type="submit"
            disabled={connect.isPending || !authCode || !knownCode}
            className="rounded bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {connect.isPending ? 'Connecting…' : 'Turn on automatic collection'}
          </button>
        </form>
      )}
    </section>
  );
}
