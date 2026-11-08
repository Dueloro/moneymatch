import type { Settlement } from '../hooks/useSettlementCelebration';
import { formatPoints } from './format';
import { terminationPhrase } from './matchResult';

/** One quiet line for every result that doesn't take the screen. */
export function settlementToast(s: Settlement): {
  kind: 'success' | 'neutral';
  text: string;
  to: string;
} {
  const vs = s.opponent ? ` vs ${s.opponent}` : '';
  const how = terminationPhrase(s.termination);
  const tail = how ? ` · ${how}` : '';
  const entry = s.entryCents ?? Math.abs(s.netCents);
  const to = s.type === 'match' ? `/play?match=${s.id}` : '/activity';
  switch (s.outcome) {
    case 'win': {
      const won = s.prizeCents ?? s.netCents;
      return { kind: 'success', text: `You won ${formatPoints(won)}${vs}${tail}`, to };
    }
    case 'loss':
      return { kind: 'neutral', text: `Lost ${formatPoints(entry)}${vs}${tail}`, to };
    case 'push':
      return {
        kind: 'neutral',
        text: `Draw${vs} · ${formatPoints(entry)} refunded`,
        to,
      };
    default:
      return {
        kind: 'neutral',
        text: `${formatPoints(entry)} refunded${vs ? vs : ` · ${s.title}`}`,
        to,
      };
  }
}
