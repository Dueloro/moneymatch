# Email Authentication + On-Brand Emails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace username-as-login with real email + password (one-time verify-on-signup), add passwordless email-code (OTP) login, and put every outbound email on one hybrid brand system.

**Architecture:** Supabase Auth owns verification tokens/flows; Resend (domain `send.dueloro.com`) is the SMTP transport configured in the Supabase dashboard. All app-logic changes are frontend-only — a verified Supabase user is just another JWT the API already provisions. The sign-in screen becomes a small explicit state machine. Email visuals (Supabase dashboard templates + our in-repo notification email) share one hybrid dark-band/light-body design.

**Tech Stack:** React 18 + TypeScript + Vite + TanStack Query (web), Vitest + Testing Library, `@supabase/supabase-js`, FastAPI + Resend via httpx (api), Supabase dashboard (SMTP + email templates).

**Spec:** `docs/superpowers/specs/2026-08-11-email-authentication-design.md`

---

## File Structure

**Frontend (app logic):**
- Modify `apps/web/src/auth/authContext.ts` — swap username methods for email-based ones; add `isPasswordRecovery`.
- Modify `apps/web/src/auth/AuthProvider.tsx` — implement the email/OTP/reset methods; track password-recovery.
- Modify `apps/web/src/pages/SignInPage.tsx` — rework `AuthStep` into a `credentials → check-email → enter-code → reset-request` machine + top-level `ResetPasswordStep`.
- Create `apps/web/src/auth/AuthProvider.test.tsx` — unit-test the new auth methods.
- Modify `apps/web/src/pages/SignInPage.test.tsx` — new email/OTP/reset UI assertions.
- Modify `apps/web/src/auth/RequireAuth.test.tsx` — update the auth mock shape.
- Modify `apps/web/src/pages/ProfilePage.test.tsx` — update the auth mock shape if it enumerates methods.
- Modify `apps/web/src/lib/usernameAuth.ts` — retire `usernameToEmail` for new signups; keep `emailToUsername` only if still referenced.

**Email brand assets:**
- Create `apps/web/public/email/logo.svg` — the lime mark on a dark lozenge (email source art).
- Create `apps/web/public/email/logo.png` — rasterized 240px logo referenced by absolute URL.
- Create `docs/email-templates/confirm-signup.html` — Supabase "Confirm signup" template (source of truth).
- Create `docs/email-templates/magic-link.html` — Supabase "Magic Link"/OTP template (shows the code).
- Create `docs/email-templates/reset-password.html` — Supabase "Reset password" template.
- Modify `apps/api/src/moneymatch_api/services/email_service.py` — restyle `_render_html` to the hybrid brand.
- Modify `apps/api/tests/test_email.py` — assert the branded markup.

**Operator docs:**
- Create `docs/email-auth-setup.md` — Supabase dashboard steps (SMTP, Confirm-email toggle, redirect URLs, template pasting).

---

## Task 1: Email-based auth context type

**Files:**
- Modify: `apps/web/src/auth/authContext.ts`

- [ ] **Step 1: Replace the username methods with email methods in the interface**

In `apps/web/src/auth/authContext.ts`, replace the `signInWithUsername` and `signUpWithUsername` members (and add the recovery flag) so the interface reads:

```ts
export interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  /** True when the session is the demo bypass (not a real Supabase account). */
  isDemo: boolean;
  /** True after arriving via a password-reset link (Supabase PASSWORD_RECOVERY);
   * the sign-in screen shows the set-new-password step while this holds. */
  isPasswordRecovery: boolean;
  /** Create an account with a real email + password. Resolves
   * `{ needsVerification: true }` when Supabase withholds the session pending
   * email confirmation (the expected first-time path), else `false`. */
  signUpWithEmail: (
    email: string,
    password: string,
  ) => Promise<{ needsVerification: boolean }>;
  /** Email + password sign-in for a verified account. */
  signInWithEmail: (email: string, password: string) => Promise<void>;
  /** Send a one-time login code to an existing account's email (no new account). */
  sendLoginCode: (email: string) => Promise<void>;
  /** Verify the emailed login code, establishing a session. */
  verifyLoginCode: (email: string, token: string) => Promise<void>;
  /** Email a password-reset link. */
  sendPasswordReset: (email: string) => Promise<void>;
  /** Set a new password for the recovery-authenticated session. */
  setNewPassword: (password: string) => Promise<void>;
  /** Start the Google OAuth flow (redirects away, only rejects in-page). */
  signInWithGoogle: () => Promise<void>;
  /** Confirm the signed-in account's current password (re-auth). */
  verifyCurrentPassword: (currentPassword: string) => Promise<boolean>;
  /** Set a new password for the signed-in Supabase account. */
  changePassword: (newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
}
```

