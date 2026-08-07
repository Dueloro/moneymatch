import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { GameSelectGrid } from '../components/GameSelectGrid';
import { LinkGames } from '../components/LinkGames';
import { TriangleMark } from '../components/ui/brand';
import { Checkbox, Field, Select, TextInput } from '../components/ui/Field';
import { PillButton } from '../components/ui/PillButton';
import { StepProgress } from '../components/ui/StepProgress';
import { useMe, useSetActiveGames } from '../hooks/useMe';
import { api } from '../lib/api';
import { enterDemo as demoEnter } from '../lib/demoAuth';
import { toast } from '../lib/toast';
import { emailToUsername } from '../lib/usernameAuth';
import { US_STATES, isExcludedState, stateName } from '../lib/usStates';

const USERNAME_RE = /^[a-z0-9_]{3,20}$/;

/** A specific, human explanation of why a username is invalid, or null when it's
 * acceptable (or still empty). Drives inline feedback so the submit button never
 * just sits greyed-out with no reason — the trap that made auth look "inactive". */
function usernameProblem(username: string): string | null {
  if (username === '') return null;
  if (username.length < 3) return 'Username must be at least 3 characters.';
  if (username.length > 20) return 'Username must be 20 characters or fewer.';
  if (!/^[a-z0-9_]+$/.test(username))
    return 'Username can use only lowercase letters, numbers, and underscore.';
  return null;
}

export function SignInPage() {
  const { session, loading } = useAuth();
  const me = useMe();
  // Post-profile onboarding runs two sub-steps: pick your games, then link them.
  const [postStep, setPostStep] = useState<'idle' | 'pick' | 'link'>('idle');

  if (loading || (session && me.isLoading && !me.isError)) {
    return <Centered>Loading…</Centered>;
  }

  // Stale browser session (e.g. HS256 token while API expects JWKS) — drop it
  // and show the sign-in form instead of spinning forever.
  if (session && me.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg px-4">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center gap-4">
            <TriangleMark className="h-11 w-11" />
            <StepProgress step={1} />
          </div>
          <StaleSessionStep />
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-4">
          <TriangleMark className="h-11 w-11" />
          <StepProgress step={!session ? 1 : me.data?.needs_onboarding ? 2 : 3} />
        </div>

        {!session ? (
          <AuthStep />
        ) : me.data?.needs_onboarding ? (
          <OnboardingStep onDone={() => setPostStep('pick')} />
        ) : postStep === 'pick' ? (
          <PickGamesStep onDone={() => setPostStep('link')} />
        ) : postStep === 'link' ? (
          <LinkGameStep />
        ) : (
          <PostAuthRedirect />
        )}
      </div>
    </div>
  );
}

/** After auth + onboarding, resume an invite-link accept if one was pending
 * (the acquisition funnel), otherwise land on Solo Pools (the default mode). */
function PostAuthRedirect() {
  const returnTo = sessionStorage.getItem('mm.returnTo');
  if (returnTo) {
    sessionStorage.removeItem('mm.returnTo');
    return <Navigate to={returnTo} replace />;
  }
  return <Navigate to="/pools" replace />;
}

/** Browser had a session the API rejects (stale / wrong signing scheme). Clear
 * it and offer a clean sign-in / demo entry. */
function StaleSessionStep() {
  const { signOut } = useAuth();
  const [busy, setBusy] = useState(false);

  async function clearAndStay() {
    setBusy(true);
    await signOut();
  }

  async function enterDemo() {
    setBusy(true);
    try {
      await demoEnter();
    } catch (err) {
      toast.error((err as Error)?.message || 'Could not enter the demo.');
      setBusy(false);
    }
  }

  return (
    <div className="text-center">
      <h1 className="text-xl font-semibold">Session expired</h1>
      <p className="mt-2 text-sm text-text-secondary">
        Your saved sign-in is no longer valid. Sign in again or enter the demo.
      </p>
      <div className="mt-8 flex flex-col gap-3">
        <PillButton
          type="button"
          fullWidth
          disabled={busy}
          onClick={() => void enterDemo()}
        >
          Enter the demo
        </PillButton>
        <PillButton
          type="button"
          variant="outline"
          fullWidth
          disabled={busy}
          onClick={() => void clearAndStay()}
        >
          Back to sign in
        </PillButton>
      </div>
    </div>
  );
}

/** Map Supabase auth errors to friendly, actionable copy. Usernames are mapped
 * to a synthetic email under the hood, so Supabase's email-shaped errors are
 * reworded in username terms. */
function friendlyAuthError(err: unknown, mode: 'signin' | 'signup'): string {
  const msg = (err as { message?: string })?.message ?? '';
  if (/invalid login credentials/i.test(msg))
    return 'Wrong username or password. New here? Create an account below.';
  if (/user already registered|already been registered/i.test(msg))
    return 'That username is already taken. Try signing in instead.';
  if (/email_confirmation_required/i.test(msg))
    return 'Your account was created but sign-in is blocked by a server setting. Please contact support.';
  if (/password should be at least/i.test(msg))
    return 'Use a password of at least 6 characters.';
  return (
    msg || (mode === 'signin' ? 'Could not sign in.' : 'Could not create account.')
  );
}

