import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { ConnectLichessButton, NotAffiliated } from '../components/ConnectLichess';
import { TriangleMark } from '../components/ui/brand';
import { Checkbox, Field, Select, TextInput } from '../components/ui/Field';
import { Loader } from '../components/ui/Loader';
import { PillButton } from '../components/ui/PillButton';
import { StepProgress } from '../components/ui/StepProgress';
import { useLinks } from '../hooks/useLinks';
import { useMe } from '../hooks/useMe';
import { api } from '../lib/api';
import { clearReturnTo, peekReturnTo, takeReturnTo } from '../lib/returnTo';
import { emailToUsername } from '../lib/usernameAuth';
import { US_STATES, isExcludedState, stateName } from '../lib/usStates';

const USERNAME_RE = /^[a-z0-9_]{3,20}$/;

export function SignInPage() {
  const { session, loading, isPasswordRecovery } = useAuth();
  const me = useMe();
  const [postStep, setPostStep] = useState<'idle' | 'link'>('idle');

  if (loading || (session && me.isLoading && !me.isError)) {
    return <Loader />;
  }

  // Stale browser session (e.g. HS256 token while API expects JWKS) — drop it
  // and show the sign-in form instead of spinning forever.
  if (session && me.isError) {
    return (
      <div className="mm-grid-surface flex min-h-screen items-center justify-center bg-bg px-4">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center">
            <TriangleMark className="h-11 w-11" />
          </div>
          <StaleSessionStep />
        </div>
      </div>
    );
  }

  return (
    <div className="mm-grid-surface flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2">
          <TriangleMark className="h-11 w-11" />
          {session &&
            !isPasswordRecovery &&
            (me.data?.needs_onboarding || postStep === 'link') && (
              <StepProgress step={me.data?.needs_onboarding ? 1 : 2} total={2} />
            )}
        </div>

        {isPasswordRecovery ? (
          <ResetPasswordStep />
        ) : !session ? (
          <AuthStep />
        ) : me.data?.needs_onboarding ? (
          <OnboardingStep onDone={() => setPostStep('link')} />
        ) : postStep === 'link' ? (
          <LinkGameStep />
        ) : (
          <PostAuthRedirect />
        )}
      </div>
    </div>
  );
}

function PostAuthRedirect() {
  const to = peekReturnTo() ?? '/play';
  useEffect(() => clearReturnTo(), []);
  return <Navigate to={to} replace />;
}

