import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { GameSelectOverlay } from '../components/GameSelectOverlay';
import { TriangleMark } from '../components/ui/brand';
import { useMe, useSetActiveGames } from '../hooks/useMe';
import { enterDemo } from '../lib/demoAuth';
import { toast } from '../lib/toast';

/**
 * Hidden demo entry point — not linked from the main sign-in form or nav.
 * Accessible at /demosignin for internal testing and demos. Enters the demo
 * session, then shows the game-select overlay in **demo** context: all four
 * games are selectable (Dota 2 keeps its SOON/grayscale look but is clickable),
 * seeded from the demo's pre-provisioned play set. Confirming lands on /play.
 */
export function DemoSignInPage() {
  const { session } = useAuth();
  const me = useMe();
  const navigate = useNavigate();
  const setGames = useSetActiveGames();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function enter() {
      try {
        await enterDemo();
      } catch (err) {
        const msg = (err as Error)?.message || 'Could not enter the demo.';
        toast.error(msg);
        setError(msg);
      }
    }
    void enter();
  }, []);

  // Once the demo session and profile are ready, pick games before entering.
  if (session && me.data) {
    return (
      <GameSelectOverlay
        context="demo"
        initialSelected={me.data.user.active_games}
        busy={setGames.isPending}
        onConfirm={(games) =>
          setGames.mutate(games, {
            onSuccess: () => navigate('/play', { replace: true }),
          })
        }
      />
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="flex flex-col items-center gap-6 text-center">
        <TriangleMark className="h-11 w-11" />
        {error ? (
          <div>
            <p className="text-sm text-red">{error}</p>
            <p className="mt-2 text-xs text-text-secondary">
              <a href="/signin" className="underline hover:text-text">
                Back to sign in
              </a>
            </p>
          </div>
        ) : (
          <p className="text-sm text-text-secondary">Entering demo…</p>
        )}
      </div>
    </div>
  );
}
