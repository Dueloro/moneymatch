import type { Contract, SoloPool, Tournament } from '../types';

// A player's aggregated competitive record, mirroring the server's
// LeaderboardEntry shape (minus identity). Ranked on ROI, not raw $ (§3.1).
export interface PlayerStats {
  contests: number; // graded (non-refunded) contests across all modes
  wins: number; // H2H wins + tournament/solo in-the-money finishes
  winRate: number; // 0..1
  staked: number; // total entries on graded contests
  net: number; // net P&L (can be negative)
  roi: number; // net / staked
}

const EMPTY: PlayerStats = { contests: 0, wins: 0, winRate: 0, staked: 0, net: 0, roi: 0 };
const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * Aggregate the signed-in user's demo record across head-to-head matches,
 * tournaments, and solo pools. Refunded/canceled contests don't count toward
 * the record (no skill outcome). ROI is the headline ranking key.
 */
export function computePlayerStats(args: {
  username: string | null;
  contracts: Contract[]; // settled H2H contracts
  tournaments: Tournament[]; // the user's tournaments
  soloPools: SoloPool[]; // the user's solo pools
}): PlayerStats {
  const { username, contracts, tournaments, soloPools } = args;
  if (!username) return EMPTY;

  let contests = 0;
  let wins = 0;
  let staked = 0;
  let net = 0;

  // Head-to-head: graded when won or lost; refunded excluded.
  for (const c of contracts) {
    if (c.outcome === 'won') {
      contests++; wins++; staked += c.entry; net += c.prize - c.entry;
    } else if (c.outcome === 'lost') {
      contests++; staked += c.entry; net -= c.entry;
    }
  }

  // Tournaments: graded when the user's entry was paid or out (not refunded).
  for (const t of tournaments) {
    if (t.status !== 'SETTLED') continue;
    const e = t.entrants.find((x) => x.player_id === username);
    if (!e || e.status === 'REFUNDED') continue;
    contests++; staked += t.entry_fee; net += e.payout - t.entry_fee;
    if (e.status === 'PAID') wins++;
  }

  // Solo pools: graded when cleared or missed (not refunded).
  for (const p of soloPools) {
    if (p.status !== 'SETTLED') continue;
    const e = p.entrants.find((x) => x.player_id === username);
    if (!e || e.status === 'REFUNDED') continue;
    contests++; staked += p.entry_fee; net += e.payout - p.entry_fee;
    if (e.status === 'CLEARED') wins++;
  }

  return {
    contests,
    wins,
    winRate: contests > 0 ? wins / contests : 0,
    staked: round2(staked),
    net: round2(net),
    roi: staked > 0 ? net / staked : 0,
  };
}

export interface OpponentRecord {
  name: string;
  rating: number;
  isBot: boolean;
  played: number;
  wins: number;
  losses: number;
  net: number;
}

/** Per-opponent head-to-head record + P&L, busiest matchups first. */
export function computeOpponentRecords(contracts: Contract[]): OpponentRecord[] {
  const byName = new Map<string, OpponentRecord>();
  for (const c of contracts) {
    if (c.outcome !== 'won' && c.outcome !== 'lost') continue; // skip refunds
    const key = c.opponent.display_name;
    const rec =
      byName.get(key) ??
      { name: key, rating: c.opponent.rating, isBot: c.opponent.is_bot, played: 0, wins: 0, losses: 0, net: 0 };
    rec.played++;
    if (c.outcome === 'won') { rec.wins++; rec.net += c.prize - c.entry; }
    else { rec.losses++; rec.net -= c.entry; }
    byName.set(key, rec);
  }
  return [...byName.values()]
    .map((r) => ({ ...r, net: round2(r.net) }))
    .sort((a, b) => b.played - a.played || b.net - a.net);
}
