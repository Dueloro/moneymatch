import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { LinkGames } from '../components/LinkGames';
import { GlowBackdrop, TriangleMark } from '../components/ui/brand';
import { PillButton } from '../components/ui/PillButton';
import { StepProgress } from '../components/ui/StepProgress';
import { useMe } from '../hooks/useMe';
import { api } from '../lib/api';
import { toast } from '../lib/toast';
import { US_STATES, isExcludedState, stateName } from '../lib/usStates';

const USERNAME_RE = /^[a-z0-9_]{3,20}$/;

export function SignInPage() {
  const { session, loading } = useAuth();
  const me = useMe();
  const [linkStep, setLinkStep] = useState(false);

  if (loading || (session && me.isLoading)) return <Centered>Loading…</Centered>;

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-bg px-4">
      <GlowBackdrop />
      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-4">
          <TriangleMark className="h-11 w-11" />
          <StepProgress step={!session ? 1 : me.data?.needs_onboarding ? 2 : 3} />
        </div>

        {!session ? (
          <AuthStep />
        ) : me.data?.needs_onboarding ? (
          <OnboardingStep onDone={() => setLinkStep(true)} />
        ) : linkStep ? (
          <LinkGameStep />
        ) : (
          <PostAuthRedirect />
        )}
      </div>
    </div>
  );
}

/** After auth + onboarding, resume an invite-link accept if one was pending
 * (the acquisition funnel), otherwise land on Play. */
function PostAuthRedirect() {
  const returnTo = sessionStorage.getItem('mm.returnTo');
  if (returnTo) {
    sessionStorage.removeItem('mm.returnTo');
    return <Navigate to={returnTo} replace />;
  }
  return <Navigate to="/play" replace />;
}

// Shared demo account for the one-click "enter demo" bypass. Play-money beta —
// see the sign-in note. Remove or gate this button before a real-money launch.
const DEMO_EMAIL = 'demo@moneymatch.gg';
const DEMO_PASSWORD = 'moneymatch-demo-2026';

/** Map Supabase auth errors to friendly, actionable copy. */
function friendlyAuthError(err: unknown, mode: 'signin' | 'signup'): string {
  const msg = (err as { message?: string })?.message ?? '';
  if (/invalid login credentials/i.test(msg))
    return 'Wrong email or password. New here? Create an account below.';
  if (/user already registered|already been registered/i.test(msg))
    return 'That email already has an account. Try signing in instead.';
  if (/email not confirmed/i.test(msg))
    return 'Confirm your email first (check your inbox), then sign in.';
  if (/password should be at least/i.test(msg))
    return 'Use a password of at least 6 characters.';
  return (
    msg || (mode === 'signin' ? 'Could not sign in.' : 'Could not create account.')
  );
}

function AuthStep() {
  const { signInWithGoogle, signInWithPassword, signUpWithPassword } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmEmail, setConfirmEmail] = useState<string | null>(null);

  if (confirmEmail) {
    return (
      <ConfirmStep
        email={confirmEmail}
        onBack={() => {
          setConfirmEmail(null);
          setMode('signin');
        }}
      />
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signInWithPassword(email, password);
      } else {
        const { needsConfirmation } = await signUpWithPassword(email, password);
        if (needsConfirmation) {
          setConfirmEmail(email);
          return;
        }
      }
      // On success the session updates and SignInPage advances automatically.
    } catch (err) {
      setError(friendlyAuthError(err, mode));
    } finally {
      setBusy(false);
    }
  }

  async function enterDemo() {
    setError(null);
    setBusy(true);
    try {
      try {
        await signInWithPassword(DEMO_EMAIL, DEMO_PASSWORD);
      } catch {
        // First run: the demo account doesn't exist yet — create it, then in.
        const { needsConfirmation } = await signUpWithPassword(
          DEMO_EMAIL,
          DEMO_PASSWORD,
        );
        if (needsConfirmation) {
          toast.error(
            'Demo needs email confirmation turned off in Supabase (Auth → Providers → Email).',
          );
          return;
        }
        await signInWithPassword(DEMO_EMAIL, DEMO_PASSWORD).catch(() => undefined);
      }
    } catch (err) {
      toast.error((err as Error)?.message || 'Could not enter the demo.');
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = email.length > 0 && password.length >= 6 && !busy;

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">
        {mode === 'signin' ? 'Sign in' : 'Create your account'}
      </h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Play skill-based matches for real payouts.
      </p>

      <div className="mt-8 flex flex-col gap-3">
        <PillButton
          type="button"
          variant="outline"
          fullWidth
          disabled={busy}
          onClick={() => void signInWithGoogle()}
        >
          Continue with Google
        </PillButton>

        <div className="my-1 flex items-center gap-3 text-xs text-text-tertiary">
          <span className="h-px flex-1 bg-hairline" />
          or
          <span className="h-px flex-1 bg-hairline" />
        </div>

        <form className="flex flex-col gap-3" onSubmit={submit}>
          <input
            type="email"
            required
            autoComplete="email"
            aria-label="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            className="rounded-pill border border-hairline bg-panel px-5 py-2.5 text-sm outline-none focus:border-text-secondary"
          />
          <input
            type="password"
            required
            minLength={6}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            aria-label="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (min 6 characters)"
            className="rounded-pill border border-hairline bg-panel px-5 py-2.5 text-sm outline-none focus:border-text-secondary"
          />
          <PillButton type="submit" variant="primary" fullWidth disabled={!canSubmit}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </PillButton>
          {error && <p className="text-center text-sm text-red">{error}</p>}
        </form>

        <button
          type="button"
          className="text-center text-sm text-text-secondary hover:text-text"
          onClick={() => {
            setMode((m) => (m === 'signin' ? 'signup' : 'signin'));
            setError(null);
          }}
        >
          {mode === 'signin'
            ? 'New here? Create an account'
            : 'Have an account? Sign in'}
        </button>
      </div>

      <div className="mt-6 border-t border-hairline pt-4">
        <PillButton
          type="button"
          variant="text"
          fullWidth
          disabled={busy}
          onClick={() => void enterDemo()}
        >
          Skip sign-up · enter the demo →
        </PillButton>
      </div>
    </div>
  );
}