function AuthStep() {
  const { signInWithUsername, signUpWithUsername } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const uProblem = usernameProblem(username);
  const pwTooShort = password.length > 0 && password.length < 6;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    // Validate on submit instead of silently disabling the button. The inline
    // field hints already name a bad username/short password as the user types,
    // so here we only stop the submit (and cover the empty-field fallback).
    if (!USERNAME_RE.test(username)) {
      if (!uProblem) setError('Enter a username to continue.');
      return;
    }
    if (password.length < 6) {
      if (password.length === 0) setError('Enter your password.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signInWithUsername(username, password);
      } else {
        await signUpWithUsername(username, password);
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
      // Full bypass: mint a demo token from the API and enter (reloads on success).
      await demoEnter();
    } catch (err) {
      toast.error((err as Error)?.message || 'Could not enter the demo.');
      setBusy(false);
    }
  }

  // Keep the button live whenever there's input so a click always yields
  // feedback; correctness is checked in submit().
  const canSubmit = !busy && username.length > 0 && password.length > 0;

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">
        {mode === 'signin' ? 'Sign in' : 'Create your account'}
      </h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Play skill-based matches for real payouts.
      </p>

      <div className="mt-8 flex flex-col gap-3">
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div>
            <TextInput
              required
              autoComplete="username"
              aria-label="Username"
              aria-invalid={uProblem ? true : undefined}
              value={username}
              onChange={(e) => setUsername(e.target.value.toLowerCase())}
              placeholder="Username"
            />
            {uProblem ? (
              <p className="mt-1 text-xs text-red">{uProblem}</p>
            ) : mode === 'signup' ? (
              <p className="mt-1 text-xs text-text-tertiary">
                3 to 20 characters: lowercase letters, numbers, underscore. This is your
                public handle and can't change.
              </p>
            ) : null}
          </div>
          <div>
            <TextInput
              type="password"
              required
              minLength={6}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              aria-label="Password"
              aria-invalid={pwTooShort ? true : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password, at least 6 characters"
            />
            {pwTooShort && (
              <p className="mt-1 text-xs text-red">
                Password must be at least 6 characters.
              </p>
            )}
          </div>
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

function OnboardingStep({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const { session } = useAuth();
  // The handle was chosen at sign-up; recover it from the synthetic email so it
  // survives across sessions (e.g. an account that signed up but didn't finish).
  const derived = emailToUsername(session?.user.email);
  const [username, setUsername] = useState(derived ?? '');
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
        A couple of details and you're in.
      </p>

      <form
        className="mt-8 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        {derived ? (
          <Field label="Username" hint="Your public handle, chosen at sign-up.">
            <TextInput value={username} readOnly disabled />
          </Field>
        ) : (
          <Field
            label="Username"
            hint="3 to 20 characters: lowercase letters, numbers, underscore."
          >
            <TextInput
              value={username}
              onChange={(e) => setUsername(e.target.value.toLowerCase())}
              placeholder="kvem_"
            />
          </Field>
        )}

        <Field
          label="Residence state"
          hint={
            isExcludedState(state)
              ? `Cash play is not available in ${stateName(state)} yet. You can still sign up and play every match for free.`
              : undefined
          }
        >
          <Select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Select a state…</option>
            {US_STATES.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>

        <Checkbox checked={attested} onChange={setAttested}>
          I am 18 years of age or older.
        </Checkbox>

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

/** Onboarding step 3a: choose which games you play. Saves the play set, which
 * drives the switcher. Everything is optional — "Skip" leaves it empty and the
 * app falls back to showing every game. */
function PickGamesStep({ onDone }: { onDone: () => void }) {
  const me = useMe();
  const setActiveGames = useSetActiveGames();
  const [selected, setSelected] = useState<string[]>(
    () => me.data?.user.active_games ?? [],
  );
  const [error, setError] = useState<string | null>(null);

  const save = (games: string[]) => {
    setError(null);
    setActiveGames.mutate(games, {
      onSuccess: onDone,
      onError: () => setError('Could not save your games. Try again.'),
    });
  };

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Which games do you play?</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Pick the games you want in your bar. You can always change this in your profile.
      </p>
      <div className="mt-8">
        <GameSelectGrid selected={selected} onChange={setSelected} />
      </div>
      <div className="mt-8 flex flex-col gap-3">
        <PillButton
          variant="primary"
          fullWidth
          disabled={selected.length === 0 || setActiveGames.isPending}
          onClick={() => save(selected)}
        >
          {setActiveGames.isPending ? 'Saving…' : 'Continue'}
        </PillButton>
        <PillButton
          variant="text"
          fullWidth
          disabled={setActiveGames.isPending}
          onClick={() => save([])}
        >
          Skip for now
        </PillButton>
        {error && <p className="text-center text-sm text-red">{error}</p>}
      </div>
    </div>
  );
}

/** Onboarding step 3b: link the games you picked so you can start playing. */
function LinkGameStep() {
  const navigate = useNavigate();
  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Link your games</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Connect an account to start playing, or do it later from your profile.
      </p>
      <div className="mt-8">
        <LinkGames onlyActive />
      </div>
      <div className="mt-8">
        <PillButton variant="primary" fullWidth onClick={() => navigate('/pools')}>
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
