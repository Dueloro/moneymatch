// Mirrors the backend Pydantic schemas (api/_lib/schemas.py), plus a few
// client-only view types. Contests and the wallet live in localStorage in the
// demo; their shapes match what the production DB will store.

export type TabKey =
  | 'h2h'
  | 'solo'
  | 'tournaments'
  | 'leaderboard'
  | 'active'
  | 'profile'
  | 'responsible';

export type Speed = 'bullet' | 'blitz' | 'rapid' | 'classical';
export type LinkMethod = 'oauth' | 'username';

// ---- Identity / profile ----

export interface FormatStat {
  speed: Speed;
  rating: number;
  games: number;
  provisional: boolean;
}

export interface SkillProfile {
  username: string;
  display_name: string;
  url: string;
  link_method: LinkMethod;
  game?: string;
  account_age_days?: number | null;
  win_rate: number;
  draw_rate?: number;
  total_games: number;
  // Chess-specific (empty for other titles).
  formats: FormatStat[];
  primary_speed?: Speed | null;
  // Generic skill descriptors usable by any title.
  rating?: number | null;
  rank_label?: string | null;
  kd?: number | null;
  avatar_url?: string | null;
}

// ---- Objectives ----

export type ObjectiveKind = 'win_h2h' | 'win_under_moves';

export interface Objective {
  kind: ObjectiveKind;
  moves?: number | null;
}

// ---- Matchmaking ----

export interface Bracket {
  your_rating: number;
  band_low: number;
  band_high: number;
  match_quality: number; // 0..1, 1.0 == dead-even
  label: string;
}

export interface Opponent {
  username: string;
  display_name: string;
  rating: number;
  is_bot: boolean;
}

// ---- Contests ----

export type ContractState =
  | 'OPEN'
  | 'MATCHED'
  | 'ACTIVE'
  | 'RESOLVING'
  | 'SETTLED'
  | 'CANCELED';

export type ContractOutcome = 'won' | 'lost' | 'refunded';
export type Winner = 'you' | 'opponent';

export interface ContractDraft {
  game: string;
  speed: Speed | string;
  format: string;
  objective: Objective;
  window_hours: number;
  entry: number;
}

export interface Contract {
  id: string;
  game: string;
  speed: Speed | string;
  format: string;
  title: string;
  objective: Objective;
  window_hours: number;
  account_id?: string | null;

  // Money (escrow + rake).
  entry: number;
  entrants: number;
  rake_pct: number;
  pot: number;
  prize: number;
  rake: number;

  // Matchmaking.
  bracket: Bracket;
  opponent: Opponent;

  state: ContractState;
  matched_at: number | null; // epoch ms
  resolved_at: number | null; // epoch ms
  qualifying_game_ids: string[];
  progress: string | null;
  winner: Winner | null;
  outcome: ContractOutcome | null;
}

export interface LobbyResponse {
  profile: SkillProfile;
  contests: Contract[];
}

export interface SettleResult {
  id: string;
  state: ContractState;
  outcome: ContractOutcome | null;
  winner: Winner | null;
  qualifying_game_ids: string[];
  progress: string | null;
  resolved_at: number | null;
  payout: number;
}

export interface SettleResponse {
  results: SettleResult[];
}

// ---- Algorithmic Solo Challenges (pooled tournaments) ----
// Mirrors api/_lib/schemas.py. Prize comes from the entrants' pool, never the
// house; clearers of a qualifying standard split the pool minus rake.

export type SoloGame =
  | 'rocketleague.psyonix'
  | 'clashroyale.supercell'
  | 'chess.lichess'
  | 'cs2.faceit'
  | 'dota2.opendota';

export type MetricKind =
  | 'rl_aerial_accuracy_pct'
  | 'rl_match_score'
  | 'cr_crown_tower_damage'
  | 'chess_accuracy_pct'
  | 'cs2_kills'
  | 'cs2_kd_ratio'
  | 'cs2_headshot_pct'
  | 'cs2_adr'
  | 'cs2_mvps'
  | 'dota2_kda_ratio'
  | 'dota2_gpm';

export type Comparator = 'gte' | 'lte';

export interface MetricTarget {
  metric: MetricKind;
  comparator: Comparator;
  threshold: number;
  secondary_metric?: string | null;
  secondary_comparator?: Comparator | null;
  secondary_threshold?: number | null;
}

export type SoloEntryStatus =
  | 'LOCKED'
  | 'CLEARED'
  | 'MISSED'
  | 'REFUNDED'
  | 'BLOCKED_REGION';

export type SoloPoolStatus = 'OPEN' | 'SETTLED' | 'CANCELED';

export interface SoloEntry {
  player_id: string;
  state: string;
  status: SoloEntryStatus;
  cleared?: boolean | null;
  payout: number;
  detail?: string | null;
}

