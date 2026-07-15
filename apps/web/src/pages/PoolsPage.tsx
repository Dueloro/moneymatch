import { EmptyState } from '../components/ui/EmptyState';

export function PoolsPage() {
  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Pools</h1>
      <EmptyState title="No pools yet" subline="Solo pools arrive in Phase 4." />
    </div>
  );
}
