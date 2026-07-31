"""Demo-login bypass — a complete, Supabase-free sign-in for demos.

`POST /demo/login` provisions + onboards a single shared demo user and mints a
short-lived token that `auth.verify_token` accepts **only** when
`demo_login_enabled` is on. It uses its own signing key, so it coexists with real
Supabase auth (Google / email + password keep working). Play-money only — never
enable on a real-money deployment.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..config import Settings, get_settings
from ..constants import (
    DEMO_AUTH_ID,
    DEMO_EMAIL,
    DEMO_JWT_SECRET,
    DEMO_RESIDENCE_STATE,
    DEMO_USERNAME,
    GAME_CS2_FACEIT,
    GAME_PUBG_STEAM,
    POOL_METRICS,
    REGISTERED_GAMES,
    TOURNAMENT_METRICS,
    game_display_name,
)
from ..db.session import get_session
from ..errors import APIError
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer
from ..models.skill import MetricModel
from ..models.user import User
from ..services import money_math, wallet_service
from ..services.user_service import (
    complete_onboarding,
    get_or_create_user,
    provision_new_user,
)

router = APIRouter(prefix="/demo", tags=["demo"])

_TOKEN_TTL = timedelta(hours=12)

# Plausible baselines (μ, σ) per metric so the demo user's pool/tournament bars
# and head-to-head duels are all non-provisional out of the box, on every game.
_DEMO_METRIC_FIXTURE: dict[str, tuple[float, float]] = {
    "chess_accuracy": (85.0, 6.0),
    "cs2_kd_ratio": (1.15, 0.22),
    "cs2_adr": (78.0, 12.0),
    "cs2_headshot_pct": (47.0, 8.0),
    "dota2_kda_ratio": (3.2, 0.8),
    "dota2_gpm": (520.0, 90.0),
    "pubg_kills": (4.5, 2.0),
    "pubg_damage": (380.0, 120.0),
    "pubg_headshot_pct": (22.0, 8.0),
}


async def _ensure_demo_fixture(session: AsyncSession, user: User) -> None:
    """Link the demo user to every playable game + seed non-provisional metric
    models, so Solo Pools, Tournaments, and Head-to-Head are populated with
    joinable cards on every game out of the box. Idempotent."""
    linked = set(
        await session.scalars(
            select(LinkedAccount.game).where(LinkedAccount.user_id == user.id)
        )
    )
    have_models = {
        (g, m)
        for g, m in await session.execute(
            select(MetricModel.game, MetricModel.metric).where(
                MetricModel.user_id == user.id
            )
        )
    }
    for game in REGISTERED_GAMES:
        if game not in linked:
            session.add(
                LinkedAccount(
                    user_id=user.id,
                    game=game,
                    host_account_id=f"{game}_{DEMO_USERNAME}",
                    host_username=DEMO_USERNAME,
                    profile_snapshot={
                        "username": DEMO_USERNAME,
                        "display_name": DEMO_USERNAME,
                        "game": game,
                        "total_games": 120,
                        "win_rate": 0.55,
                        "rank_label": game_display_name(game).split(" — ")[-1],
                    },
                )
            )
        metrics = set(POOL_METRICS.get(game, ())) | set(
            TOURNAMENT_METRICS.get(game, ())
        )
        for metric in metrics:
            if (game, metric) in have_models:
                continue
            mu, sigma = _DEMO_METRIC_FIXTURE.get(metric, (1.0, 0.2))
            session.add(
                MetricModel(
                    user_id=user.id, game=game, metric=metric, mu=mu, sigma=sigma, n=25
                )
            )
    await session.flush()


# --------------------------------------------------------------------------- #
# Demo Activity history — a set of real, ledger-consistent SETTLED matches so
# the demo lands on a populated, believable feed (CS2 + PUBG). Only the demo
# user gets these; they are created exactly once (idempotent marker on
# `host_game_id`), and every one runs the same escrow → release → payout → rake
# money flow settlement does, so the solvency invariant holds.
# --------------------------------------------------------------------------- #

_RAKE_BPS = 1_000  # 10%
_SAMPLE_MARK = "demo-sample-"  # host_game_id prefix → idempotency key


@dataclass(frozen=True)
class _SampleMatch:
    game: str
    market: str
    metric: str
    opponent: str
    entry_cents: int
    you_win: bool
    you: dict  # rich per-seat stat block (shown in the expanded card)
    opp: dict
    game_map: str
    mode: str
    days_ago: float


# CS2 (FACEIT) — K/D duels; PUBG (Steam) — kill duels. Values chosen to read like
# real games (a couple of wins, a couple of losses, one nail-biter).
_SAMPLE_MATCHES: tuple[_SampleMatch, ...] = (
    _SampleMatch(
        game=GAME_CS2_FACEIT, market="kd_ratio", metric="cs2_kd_ratio",
        opponent="s1mple_fan", entry_cents=1000, you_win=True,
        you={"K/D": 1.63, "Kills": 31, "Deaths": 19, "Assists": 6, "ADR": 98.4,
             "Headshot %": 54, "Rounds": 30},
        opp={"K/D": 1.11, "Kills": 24, "Deaths": 22, "Assists": 4, "ADR": 81.2,
             "Headshot %": 46, "Rounds": 30},
        game_map="de_dust2", mode="Competitive", days_ago=0.3,
    ),
    _SampleMatch(
        game=GAME_CS2_FACEIT, market="kd_ratio", metric="cs2_kd_ratio",
        opponent="Rojo", entry_cents=2500, you_win=False,
        you={"K/D": 0.86, "Kills": 18, "Deaths": 21, "Assists": 3, "ADR": 68.9,
             "Headshot %": 39, "Rounds": 26},
        opp={"K/D": 1.24, "Kills": 26, "Deaths": 21, "Assists": 7, "ADR": 90.1,
             "Headshot %": 51, "Rounds": 26},
        game_map="de_mirage", mode="Competitive", days_ago=1.1,
    ),
    _SampleMatch(
        game=GAME_CS2_FACEIT, market="kd_ratio", metric="cs2_kd_ratio",
        opponent="kvem_", entry_cents=500, you_win=True,
        you={"K/D": 1.30, "Kills": 26, "Deaths": 20, "Assists": 5, "ADR": 85.0,
             "Headshot %": 48, "Rounds": 30},
        opp={"K/D": 1.28, "Kills": 27, "Deaths": 21, "Assists": 8, "ADR": 88.7,
             "Headshot %": 45, "Rounds": 30},
        game_map="de_inferno", mode="Competitive", days_ago=2.4,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM, market="kills", metric="pubg_kills",
        opponent="chocoTaco", entry_cents=1000, you_win=True,
        you={"Kills": 8, "Damage": 742, "Placement": "#1 · Chicken Dinner",
             "Headshot %": 31, "Survival": "28:14"},
        opp={"Kills": 5, "Damage": 510, "Placement": "#4", "Headshot %": 22,
             "Survival": "24:02"},
        game_map="Erangel", mode="Squad TPP", days_ago=0.7,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM, market="kills", metric="pubg_kills",
        opponent="shroud_btw", entry_cents=2500, you_win=False,
        you={"Kills": 3, "Damage": 289, "Placement": "#9", "Headshot %": 18,
             "Survival": "16:41"},
        opp={"Kills": 6, "Damage": 604, "Placement": "#2", "Headshot %": 27,
             "Survival": "26:33"},
        game_map="Miramar", mode="Squad TPP", days_ago=1.8,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM, market="kills", metric="pubg_kills",
        opponent="chocoTaco", entry_cents=500, you_win=True,
        you={"Kills": 7, "Damage": 655, "Placement": "#2", "Headshot %": 29,
             "Survival": "25:10"},
        opp={"Kills": 4, "Damage": 431, "Placement": "#6", "Headshot %": 20,
             "Survival": "21:55"},
        game_map="Taego", mode="Squad TPP", days_ago=3.6,
    ),
)


async def _demo_opponent(session: AsyncSession, handle: str, game: str) -> User:
    """A funded, game-linked fake opponent for the demo history (idempotent)."""
    auth_id = f"demo_opp_{handle.lower()}"
    user = await session.scalar(select(User).where(User.auth_id == auth_id))
    if user is None:
        user = User(
            auth_id=auth_id,
            username=handle,
            email=f"{auth_id}@demo.moneymatch.test",
            residence_state=DEMO_RESIDENCE_STATE,
            dob_attested_18plus=True,
        )
        session.add(user)
        await session.flush()
        await provision_new_user(session, user)  # DEMO wallet + signup grant
    linked = await session.scalar(
        select(LinkedAccount).where(
            LinkedAccount.user_id == user.id, LinkedAccount.game == game
        )
    )
    if linked is None:
        linked = LinkedAccount(
            user_id=user.id,
            game=game,
            host_account_id=f"{game}_{handle}",
            host_username=handle,
            profile_snapshot={"username": handle, "game": game},
        )
        session.add(linked)
        await session.flush()
    return user


async def _ensure_demo_history(session: AsyncSession, demo: User) -> None:
    """Create the sample settled CS2/PUBG matches once, ledger-consistent."""
    already = await session.scalar(
        select(Match.id)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(
            MatchPlayer.user_id == demo.id,
            Match.host_game_id.like(f"{_SAMPLE_MARK}%"),
        )
        .limit(1)
    )
    if already is not None:
        return

    demo_links = {
        game: lid
        for game, lid in await session.execute(
            select(LinkedAccount.game, LinkedAccount.id).where(
                LinkedAccount.user_id == demo.id
            )
        )
    }
    now = datetime.now(UTC)
    for i, spec in enumerate(_SAMPLE_MATCHES):
        opp = await _demo_opponent(session, spec.opponent, spec.game)
        opp_link = await session.scalar(
            select(LinkedAccount.id).where(
                LinkedAccount.user_id == opp.id, LinkedAccount.game == spec.game
            )
        )
        await _seed_settled_match(
            session, demo, opp, demo_links[spec.game], opp_link, spec, now, i
        )
    await session.flush()


async def _seed_settled_match(
    session: AsyncSession,
    demo: User,
    opp: User,
    demo_link: uuid.UUID,
    opp_link: uuid.UUID,
    spec: _SampleMatch,
    now: datetime,
    idx: int,
) -> None:
    entry = spec.entry_cents
    pot = entry * 2
    split = money_math.split_pot(pot, 1, _RAKE_BPS)
    prize, rake_cents = split.payouts_cents[0], split.rake_cents
    winner_id = demo.id if spec.you_win else opp.id
    resolved = now - timedelta(days=spec.days_ago)
    matched = resolved - timedelta(minutes=35)
    gid = f"{_SAMPLE_MARK}{idx}"

    match = Match(
        game=spec.game,
        market=spec.market,
        entry_cents=entry,
        rake_bps=_RAKE_BPS,
        pot_cents=pot,
        prize_cents=prize,
        rake_cents=rake_cents,
        state="SETTLED",
        brokered=False,
        host_game_id=gid,
        matched_at=matched,
        winner_user_id=winner_id,
        resolved_at=resolved,
        created_at=matched,
        outcome_detail={
            "map": spec.game_map,
            "mode": spec.mode,
            "game_id": gid,
            "detail": {str(demo.id): spec.you, str(opp.id): spec.opp},
        },
    )
    session.add(match)
    await session.flush()

    seats = [
        (demo, demo_link, f"{spec.game}_{DEMO_USERNAME}", spec.you),
        (opp, opp_link, f"{spec.game}_{opp.username}", spec.opp),
    ]
    primary = _PRIMARY_LABEL[spec.metric]
    for member, link_id, host, stats in seats:
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=member.id,
                linked_account_id=link_id,
                host_account_id=host,
                confirmed_at=matched,
                payout_cents=prize if member.id == winner_id else 0,
                stat_line={spec.metric: stats[primary], "game_id": gid},
            )
        )

    # Money: exactly what settlement does for a WIN (escrow both, release both,
    # pay the winner, book rake) — so reconciliation on this match balances.
    for member in (demo, opp):
        await wallet_service.escrow_hold(
            session, member.id, entry, ref_type="match", ref_id=match.id,
            memo="demo sample entry",
        )
    for member in (demo, opp):
        await wallet_service.escrow_release(
            session, member.id, entry, ref_type="match", ref_id=match.id,
            memo="demo sample release",
        )
    await wallet_service.payout(
        session, winner_id, prize, ref_type="match", ref_id=match.id,
        memo=f"{spec.market} prize",
    )
    await wallet_service.rake(
        session, rake_cents, ref_type="match", ref_id=match.id,
        memo=f"{spec.market} rake",
    )


# The graded-metric value lives under a friendly label in the rich stat block.
_PRIMARY_LABEL = {"cs2_kd_ratio": "K/D", "pubg_kills": "Kills"}


class DemoLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str = DEMO_EMAIL


@router.post("/login", response_model=DemoLoginResponse)
async def demo_login(
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> DemoLoginResponse:
    # Belt-and-suspenders: the router is only mounted when enabled, but re-check.
    if not settings.demo_login_enabled:
        raise APIError("not_found", "Not found.", status_code=404)

    # Provision + onboard the shared demo user so the bypass lands straight in
    # (funded DEMO wallet + username set → no onboarding screen).
    user = await get_or_create_user(
        session, AuthedIdentity(auth_id=DEMO_AUTH_ID, email=DEMO_EMAIL)
    )
    if user.username is None:
        await complete_onboarding(
            session,
            user,
            username=DEMO_USERNAME,
            residence_state=DEMO_RESIDENCE_STATE,
            dob_attested_18plus=True,
        )
    # Populate a linked CS2 account + skill models so the pool/tournament/H2H
    # cards render immediately (otherwise the demo lands on "link your account").
    await _ensure_demo_fixture(session, user)
    # A populated, believable Activity feed of past CS2/PUBG games (demo-only).
    await _ensure_demo_history(session, user)
    await session.commit()

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": DEMO_AUTH_ID,
            "email": DEMO_EMAIL,
            "aud": settings.supabase_jwt_audience,
            "demo": True,
            "iat": int(now.timestamp()),
            "exp": int((now + _TOKEN_TTL).timestamp()),
        },
        DEMO_JWT_SECRET,
        algorithm="HS256",
    )
    return DemoLoginResponse(access_token=token)