/** Browser had a session the API rejects (stale / wrong signing scheme). */
function StaleSessionStep() {
  const { signOut } = useAuth();
  const [busy, setBusy] = useState(false);

  async function clearAndStay() {
    setBusy(true);
    await signOut();
  }

  return (
    <div>
      <AuthHeading
        title="Session expired"
        subtitle="Your saved sign-in is no longer valid. Sign in again."
      />
      <div className="mt-6 flex flex-col gap-3">
        <PillButton
          type="button"
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

type AuthView = 'credentials' | 'check-email' | 'reset-request';

function AuthStep() {
  const [view, setView] = useState<AuthView>('credentials');
  const [email, setEmail] = useState('');

  if (view === 'check-email') return <CheckEmailNotice email={email} />;
  if (view === 'reset-request')
    return <ResetRequestForm email={email} onBack={() => setView('credentials')} />;

  return (
    <CredentialsForm
      email={email}
      setEmail={setEmail}
      onNeedsVerification={() => setView('check-email')}
      onForgot={() => setView('reset-request')}
    />
  );
}

function CredentialsForm({
  email,
  setEmail,
  onNeedsVerification,
  onForgot,
}: {
  email: string;
  setEmail: (v: string) => void;
  onNeedsVerification: () => void;
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

  const canSubmit = !busy && email.length > 0 && password.length > 0;

  return (
    <div>
      <AuthHeading title={mode === 'signin' ? 'Sign in' : 'Create your account'} />
      <div className="mt-2 text-balance text-center text-sm text-text-secondary">
        <p>Chess, matched with someone at your skill level.</p>
        <p>
          Settles from Lichess in under a minute. No screenshots, no reviewers, no
          waiting.
        </p>
      </div>

      <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
        <Field label="Email">
          <TextInput
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value.trim())}
            placeholder="Enter your email"
          />
        </Field>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="signin-password"
              className="text-xs font-medium text-text-secondary"
            >
              Password
            </label>
            {mode === 'signin' && (
              <button
                type="button"
                className="text-xs text-text-tertiary hover:text-text-secondary"
                onClick={onForgot}
              >
                Forgot password?
              </button>
            )}
          </div>
          <TextInput
            id="signin-password"
            type="password"
            required
            minLength={6}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            aria-invalid={pwTooShort ? true : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
          />
          {pwTooShort && (
            <span className="text-xs text-red">
              Password must be at least 6 characters.
            </span>
          )}
        </div>

        <PillButton type="submit" variant="primary" fullWidth disabled={!canSubmit}>
          {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}
        </PillButton>
        {error && <p className="text-sm text-red">{error}</p>}
      </form>

      <Divider />

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

      <p className="mt-6 text-center text-sm text-text-secondary">
        {mode === 'signin'
          ? 'Need to create an account? '
          : 'Already have an account? '}
        <button
          type="button"
          className="font-medium text-text hover:underline"
          onClick={() => {
            setMode((m) => (m === 'signin' ? 'signup' : 'signin'));
            setError(null);
          }}
        >
          {mode === 'signin' ? 'Sign up' : 'Sign in'}
        </button>
      </p>

      <LegalFooter />
    </div>
  );
}

function CheckEmailNotice({ email }: { email: string }) {
  const { signUpWithEmail } = useAuth();
  const [resent, setResent] = useState(false);

  return (
    <div>
      <AuthHeading title="Check your email" />
      <p className="mt-3 text-sm text-text-secondary">
        We sent a verification link to <span className="text-text">{email}</span>. Click
        it to finish creating your account.
      </p>
      <p className="mt-6 text-sm text-text-tertiary">
        Didn't get it? Check spam, or{' '}
        <button
          type="button"
          className="text-text-secondary underline hover:text-text"
          onClick={async () => {
            try {
              await signUpWithEmail(email, crypto.randomUUID());
            } catch {
              // already-registered / rate-limit are fine here.
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
      <div>
        <AuthHeading title="Check your email" />
        <p className="mt-3 text-sm text-text-secondary">
          If <span className="text-text">{email}</span> has an account, a reset link is
          on its way.
        </p>
        <BackToSignIn onBack={onBack} />
      </div>
    );
  }

  return (
    <div>
      <AuthHeading
        title="Reset your password"
        subtitle="We'll email you a link to set a new one."
      />
      <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
        <Field label="Email">
          <TextInput
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value.trim())}
            placeholder="Enter your email"
          />
        </Field>
        <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
          {busy ? 'Sending…' : 'Send reset link'}
        </PillButton>
        {error && <p className="text-sm text-red">{error}</p>}
      </form>
      <BackToSignIn onBack={onBack} />
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
    } catch (err) {
      setError((err as Error)?.message || 'Could not update your password.');
      setBusy(false);
    }
  }

  return (
    <div>
      <AuthHeading title="Set a new password" />
      <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
        <Field label="New password">
          <TextInput
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 6 characters"
          />
        </Field>
        <PillButton type="submit" variant="primary" fullWidth disabled={busy}>
          {busy ? 'Saving…' : 'Update password'}
        </PillButton>
        {error && <p className="text-sm text-red">{error}</p>}
      </form>
    </div>
  );
}

function OnboardingStep({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const { session } = useAuth();
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
      <AuthHeading title="Your profile" />

      <form
        className="mt-6 flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        {derived ? (
          <p className="text-center text-sm text-text-secondary">
            Playing as <span className="font-medium text-text">{username}</span>
          </p>
        ) : (
          <Field label="Username" hint="3 to 20 lowercase letters, numbers or _.">
            <TextInput
              value={username}
              onChange={(e) => setUsername(e.target.value.toLowerCase())}
              placeholder="player_name"
            />
          </Field>
        )}

        <Field
          label="State of residence"
          hint={
            isExcludedState(state)
              ? `Staked matches aren't available in ${stateName(state)} yet. Free matches are.`
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

function LinkGameStep() {
  const navigate = useNavigate();
  const links = useLinks();
  const linked = links.data?.games.some((g) => g.status === 'LINKED') ?? false;

  if (linked) return <PostAuthRedirect />;

  return (
    <div>
      <AuthHeading
        title="Connect Lichess"
        subtitle="Your matches settle from your Lichess games."
      />
      <div className="mt-6 flex flex-col items-center gap-3">
        <ConnectLichessButton size="lg" fullWidth />
        <NotAffiliated />
      </div>
      <div className="mt-6 text-center">
        <button
          type="button"
          className="inline-flex touch:min-h-11 items-center text-sm text-text-secondary underline-offset-4 hover:text-text hover:underline"
          onClick={() => navigate(takeReturnTo() ?? '/play')}
        >
          Skip for now
        </button>
      </div>
    </div>
  );
}

function AuthHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="text-center">
      <h1 className="text-2xl font-semibold">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>}
    </div>
  );
}

function Divider() {
  return (
    <div className="my-5 flex items-center gap-3 text-xs text-text-tertiary">
      <span className="h-px flex-1 bg-hairline" />
      OR
      <span className="h-px flex-1 bg-hairline" />
    </div>
  );
}

function BackToSignIn({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      className="mt-6 text-sm text-text-secondary hover:text-text"
      onClick={onBack}
    >
      ← Back to sign in
    </button>
  );
}

function LegalFooter() {
  return (
    <p className="mt-5 text-balance text-center text-micro text-text-tertiary">
      By continuing you agree to our{' '}
      <LegalLink href="https://www.dueloro.com/terms">Terms</LegalLink>
      {' · '}
      <LegalLink href="https://www.dueloro.com/privacy">Privacy</LegalLink>
      {' · '}
      <LegalLink href="https://www.dueloro.com/responsible-gaming">
        Responsible Gaming
      </LegalLink>
      <span className="mt-1 block">Points have no cash value.</span>
    </p>
  );
}

function LegalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="whitespace-nowrap underline hover:text-text-secondary"
    >
      {children}
    </a>
  );
}

/**
 * Inlined so the button needs no icon library and no external asset (which a
 * strict CSP would have to allow).
 */
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