- [ ] **Step 2: Verify the web build typechecks against the new type (it will fail until Task 2)**

Run: `cd apps/web && pnpm exec tsc --noEmit`
Expected: FAIL — `AuthProvider.tsx` no longer satisfies `AuthContextValue`. This confirms the type is the driver; Task 2 makes it pass.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/auth/authContext.ts
git commit -m "feat(auth): email-based auth context type"
```

---

## Task 2: AuthProvider email/OTP/reset methods

**Files:**
- Modify: `apps/web/src/auth/AuthProvider.tsx`
- Test: `apps/web/src/auth/AuthProvider.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/auth/AuthProvider.test.tsx`:

```tsx
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from './AuthProvider';
import { useAuth } from './useAuth';

// Mock the supabase client the provider wraps.
const auth = {
  getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
  onAuthStateChange: vi.fn().mockReturnValue({
    data: { subscription: { unsubscribe: vi.fn() } },
  }),
  signUp: vi.fn(),
  signInWithPassword: vi.fn(),
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
  signInWithOAuth: vi.fn(),
  signOut: vi.fn().mockResolvedValue({}),
};
vi.mock('./lib/supabase', () => ({}));
vi.mock('../lib/supabase', () => ({ supabase: { auth } }));
vi.mock('../lib/telemetry', () => ({
  identify: vi.fn(),
  resetIdentity: vi.fn(),
}));

const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

describe('AuthProvider email methods', () => {
  beforeEach(() => vi.clearAllMocks());

  it('signUpWithEmail reports needsVerification when no session returns', async () => {
    auth.signUp.mockResolvedValue({ data: { session: null }, error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    let out!: { needsVerification: boolean };
    await act(async () => {
      out = await result.current.signUpWithEmail('a@b.com', 'secret6');
    });
    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'a@b.com',
      password: 'secret6',
      options: { emailRedirectTo: `${window.location.origin}/signin` },
    });
    expect(out.needsVerification).toBe(true);
  });

  it('sendLoginCode requests an OTP without creating a user', async () => {
    auth.signInWithOtp.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.sendLoginCode('a@b.com'));
    expect(auth.signInWithOtp).toHaveBeenCalledWith({
      email: 'a@b.com',
      options: { shouldCreateUser: false },
    });
  });

  it('verifyLoginCode verifies the emailed token', async () => {
    auth.verifyOtp.mockResolvedValue({ error: null });
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.verifyLoginCode('a@b.com', '123456'));
    expect(auth.verifyOtp).toHaveBeenCalledWith({
      email: 'a@b.com',
      token: '123456',
      type: 'email',
    });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/auth/AuthProvider.test.tsx`
Expected: FAIL — `signUpWithEmail`/`sendLoginCode`/`verifyLoginCode` are not functions.

- [ ] **Step 3: Implement the methods**

In `apps/web/src/auth/AuthProvider.tsx`: (a) remove the `usernameToEmail` import; (b) add a `passwordRecovery` state; (c) set it in the `onAuthStateChange` handler; (d) replace the `signInWithUsername`/`signUpWithUsername` entries in the `value` object.

Add state near the top of `AuthProvider`:

```tsx
const [passwordRecovery, setPasswordRecovery] = useState(false);
```

In the existing `onAuthStateChange` callback, extend it to observe the event:

```tsx
const { data: sub } = supabase.auth.onAuthStateChange((event, next) => {
  setSession(next);
  if (event === 'PASSWORD_RECOVERY') setPasswordRecovery(true);
  if (next) identify(next.user.id);
  else resetIdentity();
});
```

Replace the two username members in the `value` object with:

```tsx
isPasswordRecovery: passwordRecovery,
signUpWithEmail: async (email: string, password: string) => {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${window.location.origin}/signin` },
  });
  if (error) throw error;
  // With "Confirm email" on, signUp returns no session until the link is
  // clicked — that is the expected first-time path, not an error.
  return { needsVerification: data.session === null };
},
signInWithEmail: async (email: string, password: string) => {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
},
sendLoginCode: async (email: string) => {
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { shouldCreateUser: false },
  });
  if (error) throw error;
},
verifyLoginCode: async (email: string, token: string) => {
  const { error } = await supabase.auth.verifyOtp({ email, token, type: 'email' });
  if (error) throw error;
},
sendPasswordReset: async (email: string) => {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${window.location.origin}/signin`,
  });
  if (error) throw error;
},
setNewPassword: async (password: string) => {
  const { error } = await supabase.auth.updateUser({ password });
  if (error) throw error;
  setPasswordRecovery(false);
},
```

Add `passwordRecovery` to the `useMemo` dependency array: `[session, loading, passwordRecovery]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm exec vitest run src/auth/AuthProvider.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/auth/AuthProvider.tsx apps/web/src/auth/AuthProvider.test.tsx
git commit -m "feat(auth): email, OTP, and password-reset provider methods"
```

---

## Task 3: Retire the username→synthetic-email seam

**Files:**
- Modify: `apps/web/src/lib/usernameAuth.ts`

- [ ] **Step 1: Check remaining references**

Run: `cd apps/web && grep -rn "usernameToEmail\|emailToUsername" src`
Expected: `usernameToEmail` only in `usernameAuth.ts` (AuthProvider no longer imports it after Task 2). `emailToUsername` may still be used by `SignInPage.tsx` onboarding.

- [ ] **Step 2: Remove `usernameToEmail`; keep `emailToUsername` only if referenced**

If `emailToUsername` has no references outside its own file, delete the whole file and remove any import. Otherwise, delete only the `usernameToEmail` function and the `AUTH_EMAIL_DOMAIN` export it needs, leaving `emailToUsername`. After editing, the file (if kept) is:

```ts
// Synthetic-email addresses (@users.moneymatch.app) backed the retired
// username-as-login scheme. Real email is now the credential; this helper only
// recognises a leftover synthetic address so onboarding never treats it as a
// real handle source.
const AUTH_EMAIL_DOMAIN = 'users.moneymatch.app';