export interface SoloPool {
  id: string;
  game: SoloGame;
  metric_target: MetricTarget;
  entry_fee: number;
  rake_pct: number;
  min_entrants: number;
  entrants: SoloEntry[];
  pool: number;
  rake: number;
  prize_pool: number;
  status: SoloPoolStatus;
  created_at: number | null;
  resolved_at: number | null;
}

export interface TelemetrySample {
  game: SoloGame;
  metrics: Record<string, number>;
}

export interface SoloLobbyResponse {
  pools: SoloPool[];
}

// ---- Multi-entrant tournaments (roadmap §3 — Phase 2) ----
// Mirrors api/_lib/schemas.py. N entrants split a shared pool by finish rank;
// the top finishers take pool − rake per prize_split. No house.

export type TournamentFormat = 'leaderboard_pool' | 'single_elim';
export type TournamentStatus = 'OPEN' | 'SETTLED' | 'CANCELED';
export type TournamentEntryStatus = 'LOCKED' | 'PAID' | 'OUT' | 'REFUNDED';

export interface TournamentEntry {
  player_id: string;
  state: string;
  status: TournamentEntryStatus;
  score?: number | null;
  rank?: number | null;
  payout: number;
  detail?: string | null;
}

export interface BracketMatch {
  round: number;
  slot: number;
  player_a?: string | null;
  player_b?: string | null;
  winner?: string | null;
  games: number;
  detail?: string | null;
}

export interface Tournament {
  id: string;
  game: SoloGame;
  name: string;
  format: TournamentFormat;
  ranking_metric: MetricKind;
  higher_is_better: boolean;
  entry_fee: number;
  rake_pct: number;
  max_entrants: number;
  min_entrants: number;
  prize_split: number[];
  entrants: TournamentEntry[];
  pool: number;
  rake: number;
  prize_pool: number;
  rounds: BracketMatch[][];
  status: TournamentStatus;
  created_at: number | null;
  resolved_at: number | null;
}

export interface TournamentLobbyResponse {
  tournaments: Tournament[];
}

// ---- Leaderboard (ranked by ROI / record, never raw $) ----

export interface LeaderboardEntry {
  player_id: string;
  display_name: string;
  is_bot: boolean;
  contests: number;
  wins: number;
  win_rate: number;
  staked: number;
  net: number;
  roi: number;
}

export interface LeaderboardResponse {
  entries: LeaderboardEntry[];
}

// ---- Spectator view (move list + clock for your current Lichess game) ----

export interface SpectatePlayer {
  name: string;
  rating?: number | null;
}

export interface SpectateResponse {
  available: boolean;
  game_id?: string | null;
  url?: string | null;
  speed?: string | null;
  white?: SpectatePlayer | null;
  black?: SpectatePlayer | null;
  moves: string[];
  turn?: 'white' | 'black' | null;
  white_clock?: number | null;
  black_clock?: number | null;
  finished: boolean;
  status?: string | null;
  winner?: 'white' | 'black' | null;
  message?: string | null;
}

// ---- Live match tracker (CS2 / Dota) ----

export interface MatchStat {
  label: string;
  value: string;
}

export interface MatchTrackerResponse {
  available: boolean;
  headline?: string | null;
  subtitle?: string | null;
  status?: string | null; // "Live" | "Final"
  result?: 'won' | 'lost' | null;
  url?: string | null;
  stats: MatchStat[];
  message?: string | null;
}

// ---- Real head-to-head matchmaking (Phase 1) ----

export type MatchState = 'PENDING' | 'ACTIVE' | 'SETTLED' | 'CANCELED';

export interface MatchPlayer {
  player_id: string;
  display_name: string;
  rating: number;
  color?: string | null;
  confirmed: boolean;
  play_url?: string | null;
  payout: number;
}

export interface Match {
  id: string;
  game: string;
  speed: string;
  format: string;
  entry: number;
  rake_pct: number;
  pot: number;
  prize: number;
  rake: number;
  brokered: boolean;
  players: MatchPlayer[];
  state: MatchState;
  host_game_id?: string | null;
  winner_id?: string | null;
  outcome?: string | null;
  progress?: string | null;
  created_at: number;
  matched_at?: number | null;
  resolved_at?: number | null;
}

export interface QueueResponse {
  status: 'searching' | 'matched' | 'idle';
  match?: Match | null;
}

// ---- Settlement popup (client-only) ----

export interface SettlementResult {
  outcome: 'won' | 'lost' | 'refunded';
  payout: number; // amount credited back
  entry: number; // amount staked
  reason: string; // why: "You beat X", "You cleared the standard", …
  title?: string; // optional headline (contest / game)
}

// ---- Toasts (client-only) ----

export type ToastVariant = 'info' | 'success' | 'win' | 'loss';

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}
