import { AmountText } from '../components/ui/AmountText';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { ExpandableCard } from '../components/ui/ExpandableCard';
import { PillButton } from '../components/ui/PillButton';
import { PresetSelector } from '../components/ui/PresetSelector';
import { SectionHeader } from '../components/ui/SectionHeader';
import { usePageTitle } from '../hooks/usePageTitle';
import { Skeleton, SkeletonList } from '../components/ui/Skeleton';
import { formatCurrency, formatRelativeTime } from '../lib/format';
import { humanizeIds } from '../lib/labels';
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
  // Memos are server free-text that embed raw metric/market ids
  // ("chess_accuracy easy pool entry"); humanize them so no snake_case
  // identifier reaches the player.
  if (entry.memo) return humanizeIds(entry.memo);
  return ENTRY_LABELS[entry.entry_type] ?? entry.entry_type;
}

/** A small semantic dot leading each ledger row: money in, fee, or hold. */
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
  const deposit = useDemoDeposit();
  const withdraw = useDemoWithdrawal();

  const available = wallet?.available_cents ?? 0;
  const escrow = wallet?.escrow_cents ?? 0;
  const lifetime = wallet?.lifetime_net_cents ?? 0;

  const rows = ledger.data?.pages.flatMap((p) => p.entries) ?? [];
  const busy = deposit.isPending || withdraw.isPending;

  return (
    // A column the height of the viewport: the balance and the two preset rows
    // stay put and only the ledger scrolls, so the page stops growing with the
    // number of entries.
    <div className="flex h-full flex-col">
      <SectionHeader level="page" hint="Play money until full launch.">
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
          {/* One hero figure rather than three equal cells. Available is the
           * number you came for; escrow and lifetime are its context. */}
          <Card className="p-5">
            <p className="label-money">Available</p>
            <p className="mt-1 text-3xl font-semibold text-green">
              {formatCurrency(available)}
            </p>
            <p className="mt-2 text-xs text-text-secondary">
              {formatCurrency(escrow)} in play ·{' '}
              <AmountText cents={lifetime} win={lifetime > 0} /> all time
            </p>
          </Card>

          <section className="mt-8">
            <SectionHeader level="sub">Add funds</SectionHeader>
            <PresetSelector
              presetsCents={DEMO_DEPOSIT_PRESETS_CENTS}
              onSelect={(cents) => deposit.mutate(cents)}
              disabled={busy}
            />
          </section>

          <section className="mt-6">
            <SectionHeader level="sub">Cash out</SectionHeader>
            {available === 0 ? (
              <p className="text-xs text-text-tertiary">
                Nothing to cash out yet. Win a contest and it lands here.
              </p>
            ) : (
              <PresetSelector
                presetsCents={DEMO_DEPOSIT_PRESETS_CENTS.filter((c) => c <= available)}
                onSelect={(cents) => withdraw.mutate(cents)}
                disabled={busy}
              />
            )}
          </section>

          <section className="mt-8 flex min-h-0 flex-1 flex-col">
            <SectionHeader level="sub" className="shrink-0">
              Recent
            </SectionHeader>
            {rows.length === 0 ? (
              <p className="text-xs text-text-tertiary">
                Nothing yet. Add funds and join a contest to start the ledger.
              </p>
            ) : (
              // `min-h` keeps the ledger from being squeezed to nothing on a
              // short window; past that the outer column takes over scrolling.
              <div className="min-h-[9rem] flex-1 space-y-2 overflow-y-auto pb-1 pr-2">
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
