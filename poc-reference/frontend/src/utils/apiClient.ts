import type {
  Contract,
  ContractDraft,
  LeaderboardResponse,
  LobbyResponse,
  SettleResponse,
  SkillProfile,
  SoloLobbyResponse,
  SoloPool,
  Match,
  MatchTrackerResponse,
  QueueResponse,
  SpectateResponse,
  TelemetrySample,
  Tournament,
  TournamentLobbyResponse,
} from '../types';

// Same-origin in production (Vercel serves /api via the Python function).
// In dev, Vite proxies /api -> http://localhost:8000. Override with VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function postJSON<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const detail = await safeDetail(res);
    throw new Error(detail ?? `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const data = await res.json();
    return (data?.detail as string) ?? null;
  } catch {
    return null;
  }
}

const q = (s: string) => encodeURIComponent(s);

export function fetchProfile(
  username: string,
  game?: string,
  signal?: AbortSignal,
): Promise<SkillProfile> {
  const gameParam = game ? `&game=${q(game)}` : '';
  return getJSON<SkillProfile>(`/api/profile?username=${q(username)}${gameParam}`, signal);
}

export function fetchLobby(
  username: string,
  game?: string,
  signal?: AbortSignal,
): Promise<LobbyResponse> {
  const gameParam = game ? `&game=${q(game)}` : '';
  return getJSON<LobbyResponse>(`/api/lobby?username=${q(username)}${gameParam}`, signal);
}

export function priceDraft(
  username: string,
  draft: ContractDraft,
  signal?: AbortSignal,
): Promise<Contract> {
  return postJSON<Contract>(
    `/api/contracts/price?username=${q(username)}`,
    draft,
    signal,
  );
}

export function settleContracts(
  username: string,
  contracts: Contract[],
  signal?: AbortSignal,
): Promise<SettleResponse> {
  return postJSON<SettleResponse>(
    '/api/contracts/settle',
    { username, contracts },
    signal,
  );
}

// ---- Algorithmic Solo Challenges (pooled tournaments) ----

export function fetchSoloLobby(signal?: AbortSignal): Promise<SoloLobbyResponse> {
  return getJSON<SoloLobbyResponse>('/api/solo/lobby', signal);
}

export function enterSoloPool(
  pool: SoloPool,
  playerId: string,
  state: string,
  signal?: AbortSignal,
): Promise<SoloPool> {
  return postJSON<SoloPool>(
    '/api/solo/pools/enter',
    { pool, player_id: playerId, state },
    signal,
  );
}

export function settleSoloPool(
  pool: SoloPool,
  telemetry: Record<string, TelemetrySample>,
  signal?: AbortSignal,
): Promise<SoloPool> {
  return postJSON<SoloPool>(
    '/api/solo/pools/settle',
    { pool, telemetry },
    signal,
  );
}

// ---- Multi-entrant tournaments ----

export function fetchTournamentLobby(signal?: AbortSignal): Promise<TournamentLobbyResponse> {
  return getJSON<TournamentLobbyResponse>('/api/tournaments/lobby', signal);
}

export function enterTournament(
  tournament: Tournament,
  playerId: string,
  state: string,
  signal?: AbortSignal,
): Promise<Tournament> {
  return postJSON<Tournament>(
    '/api/tournaments/enter',
    { tournament, player_id: playerId, state },
    signal,
  );
}

export function settleTournament(
  tournament: Tournament,
  telemetry: Record<string, TelemetrySample>,
  signal?: AbortSignal,
): Promise<Tournament> {
  return postJSON<Tournament>(
    '/api/tournaments/settle',
    { tournament, telemetry },
    signal,
  );
}

// ---- Leaderboard + spectator ----

export function fetchLeaderboard(signal?: AbortSignal): Promise<LeaderboardResponse> {
  return getJSON<LeaderboardResponse>('/api/leaderboard', signal);
}

export function fetchSpectate(username: string, signal?: AbortSignal): Promise<SpectateResponse> {
  return getJSON<SpectateResponse>(`/api/spectate?username=${q(username)}`, signal);
}

export function fetchTrack(
  game: string,
  username: string,
  signal?: AbortSignal,
): Promise<MatchTrackerResponse> {
  return getJSON<MatchTrackerResponse>(`/api/track?game=${q(game)}&username=${q(username)}`, signal);
}

// ---- FaceIt Lab (dev-only, read-only) ----

export interface FaceitMatchRow {
  id: string;
  created_at_ms: number;
  won: boolean | null;
  metrics: Record<string, number>;
}

export interface FaceitDistribution {
  metric: string;
  count: number;
  min: number;
  p25: number;
  median: number;
  p75: number;
  p90: number;
  max: number;
  mean: number;
}

export interface FaceitTelemetry {
  game: string;
  metrics: Record<string, number>;
  won: boolean | null;
  match_id: string;
}

export function fetchFaceitMatches(username: string, signal?: AbortSignal): Promise<FaceitMatchRow[]> {
  return getJSON<FaceitMatchRow[]>(`/api/dev/faceit/matches?username=${q(username)}`, signal);
}

export function fetchFaceitDistribution(
  username: string,
  metric: string,
  signal?: AbortSignal,
): Promise<FaceitDistribution> {
  return getJSON<FaceitDistribution>(
    `/api/dev/faceit/distribution?username=${q(username)}&metric=${q(metric)}`,
    signal,
  );
}

export function fetchFaceitTelemetry(username: string, signal?: AbortSignal): Promise<FaceitTelemetry> {
  return getJSON<FaceitTelemetry>(`/api/dev/faceit/telemetry?username=${q(username)}`, signal);
}

// ---- Real head-to-head matchmaking ----

export interface QueueBody {
  player_id: string;
  display_name: string;
  game: string;
  speed: string;
  format: string;
  entry: number;
  rating: number;
}

export function mmQueue(body: QueueBody, signal?: AbortSignal): Promise<QueueResponse> {
  return postJSON<QueueResponse>('/api/mm/queue', body, signal);
}

export function mmPoll(playerId: string, signal?: AbortSignal): Promise<QueueResponse> {
  return getJSON<QueueResponse>(`/api/mm/poll?player_id=${q(playerId)}`, signal);
}

export function mmMatch(matchId: string, signal?: AbortSignal): Promise<Match> {
  return getJSON<Match>(`/api/mm/match?match_id=${q(matchId)}`, signal);
}

function mmAction(path: string, matchId: string, playerId: string, signal?: AbortSignal): Promise<Match> {
  return postJSON<Match>(path, { match_id: matchId, player_id: playerId }, signal);
}
export const mmConfirm = (m: string, p: string, s?: AbortSignal) => mmAction('/api/mm/confirm', m, p, s);
export const mmCancel = (m: string, p: string, s?: AbortSignal) => mmAction('/api/mm/cancel', m, p, s);
export const mmSettle = (m: string, p: string, s?: AbortSignal) => mmAction('/api/mm/settle', m, p, s);
