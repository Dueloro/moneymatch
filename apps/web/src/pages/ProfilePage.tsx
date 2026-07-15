import { useAuth } from '../auth/useAuth';
import { PillButton } from '../components/ui/PillButton';
import { useMe } from '../hooks/useMe';

export function ProfilePage() {
  const { signOut } = useAuth();
  const me = useMe();
  const user = me.data?.user;

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

      <dl className="mt-8 divide-y divide-hairline border-y border-hairline">
        <Row label="Residence" value={user?.residence_state ?? '—'} />
        <Row label="18+ attested" value={user?.dob_attested_18plus ? 'Yes' : 'No'} />
        <Row label="Status" value={user?.status ?? '—'} />
      </dl>

      <p className="mt-8 mb-2 text-xs uppercase tracking-wide text-text-tertiary">
        Linked games
      </p>
      <p className="text-sm text-text-secondary">Game linking arrives in Phase 2.</p>

      <div className="mt-10">
        <PillButton variant="outline" onClick={() => void signOut()}>
          Sign out
        </PillButton>
      </div>
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
