import type { Comparator, MetricTarget, SoloGame, TelemetrySample } from '../types';

// Human labels for the metric keys used in qualifying standards.
const METRIC_LABEL: Record<string, string> = {
  rl_aerial_accuracy_pct: 'Aerial accuracy',
  rl_match_score: 'Match score',
  cr_crown_tower_damage: 'Crown-tower dmg',
  cr_total_elixir: 'Total elixir',
  chess_accuracy_pct: 'Accuracy',
  chess_moves: 'Moves',
  cs2_kills: 'Kills',
  cs2_kd_ratio: 'K/D ratio',
  cs2_headshot_pct: 'Headshot %',
  cs2_adr: 'ADR',
  cs2_mvps: 'MVPs',
  dota2_kda_ratio: 'KDA ratio',
  dota2_gpm: 'GPM',
};

const PCT_METRICS = new Set(['rl_aerial_accuracy_pct', 'chess_accuracy_pct', 'cs2_headshot_pct']);

const cmpSymbol = (c: Comparator | null | undefined): string => (c === 'lte' ? '≤' : '≥');

function fmtThreshold(metric: string, value: number): string {
  if (PCT_METRICS.has(metric)) return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(1);
}

/** Plain-English description of a qualifying standard, e.g. "Accuracy ≥82% · Moves ≥20". */
export function standardLabel(target: MetricTarget): string {
  const primary = `${METRIC_LABEL[target.metric] ?? target.metric} ${cmpSymbol(target.comparator)} ${fmtThreshold(target.metric, target.threshold)}`;
  if (!target.secondary_metric) return primary;
  const sm = target.secondary_metric;
  return `${primary} · ${METRIC_LABEL[sm] ?? sm} ${cmpSymbol(target.secondary_comparator)} ${fmtThreshold(sm, target.secondary_threshold ?? 0)}`;
}

/** A value that satisfies (or deliberately violates) a comparator/threshold. */
function genValue(comparator: Comparator, threshold: number, satisfy: boolean): number {
  const margin = Math.max(2, Math.round(Math.abs(threshold) * 0.1));
  if (comparator === 'gte') {
    return satisfy ? threshold + margin : Math.max(0, threshold - margin);
  }
  return satisfy ? Math.max(0, threshold - margin) : threshold + margin;
}

/**
 * Mock telemetry for the demo. Produces metrics that pass or fail the standard:
 * a "cleared" sample satisfies both primary and secondary constraints; a "missed"
 * sample violates the primary (secondary kept satisfied so the miss is clean).
 * In production this comes from the game's authenticated data webhook, not here.
 */
export function genTelemetry(target: MetricTarget, game: SoloGame, cleared: boolean): TelemetrySample {
  const metrics: Record<string, number> = {
    [target.metric]: genValue(target.comparator, target.threshold, cleared),
  };
  if (target.secondary_metric) {
    metrics[target.secondary_metric] = genValue(
      target.secondary_comparator ?? 'gte',
      target.secondary_threshold ?? 0,
      true, // keep the secondary satisfied; the miss (if any) is on the primary
    );
  }
  return { game, metrics };
}
