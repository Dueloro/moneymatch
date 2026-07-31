import { AmountText } from '../components/ui/AmountText';
import { ErrorState } from '../components/ui/ErrorState';
import { ExpandableCard } from '../components/ui/ExpandableCard';
import { PillButton } from '../components/ui/PillButton';
import { PresetSelector } from '../components/ui/PresetSelector';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { StatBar } from '../components/ui/StatBar';
import { formatCurrency, formatRelativeTime } from '../lib/format';
import {
  DEMO_DEPOSIT_PRESETS_CENTS,
  useDemoDeposit,
  useDemoWithdrawal,
  useWallet,
  useWalletLedger,
  type LedgerEntry,
} from '../hooks/useWallet';

const ENTRY_LABELS: Record<string, string> = {
  demo_deposit: 'Added funds',
  demo_withdrawal: 'Cashed out',
  escrow_hold: 'Entry held',
  escrow_release: 'Entry settled',
  payout: 'Winnings',
  rake: 'Platform fee',
  refund: 'Refund',
  adjustment: 'Adjustment',
};

function ledgerLabel(entry: LedgerEntry): string {
  return entry.memo ?? ENTRY_LABELS[entry.entry_type] ?? entry.entry_type;
}

/** A small semantic dot leading each ledger row: green credit, red platform
 * fee, gray debit/hold — enough color to read the list at a glance. */
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
  const { data: wallet, isLoading, isError, refetch } = useWallet();
  const ledger = useWalletLedger();
  const deposit = useDemoDeposit();
  const withdraw = useDemoWithdrawal();

  const available = wallet?.available_cents ?? 0;
  const escrow = wallet?.escrow_cents ?? 0;
  const lifetime = wallet?.lifetime_net_cents ?? 0;

  const rows = ledger.data?.pages.flatMap((p) => p.entries) ?? [];
  const busy = deposit.isPending || withdraw.isPending;

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-2xl font-bold">Wallet</h1>
      <p className="mb-6 text-sm text-text-secondary">
        Play money used until full launch.
      </p>

      {isError ? (
        <ErrorState title="Could not load your wallet" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div>
          <Skeleton className="h-[74px] w-full rounded-card" />
          <Skeleton className="mt-8 h-9 w-24" />
          <div className="mt-8">
            <SkeletonList rows={3} />
          </div>
        </div>
      ) : (
        <>
          <div className="relative">
            {/* Ambient brand glow behind the balance — ties the wallet's headline
             * number to the lime "money" accent used across the app. */}
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 overflow-hidden rounded-card"
              style={{
                background:
                  'radial-gradient(70% 130% at 0% 0%, rgba(198, 244, 64, 0.1), transparent 70%)',
              }}
            />
            <StatBar
              cells={[
                {
                  label: 'Available',
                  value: (
                    <span className="text-green">{formatCurrency(available)}</span>
                  ),
                },
                { label: 'In escrow', value: formatCurrency(escrow) },
                {
                  label: 'Lifetime',
                  value: <AmountText cents={lifetime} win={lifetime > 0} />,
                },
              ]}
            />
          </div>

          <section className="mt-8">
            <h2 className="mb-3 text-sm font-semibold">Add funds</h2>
            <PresetSelector
              presetsCents={DEMO_DEPOSIT_PRESETS_CENTS}
              onSelect={(cents) => deposit.mutate(cents)}
              disabled={busy}
            />
          </section>

          <section className="mt-6">
            <h2 className="mb-3 text-sm font-semibold">Cash out</h2>
            <PresetSelector
              presetsCents={DEMO_DEPOSIT_PRESETS_CENTS.filter((c) => c <= available)}
              onSelect={(cents) => withdraw.mutate(cents)}
              disabled={busy}
            />
            {available === 0 && (
              <p className="mt-2 text-xs text-text-secondary">
                Nothing available to cash out.
              </p>
            )}
          </section>

          <section className="mt-8">
            <h2 className="mb-1 text-sm font-semibold">Recent</h2>
            {rows.length === 0 ? (
              <p className="py-6 text-sm text-text-secondary">No activity yet.</p>
            ) : (
              <div className="flex flex-col gap-2">
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
              </div>
            )}
            {ledger.hasNextPage && (
              <div className="mt-4">
                <PillButton
                  variant="outline"
                  onClick={() => ledger.fetchNextPage()}
                  disabled={ledger.isFetchingNextPage}
                >
                  Load more
                </PillButton>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
