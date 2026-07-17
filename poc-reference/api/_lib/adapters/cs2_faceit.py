"""The cs2.faceit GameAdapter — Counter-Strike 2 via the FaceIt Data API.

The second real adapter (roadmap §3/§5 — multi-game expansion). It proves the
game-agnostic seams with a genuinely different title: identity + skill come from
FaceIt rather than Lichess, and map into the same :class:`SkillProfile` the rest
of the app consumes. ``link_account`` / ``fetch_profile`` hit the live API; the
contest-settlement methods are the §5 onboarding stub (head-to-head settlement
against FaceIt match history is a later step).
"""

from __future__ import annotations

from typing import Optional

from _lib import faceit_service
from _lib.adapters.base import GameAdapter, GameFilters, NormGame
from _lib.schemas import Contract, SettleResult, SkillProfile, TelemetrySample

_GAME = "cs2"


def _to_float(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _extract_player_metrics(match_stats: dict, player_id: str) -> dict[str, float]:
    """Pull confirmed CS2 stat fields from /matches/{id}/stats for one player.

    Field names verified live against the FaceIt Data API. There is no per-player
    "Score" field; ADR (average damage per round) is the contribution metric. A
    field that is absent is simply omitted — a missing metric is never guessed.
    """
    key_map = {
        "Kills": "cs2_kills",
        "Deaths": "cs2_deaths",
        "K/D Ratio": "cs2_kd_ratio",
        "Headshots %": "cs2_headshot_pct",
        "ADR": "cs2_adr",
        "MVPs": "cs2_mvps",
    }
    for rnd in (match_stats.get("rounds") or []):
        for team in (rnd.get("teams") or []):
            for player in (team.get("players") or []):
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

    async def link_account(self, method: str, identifier: str) -> SkillProfile:
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> SkillProfile:
        player = await faceit_service.get_player(account_id, game=_GAME)
        if player is None:
            raise ValueError(f"FaceIt player '{account_id}' not found")
        games = player.get("games") or {}
        cs2 = games.get("cs2")
        if not cs2:
            # Player exists but has no CS2 block — usually a legacy CS:GO-only
            # account. csgo is out of scope; don't fabricate a profile that can
            # never settle a CS2 match. Surface a clear, actionable 404.
            raise ValueError(
                f"FaceIt user '{account_id}' has no CS2 activity. Only Counter-Strike 2 "
                f"is supported (legacy CS:GO accounts don't count)."
            )

        stats = await faceit_service.get_player_stats(player.get("player_id", ""), game=_GAME) or {}
        return self._to_profile(player, cs2, stats)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """The linked player's finished CS2 matches since ``since_ms``.

        ``account_id`` is the FaceIt nickname; resolve it to a player_id, fetch
        match history, and normalize each match to a win/loss for that player.
        """
        player = await faceit_service.get_player(account_id, game=_GAME)
        if player is None:
            return []
        player_id = player.get("player_id", "")
        if not player_id:
            return []

        # FaceIt history uses epoch seconds; widen the window slightly for clock skew.
        from_sec = max(0, int(since_ms / 1000) - 60)
        items = await faceit_service.get_player_history(player_id, _GAME, from_sec=from_sec)

        out: list[NormGame] = []
        for m in items:
            norm = self._normalize(m, player_id)
            if norm is None:
                continue
            # Enrich with per-match telemetry (kills/KD/HS%/ADR/MVPs) — powers
            # real CS2 solo grading and the FaceIt Lab. Cached, fail-soft: if the
            # stats call fails the match still settles win/loss for H2H.
            stats = await faceit_service.get_match_stats(norm.id)
            if stats:
                norm.metrics = _extract_player_metrics(stats, player_id)
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first → "next match" reads naturally
        return out

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        """Convert a normalized CS2 match to a TelemetrySample for solo grading."""
        return TelemetrySample(game="cs2.faceit", metrics=norm.metrics)

    def resolve_contract(
        self, contract: Contract, games: list[NormGame], now_ms: int
    ) -> SettleResult:
        """Grade a CS2 head-to-head against the player's next finished match.

        Head-to-head resolves on a single match: a win takes the pot minus rake;
        a loss goes to the opponent; an expired window with no qualifying match
        refunds the entry (overview §3.3). Mirrors the chess adapter's contract.
        """
        matched = contract.matched_at or 0
        window_ms = contract.window_hours * 3_600_000
        expired = now_ms > matched + window_ms

        # First finished match with a known result since the contract was made.
        q = [g for g in games if g.created_at_ms >= matched and g.won is not None]

        if q:
            g = q[0]
            user_won = bool(g.won)
            return SettleResult(
                id=contract.id, state="SETTLED",
                outcome="won" if user_won else "lost",
                winner="you" if user_won else "opponent",
                qualifying_game_ids=[g.id], resolved_at=now_ms,
                payout=round(contract.prize if user_won else 0.0, 2),
            )

        if expired:
            return SettleResult(
                id=contract.id, state="CANCELED", outcome="refunded",
                qualifying_game_ids=[], resolved_at=now_ms,
                payout=round(contract.entry, 2),
            )

        opp = contract.opponent.display_name
        return SettleResult(
            id=contract.id, state="ACTIVE",
            progress=f"Awaiting your next CS2 match vs {opp}", payout=0.0,
        )

    def _normalize(self, m: dict, player_id: str) -> Optional[NormGame]:
        """Turn a FaceIt history item into a win/loss for ``player_id``."""
        if m.get("status") != "finished":
            return None
        teams = m.get("teams") or {}
        my_faction: Optional[str] = None
        for faction, info in teams.items():
            players = (info or {}).get("players") or []
            if any(p.get("player_id") == player_id for p in players):
                my_faction = faction
                break
        if my_faction is None:
            return None

        winner = (m.get("results") or {}).get("winner")
        drawn = not winner
        won: Optional[bool] = None if drawn else (winner == my_faction)

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

    # ------------------------------------------------------------------
    # Host-specific mapping (kept private to the adapter).
    # ------------------------------------------------------------------

    def _to_profile(self, player: dict, cs2: dict, stats: dict) -> SkillProfile:
        nickname = player.get("nickname", "")
        skill_level = cs2.get("skill_level")
        elo = cs2.get("faceit_elo")

        matches = int(_to_float(stats.get("Matches")) or 0)
        win_rate_pct = _to_float(stats.get("Win Rate %"))
        win_rate = (win_rate_pct / 100.0) if win_rate_pct is not None else 0.5
        kd = _to_float(stats.get("Average K/D Ratio"))

        url = (player.get("faceit_url") or "").replace("{lang}", "en")

        return SkillProfile(
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
