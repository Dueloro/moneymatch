import { EmptyState } from '../components/ui/EmptyState';

export function WalletPage() {
  return (
    <div>
      <h1 className="mb-1 text-2xl font-bold">Wallet</h1>
      <p className="mb-6 text-sm text-text-secondary">
        Play money — no real deposits yet.
      </p>
      <EmptyState title="Wallet coming in Phase 1" />
    </div>
  );
}
