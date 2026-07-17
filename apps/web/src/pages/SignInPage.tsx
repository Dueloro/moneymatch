import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/useAuth';
import { LinkGames } from '../components/LinkGames';
import { PillButton } from '../components/ui/PillButton';
import { StepProgress } from '../components/ui/StepProgress';
import { useMe } from '../hooks/useMe';
import { api } from '../lib/api';
import { US_STATES } from '../lib/usStates';

const USERNAME_RE = /^[a-z0-9_]{3,20}$/;

export function SignInPage() {
  const { session, loading } = useAuth();
  const me = useMe();
  const [linkStep, setLinkStep] = useState(false);

  if (loading || (session && me.isLoading)) return <Centered>Loading…</Centered>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-4">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-green text-black">
            <span className="font-bold">M</span>
          </div>
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

function AuthStep() {
  const { signInWithGoogle, signInWithEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (sent) {
    return (
      <div className="text-center">
        <h1 className="text-xl font-semibold">Check your email</h1>
        <p className="mt-2 text-sm text-text-secondary">
          We sent a sign-in link to {email}.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-center text-xl font-semibold">Sign in</h1>
      <p className="mt-2 text-center text-sm text-text-secondary">
        Play skill-based matches for real payouts.
      </p>

      <form
        className="mt-8 flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            await signInWithEmail(email);
            setSent(true);
          } catch {
            setError('Could not send the sign-in link. Try again.');
          }
        }}
      >
        <PillButton
          type="button"
          variant="outline"
          fullWidth
          onClick={() => void signInWithGoogle()}
        >
          Continue with Google
        </PillButton>

        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          className="rounded-pill border border-hairline bg-panel px-5 py-2.5 text-sm outline-none focus:border-text-secondary"
        />
        <PillButton type="submit" variant="primary" fullWidth disabled={!email}>
          Continue with email
        </PillButton>
        {error && <p className="text-center text-sm text-red">{error}</p>}
      </form>
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
        Your username is your public handle — choose carefully, it can't change.
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
        Connect Chess, CS2, or Dota 2 to start playing — or do it later from your
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
