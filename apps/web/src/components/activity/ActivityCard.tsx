import { useState } from 'react';

import { toast } from '../../lib/toast';
import { formatCurrency, formatRelativeTime } from '../../lib/format';
import {
  statValue,
  type ActivityDetail,
  type ActivityItem,
} from '../../hooks/useActivity';
import { useCreateChallenge } from '../../hooks/useChallenges';
import { useFileDispute, type ContestRefType } from '../../hooks/useDisputes';
import { AmountText } from '../ui/AmountText';
import { ExpandableCard } from '../ui/ExpandableCard';
import { PillButton } from '../ui/PillButton';
import { LiveLine } from './LiveLine';

const LIVE_STATES = new Set(['ACTIVE', 'AWAITING_RESULT']);
const TERMINAL_STATES = new Set(['SETTLED', 'PUSHED', 'CANCELED']);
// A settled outcome the player can contest (matches also allow PUSHED).
const DISPUTABLE_STATES = new Set(['SETTLED', 'PUSHED', 'CANCELED']);

/** A win or a live contest gets the green dot; everything settled is gray. */
function dotClass(item: ActivityItem): string {
  const won = item.state === 'SETTLED' && (item.net_cents ?? 0) > 0;
  const live = LIVE_STATES.has(item.state) || item.state === 'LOCKED';
  return won || live ? 'bg-green' : 'bg-text-secondary';
}

function stateLabel(item: ActivityItem): string {
  switch (item.state) {
    case 'PENDING':
      return 'Awaiting confirmation';
    case 'ACTIVE':
    case 'AWAITING_RESULT':
    case 'OPEN':
    case 'LOCKED':
      return 'In progress';
    case 'PUSHED':
      return 'Push · refunded';
    case 'CANCELED':
      return 'Refunded';
    case 'SETTLED':
      if ((item.net_cents ?? 0) > 0) return 'Won';
      return (item.net_cents ?? 0) < 0 ? 'Lost' : 'Settled';
    default:
      return item.state;
  }
}

/** Stat-race result line (matches only — pools/tournaments have no opponent). */
function statLine(item: ActivityItem): string | null {
  if (item.type !== 'match') return null;
  const you = statValue(item.your_stat_line);
  const opp = statValue(item.opponent_stat_line);
  if (you == null && opp == null) return null;
  const name = item.opponent_username ?? 'opponent';
  return `You ${you ?? '—'} · ${name} ${opp ?? '—'}`;
}

function title(item: ActivityItem): string {
  if (item.title) return item.title;
  return `vs ${item.opponent_username ?? 'opponent'} · ${item.market_label}`;
}

function fmt(v: number | string): string {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return v;
}

