import type { MetricKind, SoloGame, TelemetrySample, TournamentFormat } from '../types';

// Human label + plausible value range for each ranking metric. The range drives
// the demo score generator; in production scores come from the game's data
// webhook, not here.
const METRIC: Record<MetricKind, { label: string; pct: boolean; min: number; max: number; dec?: number }> = {
  chess_accuracy_pct: { label: 'Accuracy', pct: true, min: 62, max: 96 },
  rl_aerial_accuracy_pct: { label: 'Aerial accuracy', pct: true, min: 35, max: 88 },
  rl_match_score: { label: 'Match score', pct: false, min: 220, max: 880 },
  cr_crown_tower_damage: { label: 'Crown-tower dmg', pct: false, min: 1200, max: 6800 },
  cs2_kills: { label: 'Kills', pct: false, min: 8, max: 40 },
  cs2_kd_ratio: { label: 'K/D ratio', pct: false, min: 0.6, max: 2.2, dec: 2 },
  cs2_headshot_pct: { label: 'Headshot %', pct: true, min: 30, max: 70 },
  cs2_adr: { label: 'ADR', pct: false, min: 50, max: 120 },
  cs2_mvps: { label: 'MVPs', pct: false, min: 0, max: 10 },
  dota2_kda_ratio: { label: 'KDA ratio', pct: false, min: 1.0, max: 8.0, dec: 1 },
  dota2_gpm: { label: 'GPM', pct: false, min: 300, max: 800 },
};

/** Plain-English label for the metric entrants are ranked on. */
export function rankingLabel(metric: MetricKind): string {
  return METRIC[metric]?.label ?? metric;
}

/** Format a ranking score for display, e.g. "88%", "640", or "1.74". */
export function formatScore(metric: MetricKind, value: number): string {
  const m = METRIC[metric];
  if (!m) return String(value);
  if (m.pct) return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
  if (m.dec) return value.toFixed(m.dec);
  return Math.round(value).toLocaleString();
}

/** Human summary of a prize split, e.g. "Top 3 paid · 60 / 30 / 10". */
export function prizeSplitLabel(split: number[]): string {
  const pcts = split.map((w) => Math.round(w * 100)).join(' / ');
  return `Top ${split.length} paid · ${pcts}`;
}

/** Short label for a tournament format. */
export function formatLabel(format: TournamentFormat): string {
  return format === 'single_elim' ? 'Single-elimination bracket' : 'Leaderboard pool';
}

/**
 * Round name within a bracket of ``totalRounds`` rounds, counting back from the
 * final — e.g. "Final", "Semi-finals", "Quarter-finals", then "Round 1".
 */
export function roundName(roundIndex: number, totalRounds: number): string {
  const fromEnd = totalRounds - 1 - roundIndex;
  if (fromEnd === 0) return 'Final';
  if (fromEnd === 1) return 'Semi-finals';
  if (fromEnd === 2) return 'Quarter-finals';
  return `Round ${roundIndex + 1}`;
}

/**
 * Mock telemetry for one entrant: a random plausible score for the ranking
 * metric. ``strong`` biases toward the top of the range (used to give the human
 * player a fighting chance in the demo). In production this arrives from the
 * game's authenticated data webhook.
 */
export function genScore(metric: MetricKind, game: SoloGame, strong = false): TelemetrySample {
  const m = METRIC[metric] ?? { min: 0, max: 100, pct: false, label: metric, dec: undefined };
  const lo = strong ? m.min + (m.max - m.min) * 0.55 : m.min;
  const value = lo + Math.random() * (m.max - lo);
  const rounded = m.dec
    ? Math.round(value * 10 ** m.dec) / 10 ** m.dec
    : m.pct
      ? Math.round(value * 10) / 10
      : Math.round(value);
  return { game, metrics: { [metric]: rounded } };
}
