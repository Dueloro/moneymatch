import { useState } from 'react';

import {
  useChainStatus,
  useConnectChain,
  useSteamLoginUrl,
  useSyncChain,
} from '../../hooks/useCs2';
import { useLinks } from '../../hooks/useLinks';
import { Card } from '../ui/Card';
import { PillButton } from '../ui/PillButton';

/**
 * CS2 setup: three things, once, and then never again.
 *
 * Sign in through Steam, hand over an authentication code, and name one match
 * you have played. After that every future match arrives on its own and the
 * player never touches a share code again.
 *
 * Presented as one ordered list rather than separate cards because the steps
 * are not independent -- the auth code is meaningless without the Steam link,
 * and a starting share code is meaningless without both. Three cards that each
 * look optional invite people to do them out of order and then wonder why
 * nothing works.
 *
 * Every player needs their own authentication code. It is issued per Steam
 * account and reads only that account's history, so nobody's code can cover
 * anyone else. It is not a password, cannot spend anything, and is never shown
 * again once saved.
 */

// Buried several clicks into Steam support. Linking it directly is the
// difference between a 90-second setup and the step where people give up.
const AUTH_CODE_URL =
  'https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid=730&issueid=128';

function Step({
  index,
  title,
  done,
  children,
}: {
  index: number;
  title: string;
  done: boolean;
  children?: React.ReactNode;
}) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
          done ? 'bg-action text-bg' : 'border border-hairline text-text-tertiary'
        }`}
      >
        {done ? '✓' : index}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm ${done ? 'text-text-secondary' : 'text-text'}`}>
          {title}
        </p>
        {children}
      </div>
    </li>
  );
}

/**
 * Connected or not, at a glance and in one colour.
 *
 * The old control said "Check now", which describes an action nobody needs to
 * take and answers the wrong question. What a player actually wants to know
 * before staking money is whether their matches will be collected at all, so
 * that is what the control reports; checking now is what it *does* when there
 * is something worth checking.
 */
function StatusButton({
  ok,
  label,
  onClick,
  disabled,
  testId,
}: {
  ok: boolean;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  testId?: string;
}) {
  const tone = ok
    ? 'border-green/40 bg-green/10 text-green'
    : 'border-red/40 bg-red/10 text-red';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || !onClick}
      data-testid={testId}
      data-status={ok ? 'connected' : 'not-connected'}
      // Not a button when there is nothing to do: a dead control that still
      // looks pressable is how people conclude the page is broken.
      className={`inline-flex items-center gap-2 rounded-pill border px-3 py-1.5 text-sm font-semibold ${tone} ${
        onClick && !disabled ? 'hover:opacity-80' : 'cursor-default'
      } disabled:opacity-60`}
    >
      <span
        aria-hidden
        className={`h-2 w-2 rounded-full ${ok ? 'bg-green' : 'bg-red'}`}
      />
      {label}
    </button>
  );
}

