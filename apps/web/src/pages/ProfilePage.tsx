import { useEffect, useState } from 'react';

import { useAuth } from '../auth/useAuth';
import { Cs2SetupCard } from '../components/cs2/Cs2SetupCard';
import { DemoHandles } from '../components/DemoHandles';
import { LinkGames } from '../components/LinkGames';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { useMe, useSelfExclude, useUpdateLimits, type Limits } from '../hooks/useMe';
import { useResetDemo } from '../hooks/useResetDemo';
import { formatCurrency } from '../lib/format';

export function ProfilePage() {
  const { signOut, isDemo } = useAuth();
  const me = useMe();
  const selfExclude = useSelfExclude();
  const [confirming, setConfirming] = useState(false);

  const user = me.data?.user;
  const limits = me.data?.limits;
  const excluded = user?.status === 'self_excluded';
  const showCs2 = (user?.active_games ?? []).includes('cs2.steam');

  return (
    <div className="max-w-read">
      <SectionHeader level="page">Profile</SectionHeader>

      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-full bg-panel-raised text-lg font-semibold">
          {user?.username?.slice(0, 1).toUpperCase() ?? '?'}
        </span>
        <div>
          <p className="text-lg font-semibold">{user?.username ?? '…'}</p>
          <p className="text-sm text-text-secondary">
            {user?.member_since
              ? `Member since ${new Date(user.member_since).toLocaleDateString()}`
              : ''}
          </p>
        </div>
      </div>

      <Section title="Games">
        <p className="mb-3 text-sm text-text-secondary">
          Check the games you play to add them to your bar. Link an account when you're
          ready to play for real.
        </p>
        <LinkGames />
      </Section>

      {showCs2 && (
        <Section title="Counter-Strike 2">
          <p className="mb-3 text-sm text-text-secondary">
            Connect Steam and your matches settle your wagers automatically.
          </p>
          <Cs2SetupCard />
        </Section>
      )}

      {isDemo && (
        <Section title="Test with real accounts">
          <p className="mb-3 text-sm text-text-secondary">
            The demo is linked to placeholder handles. Swap in a real account per game
            to pull its live profile and stats.
          </p>
          <DemoHandles />
        </Section>
      )}

      <Section title="Limits">
        {limits ? (
          <LimitsEditor limits={limits} />
        ) : (
          <p className="text-sm text-text-tertiary">Not set</p>
        )}
      </Section>

      {!isDemo && (
        <Section title="Security">
          <ChangePassword />
        </Section>
      )}

      <div className="mt-10 flex flex-col items-start gap-4">
        <PillButton variant="outline" onClick={() => void signOut()}>
          Sign out
        </PillButton>

        {excluded ? (
          <p className="text-sm text-red">
            You are self-excluded. Staking is disabled.
          </p>
        ) : confirming ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-text-secondary">
              This is permanent. Continue?
            </span>
            <button
              type="button"
              onClick={() => selfExclude.mutate()}
              disabled={selfExclude.isPending}
              className="text-sm font-semibold text-red hover:opacity-80 disabled:opacity-40"
            >
              {selfExclude.isPending ? 'Excluding…' : 'Yes, self-exclude'}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-sm text-text-secondary hover:text-text"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="text-sm font-semibold text-red hover:opacity-80"
          >
            Self-exclude
          </button>
        )}
      </div>

      {isDemo && <ResetDemo />}
    </div>
  );
}

/**
 * Reset the shared demo to its fresh-login state. This replaces the old per-room
 * "New pool" escape hatch: formed rooms are (correctly) uncancelable, so testers
 * get one deliberate "start over" here instead. Inline two-step confirm, matching
 * the page's other irreversible actions.
 */
function ResetDemo() {
  const reset = useResetDemo();
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="mt-10 border-t border-hairline pt-6">
      <p className="text-sm font-medium text-text">Reset demo</p>
      <p className="mt-1 max-w-read text-xs text-text-secondary">
        Clear any in-flight contests, restore your $1,000 demo balance, and refresh the
        sample activity. This resets the shared demo account for everyone.
      </p>
      {confirming ? (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() =>
              reset.mutate(undefined, { onSettled: () => setConfirming(false) })
            }
            disabled={reset.isPending}
            className="text-sm font-semibold text-text hover:opacity-80 disabled:opacity-40"
          >
            {reset.isPending ? 'Resetting…' : 'Yes, reset the demo'}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="text-sm text-text-secondary hover:text-text"
          >
            Cancel
          </button>
        </div>
      ) : (
        <PillButton
          variant="outline"
          className="mt-3"
          onClick={() => setConfirming(true)}
        >
          Reset demo
        </PillButton>
      )}
    </div>
  );
}