/** Side-by-side you-vs-opponent stat table for a match's expanded view. */
function StatCompare({ detail }: { detail: ActivityDetail }) {
  const you = detail.your_stats ?? {};
  const opp = detail.opponent_stats ?? {};
  const keys = Array.from(new Set([...Object.keys(you), ...Object.keys(opp)]));
  if (keys.length === 0) return null;
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-hairline">
      <div className="grid grid-cols-3 bg-panel-raised px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
        <span>Stat</span>
        <span className="text-right">You</span>
        <span className="text-right">{detail.opponent ?? 'Opponent'}</span>
      </div>
      {keys.map((k) => {
        const y = you[k];
        const o = opp[k];
        const better = typeof y === 'number' && typeof o === 'number' && y !== o;
        return (
          <div
            key={k}
            className="grid grid-cols-3 border-t border-hairline px-3 py-1.5 text-sm"
          >
            <span className="text-text-secondary">{k}</span>
            <span
              className={`text-right ${better && y > o ? 'font-semibold text-green' : 'text-text'}`}
            >
              {y == null ? '—' : fmt(y)}
            </span>
            <span
              className={`text-right ${better && o > y ? 'font-semibold text-green' : 'text-text'}`}
            >
              {o == null ? '—' : fmt(o)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** A labelled fact chip used in the pool/tournament expanded view. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-panel-raised px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-text-secondary">
        {label}
      </div>
      <div className="text-sm font-medium text-text">{value}</div>
    </div>
  );
}

function DetailBody({ item }: { item: ActivityItem }) {
  const d = item.detail;
  if (!d)
    return <p className="text-sm text-text-secondary">No details for this one.</p>;

  if (d.kind === 'match') {
    const meta = [d.map, d.mode].filter(Boolean).join(' · ');
    return (
      <div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-secondary">
          {d.opponent && (
            <span>
              Opponent <span className="text-text">{d.opponent}</span>
            </span>
          )}
          {meta && <span>{meta}</span>}
          {item.resolved_at && <span>{formatRelativeTime(item.resolved_at)}</span>}
        </div>
        <StatCompare detail={d} />
        <div className="mt-3 flex flex-wrap gap-2">
          <Fact label="Entry" value={formatCurrency(d.entry_cents ?? 0)} />
          {d.prize_cents ? (
            <Fact label="Prize" value={formatCurrency(d.prize_cents)} />
          ) : null}
          {d.host_game_id && !d.host_game_id.startsWith('demo-') ? (
            <Fact label="Match id" value={d.host_game_id} />
          ) : null}
        </div>
      </div>
    );
  }

  // pool / tournament
  const facts: Array<[string, string]> = [];
  if (d.metric_label) facts.push(['Metric', d.metric_label]);
  if (d.difficulty) facts.push(['Difficulty', d.difficulty]);
  if (d.room_bar != null) facts.push(['Room bar', fmt(d.room_bar)]);
  if (d.personal_bar != null) facts.push(['Your bar', fmt(d.personal_bar)]);
  if (d.your_rank != null) facts.push(['Your rank', `#${d.your_rank}`]);
  if (d.your_score != null) facts.push(['Your score', fmt(d.your_score)]);
  if (d.field_size != null) facts.push(['Field', `${d.field_size} players`]);
  if (d.room_size != null) facts.push(['Room', `${d.room_size} players`]);
  if (d.entry_cents != null) facts.push(['Entry', formatCurrency(d.entry_cents)]);
  if (d.prize_cents) facts.push(['Prize pool', formatCurrency(d.prize_cents)]);
  return (
    <div className="flex flex-wrap gap-2">
      {facts.map(([label, value]) => (
        <Fact key={label} label={label} value={value} />
      ))}
    </div>
  );
}

const REF_OF: Record<ActivityItem['type'], ContestRefType> = {
  match: 'match',
  pool: 'pool',
  tournament: 'tournament',
};

/** "Contest this result" — files a dispute (support review) inline. */
function ContestSection({ item }: { item: ActivityItem }) {
  const file = useFileDispute();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');

  if (item.dispute_status) {
    const label =
      item.dispute_status === 'open'
        ? 'Contested · under review'
        : item.dispute_status === 'resolved'
          ? 'Contest resolved'
          : 'Contest reviewed · result stands';
    return (
      <div className="mt-3 rounded-lg bg-panel-raised px-3 py-2 text-xs text-text-secondary">
        {label}
      </div>
    );
  }
  if (!DISPUTABLE_STATES.has(item.state)) return null;

  async function submit() {
    try {
      await file.mutateAsync({
        ref_type: REF_OF[item.type],
        ref_id: item.id,
        reason: reason.trim(),
      });
      toast.success('Contest submitted — support will review it.');
      setOpen(false);
      setReason('');
    } catch (err) {
      toast.error((err as Error)?.message ?? 'Could not submit your contest.');
    }
  }

  return (
    <div className="mt-3">
      {open ? (
        <div className="rounded-xl border border-hairline p-3">
          <label className="text-xs text-text-secondary" htmlFor={`contest-${item.id}`}>
            Tell support what looks wrong
          </label>
          <textarea
            id={`contest-${item.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="e.g. my last round wasn't counted"
            className="mt-1 w-full resize-none rounded-lg border border-hairline bg-bg px-3 py-2 text-sm text-text outline-none focus:border-text-secondary"
          />
          <div className="mt-2 flex items-center gap-2">
            <PillButton
              onClick={submit}
              disabled={file.isPending || reason.trim().length === 0}
            >
              Submit for review
            </PillButton>
            <PillButton variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </PillButton>
          </div>
        </div>
      ) : (
        <PillButton variant="outline" onClick={() => setOpen(true)}>
          Contest this result
        </PillButton>
      )}
    </div>
  );
}

/** One-tap rematch on a settled H2H row → challenge the same opponent. */
function RematchButton({ item }: { item: ActivityItem }) {
  const rematch = useCreateChallenge();
  if (item.type !== 'match' || !TERMINAL_STATES.has(item.state)) return null;
  return (
    <PillButton
      variant="outline"
      disabled={rematch.isPending}
      onClick={async () => {
        try {
          await rematch.mutateAsync({ rematch_of: item.id });
          toast.success(`Rematch sent to ${item.opponent_username ?? 'opponent'}`);
        } catch {
          // Surfaced by the global mutation-error toast.
        }
      }}
    >
      Rematch
    </PillButton>
  );
}

export function ActivityCard({ item }: { item: ActivityItem }) {
  const sub = statLine(item);
  return (
    <ExpandableCard
      ariaLabel={`${title(item)} — details`}
      left={
        <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${dotClass(item)}`} />
      }
      title={title(item)}
      subline={
        <>
          {stateLabel(item)}
          {sub && <span className="text-text-secondary"> · {sub}</span>}
          {item.resolved_at && (
            <span className="text-text-secondary">
              {' '}
              · {formatRelativeTime(item.resolved_at)}
            </span>
          )}
        </>
      }
      right={
        item.net_cents != null ? (
          <AmountText cents={item.net_cents} win={item.net_cents > 0} />
        ) : (
          <span className="text-xs text-text-secondary">
            {formatCurrency(item.entry_cents)} in play
          </span>
        )
      }
      footer={item.live ? <LiveLine live={item.live} /> : undefined}
    >
      <DetailBody item={item} />
      <div className="mt-3 flex items-center gap-2">
        <RematchButton item={item} />
      </div>
      <ContestSection item={item} />
    </ExpandableCard>
  );
}
