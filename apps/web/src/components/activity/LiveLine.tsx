import type { LiveInfo } from '../../hooks/useActivity';
import { formatMetric } from '../../lib/metrics';

type Tone = 'live' | 'good' | 'bad' | 'muted';

// The live payload carries the winner but not how the game ended, so a result
// line never names checkmate, resignation or time.
function liveDescriptor(
  live: LiveInfo,
  metric: string,
): { text: string; tone: Tone } | null {
  const fm = (v: number | null | undefined) => formatMetric(metric, v);
  if (live.kind === 'pool') {
    switch (live.status) {
      case 'cleared':
        return {
          text: `cleared · ${fm(live.current)}, bar ${fm(live.target)}`,
          tone: 'good',
        };
      case 'missed':
        return {
          text: `missed · ${fm(live.current)}, bar ${fm(live.target)}`,
          tone: 'bad',
        };
      case 'unavailable':
        return { text: `can't reach Lichess right now`, tone: 'muted' };
      default:
        return { text: `waiting for your next game`, tone: 'muted' };
    }
  }
  if (live.kind === 'tournament') {
    if (live.status === 'scoring')
      return {
        text: `#${live.rank ?? '-'} of ${live.field ?? '-'} · ${fm(live.score)}`,
        tone: 'live',
      };
    return { text: `waiting for your first game`, tone: 'muted' };
  }
  if (live.format === 'chess') {
    if (live.status === 'waiting')
      return { text: `game not started yet`, tone: 'muted' };
    if (live.status === 'finished') {
      if (live.result === 'you') return { text: `you won`, tone: 'good' };
      if (live.result === 'opp') return { text: `you lost`, tone: 'bad' };
      if (live.result === 'draw') return { text: `draw`, tone: 'muted' };
      return { text: `game over`, tone: 'muted' };
    }
    const whose =
      live.turn === 'you' ? 'your move' : live.turn === 'opp' ? "opponent's move" : '';
    return {
      text: `move ${live.moves ?? 0}${whose ? ` · ${whose}` : ''}`,
      tone: 'live',
    };
  }
  return null;
}

const TONE_DOT: Record<Tone, string> = {
  live: 'bg-live animate-pulse',
  good: 'bg-green',
  bad: 'bg-text-secondary',
  muted: 'bg-text-secondary',
};
const TONE_TEXT: Record<Tone, string> = {
  live: 'text-text',
  good: 'text-green',
  bad: 'text-text-secondary',
  muted: 'text-text-secondary',
};

export function LiveLine({ live, metric = '' }: { live: LiveInfo; metric?: string }) {
  const d = liveDescriptor(live, metric);
  if (!d) return null;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${TONE_DOT[d.tone]}`} />
      <span className="uppercase tracking-wide text-text-secondary">
        {live.status === 'finished' ? 'Final' : 'Live'}
      </span>
      <span className={TONE_TEXT[d.tone]}>{d.text}</span>
    </div>
  );
}
