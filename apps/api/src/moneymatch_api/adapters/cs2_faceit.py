"""The cs2.faceit GameAdapter — Counter-Strike 2 via the FaceIt Data API.

Ported from poc-reference. Identity + skill from FaceIt map into the same
`ProfileSnapshot`. Per-match rate telemetry (K/D, ADR, HS%…) is enriched from
`/matches/{id}/stats` for the metric-model bootstrap and Phase-4 solo grading
(`norm_to_telemetry`). Legacy CS:GO-only accounts are rejected — csgo is out of
scope and can never settle a CS2 match.
"""

from __future__ import annotations

from ..schemas.profile import ProfileSnapshot
from ..services.hosts import faceit
from .base import GameAdapter, GameFilters, NormGame, TelemetrySample

_GAME = "cs2"


def _to_float(v: str | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _extract_player_metrics(match_stats: dict, player_id: str) -> dict[str, float]:
    """Pull confirmed CS2 stat fields from /matches/{id}/stats for one player.

    Field names verified live against the FaceIt Data API. There is no per-player
    "Score" field; ADR is the contribution metric. An absent field is omitted —
    a missing metric is never guessed.
    """
    key_map = {
        "Kills": "cs2_kills",
        "Deaths": "cs2_deaths",
        "K/D Ratio": "cs2_kd_ratio",
        "Headshots %": "cs2_headshot_pct",
        "ADR": "cs2_adr",
        "MVPs": "cs2_mvps",
    }
    for rnd in match_stats.get("rounds") or []:
        for team in rnd.get("teams") or []:
            for player in team.get("players") or []:
                if (player.get("player_id") or "") != player_id:
                    continue
                ps = player.get("player_stats") or {}
                metrics: dict[str, float] = {}
                for src, dst in key_map.items():
                    if src in ps:
                        val = _to_float(ps[src])
                        if val is not None:
                            metrics[dst] = val
                return metrics
    return {}


class CS2FaceitAdapter(GameAdapter):
    id = "cs2.faceit"

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        player = await faceit.get_player(account_id, game=_GAME)
        if player is None:
            raise ValueError(f"FaceIt player '{account_id}' not found")
        games = player.get("games") or {}
        cs2 = games.get("cs2")
        if not cs2:
            # Player exists but has no CS2 block — usually a legacy CS:GO-only
            # account. Don't fabricate a profile that can never settle a CS2
            # match; surface a clear, actionable error (the router maps to 404).
            raise ValueError(
                f"FaceIt user '{account_id}' has no CS2 activity. Only "
                f"Counter-Strike 2 is supported (legacy CS:GO accounts don't count)."
            )

        stats = (
            await faceit.get_player_stats(player.get("player_id", ""), game=_GAME) or {}
        )
        return self._to_profile(player, cs2, stats)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """The linked player's finished CS2 matches since ``since_ms``.

        ``account_id`` is the FaceIt nickname; resolve to a player_id, fetch
        history, and normalize each match to a win/loss + per-match telemetry.
        """
        player = await faceit.get_player(account_id, game=_GAME)
        if player is None:
            return []
        player_id = player.get("player_id", "")
        if not player_id:
            return []

        # FaceIt history uses epoch seconds; widen slightly for clock skew.
        from_sec = max(0, int(since_ms / 1000) - 60)
        items = await faceit.get_player_history(player_id, _GAME, from_sec=from_sec)

        out: list[NormGame] = []
        for m in items:
            norm = self._normalize(m, player_id)
            if norm is None:
                continue
            # Enrich with per-match telemetry (kills/KD/HS%/ADR/MVPs). Fail-soft:
            # if stats are unavailable the match still settles win/loss for H2H.
            stats = await faceit.get_match_stats(norm.id)
            if stats:
                norm.metrics = _extract_player_metrics(stats, player_id)
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        """Convert a normalized CS2 match to a TelemetrySample for solo grading."""
        return TelemetrySample(game="cs2.faceit", metrics=norm.metrics)

    def _normalize(self, m: dict, player_id: str) -> NormGame | None:
        """Turn a FaceIt history item into a win/loss for ``player_id``."""
        if m.get("status") != "finished":
            return None
        teams = m.get("teams") or {}
        my_faction: str | None = None
        for faction, info in teams.items():
            players = (info or {}).get("players") or []
            if any(p.get("player_id") == player_id for p in players):
                my_faction = faction
                break
        if my_faction is None:
            return None

        winner = (m.get("results") or {}).get("winner")
        drawn = not winner
        won: bool | None = None if drawn else (winner == my_faction)

        started = m.get("started_at") or m.get("finished_at") or 0
        return NormGame(
            id=m.get("match_id", ""),
            speed=_GAME,
            rated=True,
            created_at_ms=int(started) * 1000,  # FaceIt timestamps are epoch seconds
            moves=0,
            won=won,
            drawn=drawn,
        )

    # --- Host-specific mapping (private to the adapter) -------------------- #

    def _to_profile(self, player: dict, cs2: dict, stats: dict) -> ProfileSnapshot:
        nickname = player.get("nickname", "")
        skill_level = cs2.get("skill_level")
        elo = cs2.get("faceit_elo")

        matches = int(_to_float(stats.get("Matches")) or 0)
        win_rate_pct = _to_float(stats.get("Win Rate %"))
        win_rate = (win_rate_pct / 100.0) if win_rate_pct is not None else 0.5
        kd = _to_float(stats.get("Average K/D Ratio"))

        url = (player.get("faceit_url") or "").replace("{lang}", "en")

        return ProfileSnapshot(
            username=nickname,
            display_name=nickname,
            url=url or f"https://www.faceit.com/en/players/{nickname}",
            link_method="username",
            game=self.id,
            win_rate=round(win_rate, 4),
            draw_rate=0.0,
            total_games=matches,
            rating=int(elo) if elo is not None else None,
            rank_label=f"Level {skill_level}" if skill_level is not None else None,
            kd=kd,
            avatar_url=player.get("avatar") or None,
        )