/**
 * Change the account password via Supabase. A "Change password" button opens a
 * two-step flow: confirm the current password, then set + confirm the new one.
 * Accounts sign in by username (no email on file), so there is no email-based
 * reset; this only re-auths and sets the new password on the signed-in account.
 */
function ChangePassword() {
  const { verifyCurrentPassword, changePassword } = useAuth();
  const [step, setStep] = useState<'closed' | 'current' | 'new'>('closed');

  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reset = () => {
    setStep('closed');
    setCurrent('');
    setPassword('');
    setConfirm('');
    setError(null);
    setNotice(null);
    setBusy(false);
  };

  const confirmCurrent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!current) return;
    setError(null);
    setBusy(true);
    try {
      const ok = await verifyCurrentPassword(current);
      if (!ok) {
        setError('Incorrect password.');
        return;
      }
      setCurrent('');
      setStep('new');
    } catch {
      setError('Could not verify your password. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const tooShort = password.length > 0 && password.length < 6;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSave = password.length >= 6 && confirm === password;

  const saveNew = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSave) return;
    setError(null);
    setBusy(true);
    try {
      await changePassword(password);
      reset();
      setNotice('Password updated.');
    } catch (err) {
      setError((err as { message?: string })?.message ?? 'Could not update password.');
    } finally {
      setBusy(false);
    }
  };

  if (step === 'closed') {
    return (
      <div className="flex flex-col gap-2">
        <PillButton variant="outline" onClick={() => setStep('current')}>
          Change password
        </PillButton>
        {notice && <p className="text-xs text-live">{notice}</p>}
      </div>
    );
  }

  if (step === 'current') {
    return (
      <form className="flex flex-col gap-3" onSubmit={confirmCurrent}>
        <input
          type="password"
          autoComplete="current-password"
          placeholder="Enter current password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="w-full rounded-pill border border-hairline bg-panel-raised px-4 py-2.5 text-sm text-text transition-colors placeholder:text-text-tertiary hover:border-line-strong"
        />
        {error && <p className="text-xs text-red">{error}</p>}
        {notice && <p className="text-xs text-live">{notice}</p>}
        <div className="flex items-center gap-3">
          <PillButton type="submit" variant="primary" disabled={!current || busy}>
            {busy ? 'Checking…' : 'Continue'}
          </PillButton>
          <PillButton type="button" variant="text" onClick={reset}>
            Cancel
          </PillButton>
        </div>
      </form>
    );
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={saveNew}>
      <input
        type="password"
        autoComplete="new-password"
        placeholder="New password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full rounded-pill border border-hairline bg-panel-raised px-4 py-2.5 text-sm text-text transition-colors placeholder:text-text-tertiary hover:border-line-strong"
      />
      <input
        type="password"
        autoComplete="new-password"
        placeholder="Confirm new password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        className="w-full rounded-pill border border-hairline bg-panel-raised px-4 py-2.5 text-sm text-text transition-colors placeholder:text-text-tertiary hover:border-line-strong"
      />
      {tooShort && (
        <p className="text-xs text-text-secondary">Use at least 6 characters.</p>
      )}
      {mismatch && <p className="text-xs text-red">Passwords don't match.</p>}
      {error && <p className="text-xs text-red">{error}</p>}
      <div className="flex items-center gap-3">
        <PillButton type="submit" variant="primary" disabled={!canSave || busy}>
          {busy ? 'Updating…' : 'Update password'}
        </PillButton>
        <PillButton type="button" variant="text" onClick={reset}>
          Cancel
        </PillButton>
      </div>
    </form>
  );
}

/** Editable protective caps. Lowering applies instantly; raising is staged 24 h
 * server-side and surfaced here as a pending note. Max-concurrent is
 * system-owned, shown read-only. */
