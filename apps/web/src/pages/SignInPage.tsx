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

export function SignInPage() {
  const { session, loading, isPasswordRecovery } = useAuth();
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

        {isPasswordRecovery ? (
          <ResetPasswordStep />
        ) : !session ? (
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

function friendlyAuthError(err: unknown, mode: 'signin' | 'signup'): string {
  const msg = (err as { message?: string })?.message ?? '';
  if (/invalid login credentials/i.test(msg))
    return 'Wrong email or password. New here? Create an account below.';
  if (/user already registered|already been registered/i.test(msg))
    return 'That email already has an account. Try signing in instead.';
  if (/email not confirmed/i.test(msg))
    return 'Please verify your email first — check your inbox for the link.';
  if (/password should be at least/i.test(msg))
    return 'Use a password of at least 6 characters.';
  return (
    msg || (mode === 'signin' ? 'Could not sign in.' : 'Could not create account.')
  );
}

type AuthView = 'credentials' | 'check-email' | 'enter-code' | 'reset-request';

function AuthStep() {
  const [view, setView] = useState<AuthView>('credentials');
  const [email, setEmail] = useState('');

  if (view === 'check-email') return <CheckEmailNotice email={email} />;
  if (view === 'enter-code')
    return <EnterCodeForm email={email} onBack={() => setView('credentials')} />;
  if (view === 'reset-request')
    return <ResetRequestForm email={email} onBack={() => setView('credentials')} />;

  return (
    <CredentialsForm
      email={email}
      setEmail={setEmail}
      onNeedsVerification={() => setView('check-email')}
      onUseCode={() => setView('enter-code')}
      onForgot={() => setView('reset-request')}
    />
  );
}

function CredentialsForm({
  email,
  setEmail,
  onNeedsVerification,
  onUseCode,
  onForgot,
}: {
  email: string;
  setEmail: (v: string) => void;
  onNeedsVerification: () => void;
  onUseCode: () => void;
  onForgot: () => void;
}) {
  const { signInWithEmail, signUpWithEmail, signInWithGoogle } = useAuth();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pwTooShort = password.length > 0 && password.length < 6;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    if (password.length < 6) {
      setError('Use a password of at least 6 characters.');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'signin') {
        await signInWithEmail(email, password);
      } else {
        const { needsVerification } = await signUpWithEmail(email, password);
        if (needsVerification) onNeedsVerification();
      }
    } catch (err) {
      setError(friendlyAuthError(err, mode));
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setError(null);
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch {
      setError('Could not start Google sign-in. Try again.');
      setBusy(false);
    }
  }

  async function enterDemo() {
    setError(null);
    setBusy(true);
    try {
      await demoEnter();
    } catch (err) {
      toast.error((err as Error)?.message || 'Could not enter the demo.');
      setBusy(false);
    }
  }

  const canSubmit = !busy && email.length > 0 && password.length > 0;

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
          onClick={() => void google()}
        >
          <GoogleMark className="h-4 w-4" />
          Continue with Google
        </PillButton>

        <div className="flex items-center gap-3 py-1 text-xs text-text-tertiary">
          <span className="h-px flex-1 bg-hairline" />
          or
          <span className="h-px flex-1 bg-hairline" />
        </div>

        <form className="flex flex-col gap-3" onSubmit={submit}>
          <TextInput
            type="email"
            required
            autoComplete="email"
            aria-label="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value.trim())}
            placeholder="you@example.com"
          />
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

        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            className="text-text-secondary hover:text-text"
            onClick={onUseCode}
          >
            Email me a code instead
          </button>
          {mode === 'signin' && (
            <button
              type="button"
              className="text-text-secondary hover:text-text"
              onClick={onForgot}
            >
              Forgot password?
            </button>
          )}
        </div>

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

function CheckEmailNotice({ email }: { email: string }) {
  const { signUpWithEmail } = useAuth();
  const [resent, setResent] = useState(false);

  return (
    <div className="text-center">
      <h1 className="text-xl font-semibold">Check your email</h1>
      <p className="mt-2 text-sm text-text-secondary">
        We sent a verification link to <span className="text-text">{email}</span>. Click
        it to finish creating your account.
      </p>
      <p className="mt-6 text-sm text-text-tertiary">
        Didn't get it? Check spam, or{' '}
        <button
          type="button"
          className="text-text-secondary underline hover:text-text"
          onClick={async () => {
            // Re-issuing signUp for an unconfirmed address re-sends the link.
            try {
              await signUpWithEmail(email, crypto.randomUUID());
            } catch {
              /* already-registered / rate-limit are fine here */
            }
            setResent(true);
          }}
        >
          resend it
        </button>
        .
      </p>
      {resent && (
        <p className="mt-2 text-sm text-green">Sent — check your inbox again.</p>
      )}
    </div>
  );
}
function EnterCodeForm({
  email: initial,
  onBack,
}: {
  email: string;
  onBack: () => void;
}) {
  const { sendLoginCode, verifyLoginCode } = useAuth();
  const [email, setEmail] = useState(initial);
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    setBusy(true);
    try {
      await sendLoginCode(email);
      setSent(true);
    } catch (err) {
      setError((err as Error)?.message || 'Could not send a code. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await verifyLoginCode(email, code.trim());
    } catch {
      setError("That code didn't work or expired — send a new one.");
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">
        {sent ? 'Enter your code' : 'Email me a code'}
      </h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        {sent
          ? `We sent a 6-digit code to ${email}.`
          : 'We’ll email you a one-time login code.'}
      </p>

      {!sent ? (
        <form className="mt-8 flex flex-col gap-3" onSubmit={send}>
          <TextInput
            type="email"
            required
            autoComplete="email"
            aria-label="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value.trim())}
            placeholder="you@example.com"
          />
          <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
            {busy ? 'Sending…' : 'Send code'}
          </PillButton>
          {error && <p className="text-center text-sm text-red">{error}</p>}
        </form>
      ) : (
        <form className="mt-8 flex flex-col gap-3" onSubmit={verify}>
          <TextInput
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            aria-label="Login code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="123456"
          />
          <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
            {busy ? 'Verifying…' : 'Verify'}
          </PillButton>
          {error && <p className="text-center text-sm text-red">{error}</p>}
        </form>
      )}

      <button
        type="button"
        className="mt-6 w-full text-center text-sm text-text-secondary hover:text-text"
        onClick={onBack}
      >
        ← Back to sign in
      </button>
    </div>
  );
}
function ResetRequestForm({
  email: initial,
  onBack,
}: {
  email: string;
  onBack: () => void;
}) {
  const { sendPasswordReset } = useAuth();
  const [email, setEmail] = useState(initial);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    setBusy(true);
    try {
      await sendPasswordReset(email);
      setSent(true);
    } catch (err) {
      setError((err as Error)?.message || 'Could not send a reset link.');
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="text-center">
        <h1 className="text-xl font-semibold">Check your email</h1>
        <p className="mt-2 text-sm text-text-secondary">
          If <span className="text-text">{email}</span> has an account, a reset link is
          on its way.
        </p>
        <button
          type="button"
          className="mt-6 w-full text-center text-sm text-text-secondary hover:text-text"
          onClick={onBack}
        >
          ← Back to sign in
        </button>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Reset your password</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        We'll email you a link to set a new one.
      </p>
      <form className="mt-8 flex flex-col gap-3" onSubmit={submit}>
        <TextInput
          type="email"
          required
          autoComplete="email"
          aria-label="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value.trim())}
          placeholder="you@example.com"
        />
        <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
          {busy ? 'Sending…' : 'Send reset link'}
        </PillButton>
        {error && <p className="text-center text-sm text-red">{error}</p>}
      </form>
      <button
        type="button"
        className="mt-6 w-full text-center text-sm text-text-secondary hover:text-text"
        onClick={onBack}
      >
        ← Back to sign in
      </button>
    </div>
  );
}

function ResetPasswordStep() {
  const { setNewPassword } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError('Use a password of at least 6 characters.');
      return;
    }
    setBusy(true);
    try {
      await setNewPassword(password);
      // On success isPasswordRecovery clears and the normal flow resumes.
    } catch (err) {
      setError((err as Error)?.message || 'Could not update your password.');
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Set a new password</h1>
      <form className="mt-8 flex flex-col gap-3" onSubmit={submit}>
        <TextInput
          type="password"
          required
          minLength={6}
          autoComplete="new-password"
          aria-label="New password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 6 characters"
        />
        <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
          {busy ? 'Saving…' : 'Update password'}
        </PillButton>
        {error && <p className="text-center text-sm text-red">{error}</p>}
      </form>
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

/** Google's four-colour "G" mark. Inlined so the button needs no icon library
 * and no external asset (which a strict CSP would have to allow). */
function GoogleMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg text-text-secondary">
      {children}
    </div>
  );
}
