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

Only *official* modes settle (`_is_official`): custom / arcade / war / event /
training are skipped. `NormGame.speed` carries the settling match's `gameMode`
(the audit trail for which mode graded). Team-mode `winPlace == 1` still credits
one player, and a stat duel can compare a squad game against a solo game — both
are accepted residuals of the "official modes, no custom" policy.
"""

from __future__ import annotations

from datetime import datetime

from ..constants import (
    PUBG_INGEST_MATCHES_PER_POLL,
    PUBG_MATCH_FANOUT,
    PUBG_OFFICIAL_GAME_MODES,
    PUBG_OFFICIAL_MATCH_TYPES,
)
from ..schemas.profile import ProfileSnapshot
from ..services.hosts import pubg
from ..services.hosts.errors import HostNotConfigured
from .base import (
    GameAdapter,
    GameFilters,
    HistoryBatch,
    NormGame,
    TelemetrySample,
)

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
    # PUBG's ~10 req/min budget makes a link-time history bootstrap too expensive
    # to run inline; the settlement worker bootstraps the metric models instead.
    defer_bootstrap = True

    @property
    def _shard(self) -> str:
        # `pubg.steam` → `steam`; console shards (`pubg.psn`) map the same way.
        return self.id.split(".", 1)[1] if "." in self.id else "steam"

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        if not pubg.is_configured():
            raise HostNotConfigured("pubg", "PUBG_API_KEY is not configured")
        player = await pubg.get_player_by_name(identifier.strip(), self._shard)
        if player is None:
            raise ValueError(
                f"PUBG player '{identifier}' not found. Names are case-sensitive, "
                "so check the exact spelling. A brand-new account only appears "
                "after it finishes its first match: play one, wait a few "
                "minutes, then try again."
            )
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
        for match_id in match_ids[:PUBG_MATCH_FANOUT]:
            match = await pubg.get_match(match_id, self._shard)
            if not match:
                continue
            norm = self._normalize(match, account_id)
            if norm is None or not norm.eligible:
                continue  # unreadable or a non-official mode — skip, keep scanning
            if norm.created_at_ms < since_ms:
                # The match list is newest-first, so everything past here is older.
                break
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out

    async def fetch_history(
        self,
        account_id: str,
        since_ms: int,
        *,
        known_ids: set[str],
        first_poll: bool,
    ) -> HistoryBatch:
        """New matches for the background ingester, spending as few calls as
        possible out of PUBG's ~10 req/min.

        One call lists the player's recent match ids; only ids we have never
        stored are then fetched, one call each. The first poll of an account
        backfills the newest `PUBG_MATCH_FANOUT`; after that, new ids are taken
        **oldest first**, capped at `PUBG_INGEST_MATCHES_PER_POLL`, so a player
        who played a lot between polls catches up over the next polls without
        their earliest (tournament-counting) matches being skipped.

        A host outage raises (`HostUnavailable` from the client), so the
        ingester retries instead of recording "no new matches".
        """
        # Without a key every lookup "finds nothing", which would read as a
        # successful poll with no new matches and let a tournament settle on an
        # empty history. A missing key is a failure: the account stays unpolled
        # (its entrants are refunded at the timeout, never scored as absent).
        if not pubg.is_configured():
            raise HostNotConfigured("pubg", "PUBG_API_KEY is not configured")
        player = await pubg.get_player_by_id(account_id, self._shard)
        if player is None:
            return HistoryBatch([])
        ids = [
            m.get("id")
            for m in (player.get("relationships") or {})
            .get("matches", {})
            .get("data", [])
            if m.get("id")
        ]  # newest first
        new_ids = [i for i in ids if i not in known_ids]
        # The first poll deliberately stops at the newest `PUBG_MATCH_FANOUT`
        # (older matches are not needed), so it counts as complete.
        complete = True
        if first_poll:
            new_ids = new_ids[:PUBG_MATCH_FANOUT]
        else:
            complete = len(new_ids) <= PUBG_INGEST_MATCHES_PER_POLL
            new_ids = list(reversed(new_ids))[:PUBG_INGEST_MATCHES_PER_POLL]

        out: list[NormGame] = []
        for match_id in new_ids:
            match = await pubg.get_match(match_id, self._shard)
            if not match:
                continue  # expired (404) — nothing to store
            norm = self._normalize(match, account_id)
            if norm is not None:
                out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)
        return HistoryBatch(out, complete=complete)

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        return TelemetrySample(game="pubg.steam", metrics=norm.metrics)

    # --- Host-specific mapping (private to the adapter) -------------------- #

    def _normalize(self, match: dict, account_id: str) -> NormGame | None:
        """Turn a raw match document into a NormGame for ``account_id``."""
        data = match.get("data") or {}
        attrs = data.get("attributes") or {}
        # Custom / arcade / war / event / training never settle a contest, but
        # the match is still returned (marked ineligible) so the ingester can
        # store it: it is history, and the admin log should show it.
        official = self._is_official(attrs)
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
        created_ms = _created_ms(attrs.get("createdAt"))
        # When *this player's* game ended: start + their time survived. Their
        # kills/damage/headshots are final from that moment. The match's own
        # `duration` runs until the last player dies (and overshoots: a match
        # fetched at 23:12 reported an end of 23:22), which wrongly pushed games
        # past a tournament's cutoff.
        survived_s = stats.get("timeSurvived")
        duration_s = survived_s if survived_s else attrs.get("duration")
        ended_ms = (
            created_ms + int(duration_s) * 1000
            if created_ms and isinstance(duration_s, (int, float))
            else None
        )
        return NormGame(
            id=data.get("id", ""),
            speed=str(attrs.get("gameMode") or "unknown"),
            rated=official,
            created_at_ms=created_ms,
            moves=0,
            won=stats.get("winPlace") == 1,
            drawn=False,  # battle royale has no draws
            metrics=metrics,
            ended_at_ms=ended_ms,
            eligible=official,
            detail={
                "win_place": stats.get("winPlace"),
                "game_mode": attrs.get("gameMode"),
                "match_type": attrs.get("matchType"),
                "map": attrs.get("mapName"),
                "time_survived": stats.get("timeSurvived"),
            },
        )

    @staticmethod
    def _is_official(attrs: dict) -> bool:
        """Only standard battle-royale play settles: an allowlisted gameMode, an
        official/competitive matchType, and not a custom lobby. Team-mode win
        attribution and cross-mode stat comparison are accepted residuals."""
        if attrs.get("isCustomMatch"):
            return False
        game_mode = str(attrs.get("gameMode") or "")
        match_type = str(attrs.get("matchType") or "")
        return (
            game_mode in PUBG_OFFICIAL_GAME_MODES
            and match_type in PUBG_OFFICIAL_MATCH_TYPES
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
        # PUBG's conventional K/D: kills per non-winning round (losses = rounds −
        # wins), NOT kills/deaths. A soft profile/bracketing signal only.
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
