import { useState } from 'react';

import { AmountText, PointsFigure } from '../components/ui/AmountText';
import { AnimatedBalance } from '../components/ui/AnimatedBalance';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { ExpandableCard } from '../components/ui/ExpandableCard';
import { PillButton } from '../components/ui/PillButton';
import { PresetSelector } from '../components/ui/PresetSelector';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { formatPoints, formatRelativeTime } from '../lib/format';
import { ledgerLabel } from '../lib/labels';
import {
  DEPOSIT_PRESETS_CENTS,
  usePlayMoneyDeposit,
  useWallet,
  useWalletLedger,
  type LedgerEntry,
} from '../hooks/useWallet';

function LedgerDot({ entry }: { entry: LedgerEntry }) {
  const color =
    entry.entry_type === 'rake'
      ? 'bg-red'
      : entry.amount_cents > 0
        ? 'bg-green'
        : 'bg-text-tertiary';
  return <span className={`h-2 w-2 shrink-0 rounded-full ${color}`} aria-hidden />;
}

export function WalletPage() {
  usePageTitle('Wallet');
  const { data: wallet, isLoading, isError, refetch } = useWallet();
  const ledger = useWalletLedger();
  const deposit = usePlayMoneyDeposit();
  const [pick, setPick] = useState<number | null>(null);

  const available = wallet?.available_cents ?? 0;
  const escrow = wallet?.escrow_cents ?? 0;
  const lifetime = wallet?.lifetime_net_cents ?? 0;

  const rows = ledger.data?.pages.flatMap((p) => p.entries) ?? [];

  const confirmAdd = () => {
    if (pick == null) return;
    deposit.mutate(pick, { onSuccess: () => setPick(null) });
  };

  return (
    <div className="flex h-full flex-col">
      <SectionHeader level="page" hint="Points have no cash value.">
        Wallet
      </SectionHeader>

      {isError ? (
        <ErrorState
          title="Could not load your wallet"
          subline="The connection dropped. Try again."
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <div>
          <Skeleton className="h-28 w-full rounded-card" />
          <div className="mt-8">
            <SkeletonList rows={3} />
          </div>
        </div>
      ) : (
        <>
          {/* Available is the number you came for; escrow and lifetime are
           * its context. */}
          <Card className="p-5">
            <p className="label-money">Available</p>
            <p className="mt-1 text-3xl font-semibold text-green">
              <AnimatedBalance cents={available} testId="wallet-balance" />
            </p>
            <p className="mt-2 text-xs text-text-secondary">
              In play{' '}
              <span className="num text-text">
                <PointsFigure cents={escrow} />
              </span>
              <span className="mx-1.5 text-text-tertiary">·</span>
              Net all time <AmountText cents={lifetime} win={lifetime > 0} />
            </p>
          </Card>

          <section className="mt-8">
            <SectionHeader level="sub" hint="Free top-ups, any time.">
              Add points
            </SectionHeader>
            <div
              className="flex flex-wrap items-center gap-x-4 gap-y-3"
              data-testid="deposit-presets"
            >
              <PresetSelector
                presetsCents={DEPOSIT_PRESETS_CENTS}
                selectedCents={pick}
                onSelect={(cents) => setPick(cents === pick ? null : cents)}
                disabled={deposit.isPending}
              />
              <div className="flex items-center gap-1">
                <PillButton
                  variant="primary"
                  onClick={confirmAdd}
                  disabled={pick == null || deposit.isPending}
                >
                  {deposit.isPending
                    ? 'Adding…'
                    : pick == null
                      ? 'Add points'
                      : `Add ${formatPoints(pick)}`}
                </PillButton>
                {pick != null && !deposit.isPending && (
                  <PillButton variant="text" onClick={() => setPick(null)}>
                    Cancel
                  </PillButton>
                )}
              </div>
            </div>
          </section>

          <section className="mt-8 flex min-h-0 flex-1 flex-col">
            <SectionHeader level="sub" className="shrink-0">
              Recent
            </SectionHeader>
            {rows.length === 0 ? (
              <p className="text-xs text-text-tertiary">
                Nothing yet. Join a match and it shows up here.
              </p>
            ) : (
              <div className="space-y-2 pb-1 md:min-h-[9rem] md:flex-1 md:overflow-y-auto md:pr-2">
                {rows.map((entry) => (
                  <ExpandableCard
                    key={entry.id}
                    left={<LedgerDot entry={entry} />}
                    title={ledgerLabel(entry)}
                    subline={formatRelativeTime(entry.created_at)}
                    right={
                      <AmountText
                        cents={entry.amount_cents}
                        win={entry.entry_type === 'payout'}
                      />
                    }
                  />
                ))}
                {ledger.hasNextPage && (
                  <div className="pt-2">
                    <PillButton
                      variant="outline"
                      onClick={() => ledger.fetchNextPage()}
                      disabled={ledger.isFetchingNextPage}
                    >
                      {ledger.isFetchingNextPage ? 'Loading…' : 'Load more'}
                    </PillButton>
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
