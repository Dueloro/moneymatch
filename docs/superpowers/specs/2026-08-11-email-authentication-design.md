# Email authentication + on-brand emails — design

**Date:** 2026-08-11
**Status:** Approved (brainstorming), pending implementation plan
**Author:** brainstorming session (Shreyansh + Claude)

## Summary

Reactivate real email-based account creation with a one-time "verify your email"
step, add passwordless email-code (OTP) login as a second sign-in method, and put
every outbound email on one consistent brand system. Supabase Auth owns the
verification tokens and flows; Resend (already integrated, sending domain
`send.dueloro.com`) is the delivery transport via Supabase Custom SMTP.

## Locked decisions

1. **Email replaces username as the login credential.** The username becomes a
   display-only handle chosen during onboarding (onboarding already prompts for
   one when the email is real). Existing username-only accounts are not migrated
   (see Decision A).
2. **Supabase owns verification; delivery via Resend SMTP; templates in the
   Supabase dashboard.** We do not re-implement token generation/verification.
3. **Two credential methods this phase:** email + password, *and* passwordless
   email-code (OTP). Plus the existing Google sign-in.
4. **Hybrid email visual style:** dark header/footer bands carrying the lime mark;
   light, readable body; lime CTA button. Chosen for brand fidelity + reliable
   rendering across email clients (incl. dark mode).

## Confirmed decisions

- **Decision A — legacy username accounts:** Accepted. Old username-only accounts
  (synthetic `@users.moneymatch.app` addresses) cannot sign in through the new
  email form. On beta (play-money, demo-driven) there are ~none, and Google/demo
  entry are unaffected. No legacy-login UI will be built. Revisit only if real
  legacy accounts surface.
- **Decision B — logo hosting:** Host the email logo PNG at
  `https://moneymatch-beta.vercel.app/email/logo.png` for now (served from
  `apps/web/public/email/logo.png`). Move to a permanent brand domain later; the
  URL is defined in one place so it is a one-line change.

## Blocker (external, not in scope)

Live sending requires `send.dueloro.com` to be DNS-verified in Resend (SPF/DKIM),
which is pending someone adding the DNS records. All code and templates can be
built and reviewed now; emails begin flowing the moment the domain verifies.
Supabase Custom SMTP will also refuse to send from an unverified sender domain
until then.

## User-facing flows

### Sign up (new account)
1. User enters email + password on the sign-in screen (sign-up mode).
2. `supabase.auth.signUp({ email, password, options: { emailRedirectTo } })`.
   With "Confirm email" on, this returns **no session** — the client shows a
   **"Check your email"** state (with a resend control), it does not treat the
   missing session as an error (current behavior throws
   `email_confirmation_required`; that path is replaced by this state).
3. User clicks the verification link → Supabase confirms → redirects to
   `‹origin›/signin` with a session in the URL (`detectSessionInUrl` adopts it).
4. New user has no username → onboarding (username, residence state, 18+) → app.

### Sign in — password
1. Email + password → `signInWithPassword`.
2. On success the session updates and the screen advances (onboarding if needed,
   else the app). Unverified/invalid credentials map to friendly copy.

### Sign in — email code (OTP)
1. User toggles "Use a login code instead", enters email → `signInWithOtp({ email,
   options: { shouldCreateUser: false } })` sends a 6-digit code.
2. Client shows an **enter-code** state → `verifyOtp({ email, token, type: 'email'
   })` → session → advance.

### Forgot / reset password
1. "Forgot password?" → enter email → `resetPasswordForEmail(email, {
   redirectTo: ‹origin›/signin })`.
2. Reset link returns to the app with a recovery session → **set-new-password**
   state → `updateUser({ password })` → signed in.

## Components & changes

### Frontend (app logic — no backend change)

- **`apps/web/src/auth/authContext.ts` + `AuthProvider.tsx`:** replace the
  username methods with email-based ones:
  - `signUpWithEmail(email, password)` — returns a discriminant of
    `{ needsVerification: true }` vs signed-in, so the UI can branch to
    "check your email" without treating no-session as an error.
  - `signInWithEmail(email, password)`
  - `sendLoginCode(email)` (`signInWithOtp`)
  - `verifyLoginCode(email, token)` (`verifyOtp`)
  - `sendPasswordReset(email)` (`resetPasswordForEmail`)
  - `setNewPassword(password)` (`updateUser`)
  - `signInWithGoogle` — unchanged.
  - `verifyCurrentPassword` / `changePassword` — retained (profile page uses them),
    keyed on the real email now.