export function Cs2SetupCard() {
  const { data: status } = useChainStatus();
  const { data: loginUrl } = useSteamLoginUrl();
  const { data: links } = useLinks();

  const steamLink = links?.games.find((game) => game.game === 'cs2.steam');
  // The SteamID64 is the identity and lives on the profile. `host_username` is
  // the persona name, which is mutable and must never be treated as the id. A
  // real SteamID64 is 17 digits, so anything else is a seeded placeholder
  // rather than a connected account, and calling that "linked" would be a lie.
  const steamId = steamLink?.profile?.username ?? '';
  const linked = steamLink?.status === 'LINKED' && /^\d{17}$/.test(steamId);
  const profile = steamLink?.profile;
  const connect = useConnectChain();
  const sync = useSyncChain();
  const [authCode, setAuthCode] = useState('');
  const [knownCode, setKnownCode] = useState('');
  // Steam lets a player regenerate their authentication code, which silently
  // invalidates ours. Without a way back to the form the only route to fixing
  // that is waiting for collection to break first.
  const [editing, setEditing] = useState(false);

  const connected = Boolean(status?.connected) && status?.state === 'active';
  // A chain that has stopped is not something to hide. It has stopped
  // collecting, and it stays stopped until the player reconnects it.
  const broken = Boolean(status?.connected) && status?.state !== 'active';

  if (connected && !editing) {
    return (
      <Card className="p-5" data-testid="cs2-setup-card">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold text-text">CS2 is set up</h3>
          <span className="text-xs text-text-tertiary">Collecting automatically</span>
        </div>
        <p className="mt-2 text-xs text-text-secondary">
          Your matches are picked up on their own. Nothing to paste.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusButton
            ok
            label={sync.isPending ? 'Checking…' : 'Connected'}
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
            testId="cs2-status"
          />
          {sync.isSuccess && (
            <span className="text-xs text-text-secondary" data-testid="cs2-sync-result">
              {sync.data.collected === 0
                ? 'Up to date.'
                : `Collected ${sync.data.collected} match${
                    sync.data.collected === 1 ? '' : 'es'
                  }.`}
            </span>
          )}
          {sync.isError && (
            <span className="text-xs text-red" role="alert">
              {(sync.error as Error).message}
            </span>
          )}
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs text-text-tertiary underline"
          >
            Change codes
          </button>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5" data-testid="cs2-setup-card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-text">Set up CS2</h3>
          <p className="mt-2 text-xs text-text-secondary">
            Three things, once. After this your matches are collected automatically.
          </p>
        </div>
        {/* Red until collection actually works. Until then a wager can be
         * joined and played with nothing to settle it, which is the one state
         * worth shouting about. */}
        <StatusButton
          ok={false}
          label={broken ? 'Disconnected' : 'Not connected'}
          testId="cs2-status"
        />
      </div>

      {broken && (
        <p
          className="mt-3 text-xs text-red"
          role="alert"
          data-testid="cs2-chain-broken"
        >
          {status?.last_error ?? 'Automatic collection stopped. Reconnect below.'}
        </p>
      )}

      <ol className="mt-4 flex flex-col gap-4">
        <Step index={1} title="Sign in through Steam" done={linked}>
          {!linked && loginUrl && (
            <a
              href={loginUrl}
              className="mt-2 inline-block rounded-pill bg-action px-4 py-2 text-sm font-semibold text-bg"
            >
              Sign in through Steam
            </a>
          )}
          {linked && (
            <>
              <p className="text-xs text-text">{profile?.display_name ?? steamId}</p>
              <p className="text-xs text-text-tertiary">
                SteamID {steamId}
                {profile?.rank_label ? ` · ${profile.rank_label}` : ''}
              </p>
              {(profile?.total_games || profile?.extra?.total_kills) && (
                <p className="mt-0.5 text-xs text-text-tertiary">
                  {profile?.total_games ? `${profile.total_games} matches` : null}
                  {profile?.extra?.total_kills
                    ? `${profile?.total_games ? ' · ' : ''}${Number(
                        profile.extra.total_kills,
                      ).toLocaleString()} kills`
                    : null}
                </p>
              )}
              {loginUrl && (
                <a
                  href={loginUrl}
                  className="mt-1 inline-block text-xs text-text-tertiary underline"
                >
                  Reconnect Steam
                </a>
              )}
            </>
          )}
        </Step>

        {/* Steps two and three are meaningless without a SteamID to attach
         * them to, and showing two disabled boxes above a disabled button just
         * asks the reader to work out which thing to do first. They appear when
         * they become doable. */}
        {linked && (
          <>
            <Step index={2} title="Create a match authentication code" done={false}>
              <p className="mt-1 text-xs text-text-secondary">
                Steam issues one per account.{' '}
                <a
                  href={AUTH_CODE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="text-action underline"
                >
                  Create yours
                </a>
                , then paste it below.
              </p>
            </Step>

            <Step index={3} title="Name one match you have played" done={false}>
              <p className="mt-1 text-xs text-text-secondary">
                In CS2: <span className="text-text">Watch</span> →{' '}
                <span className="text-text">Your Matches</span> → copy any share code.
                It is only a starting point, so any of your matches will do.
              </p>
            </Step>
          </>
        )}
      </ol>

      {!linked && (
        <p className="mt-4 text-xs text-text-tertiary">
          Two short codes come next. They take about a minute and are saved once, not
          per match.
        </p>
      )}

      {linked && (
        <form
          className="mt-4 flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            connect.mutate({ authCode: authCode.trim(), knownCode: knownCode.trim() });
          }}
        >
          <label htmlFor="cs2-auth-code" className="sr-only">
            Steam match authentication code
          </label>
          <input
            id="cs2-auth-code"
            value={authCode}
            onChange={(event) => setAuthCode(event.target.value)}
            placeholder="Authentication code"
            autoComplete="off"
            spellCheck={false}
            className="w-full rounded-inset border border-hairline bg-panel px-3 py-2 font-mono text-sm text-text placeholder:text-text-tertiary"
          />

          <label htmlFor="cs2-known-code" className="sr-only">
            A share code from one of your matches
          </label>
          <input
            id="cs2-known-code"
            value={knownCode}
            onChange={(event) => setKnownCode(event.target.value)}
            placeholder="CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx"
            autoComplete="off"
            spellCheck={false}
            className="w-full rounded-inset border border-hairline bg-panel px-3 py-2 font-mono text-sm text-text placeholder:text-text-tertiary"
          />

          <div className="flex items-center gap-2">
            <PillButton
              type="submit"
              disabled={
                connect.isPending ||
                authCode.trim().length < 8 ||
                knownCode.trim().length < 10
              }
            >
              {connect.isPending ? 'Checking…' : 'Finish setup'}
            </PillButton>
            <span className="text-xs text-text-tertiary">
              Saved once, not per match
            </span>
          </div>
        </form>
      )}

      {connect.isError && (
        <p
          className="mt-3 text-xs text-red"
          role="alert"
          data-testid="cs2-connect-error"
        >
          {(connect.error as Error).message}
        </p>
      )}
    </Card>
  );
}
