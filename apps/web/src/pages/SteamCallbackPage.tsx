import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { api } from '../lib/api';
import { takeSteamReturn } from '../lib/steamReturn';
import { Card } from '../components/ui/Card';
import { PillButton } from '../components/ui/PillButton';

/**
 * Where Steam sends you back after signing in.
 *
 * Steam OpenID is a full-page redirect, not a popup: you leave the app, approve
 * on steamcommunity.com, and Steam returns you here with a pile of `openid.*`
 * query parameters.
 *
 * Those parameters are **not** proof on their own. Anyone can construct this URL
 * naming any SteamID. They are forwarded to the server verbatim, which hands
 * them back to Steam to confirm it signed them. That round trip is the entire
 * security of the flow, which is why nothing here filters, reorders or trusts
 * them.
 */
export function SteamCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [steamId, setSteamId] = useState<string | null>(null);
  // Strict mode mounts effects twice in development, and this one links an
  // account. Once is enough.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const openid: Record<string, string> = {};
    params.forEach((value, key) => {
      if (key.startsWith('openid.')) openid[key] = value;
    });

    if (Object.keys(openid).length === 0) {
      setError('Steam did not return a sign-in to verify.');
      return;
    }

    void (async () => {
      const { data, error: apiError } = await api.POST('/api/v1/cs2/steam/callback', {
        body: { params: openid },
      });
      if (apiError || !data) {
        const detail = apiError as { message?: string } | undefined;
        setError(detail?.message ?? 'Steam sign-in could not be verified.');
        return;
      }
      const body = data as { steam_id: string };
      setSteamId(body.steam_id);

      // Drop the cached link list before leaving. It is only stale for a few
      // seconds, but those are exactly the seconds you arrive in: without this
      // the CS2 card renders from a copy fetched *before* the link and asks you
      // to sign in to Steam again, with nowhere to enter the codes you came
      // back to enter.
      await queryClient.invalidateQueries({ queryKey: ['links'] });
      await queryClient.invalidateQueries({ queryKey: ['cs2-chain'] });

      // Back to the page you left, not a fixed one. Steam sign-in is a
      // full-page redirect, so being returned somewhere else reads as having
      // lost your place.
      const returnTo = takeSteamReturn();
      setTimeout(() => navigate(returnTo || '/profile', { replace: true }), 1200);
    })();
  }, [params, navigate, queryClient]);

  return (
    <div className="mx-auto mt-24 max-w-md px-4">
      <Card className="p-6 text-center">
        {error ? (
          <>
            <h1 className="text-lg font-semibold text-text">Steam sign-in failed</h1>
            <p className="mt-2 text-sm text-text-secondary">{error}</p>
            <PillButton className="mt-4" onClick={() => navigate('/profile')}>
              Back to profile
            </PillButton>
          </>
        ) : steamId ? (
          <>
            <h1 className="text-lg font-semibold text-text">Steam connected</h1>
            <p className="mt-2 text-sm text-text-secondary">
              SteamID <span className="font-mono text-text">{steamId}</span>
            </p>
            <p className="mt-1 text-xs text-text-tertiary">Taking you back…</p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold text-text">Confirming with Steam…</h1>
            <p className="mt-2 text-sm text-text-secondary">
              Checking that Steam really signed this.
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
