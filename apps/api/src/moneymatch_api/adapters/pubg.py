"""The pubg.steam GameAdapter — PUBG: Battlegrounds via the official PUBG API.

Same surface as the other adapters (identity/profile/history → `ProfileSnapshot`
/ `NormGame`), sourced directly from the PUBG (gamelocker) API through
`services.hosts.pubg`. Battle-royale has no head-to-head "draw"; a match "win" is
a #1 finish (`winPlace == 1`). Per-match rate metrics (`pubg_kills`,
`pubg_damage`, `pubg_headshot_pct`) feed the metric-model bootstrap and the
solo/tournament grading — never raw lifetime totals.

PUBG is a fully registered, playable game: it's in `REGISTERED_GAMES`, this
adapter is in the registry, and its metrics drive pools / tournaments / stat
duels (constants: `GAME_RATE_METRICS`, `POOL_METRICS`, `TOURNAMENT_METRICS`,
`GAME_HISTORY_FLOOR`, `METRIC_BAR_INCREMENT`).
"""

from __future__ import annotations

from datetime import datetime

from ..schemas.profile import ProfileSnapshot
from ..services.hosts import pubg
from .base import GameAdapter, GameFilters, NormGame, TelemetrySample

# Cap match fan-out per history poll: the PUBG public rate limit is ~10 req/min,
# and one poll already spends a player lookup plus one request per match.
_MATCH_LIMIT = 8

# Lifetime totals we sum across game modes for the profile's soft skill signals.
_LIFETIME_FIELDS = ("roundsPlayed", "wins", "kills", "losses", "damageDealt")


def _num(v: object) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def _created_ms(iso: str | None) -> int:
    """PUBG `createdAt` (`2026-07-24T00:23:07Z`) → epoch ms; 0 if unparseable."""
    if not iso:
        return 0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return int(dt.timestamp() * 1000)


class PubgAdapter(GameAdapter):
    id = "pubg.steam"

    @property
    def _shard(self) -> str:
        # `pubg.steam` → `steam`; console shards (`pubg.psn`) map the same way.
        return self.id.split(".", 1)[1] if "." in self.id else "steam"

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        player = await pubg.get_player_by_name(identifier.strip(), self._shard)
        if player is None:
            raise ValueError(f"PUBG player '{identifier}' not found")
        account_id = player.get("id") or ""
        name = (player.get("attributes") or {}).get("name") or identifier
        profile = await self._profile_from(account_id, name)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        player = await pubg.get_player_by_id(account_id, self._shard)
        if player is None:
            raise ValueError(f"PUBG account '{account_id}' not found")
        name = (player.get("attributes") or {}).get("name") or account_id
        return await self._profile_from(account_id, name)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """The linked player's finished PUBG matches since ``since_ms``.

        Resolve the account, walk its recent match ids (capped), and normalize
        each to a win (#1 finish) + per-match rate telemetry. Fail-soft: an
        unavailable match is skipped, not fatal.
        """
        player = await pubg.get_player_by_id(account_id, self._shard)
        if player is None:
            return []
        match_ids = [
            m.get("id")
            for m in (player.get("relationships") or {})
            .get("matches", {})
            .get("data", [])
            if m.get("id")
        ]

        out: list[NormGame] = []
        for match_id in match_ids[:_MATCH_LIMIT]:
            match = await pubg.get_match(match_id, self._shard)
            if not match:
                continue
            norm = self._normalize(match, account_id)
            if norm is None or norm.created_at_ms < since_ms:
                continue
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        return TelemetrySample(game="pubg.steam", metrics=norm.metrics)

    # --- Host-specific mapping (private to the adapter) -------------------- #

    def _normalize(self, match: dict, account_id: str) -> NormGame | None:
        """Turn a raw match document into a NormGame for ``account_id``."""
        data = match.get("data") or {}
        attrs = data.get("attributes") or {}
        stats = self._participant_stats(match, account_id)
        if stats is None:
            return None

        kills = _num(stats.get("kills"))
        headshots = _num(stats.get("headshotKills"))
        metrics = {
            "pubg_kills": kills,
            "pubg_damage": round(_num(stats.get("damageDealt")), 1),
            "pubg_headshot_pct": round(100.0 * headshots / kills, 1) if kills else 0.0,
        }
        return NormGame(
            id=data.get("id", ""),
            speed=str(attrs.get("gameMode") or "unknown"),
            rated=True,
            created_at_ms=_created_ms(attrs.get("createdAt")),
            moves=0,
            won=stats.get("winPlace") == 1,
            drawn=False,  # battle royale has no draws
            metrics=metrics,
        )

    @staticmethod
    def _participant_stats(match: dict, account_id: str) -> dict | None:
        for inc in match.get("included") or []:
            if inc.get("type") != "participant":
                continue
            st = (inc.get("attributes") or {}).get("stats") or {}
            if st.get("playerId") == account_id:
                return st
        return None

    async def _profile_from(self, account_id: str, name: str) -> ProfileSnapshot:
        modes = await pubg.get_lifetime(account_id, self._shard) or {}
        agg = {k: 0.0 for k in _LIFETIME_FIELDS}
        for mode_stats in modes.values():
            for field in _LIFETIME_FIELDS:
                agg[field] += _num((mode_stats or {}).get(field))

        rounds = int(agg["roundsPlayed"])
        wins = int(agg["wins"])
        losses = int(agg["losses"])
        win_rate = (wins / rounds) if rounds else 0.5
        kd = (agg["kills"] / losses) if losses else agg["kills"]

        return ProfileSnapshot(
            username=account_id,  # the stable host id (bind() keys on this)
            display_name=name,
            url=f"https://pubg.op.gg/user/{name}",
            link_method="username",
            game=self.id,
            win_rate=round(win_rate, 4),
            draw_rate=0.0,
            total_games=rounds,
            rating=None,
            rank_label=None,
            kd=round(kd, 2) if rounds else None,
        )
