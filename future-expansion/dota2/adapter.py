"""The dota2.opendota GameAdapter — Dota 2 via the public OpenDota API.

Ported from poc-reference. Identity + skill from OpenDota map into the same
`ProfileSnapshot`; recent matches yield win/loss (from ``player_slot`` vs
``radiant_win``) plus rate telemetry (KDA, GPM) for the metric-model bootstrap.

Two edge cases kept exactly as the PoC encoded them, plus one added gate:
- a numeric Steam32 id is used directly; a persona name is searched and
  candidates (most-active first) are tried until one has a public profile;
- **expose-data gate at link time** (launch plan §6.1): if the account's recent
  matches aren't readable ("Expose Public Match Data" off), the link is blocked
  with instructions rather than failing silently at settlement later.
"""

from __future__ import annotations

from ..schemas.profile import ProfileSnapshot
from ..services.hosts import opendota
from .base import GameAdapter, GameFilters, NormGame, TelemetrySample

_MODE = "dota2"

_EXPOSE_DATA_MSG = (
    "This Dota 2 account has no readable public matches. In the Dota 2 client, "
    "enable Settings → Options → Advanced → 'Expose Public Match Data', then play "
    "a match and try linking again."
)


class Dota2OpenDotaAdapter(GameAdapter):
    id = "dota2.opendota"

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        profile = await self.fetch_profile(identifier)
        # Expose-data gate: settlement needs readable recent matches. profile.
        # username is the resolved numeric account_id (the settlement poll key).
        recent = await opendota.get_recent_matches(profile.username, limit=5)
        if not recent:
            raise ValueError(_EXPOSE_DATA_MSG)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        ident = account_id.strip()
        # A numeric Steam32 id is used directly; a name is searched.
        candidates = (
            [ident] if ident.isdigit() else await opendota.search_players(ident)
        )
        resolved: str | None = None
        player: dict | None = None
        for cid in candidates:
            player = await opendota.get_player(cid)
            if player is not None:
                resolved = cid
                break
        if player is None or resolved is None:
            raise ValueError(
                f"Dota 2 player '{account_id}' not found (or profile is private)"
            )
        wl = await opendota.get_player_wl(resolved)
        return self._to_profile(resolved, player, wl)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """The player's finished matches since ``since_ms`` (account_id numeric)."""
        matches = await opendota.get_recent_matches(account_id, limit=20)
        out: list[NormGame] = []
        for m in matches:
            norm = self._normalize(m)
            if norm is not None and norm.created_at_ms >= since_ms - 60_000:
                out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out

    @staticmethod
    def norm_to_telemetry(norm: NormGame) -> TelemetrySample:
        """Convert a normalized Dota match to a TelemetrySample for solo grading."""
        return TelemetrySample(game="dota2.opendota", metrics=norm.metrics)

    # --- Host-specific mapping (private to the adapter) -------------------- #

    def _to_profile(self, account_id: str, player: dict, wl: dict) -> ProfileSnapshot:
        prof = player.get("profile") or {}
        persona = prof.get("personaname") or f"Player {account_id}"
        wins = int(wl.get("win", 0))
        losses = int(wl.get("lose", 0))
        total = wins + losses
        win_rate = wins / total if total else 0.5

        rank_tier = player.get("rank_tier")
        mmr = (player.get("mmr_estimate") or {}).get("estimate")
        rating = int(mmr) if mmr else opendota.mmr_from_rank(rank_tier)

        return ProfileSnapshot(
            username=str(account_id),  # numeric id — the settlement poll key
            display_name=persona,
            url=f"https://www.opendota.com/players/{account_id}",
            link_method="username",
            game=self.id,
            win_rate=round(win_rate, 4),
            draw_rate=0.0,
            total_games=total,
            rating=rating,
            rank_label=opendota.rank_label(rank_tier),
            avatar_url=prof.get("avatarfull") or None,
        )

    def _normalize(self, m: dict) -> NormGame | None:
        """Win/loss + rate telemetry for the linked player from a match row."""
        radiant_win = m.get("radiant_win")
        slot = m.get("player_slot")
        if radiant_win is None or slot is None:
            return None
        is_radiant = slot < 128
        won = is_radiant == bool(radiant_win)
        return NormGame(
            id=str(m.get("match_id", "")),
            speed=_MODE,
            rated=True,
            created_at_ms=int(m.get("start_time", 0)) * 1000,  # epoch seconds
            moves=0,
            won=won,
            drawn=False,
            metrics=_match_metrics(m),
        )


def _match_metrics(m: dict) -> dict[str, float]:
    """Rate metrics from a recent-match row (rate-based only — no raw totals)."""
    metrics: dict[str, float] = {}
    kills = m.get("kills")
    deaths = m.get("deaths")
    assists = m.get("assists")
    if kills is not None and deaths is not None and assists is not None:
        metrics["dota2_kda_ratio"] = round((kills + assists) / max(int(deaths), 1), 4)
    gpm = m.get("gold_per_min")
    if gpm is not None:
        metrics["dota2_gpm"] = float(gpm)
    return metrics
