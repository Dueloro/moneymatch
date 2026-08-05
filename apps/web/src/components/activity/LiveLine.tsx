import type { LiveInfo } from '../../hooks/useActivity';

type Tone = 'live' | 'good' | 'bad' | 'muted';

/** Format a live metric value: numbers to ≤2 dp, win/next verbs to words. */
function fmtVal(v: number | string | null | undefined): string {
  if (v == null) return '-';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return { won: 'won', lost: 'lost', pending: 'in a match' }[v] ?? v;
}

/** Collapse a viewer-oriented `live` object into one line + a tone. */
function liveDescriptor(live: LiveInfo): { text: string; tone: Tone } | null {
  const label = live.label ?? 'stat';
  if (live.kind === 'pool') {
    switch (live.status) {
      case 'cleared':
        return {
          text: `${label} ${fmtVal(live.current)} · cleared ${fmtVal(live.target)}`,
          tone: 'good',
        };
      case 'missed':
        return {
          text: `${label} ${fmtVal(live.current)} · target ${fmtVal(live.target)}`,
          tone: 'bad',
        };
      case 'unavailable':
        return { text: `can't read the host right now`, tone: 'muted' };
      default:
        return { text: `waiting for your next match`, tone: 'muted' };
    }
  }
  if (live.kind === 'tournament') {
    if (live.status === 'scoring')
      return {
        text: `#${live.rank ?? '-'} of ${live.field ?? '-'} · ${label} ${fmtVal(live.score)}`,
        tone: 'live',
      };
    return { text: `waiting for your first match`, tone: 'muted' };
  }
  // match
  if (live.format === 'chess') {
    if (live.status === 'waiting')
      return { text: `game not started yet`, tone: 'muted' };
    if (live.status === 'finished') {
      if (live.result === 'you') return { text: `checkmate · you won`, tone: 'good' };
      if (live.result === 'opp') return { text: `game over · you lost`, tone: 'bad' };
      return { text: `game over · draw`, tone: 'muted' };
    }
    const whose =
      live.turn === 'you' ? 'your move' : live.turn === 'opp' ? "opponent's move" : '';
    return {
      text: `move ${live.moves ?? 0}${whose ? ` · ${whose}` : ''}`,
      tone: 'live',
    };
  }
  if (live.status === 'waiting')
    return { text: `waiting for your next match`, tone: 'muted' };
  if (live.format === 'stat_race') {
    const tone: Tone =
      live.leader === 'you' ? 'good' : live.leader === 'opp' ? 'bad' : 'live';
    return {
      text: `${label} · you ${fmtVal(live.you)} · opp ${fmtVal(live.opp)}`,
      tone,
    };
  }
  // win_next
  return { text: `you ${fmtVal(live.you)} · opp ${fmtVal(live.opp)}`, tone: 'live' };
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

/** The under-the-card live line for an in-flight contest. */
export function LiveLine({ live }: { live: LiveInfo }) {
  const d = liveDescriptor(live);
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