- **`apps/web/src/lib/usernameAuth.ts`:** the `usernameToEmail` synthetic-email
  seam is retired for new sign-ups. `emailToUsername` may be removed once the
  onboarding no longer derives a handle from a synthetic address (it already
  falls back to an editable field for real emails). Keep or delete based on
  remaining references at implementation time.
- **`apps/web/src/pages/SignInPage.tsx`:** rework `AuthStep` into an explicit
  small state machine: `credentials` (email+password, with "use a login code"
  toggle and "forgot password?" link) → `check-email` → `enter-code` →
  `reset-password`. Each state is a focused sub-component. Google + demo entry
  preserved. Friendly error mapping updated from username-shaped to email-shaped.
- **Onboarding:** unchanged. `OnboardingStep` already shows an editable username
  field when the session email is real.

### Backend

No change. A verified Supabase user is just another JWT; `get_or_create_user`
provisions the row and backfills the real email exactly as today.

### Email delivery & Supabase configuration (dashboard — operator task)

Operator (you) configures in the Supabase dashboard; the design supplies the
paste-ready assets:
- **Auth → SMTP Settings → Custom SMTP:** host `smtp.resend.com`, port 465
  (implicit TLS) or 587, username `resend`, password = a Resend API key, sender
  `Money Match <noreply@send.dueloro.com>`.
- **Auth → Providers → Email:** enable **Confirm email**.
- **Auth → URL Configuration:** Site URL + Redirect URLs include
  `http://localhost:5173/**` and `https://moneymatch-beta.vercel.app/**`.
- **Auth → Email Templates:** paste the provided HTML for **Confirm signup**,
  **Magic Link** (OTP — must surface `{{ .Token }}` prominently), and **Reset
  password**.

### Brand system & templates (deliverables of implementation)

- One hybrid template shared visually across:
  - the three Supabase dashboard templates (Confirm signup, Magic Link/OTP, Reset
    password), authored as inline-styled, table-based, bulletproof HTML using
    Supabase variables (`{{ .ConfirmationURL }}`, `{{ .Token }}`); and
  - the in-repo notification email in
    `apps/api/src/moneymatch_api/services/email_service.py` (`_render_html`),
    restyled to match.
- **Voice:** "Money Match" everywhere in body copy; "Dueloro · Support" only in
  the footer (per `docs/brand-and-name.md`). Friendly, skill-proud, anti-casino
  tone.
- **Logo asset:** export the lime triangle mark to
  `apps/web/public/email/logo.png` (2× raster, ~120px display width, transparent
  or dark-lozenge background to read on the dark band), referenced by the
  absolute URL from Decision B, with descriptive `alt` text.
- **Bulletproof HTML constraints:** table layout, inline styles, hosted PNG (no
  inline SVG), a plaintext fallback link under every CTA button, ≤ 600px width.

## Error handling

- **No session after signUp** is the expected "confirm required" path → the
  check-email state, never an error toast.
- **OTP:** wrong/expired code → inline "That code didn't work or expired — send a
  new one." Rate-limit / resend cooldown surfaced.
- **Password reset:** expired recovery link → prompt to request a new one.
- **SMTP not yet live (domain unverified):** Supabase returns a send error; copy
  should not promise delivery it cannot make during the blocker window. (Local dev
  without SMTP falls back to Supabase's built-in low-rate sender for testing.)
- All email sends remain best-effort on our side; auth correctness never depends
  on a notification email.

## Testing

- **Vitest:** new `AuthProvider` methods (mock `supabase.auth`), and `SignInPage`
  state transitions (credentials → check-email → enter-code → reset). Update the
  existing `SignInPage`/`RequireAuth` auth mocks to the new context shape.
- **API:** the email/notification suites already pass; only
  `email_service._render_html` output changes — assert the branded markup
  (logo URL, CTA, plaintext link) is present.
- **Manual:** end-to-end verify/OTP/reset against real Supabase once the domain
  is verified.

## Out of scope

- Migrating existing username-only accounts (Decision A).
- Social/third-party providers beyond Google.
- Marketing/broadcast email (transactional only).
- A permanent brand domain for the logo (beta domain for now, Decision B).
- Inbound email / webhooks.

## Dependencies

- `send.dueloro.com` verified in Resend (blocker above).
- Supabase dashboard access to set SMTP, toggles, redirect URLs, and templates.
- Resend API key usable as the SMTP password.
