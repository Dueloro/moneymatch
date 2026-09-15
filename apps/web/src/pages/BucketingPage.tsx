import { ModeSwitcher } from '../components/ModeSwitcher';
import { AmountText } from '../components/ui/AmountText';
import { Card } from '../components/ui/Card';
import { CardGrid } from '../components/ui/CardGrid';
import { HowItWorks } from '../components/ui/Disclosure';
import { EmptyState } from '../components/ui/EmptyState';
import { PillButton } from '../components/ui/PillButton';
import { SectionHeader } from '../components/ui/SectionHeader';
import { SkeletonList } from '../components/ui/Skeleton';
import { usePageTitle } from '../hooks/usePageTitle';
import {
  useBucketMarkets,
  usePlaceBucketWager,
  type BucketMarketCard,
} from '../hooks/useBucketing';
import { toast } from '../lib/toast';

/**
 * Bucketing markets — the one-bar-per-bucket wager system. Ships behind the
 * `bucketing_enabled` server flag; while it's off the endpoint returns
 * `enabled: false` and this page shows a "not enabled yet" state rather than an
 * error, so the section can exist in the nav without being live.
 */
export function BucketingPage() {
  usePageTitle('Bucketing');
  const { data, isLoading } = useBucketMarkets();
  const place = usePlaceBucketWager();

  const header = (
    <div className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <ModeSwitcher />
        <div className="ml-auto">
          <HowItWorks id="bucketing">
            Players are sorted into skill buckets. Everyone in a bucket wagers against
            the same bar for that bucket; clear it and you split the pot, minus rake.
            The server owns every bucket, bar and cap.
          </HowItWorks>
        </div>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div>
        {header}
        <SkeletonList rows={3} />
      </div>
    );
  }

  if (!data?.enabled) {
    return (
      <div>
        {header}
        <EmptyState
          title="Bucketing isn't enabled yet"
          subline="This market type is built and ready, but turned off. An admin enables it with the bucketing_enabled flag when it's time to launch."
        />
      </div>
    );
  }

  const placed = data.markets.filter((m) => m.placed);

  return (
    <div>
      {header}
      <SectionHeader level="page">Bucketing markets</SectionHeader>
      {placed.length === 0 ? (
        <EmptyState
          title="No placed markets yet"
          subline="Play a qualifying match on a game to get placed in a bucket, then its market appears here."
        />
      ) : (
        <CardGrid count={placed.length}>
          {placed.map((m) => (
            <BucketMarketTile
              key={`${m.game}:${m.mode}:${m.metric}`}
              market={m}
              placing={place.isPending}
              onPlace={(stake) =>
                place
                  .mutateAsync({
                    game: m.game,
                    mode: m.mode,
                    metric: m.metric,
                    stake_cents: stake,
                  })
                  .then(() => toast.success('Wager placed'))
                  .catch((e: Error) => toast.error(e.message))
              }
            />
          ))}
        </CardGrid>
      )}
    </div>
  );
}

function BucketMarketTile({
  market,
  placing,
  onPlace,
}: {
  market: BucketMarketCard;
  placing: boolean;
  onPlace: (stakeCents: number) => void;
}) {
  const cap = market.stake_cap_cents;
  // Offer the floor preset up to the cap; the server is authoritative either way.
  const stake = cap ?? 500;
  return (
    <Card className="flex flex-col gap-3 p-4" data-testid="bucket-market">
      <div>
        <p className="text-sm font-medium text-text">{market.label}</p>
        <p className="text-xs text-text-secondary">
          {market.game} · bucket {market.bucket ?? '—'}
          {market.bar != null && ` · bar ${market.bar}`}
          {market.provisional && ' · provisional'}
        </p>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-secondary">
          Stake cap {cap == null ? 'uncapped' : <AmountText cents={cap} />}
        </span>
        <PillButton onClick={() => onPlace(stake)} disabled={placing}>
          Wager
        </PillButton>
      </div>
    </Card>
  );
}
