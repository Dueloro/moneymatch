import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { PillButton } from '../components/ui/PillButton';
import { useAcceptInvite, useInvitePreview } from '../hooks/useChallenges';
import { useMe } from '../hooks/useMe';
import { formatCurrency } from '../lib/format';
import { track } from '../lib/telemetry';

/**
 * Public invite-link landing (`/i/:token`) — the acquisition funnel's front door
 * (08-phase-5 · deliverable 3). Preview is public; accepting requires sign-in +
 * a linked game. Every step emits a telemetry event (exit criterion 2).
 */
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
    if (token) sessionStorage.setItem('mm.returnTo', `/i/${token}`);
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
        <div className="mx-auto mb-6 grid h-10 w-10 place-items-center rounded-xl bg-green text-black">
          <span className="font-bold">M</span>
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
              {preview.market_label} · {formatCurrency(preview.entry_cents)} entry
            </p>

            {!preview.valid ? (
              <p className="mt-6 text-sm text-red">This challenge is no longer open.</p>
            ) : !session ? (
              <div className="mt-8">
                <PillButton fullWidth onClick={goSignIn}>
                  Sign in to accept
                </PillButton>
                <p className="mt-3 text-xs text-text-secondary">
                  New here? You&apos;ll create an account and link your game next.
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
                    Link your {preview.game} account first —{' '}
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
