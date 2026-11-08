import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { NotAffiliated } from '../components/ConnectLichess';
import { TriangleMark } from '../components/ui/brand';
import { Loader } from '../components/ui/Loader';
import { PillButton } from '../components/ui/PillButton';
import { useCompleteLichessLink, useConnectLichess } from '../hooks/useLinks';
import { clearLinkReturnTo, peekLinkReturnTo } from '../lib/linkReturnTo';
import { clearReturnTo, peekReturnTo } from '../lib/returnTo';

const REDIRECT_MS = 1500;

function lichessErrorMessage(error: string): string {
  return error === 'access_denied'
    ? 'You cancelled on Lichess.'
    : "Lichess didn't confirm the account.";
}

export function LichessCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const complete = useCompleteLichessLink();
  const connect = useConnectLichess();
  const sent = useRef(false);

  const code = params.get('code');
  const state = params.get('state');
  const lichessError = params.get('error');

  useEffect(() => {
    if (sent.current || lichessError || !code || !state) return;
    sent.current = true;
    complete.mutate({ code, state });
  }, [code, state, lichessError, complete]);

  const finish = () => {
    const to = peekLinkReturnTo();
    clearLinkReturnTo();
    if (peekReturnTo() === to) clearReturnTo();
    navigate(to, { replace: true });
  };

  useEffect(() => {
    if (!complete.isSuccess) return;
    const t = window.setTimeout(finish, REDIRECT_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [complete.isSuccess]);

  const error = lichessError
    ? lichessErrorMessage(lichessError)
    : !code || !state
      ? 'That Lichess link is incomplete.'
      : complete.isError
        ? complete.error.message
        : null;

  const linked = complete.data?.games.find((g) => g.status === 'LINKED');

  return (
    <div className="mm-grid-surface flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <TriangleMark className="h-11 w-11" />
        {error ? (
          <>
            <div>
              <h1 className="text-2xl font-semibold">Couldn&apos;t connect Lichess</h1>
              <p className="mt-1 text-sm text-text-secondary">{error}</p>
            </div>
            <div className="flex w-full flex-col gap-2">
              <PillButton
                fullWidth
                disabled={connect.isPending}
                onClick={() => connect.mutate(null)}
              >
                {connect.isPending ? 'Opening Lichess…' : 'Try again'}
              </PillButton>
              <PillButton variant="text" fullWidth onClick={finish}>
                Back
              </PillButton>
              {connect.error && (
                <p className="text-xs text-red">{connect.error.message}</p>
              )}
            </div>
            <NotAffiliated />
          </>
        ) : complete.isSuccess ? (
          <>
            <div>
              <h1 className="text-2xl font-semibold">Lichess connected</h1>
              <p className="mt-1 text-sm text-text-secondary">
                {linked?.host_username
                  ? `Linked as ${linked.host_username}.`
                  : 'Your account is linked.'}
              </p>
            </div>
            <PillButton fullWidth onClick={finish}>
              Continue
            </PillButton>
          </>
        ) : (
          <Loader label="Confirming with Lichess" fullScreen={false} />
        )}
      </div>
    </div>
  );
}
