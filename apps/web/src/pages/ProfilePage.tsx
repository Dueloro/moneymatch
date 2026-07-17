import { useState } from 'react';

import { useAuth } from '../auth/useAuth';
import { LinkGames } from '../components/LinkGames';
import { FooterBreadcrumb } from '../components/ui/FooterBreadcrumb';
import { PillButton } from '../components/ui/PillButton';
import { useMe, useSelfExclude } from '../hooks/useMe';
import { formatCurrency } from '../lib/format';

export function ProfilePage() {
  const { signOut } = useAuth();
  const me = useMe();
  const selfExclude = useSelfExclude();
  const [confirming, setConfirming] = useState(false);

  const user = me.data?.user;
  const limits = me.data?.limits;
  const excluded = user?.status === 'self_excluded';

  return (
    <div className="max-w-lg">
      <h1 className="mb-6 text-2xl font-bold">Profile</h1>

      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-full bg-panel-raised text-lg">
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

      <Section title="Linked games">
        <LinkGames />
      </Section>

      <Section title="Limits">
        <dl className="divide-y divide-hairline border-y border-hairline">
          <Row
            label="Daily loss cap"
            value={limits ? formatCurrency(limits.daily_loss_cap_cents) : '—'}
          />
          <Row
            label="Daily entries cap"
            value={limits ? formatCurrency(limits.daily_entry_cap_cents) : '—'}
          />
          <Row
            label="Max concurrent contests"
            value={limits ? String(limits.max_concurrent_contests) : '—'}
          />
        </dl>
      </Section>

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

      <FooterBreadcrumb segments={['PROFILE']} />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-8">
      <p className="mb-2 text-xs uppercase tracking-wide text-text-tertiary">{title}</p>
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
