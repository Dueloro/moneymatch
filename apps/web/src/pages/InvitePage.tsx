import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { TriangleMark } from '../components/ui/brand';
import { PillButton } from '../components/ui/PillButton';
import { useAcceptInvite, useInvitePreview } from '../hooks/useChallenges';
import { useMe } from '../hooks/useMe';
import { formatCurrency } from '../lib/format';
import { setReturnTo } from '../lib/returnTo';
import { track } from '../lib/telemetry';

export function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const { session } = useAuth();
  const me = useMe();
  const navigate = useNavigate();
  const { data: preview, isLoading, error } = useInvitePreview(token);
  const accept = useAcceptInvite();

  useEffect(() => {
    if (preview) track('invite_viewed', { valid: preview.valid });
  }, [preview]);

  function goSignIn() {
    if (token) setReturnTo(`/i/${token}`);
    navigate('/signin');
  }

  async function onAccept() {
    if (!token) return;
    try {
      const res = await accept.mutateAsync(token);
      navigate(`/play?match=${res.match_id}`);
    } catch {
      // needs_link (or other) surfaces below; nudge to Profile to link.
    }
  }

  const needsLink =
    (accept.error as Error | null)?.message?.toLowerCase().includes('link') ?? false;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm text-center">
        <div className="mx-auto mb-6 flex justify-center">
          <TriangleMark className="h-11 w-11" />
        </div>

        {isLoading ? (
          <p className="text-text-secondary">Loading invite…</p>
        ) : error || !preview ? (
          <p className="text-text-secondary">This invite link is invalid or expired.</p>
        ) : (
          <>
            <h1 className="text-xl font-semibold text-text">
              {preview.challenger_username ?? 'A player'} challenged you
            </h1>
            <p className="mt-2 text-sm text-text-secondary">
              {preview.market_label} for{' '}
              <span className="text-green">{formatCurrency(preview.entry_cents)}</span>
            </p>

            {!preview.valid ? (
              <p className="mt-6 text-sm text-red">This challenge is no longer open.</p>
            ) : !session ? (
              <div className="mt-8">
                <PillButton fullWidth onClick={goSignIn}>
                  Sign in to accept
                </PillButton>
                <p className="mt-3 text-xs text-text-secondary">
                  New here? You&apos;ll create an account and link Lichess next.
                </p>
              </div>
            ) : me.data?.needs_onboarding ? (
              <div className="mt-8">
                <PillButton fullWidth onClick={goSignIn}>
                  Finish setup to accept
                </PillButton>
              </div>
            ) : (
              <div className="mt-8">
                <PillButton fullWidth disabled={accept.isPending} onClick={onAccept}>
                  {accept.isPending ? 'Accepting…' : 'Accept challenge'}
                </PillButton>
                {needsLink && (
                  <p className="mt-3 text-xs text-red">
                    Link your Lichess account first.{' '}
                    <button className="underline" onClick={() => navigate('/profile')}>
                      go to Profile
                    </button>
                    .
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