/** Recover the username from a legacy synthetic email, or null for a real one. */
export function emailToUsername(email: string | null | undefined): string | null {
  if (!email) return null;
  const suffix = `@${AUTH_EMAIL_DOMAIN}`;
  const lower = email.toLowerCase();
  return lower.endsWith(suffix) ? lower.slice(0, -suffix.length) : null;
}
```

- [ ] **Step 3: Verify typecheck (SignInPage still references old names until Task 4)**

Run: `cd apps/web && pnpm exec tsc --noEmit`
Expected: FAIL only in `SignInPage.tsx` (still uses `signInWithUsername` etc.). Task 4 resolves it.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/usernameAuth.ts
git commit -m "refactor(auth): retire username->synthetic-email seam"
```

---

## Task 4: Sign-in screen — credentials state (email + password)

**Files:**
- Modify: `apps/web/src/pages/SignInPage.tsx`
- Test: `apps/web/src/pages/SignInPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Replace the body of `apps/web/src/pages/SignInPage.test.tsx`'s auth mock and the first tests. Update the mock in `beforeEach` to the new shape and add email-form assertions:

```tsx
mockUseAuth.mockReturnValue({
  session: null,
  loading: false,
  isDemo: false,
  isPasswordRecovery: false,
  signUpWithEmail: vi.fn(),
  signInWithEmail,
  sendLoginCode: vi.fn(),
  verifyLoginCode: vi.fn(),
  sendPasswordReset: vi.fn(),
  setNewPassword: vi.fn(),
  signInWithGoogle,
  verifyCurrentPassword: vi.fn(),
  changePassword: vi.fn(),
  signOut: vi.fn(),
});
```

Declare `const signInWithEmail = vi.fn();` at module scope (replacing `signInWithUsername`) and reset it in `beforeEach`. Replace the username-specific tests with:

```tsx
it('renders email + password with Google and demo options', () => {
  renderWithProviders(<SignInPage />, { route: '/signin' });
  expect(
    screen.getByRole('button', { name: /continue with google/i }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('Email')).toBeInTheDocument();
  expect(screen.getByLabelText('Password')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /enter the demo/i })).toBeInTheDocument();
});

