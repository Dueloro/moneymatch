# Email auth — Supabase dashboard setup

The app code and email templates ship in the repo; these dashboard steps turn on
real email auth. **Prerequisite:** `send.dueloro.com` is verified in Resend.

> **Sequencing — do NOT enable Custom SMTP until DNS is verified.** As of this
> writing `send.dueloro.com` is **not yet** DNS-verified in Resend. Enabling
> Custom SMTP with an unverified sender domain makes Resend reject every send, so
> signup/OTP/reset emails fail silently — worse than leaving it off. Order:
> 1. Add the SPF/DKIM records and confirm the domain shows **Verified** in Resend.
> 2. **Then** enable Custom SMTP (step 1 below).
>
> To test the flows before DNS is done, leave Custom SMTP **off**: Supabase's
> built-in sender delivers these templates to a few addresses at a low rate —
> enough to walk through verify / "Email me a code" / "Forgot password" locally.
> It is rate-limited and not for real traffic; flip Custom SMTP on once verified.

## 1. Custom SMTP (Resend)
Auth → Settings → SMTP Settings → enable Custom SMTP (**only after the domain is
verified — see the sequencing note above**):
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
