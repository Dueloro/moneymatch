"""The cs2.steam GameAdapter — Counter-Strike 2 through Steam.

Identity is a **SteamID64**, never a display name: persona names are mutable,
non-unique and unsearchable, which makes them an impersonation vector on a
product where money moves.

Match history is not fetched from a host. CS2 has no public per-match stats
API; the scoreboard comes from the Game Coordinator when a share code is
resolved, and is stored (`services/cs2_matches.py`). This adapter reads those
stored rows, so settlement never depends on the GC being reachable.

One consequence is a feature: **only Premier, Competitive and Wingman produce
share codes at all.** Casual, Deathmatch and Arms Race generate none, so mode
eligibility is enforced for free by the intake path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from ..db.session import get_sessionmaker
from ..schemas.profile import ProfileSnapshot
from ..services import cs2_matches
from ..services.hosts import steam
from .base import GameAdapter, GameFilters, NormGame, TelemetrySample

log = structlog.get_logger(__name__)

_GAME = "cs2.steam"


def _ban_label(bans: steam.BanStatus | None) -> str | None:
    """What to show about a player's standing.

    `None` from Steam means *unknown*, not *clean*. On a product where money
    moves, those must not render as the same thing.
    """
    if bans is None:
        return "Ban status unknown"
    return "VAC ban" if not bans.is_clean else None


def _won(row: Any, line: dict[str, Any]) -> bool | None:
    """Whether this player's side won, from the team scores.

    `None` when the scoreboard does not say which side the player was on. An
    unknown result must not be recorded as a loss.
    """
    if row.score_a == row.score_b:
        return False
    team = line.get("team")
    if team is None:
        return None
    winning = "a" if row.score_a > row.score_b else "b"
    return str(team).lower() == winning


class CS2SteamAdapter(GameAdapter):
    id = _GAME

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        """`identifier` is a SteamID64, established by Steam OpenID."""
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        steam_id = str(account_id).strip()
        if not steam_id.isdigit():
            raise ValueError(
                "A CS2 account is identified by its SteamID64. Sign in through "
                "Steam rather than typing a name."
            )

        # The SteamID is already proven at this point: OpenID verified it with
        # Steam itself. Everything below is enrichment, so a Steam Web API
        # outage or a missing key must not throw away a verified identity. It
        # degrades to a profile carrying the SteamID and an explicit unknown.
        summary = await steam.get_player_summary(steam_id)
        if summary is None:
            log.warning(
                "cs2.steam_profile_unavailable",
                steam_id=steam_id,
                key_configured=steam.is_configured(),
            )
            summary = {}

        # A lifetime K/D is the only skill signal available before the user has
        # played anything through us. It is cumulative across casual, deathmatch
        # and bot games, so it seeds a prior and is never shown as a rating.
        stats = await steam.get_cs2_lifetime_stats(steam_id)
        bans = await steam.get_player_bans(steam_id)
        kd = stats.kd_ratio if stats else None

        return ProfileSnapshot(
            username=steam_id,
            display_name=summary.get("personaname") or steam_id,
            url=summary.get("profileurl")
            or f"https://steamcommunity.com/profiles/{steam_id}",
            link_method="username",
            game=self.id,
            win_rate=(
                stats.total_matches_won / stats.total_matches_played
                if stats and stats.total_matches_played
                else 0.5
            ),
            draw_rate=0.0,
            total_games=stats.total_matches_played if stats else 0,
            rating=None,
            rank_label=_ban_label(bans),
            kd=round(kd, 4) if kd is not None else None,
            avatar_url=summary.get("avatarfull") or None,
            # Lifetime counters, so the profile row can show something concrete
            # rather than just an opaque 17-digit id. Absent when the profile
            # keeps its game details private, which is the common case.
            extra=(
                {
                    "total_kills": stats.total_kills,
                    "total_deaths": stats.total_deaths,
                    "hours_played": round(stats.total_time_played / 3600),
                }
                if stats
                else {}
            ),
        )

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """Stored matches whose roster contains this SteamID64, oldest first."""
        since = datetime.fromtimestamp(since_ms / 1000, UTC) if since_ms else None
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            rows = await cs2_matches.matches_for_steam_id(session, account_id, since)

        out: list[NormGame] = []
        for row in rows:
            line = row.line_for(account_id)
            if line is None:
                continue
            out.append(
                NormGame(
                    id=row.share_code,
                    speed=_GAME,
                    rated=True,
                    created_at_ms=int(row.match_time.timestamp() * 1000),
                    moves=0,
                    won=_won(row, line),
                    drawn=row.score_a == row.score_b,
                    metrics=cs2_matches.metrics_from_line(line),
                )
            )
        return out

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        return TelemetrySample(game=_GAME, metrics=norm.metrics)