it('signs in with email + password', async () => {
  signInWithEmail.mockResolvedValue(undefined);
  renderWithProviders(<SignInPage />, { route: '/signin' });
  await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'longenough');
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(signInWithEmail).toHaveBeenCalledWith('kv@example.com', 'longenough');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx`
Expected: FAIL — no `Email` label; `signInWithEmail` not wired.

- [ ] **Step 3: Rewrite `AuthStep` as a state machine with the credentials view**

In `apps/web/src/pages/SignInPage.tsx`, replace the entire `AuthStep` function. Remove the username regex/`usernameProblem` helpers and the `emailToUsername` import usage in `AuthStep` (onboarding keeps `emailToUsername`). New `AuthStep`:

```tsx
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
```

Update `friendlyAuthError` copy to email terms (replace the username-specific branches):

```tsx
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
```

Add the stub sub-components (fully implemented in Tasks 5–7) so the file compiles now:

```tsx
function CheckEmailNotice(_: { email: string }) {
  return <div />;
}
function EnterCodeForm(_: { email: string; onBack: () => void }) {
  return <div />;
}
function ResetRequestForm(_: { email: string; onBack: () => void }) {
  return <div />;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx`
Expected: PASS for the credentials tests.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/SignInPage.tsx apps/web/src/pages/SignInPage.test.tsx
git commit -m "feat(auth): email+password credentials sign-in view"
```

---

## Task 5: Check-your-email + resend

**Files:**
- Modify: `apps/web/src/pages/SignInPage.tsx`
- Test: `apps/web/src/pages/SignInPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `SignInPage.test.tsx`:

```tsx
it('shows check-your-email after a signup that needs verification', async () => {
  const signUpWithEmail = vi.fn().mockResolvedValue({ needsVerification: true });
  mockUseAuth.mockReturnValue({
    ...mockUseAuth.mock.results[0]?.value,
    session: null,
    loading: false,
    isDemo: false,
    isPasswordRecovery: false,
    signUpWithEmail,
    signInWithEmail,
    sendLoginCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    sendPasswordReset: vi.fn(),
    setNewPassword: vi.fn(),
    signInWithGoogle,
    verifyCurrentPassword: vi.fn(),
    changePassword: vi.fn(),
    signOut: vi.fn(),
  });
  renderWithProviders(<SignInPage />, { route: '/signin' });
  await userEvent.click(screen.getByRole('button', { name: /create an account/i }));
  await userEvent.type(screen.getByLabelText('Email'), 'new@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'longenough');
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
  expect(screen.getByText(/new@example.com/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx -t "check-your-email"`
Expected: FAIL — the notice renders an empty `<div />`.

- [ ] **Step 3: Implement `CheckEmailNotice`**

Replace the `CheckEmailNotice` stub in `SignInPage.tsx`:

```tsx
function CheckEmailNotice({ email }: { email: string }) {
  const { signUpWithEmail } = useAuth();
  const [resent, setResent] = useState(false);

  return (
    <div className="text-center">
      <h1 className="text-xl font-semibold">Check your email</h1>
      <p className="mt-2 text-sm text-text-secondary">
        We sent a verification link to <span className="text-text">{email}</span>.
        Click it to finish creating your account.
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/SignInPage.tsx apps/web/src/pages/SignInPage.test.tsx
git commit -m "feat(auth): check-your-email verification notice"
```

---

## Task 6: Passwordless email-code (OTP) login

**Files:**
- Modify: `apps/web/src/pages/SignInPage.tsx`
- Test: `apps/web/src/pages/SignInPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `SignInPage.test.tsx`:

```tsx
it('sends and verifies an email login code', async () => {
  const sendLoginCode = vi.fn().mockResolvedValue(undefined);
  const verifyLoginCode = vi.fn().mockResolvedValue(undefined);
  mockUseAuth.mockReturnValue({
    session: null,
    loading: false,
    isDemo: false,
    isPasswordRecovery: false,
    signUpWithEmail: vi.fn(),
    signInWithEmail,
    sendLoginCode,
    verifyLoginCode,
    sendPasswordReset: vi.fn(),
    setNewPassword: vi.fn(),
    signInWithGoogle,
    verifyCurrentPassword: vi.fn(),
    changePassword: vi.fn(),
    signOut: vi.fn(),
  });
  renderWithProviders(<SignInPage />, { route: '/signin' });
  await userEvent.click(screen.getByRole('button', { name: /email me a code/i }));
  await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
  await userEvent.click(screen.getByRole('button', { name: /send code/i }));
  expect(sendLoginCode).toHaveBeenCalledWith('kv@example.com');
  await userEvent.type(await screen.findByLabelText(/code/i), '123456');
  await userEvent.click(screen.getByRole('button', { name: /verify/i }));
  expect(verifyLoginCode).toHaveBeenCalledWith('kv@example.com', '123456');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx -t "email login code"`
Expected: FAIL — `EnterCodeForm` renders an empty `<div />`.

- [ ] **Step 3: Implement `EnterCodeForm`**

Replace the `EnterCodeForm` stub in `SignInPage.tsx`:

```tsx
function EnterCodeForm({ email: initial, onBack }: { email: string; onBack: () => void }) {
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/SignInPage.tsx apps/web/src/pages/SignInPage.test.tsx
git commit -m "feat(auth): passwordless email-code login"
```

---

## Task 7: Password reset (request + set-new-password)

**Files:**
- Modify: `apps/web/src/pages/SignInPage.tsx`
- Test: `apps/web/src/pages/SignInPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add to `SignInPage.test.tsx`:

```tsx
it('requests a password reset email', async () => {
  const sendPasswordReset = vi.fn().mockResolvedValue(undefined);
  mockUseAuth.mockReturnValue({
    session: null,
    loading: false,
    isDemo: false,
    isPasswordRecovery: false,
    signUpWithEmail: vi.fn(),
    signInWithEmail,
    sendLoginCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    sendPasswordReset,
    setNewPassword: vi.fn(),
    signInWithGoogle,
    verifyCurrentPassword: vi.fn(),
    changePassword: vi.fn(),
    signOut: vi.fn(),
  });
  renderWithProviders(<SignInPage />, { route: '/signin' });
  await userEvent.click(screen.getByRole('button', { name: /forgot password/i }));
  await userEvent.type(screen.getByLabelText('Email'), 'kv@example.com');
  await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));
  expect(sendPasswordReset).toHaveBeenCalledWith('kv@example.com');
  expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
});

it('shows set-new-password when in recovery', async () => {
  const setNewPassword = vi.fn().mockResolvedValue(undefined);
  mockUseAuth.mockReturnValue({
    session: { user: { id: 'u1' } } as never,
    loading: false,
    isDemo: false,
    isPasswordRecovery: true,
    signUpWithEmail: vi.fn(),
    signInWithEmail,
    sendLoginCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    sendPasswordReset: vi.fn(),
    setNewPassword,
    signInWithGoogle,
    verifyCurrentPassword: vi.fn(),
    changePassword: vi.fn(),
    signOut: vi.fn(),
  });
  mockUseMe.mockReturnValue({ data: undefined, isLoading: false } as ReturnType<
    typeof useMe
  >);
  renderWithProviders(<SignInPage />, { route: '/signin' });
  await userEvent.type(screen.getByLabelText(/new password/i), 'brandnew1');
  await userEvent.click(screen.getByRole('button', { name: /update password/i }));
  expect(setNewPassword).toHaveBeenCalledWith('brandnew1');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx -t "password reset"`
Expected: FAIL — `ResetRequestForm` is empty and no recovery branch exists.

- [ ] **Step 3: Implement `ResetRequestForm`, `ResetPasswordStep`, and wire the recovery branch**

Replace the `ResetRequestForm` stub in `SignInPage.tsx`:

```tsx
function ResetRequestForm({ email: initial, onBack }: { email: string; onBack: () => void }) {
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
          If <span className="text-text">{email}</span> has an account, a reset
          link is on its way.
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
```

Wire the recovery branch at the top of the `SignInPage` component's return, before the `!session ? ...` ladder. Add `const { session, loading, isPasswordRecovery } = useAuth();` (extend the existing destructure) and, inside the outer wrapper where `AuthStep`/onboarding render, branch first on recovery:

```tsx
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && pnpm exec vitest run src/pages/SignInPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/SignInPage.tsx apps/web/src/pages/SignInPage.test.tsx
git commit -m "feat(auth): password reset request and set-new-password"
```

---

## Task 8: Fix the remaining auth mocks + full web suite

**Files:**
- Modify: `apps/web/src/auth/RequireAuth.test.tsx`
- Modify: `apps/web/src/pages/ProfilePage.test.tsx` (only if it enumerates auth methods)

- [ ] **Step 1: Update `RequireAuth.test.tsx` mocks**

In both `mockUseAuth.mockReturnValue({...})` blocks, replace the `signInWithUsername`/`signUpWithUsername` lines with the new method set:

```tsx
      isPasswordRecovery: false,
      signUpWithEmail: vi.fn(),
      signInWithEmail: vi.fn(),
      sendLoginCode: vi.fn(),
      verifyLoginCode: vi.fn(),
      sendPasswordReset: vi.fn(),
      setNewPassword: vi.fn(),
      signInWithGoogle: vi.fn(),
      verifyCurrentPassword: vi.fn(),
      changePassword: vi.fn(),
```

(Keep the existing `session`, `loading`, `isDemo`, `signOut` lines.)

- [ ] **Step 2: Check ProfilePage mock**

Run: `cd apps/web && grep -n "signInWithUsername\|signUpWithUsername\|as unknown as ReturnType<typeof useAuth>" src/pages/ProfilePage.test.tsx`
If it casts via `as unknown as ReturnType<typeof useAuth>`, no change is needed. If it enumerates the old methods, replace them with the set from Step 1.

- [ ] **Step 3: Run the full web suite + typecheck**

Run: `cd apps/web && pnpm exec tsc --noEmit && pnpm exec vitest run`
Expected: PASS — 0 type errors, all suites green.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/auth/RequireAuth.test.tsx apps/web/src/pages/ProfilePage.test.tsx
git commit -m "test(auth): update auth mocks to the email context shape"
```

---

## Task 9: Email logo asset

**Files:**
- Create: `apps/web/public/email/logo.svg`
- Create: `apps/web/public/email/logo.png`

- [ ] **Step 1: Create the SVG source art**

Create `apps/web/public/email/logo.svg` — the lime triangle on a dark rounded lozenge (mirrors the in-app `TriangleMark`), sized for a 2× raster:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" viewBox="0 0 240 240">
  <rect width="240" height="240" rx="52" fill="#0B0B0C"/>
  <path d="M120 66 205 216a10 10 0 0 1-8.7 15H43.7A10 10 0 0 1 35 216L120 66Z" fill="#C6F440"/>
</svg>
```

- [ ] **Step 2: Rasterize to PNG**

Run (one-off; `sharp-cli` is fetched transiently, not added as a dependency):

```bash
cd apps/web/public/email && npx --yes sharp-cli -i logo.svg -o logo.png resize 240 240
```

Expected: `logo.png` created (~a few KB). Verify: `file logo.png` reports "PNG image data, 240 x 240".

- [ ] **Step 3: Commit**

```bash
git add apps/web/public/email/logo.svg apps/web/public/email/logo.png
git commit -m "feat(email): add hybrid-brand email logo asset"
```

---

## Task 10: Restyle the notification email to the hybrid brand

**Files:**
- Modify: `apps/api/src/moneymatch_api/services/email_service.py`
- Test: `apps/api/tests/test_email.py`

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_email.py`:

```python
async def test_html_uses_hybrid_brand(session, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "web_origin", "https://moneymatch-beta.vercel.app")
    user = await _make_user(session, email="real@example.com")
    with respx.mock:
        route = respx.post(email_service._RESEND_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "e1"})
        )
        await email_service.send_to_user(
            session, user.id, subject="Your contest settled",
            body="Your result is in.", link_path="/activity",
        )
    html = json.loads(route.calls.last.request.content)["html"]
    # Brand: hosted logo, the lime CTA, and the Dueloro support footer.
    assert "/email/logo.png" in html
    assert "Open Money Match" in html
    assert "Dueloro" in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/api && TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' uv run pytest tests/test_email.py::test_html_uses_hybrid_brand -q`
Expected: FAIL — current `_render_html` has no logo/footer.

- [ ] **Step 3: Implement the hybrid `_render_html`**

Replace `_render_html` in `apps/api/src/moneymatch_api/services/email_service.py`. Add a module constant for the logo near the endpoint constant:

```python
# Hosted email logo (Decision B — beta domain for now; one-line change later).
_LOGO_URL = "https://moneymatch-beta.vercel.app/email/logo.png"
```

```python
def _render_html(body: str, url: str | None) -> str:
    """Hybrid-brand HTML: dark header/footer bands with the lime mark, light body,
    lime CTA. Table-based + inline styles for email-client reliability."""
    button = (
        f'<tr><td style="padding:8px 0 4px"><a href="{url}" '
        'style="display:inline-block;background:#C6F440;color:#0B0B0C;'
        'padding:12px 22px;border-radius:9999px;text-decoration:none;'
        'font-weight:700;font-size:15px">Open Money Match</a></td></tr>'
        if url
        else ""
    )
    fallback = (
        f'<tr><td style="padding:12px 0 0;font-size:12px;color:#6b7280">'
        f'Button not working? Paste this link: <br>{url}</td></tr>'
        if url
        else ""
    )
    return (
        '<div style="background:#f3f4f6;padding:24px 0;'
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:600px;margin:0 auto;background:#ffffff;'
        'border-radius:16px;overflow:hidden">'
        # Dark header band with the mark + wordmark.
        '<tr><td style="background:#0B0B0C;padding:20px 28px">'
        f'<img src="{_LOGO_URL}" width="28" height="28" alt="Money Match" '
        'style="vertical-align:middle;border-radius:8px">'
        '<span style="color:#ffffff;font-weight:600;font-size:15px;'
        'vertical-align:middle;margin-left:10px">Money Match</span>'
        '</td></tr>'
        # Light body.
        '<tr><td style="padding:28px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="font-size:16px;line-height:1.5;color:#111827">{body}</td></tr>'
        f"{button}{fallback}"
        '</table></td></tr>'
        # Dark footer band.
        '<tr><td style="background:#0B0B0C;padding:16px 28px;font-size:12px;'
        'color:#9ca3af">Money Match · peer-to-peer skill wagering<br>'
        'Need help? Contact Dueloro Support.</td></tr>'
        '</table></div>'
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && TEST_DATABASE_URL='postgresql+asyncpg://moneymatch:moneymatch@localhost:5433/moneymatch_test' uv run pytest tests/test_email.py -q`
Expected: PASS (all email tests).

- [ ] **Step 5: Lint + commit**

Run: `cd apps/api && uv run ruff check src/moneymatch_api/services/email_service.py`
Expected: All checks passed.

```bash
git add apps/api/src/moneymatch_api/services/email_service.py apps/api/tests/test_email.py
git commit -m "feat(email): hybrid-brand notification email template"
```

---

## Task 11: Supabase auth email templates (source of truth in repo)

**Files:**
- Create: `docs/email-templates/confirm-signup.html`
- Create: `docs/email-templates/magic-link.html`
- Create: `docs/email-templates/reset-password.html`

These are the exact HTML bodies to paste into Supabase → Auth → Email Templates. They use Supabase template variables and the same hybrid brand as Task 10.

- [ ] **Step 1: Create `docs/email-templates/confirm-signup.html`**

```html
<div style="background:#f3f4f6;padding:24px 0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden">
    <tr><td style="background:#0B0B0C;padding:20px 28px">
      <img src="https://moneymatch-beta.vercel.app/email/logo.png" width="28" height="28" alt="Money Match" style="vertical-align:middle;border-radius:8px">
      <span style="color:#ffffff;font-weight:600;font-size:15px;vertical-align:middle;margin-left:10px">Money Match</span>
    </td></tr>
    <tr><td style="padding:28px;color:#111827">
      <h1 style="margin:0 0 8px;font-size:20px">Verify your email</h1>
      <p style="margin:0 0 20px;font-size:16px;line-height:1.5;color:#374151">You're almost in. Confirm this address to finish creating your Money Match account and start playing.</p>
      <a href="{{ .ConfirmationURL }}" style="display:inline-block;background:#C6F440;color:#0B0B0C;padding:12px 22px;border-radius:9999px;text-decoration:none;font-weight:700;font-size:15px">Verify my email</a>
      <p style="margin:20px 0 0;font-size:12px;color:#6b7280">Button not working? Paste this link:<br>{{ .ConfirmationURL }}</p>
      <p style="margin:16px 0 0;font-size:12px;color:#6b7280">Didn't create an account? You can ignore this email.</p>
    </td></tr>
    <tr><td style="background:#0B0B0C;padding:16px 28px;font-size:12px;color:#9ca3af">Money Match · peer-to-peer skill wagering<br>Need help? Contact Dueloro Support.</td></tr>
  </table>
</div>
```

- [ ] **Step 2: Create `docs/email-templates/magic-link.html`** (OTP — surfaces `{{ .Token }}`)

```html
<div style="background:#f3f4f6;padding:24px 0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden">
    <tr><td style="background:#0B0B0C;padding:20px 28px">
      <img src="https://moneymatch-beta.vercel.app/email/logo.png" width="28" height="28" alt="Money Match" style="vertical-align:middle;border-radius:8px">
      <span style="color:#ffffff;font-weight:600;font-size:15px;vertical-align:middle;margin-left:10px">Money Match</span>
    </td></tr>
    <tr><td style="padding:28px;color:#111827">
      <h1 style="margin:0 0 8px;font-size:20px">Your login code</h1>
      <p style="margin:0 0 16px;font-size:16px;line-height:1.5;color:#374151">Enter this code to sign in. It expires shortly and is good for one use.</p>
      <div style="font-size:30px;font-weight:800;letter-spacing:8px;color:#0B0B0C;background:#F3F7E6;border-radius:12px;padding:14px 0;text-align:center">{{ .Token }}</div>
      <p style="margin:16px 0 0;font-size:12px;color:#6b7280">Didn't try to sign in? You can ignore this email.</p>
    </td></tr>
    <tr><td style="background:#0B0B0C;padding:16px 28px;font-size:12px;color:#9ca3af">Money Match · peer-to-peer skill wagering<br>Need help? Contact Dueloro Support.</td></tr>
  </table>
</div>
```

- [ ] **Step 3: Create `docs/email-templates/reset-password.html`**

```html
<div style="background:#f3f4f6;padding:24px 0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden">
    <tr><td style="background:#0B0B0C;padding:20px 28px">
      <img src="https://moneymatch-beta.vercel.app/email/logo.png" width="28" height="28" alt="Money Match" style="vertical-align:middle;border-radius:8px">
      <span style="color:#ffffff;font-weight:600;font-size:15px;vertical-align:middle;margin-left:10px">Money Match</span>
    </td></tr>
    <tr><td style="padding:28px;color:#111827">
      <h1 style="margin:0 0 8px;font-size:20px">Reset your password</h1>
      <p style="margin:0 0 20px;font-size:16px;line-height:1.5;color:#374151">Click below to choose a new password. If you didn't ask for this, you can safely ignore it — your password won't change.</p>
      <a href="{{ .ConfirmationURL }}" style="display:inline-block;background:#C6F440;color:#0B0B0C;padding:12px 22px;border-radius:9999px;text-decoration:none;font-weight:700;font-size:15px">Set a new password</a>
      <p style="margin:20px 0 0;font-size:12px;color:#6b7280">Button not working? Paste this link:<br>{{ .ConfirmationURL }}</p>
    </td></tr>
    <tr><td style="background:#0B0B0C;padding:16px 28px;font-size:12px;color:#9ca3af">Money Match · peer-to-peer skill wagering<br>Need help? Contact Dueloro Support.</td></tr>
  </table>
</div>
```

- [ ] **Step 4: Commit**

```bash
git add docs/email-templates
git commit -m "docs(email): hybrid-brand Supabase auth email templates"
```

---

## Task 12: Operator setup doc

**Files:**
- Create: `docs/email-auth-setup.md`

- [ ] **Step 1: Write the setup doc**

Create `docs/email-auth-setup.md`:

```markdown
# Email auth — Supabase dashboard setup

The app code and email templates ship in the repo; these dashboard steps turn on
real email auth. **Prerequisite:** `send.dueloro.com` is verified in Resend.

## 1. Custom SMTP (Resend)
Auth → Settings → SMTP Settings → enable Custom SMTP:
- Host: `smtp.resend.com`
- Port: `465` (implicit TLS) or `587`
- Username: `resend`
- Password: a Resend API key (Sending access)
- Sender name: `Money Match`
- Sender email: `noreply@send.dueloro.com`

## 2. Confirm email
Auth → Providers → Email → enable **Confirm email**. Leave email OTP enabled
(default) so the login-code flow works.

## 3. URL configuration
Auth → URL Configuration:
- Site URL: `https://moneymatch-beta.vercel.app`
- Redirect URLs: add `http://localhost:5173/**` and
  `https://moneymatch-beta.vercel.app/**`

## 4. Email templates
Auth → Email Templates — paste the bodies from `docs/email-templates/`:
- **Confirm signup** ← `confirm-signup.html`
- **Magic Link** ← `magic-link.html` (must include `{{ .Token }}`)
- **Reset Password** ← `reset-password.html`

## 5. Verify
Sign up locally with a real address → receive the branded verify email → confirm
→ land in onboarding. Test "Email me a code" and "Forgot password?" similarly.
```

- [ ] **Step 2: Commit**

```bash
git add docs/email-auth-setup.md
git commit -m "docs(email): Supabase dashboard setup for email auth"
```

---

## Self-Review

**Spec coverage:**
- Email replaces username → Tasks 1–4, 8.
- Verify-on-signup + check-email → Tasks 2, 5.
- Email-code (OTP) login → Tasks 1, 2, 6.
- Password reset → Tasks 1, 2, 7.
- Supabase SMTP + dashboard templates → Tasks 11, 12.
- Hybrid brand across auth emails + notification email + logo → Tasks 9, 10, 11.
- Decision A (no legacy migration) → Task 3 retires the seam; no legacy UI (as designed).
- Decision B (logo on beta domain) → Task 9 + `_LOGO_URL`/template URLs.
- No backend change → confirmed; only `email_service` HTML changes.

**Placeholder scan:** No TBD/TODO; every code step shows full code; the `emailToUsername` keep/delete choice in Task 3 is gated on a concrete `grep`, not left vague.

**Type consistency:** Method names match across tasks — `signUpWithEmail` (returns `{ needsVerification }`), `signInWithEmail`, `sendLoginCode`, `verifyLoginCode`, `sendPasswordReset`, `setNewPassword`, `isPasswordRecovery` — identical in `authContext.ts` (Task 1), `AuthProvider.tsx` (Task 2), and every test mock (Tasks 4–8). Endpoint/constant names (`_RESEND_ENDPOINT`, `_LOGO_URL`) consistent between Task 10 code and tests.

**Blocker:** live sending waits on `send.dueloro.com` DNS verification — all tasks are buildable and testable without it (Vitest mocks Supabase; pytest mocks Resend via respx).
```