function ConfirmStep({ email, onBack }: { email: string; onBack: () => void }) {
  return (
    <div className="text-center">
      <h1 className="text-xl font-semibold">Confirm your email</h1>
      <p className="mt-2 text-sm text-text-secondary">
        We sent a confirmation link to <span className="text-text">{email}</span>. Open
        it, then come back and sign in.
      </p>
      <div className="mt-8">
        <PillButton variant="text" fullWidth onClick={onBack}>
          Back to sign in
        </PillButton>
      </div>
    </div>
  );
}

function OnboardingStep({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [state, setState] = useState('');
  const [attested, setAttested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const valid = USERNAME_RE.test(username) && state !== '' && attested;

  const mutation = useMutation({
    mutationFn: async () => {
      const { error: apiError } = await api.PATCH('/api/v1/me', {
        body: {
          username,
          residence_state: state,
          dob_attested_18plus: attested,
        },
      });
      if (apiError) {
        const code = (apiError as { code?: string }).code;
        throw new Error(
          code === 'username_taken'
            ? 'That username is already taken.'
            : 'Could not save. Check your details and try again.',
        );
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
      onDone();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Create your profile</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Your username is your public handle. Choose carefully, it can't change.
      </p>

      <form
        className="mt-8 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-text-secondary">Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase())}
            placeholder="kvem_"
            className="rounded-pill border border-hairline bg-panel px-5 py-2.5 outline-none focus:border-text-secondary"
          />
          <span className="text-xs text-text-tertiary">
            3–20 characters: lowercase letters, numbers, underscore.
          </span>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-text-secondary">Residence state</span>
          <select
            value={state}
            onChange={(e) => setState(e.target.value)}
            className="rounded-pill border border-hairline bg-panel px-5 py-2.5 outline-none focus:border-text-secondary"
          >
            <option value="">Select a state…</option>
            {US_STATES.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name}
              </option>
            ))}
          </select>
          {isExcludedState(state) && (
            <span className="text-xs text-text-secondary">
              Cash play is not available in {stateName(state)} yet. You can still sign
              up and play every match for free.
            </span>
          )}
        </label>

        <label className="flex items-start gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={attested}
            onChange={(e) => setAttested(e.target.checked)}
            className="mt-0.5"
          />
          <span>I am 18 years of age or older.</span>
        </label>

        <PillButton
          type="submit"
          variant="primary"
          fullWidth
          disabled={!valid || mutation.isPending}
        >
          {mutation.isPending ? 'Saving…' : 'Continue'}
        </PillButton>
        {error && <p className="text-center text-sm text-red">{error}</p>}
      </form>
    </div>
  );
}

function LinkGameStep() {
  const navigate = useNavigate();
  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Link your first game</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Connect Chess, CS2, or Dota 2 to start playing, or do it later from your
        profile.
      </p>
      <div className="mt-8">
        <LinkGames />
      </div>
      <div className="mt-8">
        <PillButton variant="primary" fullWidth onClick={() => navigate('/play')}>
          Enter Money Match
        </PillButton>
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg text-text-secondary">
      {children}
    </div>
  );
}