function LimitsEditor({ limits }: { limits: Limits }) {
  const update = useUpdateLimits();
  const [loss, setLoss] = useState('');
  const [entry, setEntry] = useState('');
  const [deposit, setDeposit] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Seed the dollar inputs from the live caps whenever they change.
  useEffect(() => {
    setLoss(dollars(limits.daily_loss_cap_cents));
    setEntry(dollars(limits.daily_entry_cap_cents));
    setDeposit(dollars(limits.daily_deposit_cap_cents));
  }, [
    limits.daily_loss_cap_cents,
    limits.daily_entry_cap_cents,
    limits.daily_deposit_cap_cents,
  ]);

  const lossCents = toCents(loss);
  const entryCents = toCents(entry);
  const depositCents = toCents(deposit);
  const valid = lossCents != null && entryCents != null && depositCents != null;
  const changed =
    valid &&
    (lossCents !== limits.daily_loss_cap_cents ||
      entryCents !== limits.daily_entry_cap_cents ||
      depositCents !== limits.daily_deposit_cap_cents);

  const pending = limits.pending_limits ?? null;
  const effectiveAt = limits.pending_effective_at
    ? new Date(limits.pending_effective_at).toLocaleString()
    : null;

  const save = () => {
    if (!valid || !changed) return;
    setError(null);
    setSaved(false);
    update.mutate(
      {
        daily_loss_cap_cents: lossCents,
        daily_entry_cap_cents: entryCents,
        daily_deposit_cap_cents: depositCents,
      },
      {
        onSuccess: () => setSaved(true),
        onError: () => setError('Could not update your limits. Try again.'),
      },
    );
  };

  return (
    <div>
      <p className="mb-3 text-sm text-text-secondary">
        Set protective caps on your play. Lowering a cap is instant; raising one takes
        effect after 24 hours.
      </p>
      <div className="flex flex-col gap-4">
        <DollarField label="Daily loss cap" value={loss} onChange={setLoss} />
        {pending?.daily_loss_cap_cents != null && effectiveAt && (
          <PendingNote cents={pending.daily_loss_cap_cents} at={effectiveAt} />
        )}
        <DollarField label="Daily entries cap" value={entry} onChange={setEntry} />
        {pending?.daily_entry_cap_cents != null && effectiveAt && (
          <PendingNote cents={pending.daily_entry_cap_cents} at={effectiveAt} />
        )}
        <DollarField label="Daily deposit cap" value={deposit} onChange={setDeposit} />
        {pending?.daily_deposit_cap_cents != null && effectiveAt && (
          <PendingNote cents={pending.daily_deposit_cap_cents} at={effectiveAt} />
        )}
      </div>

      <dl className="mt-4 border-t border-hairline">
        <Row
          label="Max concurrent contests"
          value={String(limits.max_concurrent_contests)}
        />
      </dl>

      <div className="mt-4 flex items-center gap-3">
        <PillButton
          variant="primary"
          onClick={save}
          disabled={!changed || update.isPending}
        >
          {update.isPending ? 'Saving…' : 'Save limits'}
        </PillButton>
        {saved && !changed && (
          <span className="text-sm text-text-secondary">Saved.</span>
        )}
        {error && <span className="text-sm text-red">{error}</span>}
      </div>

      <CoolOff timeoutUntil={limits.timeout_until} />
    </div>
  );
}

/** A self-imposed break: staking is refused until it ends (extend-only). */
function CoolOff({ timeoutUntil }: { timeoutUntil: string | null }) {
  const update = useUpdateLimits();
  const [confirming, setConfirming] = useState<number | null>(null);
  const active = timeoutUntil != null && new Date(timeoutUntil).getTime() > Date.now();

  const start = (days: number) => {
    update.mutate({ cooloff_days: days }, { onSuccess: () => setConfirming(null) });
  };

  return (
    <div className="mt-6 border-t border-hairline pt-4">
      <p className="text-sm font-medium text-text">Take a break</p>
      <p className="mt-1 text-xs text-text-secondary">
        Pause all staking for a set time. A break can be extended but not shortened.
      </p>
      {active ? (
        <p className="mt-2 text-sm text-red">
          You're on a break until {new Date(timeoutUntil!).toLocaleString()}.
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {[1, 7, 30].map((days) => (
            <span key={days}>
              {confirming === days ? (
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => start(days)}
                    disabled={update.isPending}
                    className="text-sm font-semibold text-red hover:opacity-80 disabled:opacity-40"
                  >
                    Confirm {days}-day break
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirming(null)}
                    className="text-sm text-text-secondary hover:text-text"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <PillButton variant="outline" onClick={() => setConfirming(days)}>
                  {days} day{days > 1 ? 's' : ''}
                </PillButton>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function DollarField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4 text-sm">
      <span className="text-text-secondary">{label}</span>
      <span className="flex items-center gap-1">
        <span className="text-text-secondary">$</span>
        <input
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-24 rounded-pill border border-hairline bg-panel-raised px-4 py-1.5 text-right text-sm text-text transition-colors hover:border-line-strong"
        />
      </span>
    </label>
  );
}

function PendingNote({ cents, at }: { cents: number; at: string }) {
  return (
    <p className="-mt-2 text-xs text-text-secondary">
      Raise to {formatCurrency(cents)} takes effect {at}.
    </p>
  );
}

/** Dollars string (no trailing .00 for whole amounts) from integer cents. */
function dollars(cents: number): string {
  return (cents / 100).toFixed(2).replace(/\.00$/, '');
}

/** Parse a dollar input to integer cents; null when not a positive number. */
function toCents(value: string): number | null {
  const n = Number(value.trim());
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 100);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-10">
      <SectionHeader level="sub">{title}</SectionHeader>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <dt className="text-sm text-text-secondary">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}
