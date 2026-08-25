import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { TriangleMark } from '../components/ui/brand';
import { enterDemo } from '../lib/demoAuth';
import { toast } from '../lib/toast';

/**
 * Hidden demo entry point — not linked from the main sign-in form or nav.
 * Accessible at /demosignin for internal testing and demos.
 * Automatically initiates the demo session on load.
 */
export function DemoSignInPage() {
  const { session } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    async function enter() {
      try {
        await enterDemo();
      } catch (err) {
        const msg = (err as Error)?.message || 'Could not enter the demo.';
        toast.error(msg);
        setError(msg);
        setBusy(false);
      }
    }
    void enter();
  }, []);

  if (session) return <Navigate to="/play" replace />;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="flex flex-col items-center gap-6 text-center">
        <TriangleMark className="h-11 w-11" />
        {busy ? (
          <p className="text-sm text-text-secondary">Entering demo…</p>
        ) : error ? (
          <div>
            <p className="text-sm text-red">{error}</p>
            <p className="mt-2 text-xs text-text-secondary">
              <a href="/signin" className="underline hover:text-text">
                Back to sign in
              </a>
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
