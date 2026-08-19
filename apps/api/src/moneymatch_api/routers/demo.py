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
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthedIdentity
from ..config import Settings, get_settings
from ..constants import (
    DEMO_AUTH_ID,
    DEMO_EMAIL,
    DEMO_JWT_SECRET,
    DEMO_RESIDENCE_STATE,
    DEMO_USERNAME,
    GAME_CHESS_LICHESS,
    GAME_CS2_STEAM,
    GAME_DOTA2_OPENDOTA,
    GAME_PUBG_STEAM,
    POOL_METRICS,
    REGISTERED_GAMES,
    STAT_BASELINE_MIN_N,
    TOURNAMENT_METRICS,
    game_display_name,
)
from ..db.session import get_session
from ..dependencies import AdminUser, CurrentUser
from ..errors import APIError
from ..models.chat import Conversation, ConversationMember, Message
from ..models.linked_account import LinkedAccount
from ..models.play import Match, MatchPlayer
from ..models.pools import SoloEntry, SoloPool
from ..models.skill import MetricModel
from ..models.social import Friendship
from ..models.tournaments import Tournament, TournamentEntry
from ..models.user import User
from ..models.wallet import SIGNUP_GRANT_CENTS
from ..schemas.links import CreateLinkRequest, LinksResponse
from ..services import (
    admin_contests_service,
    challenge_service,
    chat_service,
    demo_simulation,
    linking_service,
    matchmaking,
    money_math,
    pool_engine,
    telemetry_fetch,
    tournament_engine,
    wallet_service,
)
from ..services.user_service import (
    complete_onboarding,
    get_or_create_user,
    provision_new_user,
)
from .links import _links_response

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

_TOKEN_TTL = timedelta(hours=12)

# Plausible baselines (μ, σ) per metric so the demo user's pool/tournament bars
# and head-to-head duels are all non-provisional out of the box, on every game.
_DEMO_METRIC_FIXTURE: dict[str, tuple[float, float]] = {
    "chess_accuracy": (85.0, 6.0),
    "cs2_kd_ratio": (1.15, 0.22),
    "cs2_headshot_pct": (47.0, 8.0),
    "dota2_kda_ratio": (3.2, 0.8),
    "dota2_gpm": (520.0, 90.0),
    "pubg_kills": (4.5, 2.0),
    "pubg_damage": (380.0, 120.0),
    "pubg_headshot_pct": (22.0, 8.0),
}

# Sample count stamped on a seeded model — comfortably clear of every baseline
# floor, so the demo never reads as provisional.
_DEMO_METRIC_N = 25


#: The demo's play set. CS2 is the Steam game, which is now the only one:
#: FACEIT was retired on 2026-08-12.
_DEMO_ACTIVE_GAMES = [
    GAME_CS2_STEAM,
    GAME_PUBG_STEAM,
    GAME_DOTA2_OPENDOTA,
    GAME_CHESS_LICHESS,
]


async def _ensure_demo_fixture(session: AsyncSession, user: User) -> None:
    """Link the demo user to every playable game + seed non-provisional metric
    models, so Solo Pools, Tournaments, and Head-to-Head are populated with
    joinable cards on every game out of the box. Idempotent."""
    linked = set(
        await session.scalars(
            select(LinkedAccount.game).where(LinkedAccount.user_id == user.id)
        )
    )
    models = {
        (m.game, m.metric): m
        for m in await session.scalars(
            select(MetricModel).where(MetricModel.user_id == user.id)
        )
    }
    for game in REGISTERED_GAMES:
        # A Steam identity cannot be faked. `cs2.steam` is keyed by a SteamID64
        # that only Steam can vouch for, so a placeholder link there would be a
        # lie that also blocks the real sign-in from ever binding.
        if game == GAME_CS2_STEAM:
            continue
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
            mu, sigma = _DEMO_METRIC_FIXTURE.get(metric, (1.0, 0.2))
            existing = models.get((game, metric))
            if existing is None:
                session.add(
                    MetricModel(
                        user_id=user.id,
                        game=game,
                        metric=metric,
                        mu=mu,
                        sigma=sigma,
                        n=_DEMO_METRIC_N,
                    )
                )
            elif existing.n < STAT_BASELINE_MIN_N:
                # A history bootstrap over the demo's synthetic host account
                # leaves an empty model (n=0). That reads as provisional and
                # hides every pool/tournament card, so restore the baseline
                # rather than skipping on mere row existence.
                existing.mu = mu
                existing.sigma = sigma
                existing.n = _DEMO_METRIC_N
    # The play set drives the game tabs, so a reset must not put the demo back
    # on the FACEIT game it can no longer settle.
    user.active_games = list(_DEMO_ACTIVE_GAMES)
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
        game=GAME_CS2_STEAM,
        market="kd_ratio",
        metric="cs2_kd_ratio",
        opponent="s1mple_fan",
        entry_cents=1000,
        you_win=True,
        you={
            "K/D": 1.63,
            "Kills": 31,
            "Deaths": 19,
            "Assists": 6,
            "ADR": 98.4,
            "Headshot %": 54,
            "Rounds": 30,
        },
        opp={
            "K/D": 1.11,
            "Kills": 24,
            "Deaths": 22,
            "Assists": 4,
            "ADR": 81.2,
            "Headshot %": 46,
            "Rounds": 30,
        },
        game_map="de_dust2",
        mode="Competitive",
        days_ago=0.3,
    ),
    _SampleMatch(
        game=GAME_CS2_STEAM,
        market="kd_ratio",
        metric="cs2_kd_ratio",
        opponent="Rojo",
        entry_cents=2500,
        you_win=False,
        you={
            "K/D": 0.86,
            "Kills": 18,
            "Deaths": 21,
            "Assists": 3,
            "ADR": 68.9,
            "Headshot %": 39,
            "Rounds": 26,
        },
        opp={
            "K/D": 1.24,
            "Kills": 26,
            "Deaths": 21,
            "Assists": 7,
            "ADR": 90.1,
            "Headshot %": 51,
            "Rounds": 26,
        },
        game_map="de_mirage",
        mode="Competitive",
        days_ago=1.1,
    ),
    _SampleMatch(
        game=GAME_CS2_STEAM,
        market="kd_ratio",
        metric="cs2_kd_ratio",
        opponent="kvem_",
        entry_cents=500,
        you_win=True,
        you={
            "K/D": 1.30,
            "Kills": 26,
            "Deaths": 20,
            "Assists": 5,
            "ADR": 85.0,
            "Headshot %": 48,
            "Rounds": 30,
        },
        opp={
            "K/D": 1.28,
            "Kills": 27,
            "Deaths": 21,
            "Assists": 8,
            "ADR": 88.7,
            "Headshot %": 45,
            "Rounds": 30,
        },
        game_map="de_inferno",
        mode="Competitive",
        days_ago=2.4,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM,
        market="kills",
        metric="pubg_kills",
        opponent="chocoTaco",
        entry_cents=1000,
        you_win=True,
        you={
            "Kills": 8,
            "Damage": 742,
            "Placement": "#1 · Chicken Dinner",
            "Headshot %": 31,
            "Survival": "28:14",
        },
        opp={
            "Kills": 5,
            "Damage": 510,
            "Placement": "#4",
            "Headshot %": 22,
            "Survival": "24:02",
        },
        game_map="Erangel",
        mode="Squad TPP",
        days_ago=0.7,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM,
        market="kills",
        metric="pubg_kills",
        opponent="shroud_btw",
        entry_cents=2500,
        you_win=False,
        you={
            "Kills": 3,
            "Damage": 289,
            "Placement": "#9",
            "Headshot %": 18,
            "Survival": "16:41",
        },
        opp={
            "Kills": 6,
            "Damage": 604,
            "Placement": "#2",
            "Headshot %": 27,
            "Survival": "26:33",
        },
        game_map="Miramar",
        mode="Squad TPP",
        days_ago=1.8,
    ),
    _SampleMatch(
        game=GAME_PUBG_STEAM,
        market="kills",
        metric="pubg_kills",
        opponent="chocoTaco",
        entry_cents=500,
        you_win=True,
        you={
            "Kills": 7,
            "Damage": 655,
            "Placement": "#2",
            "Headshot %": 29,
            "Survival": "25:10",
        },
        opp={
            "Kills": 4,
            "Damage": 431,
            "Placement": "#6",
            "Headshot %": 20,
            "Survival": "21:55",
        },
        game_map="Taego",
        mode="Squad TPP",
        days_ago=3.6,
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
        # Sample history needs an identity to hang itself on, and the demo user
        # does not hold one for every game. `_ensure_demo_fixture` deliberately
        # refuses to create a `cs2.steam` link: a SteamID64 is vouched for by
        # Steam alone, and a placeholder would occupy the slot the player's real
        # account has to bind into.
        #
        # Skipping rather than deleting the CS2 specs is what makes this
        # self-correcting — the moment a real Steam account is linked, that
        # game's samples seed on the next history rebuild.
        #
        # Without this the lookup below raised `KeyError: 'cs2.steam'` and every
        # demo sign-in 500'd. It only surfaced on a database with no sample
        # history: production still had rows from the FACEIT era, when a
        # placeholder CS2 link *was* allowed, so the guard above short-circuited
        # and hid it until the database was rebuilt from empty.
        if spec.game not in demo_links:
            continue
        opp = await _demo_opponent(session, spec.opponent, spec.game)
        opp_link = await session.scalar(
            select(LinkedAccount.id).where(
                LinkedAccount.user_id == opp.id, LinkedAccount.game == spec.game
            )
        )
        assert opp_link is not None  # the demo opponent is seeded with this link
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
            session,
            member.id,
            entry,
            ref_type="match",
            ref_id=match.id,
            memo="demo sample entry",
        )
    for member in (demo, opp):
        await wallet_service.escrow_release(
            session,
            member.id,
            entry,
            ref_type="match",
            ref_id=match.id,
            memo="demo sample release",
        )
    await wallet_service.payout(
        session,
        winner_id,
        prize,
        ref_type="match",
        ref_id=match.id,
        memo=f"{spec.market} prize",
    )
    await wallet_service.rake(
        session,
        rake_cents,
        ref_type="match",
        ref_id=match.id,
        memo=f"{spec.market} rake",
    )


# The graded-metric value lives under a friendly label in the rich stat block.
_PRIMARY_LABEL = {"cs2_kd_ratio": "K/D", "pubg_kills": "Kills"}


# --------------------------------------------------------------------------- #
# Demo social — accepted friends, chat threads, and invite cards, so the Inbox
# opens on a populated messaging surface instead of an empty rail. The same
# opponents from the Activity history double as the demo's friends. Created
# exactly once (guarded on "does this user have any conversation yet").
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _ChatLine:
    """One seeded message. `invite` carries the extra payload for a card."""

    mine: bool  # the demo user wrote it
    minutes_ago: float
    body: str | None = None
    invite: dict | None = None  # {invite_kind, game, entry_cents, ...}


@dataclass(frozen=True)
class _DemoThread:
    friend: str  # opponent handle (reused from the Activity history)
    game: str
    online: bool  # seeds `last_seen_at` → the presence dot
    lines: tuple[_ChatLine, ...]


_DAY = 60 * 24

_DEMO_THREADS: tuple[_DemoThread, ...] = (
    _DemoThread(
        friend="s1mple_fan",
        game=GAME_CS2_STEAM,
        online=True,
        lines=(
            _ChatLine(False, 2 * _DAY + 40, "gg earlier, that dust2 half was rough"),
            _ChatLine(True, 2 * _DAY + 33, "you were 1 kill off. run it back later?"),
            _ChatLine(False, 2 * _DAY + 30, "for sure. $10 K/D duel?"),
            _ChatLine(
                False,
                _DAY + 90,
                None,
                {
                    "invite_kind": "pool",
                    "game": GAME_CS2_STEAM,
                    "entry_cents": 1000,
                    "metric": "cs2_kd_ratio",
                    "difficulty": "medium",
                    "status": "accepted",
                },
            ),
            _ChatLine(True, _DAY + 80, "in. cleared the bar with room to spare"),
            _ChatLine(False, 55, "queueing now — send me something for tonight"),
        ),
    ),
    _DemoThread(
        friend="chocoTaco",
        game=GAME_PUBG_STEAM,
        online=False,
        lines=(
            _ChatLine(True, _DAY + 200, "erangel squads later?"),
            _ChatLine(False, _DAY + 190, "yeah. tournament instead? best 3 kills"),
            _ChatLine(
                True,
                _DAY + 20,
                None,
                {
                    "invite_kind": "tournament",
                    "game": GAME_PUBG_STEAM,
                    "entry_cents": 2500,
                    "metric": "pubg_kills",
                    "status": "pending",
                },
            ),
            _ChatLine(False, 240, "saw it — jumping in after this game"),
            _ChatLine(
                False,
                180,
                None,
                {
                    "invite_kind": "pool",
                    "game": GAME_PUBG_STEAM,
                    "entry_cents": 500,
                    "metric": "pubg_kills",
                    "difficulty": "easy",
                    "status": "pending",
                },
            ),
        ),
    ),
    _DemoThread(
        friend="kvem_",
        game=GAME_CS2_STEAM,
        online=False,
        lines=(
            _ChatLine(False, 4 * _DAY, "that inferno one came down to the last round"),
            _ChatLine(True, 4 * _DAY - 5, "closest match I've had on here"),
            _ChatLine(
                True,
                3 * _DAY,
                None,
                {
                    "invite_kind": "pool",
                    "game": GAME_CS2_STEAM,
                    "entry_cents": 2500,
                    "metric": "cs2_kills",
                    "difficulty": "hard",
                    "status": "declined",
                },
            ),
            _ChatLine(False, 3 * _DAY - 10, "hard ADR bar is not my week, sorry"),
        ),
    ),
)

# The support thread the demo lands on: a real question, the auto-ack, and an
# agent follow-up, so the thread reads like a conversation and not a form.
_DEMO_SUPPORT: tuple[_ChatLine, ...] = (
    _ChatLine(False, _DAY + 400, chat_service.SUPPORT_GREETING),
    _ChatLine(
        True, _DAY + 60, "My K/D duel from Tuesday settled — where's the payout?"
    ),
    _ChatLine(False, _DAY + 59, chat_service.SUPPORT_AUTO_REPLY),
    _ChatLine(
        False,
        _DAY + 20,
        "Checked it: the prize posted to your balance at 9:14pm, under "
        "Activity → Settled. Anything else, just reply here.",
    ),
)


def _seed_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    sender_id: uuid.UUID | None,
    line: _ChatLine,
    now: datetime,
) -> None:
    """Append one backdated message (explicit `created_at`, so the transcript has
    real day dividers instead of collapsing onto today)."""
    created = now - timedelta(minutes=line.minutes_ago)
    payload: dict = {}
    if line.invite is not None:
        payload = {
            **line.invite,
            "redirect_path": (
                "/pools" if line.invite["invite_kind"] == "pool" else "/tournament"
            ),
        }
        payload["title"] = chat_service.invite_title(payload)
    session.add(
        Message(
            conversation_id=conversation.id,
            sender_id=sender_id,
            kind="invite" if line.invite else ("text" if sender_id else "system"),
            body=line.body,
            payload=payload,
            created_at=created,
        )
    )
    if conversation.last_message_at is None or created > conversation.last_message_at:
        conversation.last_message_at = created


async def _ensure_demo_social(session: AsyncSession, demo: User) -> None:
    """Friend the demo user to its Activity opponents and seed their threads."""
    already = await session.scalar(
        select(ConversationMember.id)
        .where(ConversationMember.user_id == demo.id)
        .limit(1)
    )
    if already is not None:
        return

    now = datetime.now(UTC)
    for spec in _DEMO_THREADS:
        friend = await _demo_opponent(session, spec.friend, spec.game)
        friend.last_seen_at = now if spec.online else now - timedelta(hours=6)
        # Guarded independently of the conversation check above: the friendship
        # may already exist (added by hand, or left behind when a thread was
        # cleared), and `uq_friendships_pair` covers the pair in one direction.
        existing = await session.scalar(
            select(Friendship.id).where(
                or_(
                    and_(
                        Friendship.user_id == friend.id,
                        Friendship.friend_id == demo.id,
                    ),
                    and_(
                        Friendship.user_id == demo.id,
                        Friendship.friend_id == friend.id,
                    ),
                )
            )
        )
        if existing is None:
            session.add(
                Friendship(
                    user_id=friend.id,
                    friend_id=demo.id,
                    state="accepted",
                    accepted_at=now - timedelta(days=9),
                )
            )
        conversation = Conversation(kind="dm")
        session.add(conversation)
        await session.flush()
        session.add_all(
            [
                ConversationMember(conversation_id=conversation.id, user_id=demo.id),
                ConversationMember(conversation_id=conversation.id, user_id=friend.id),
            ]
        )
        for line in spec.lines:
            _seed_message(
                session,
                conversation,
                sender_id=demo.id if line.mine else friend.id,
                line=line,
                now=now,
            )

    support = Conversation(kind="support", subject=chat_service.SUPPORT_TITLE)
    session.add(support)
    await session.flush()
    session.add(ConversationMember(conversation_id=support.id, user_id=demo.id))
    for line in _DEMO_SUPPORT:
        _seed_message(
            session,
            support,
            sender_id=demo.id if line.mine else None,
            line=line,
            now=now,
        )
    await session.flush()

    # One live head-to-head challenge from a friend: a *real* `challenges` row, so
    # the invite card in chat (and the Inbox pill) actually forms a match on
    # accept. Posted last so it's the newest thing in the Inbox.
    challenger = await _demo_opponent(session, _DEMO_THREADS[0].friend, GAME_CS2_STEAM)
    try:
        await challenge_service.create_direct(
            session,
            challenger,
            challengee_id=demo.id,
            game=GAME_CS2_STEAM,
            market_key="kd_ratio",
            entry_cents=1000,
        )
    except APIError as exc:  # e.g. the game flag is off — the threads still stand
        log.warning("demo.challenge_seed_skipped", error=str(exc))


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
    # Friends + chat threads (with invite cards) so the Inbox opens populated.
    await _ensure_demo_social(session, user)
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


@router.post("/relink", response_model=LinksResponse)
async def demo_relink(
    body: CreateLinkRequest,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> LinksResponse:
    """Swap the shared demo user's placeholder handle for a real one, per game.

    This router is only mounted when `demo_login_enabled` (main.py), so demo mode
    is already enforced. Scoped further to the demo user (`auth_id ==
    DEMO_AUTH_ID`) so real users' immutable bindings and the admin-only unlink are
    untouched. `rebind` soft-unbinds the old link and binds the new handle — live
    host verification + real skill bootstrap — in one transaction, so a bad handle
    leaves the old link intact. Returns the same `LinksResponse` as `/links`.
    """
    if user.auth_id != DEMO_AUTH_ID:
        raise APIError("not_found", "Not found.", status_code=404)
    await linking_service.rebind(session, user, body.game, body.username)
    await session.commit()
    return await _links_response(session, user.id)


class DemoResetResponse(BaseModel):
    ok: bool = True


async def _reset_demo_state(session: AsyncSession, user: User) -> None:
    """Return the shared demo account to its fresh-login state.

    Formed rooms are deliberately uncancelable for real accounts, so testers need
    a way to start over once the "New pool" escape hatch is gone. This refunds and
    clears every in-flight contest (tickets, pools, matches, tournaments), restores
    the wallet to the starting funded balance, then re-applies the idempotent seed
    so the sample Activity + friends are present again. Every money move goes
    through the normal ledger paths, so reconciliation still holds afterwards.
    """
    # 1. Waiting tickets (no escrow held yet) across all three modes.
    await matchmaking.cancel(session, user)
    await tournament_engine.cancel(session, user)

    # 2. In-flight head-to-head matches → void (CANCEL + full refund).
    match_ids = list(
        await session.scalars(
            select(Match.id)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(
                MatchPlayer.user_id == user.id,
                Match.state.in_(("PENDING", "ACTIVE", "AWAITING_RESULT")),
            )
        )
    )
    for match_id in match_ids:
        await admin_contests_service.void_match(session, match_id, reason="demo reset")

    # 3. Forming/formed pools the demo is in → refund every entry. `cancel` covers
    #    a waiting ticket or the demo's own formed room; the query mops up any
    #    other OPEN/LOCKED pool the demo entered.
    for _ in range(10):
        if not await pool_engine.cancel(session, user):
            break
    pool_ids = list(
        await session.scalars(
            select(SoloPool.id)
            .join(SoloEntry, SoloEntry.pool_id == SoloPool.id)
            .where(
                SoloEntry.user_id == user.id,
                SoloPool.state.in_(("OPEN", "LOCKED")),
            )
        )
    )
    for pool_id in pool_ids:
        pool = await session.get(SoloPool, pool_id)
        if pool is not None:
            await pool_engine.cancel_pool(session, pool, reason="demo reset")

    # 4. In-flight tournaments the demo entered → cancel + refund the field.
    tournament_ids = list(
        await session.scalars(
            select(Tournament.id)
            .join(TournamentEntry, TournamentEntry.tournament_id == Tournament.id)
            .where(
                TournamentEntry.user_id == user.id,
                Tournament.state.in_(("OPEN", "LOCKED")),
            )
        )
    )
    for tournament_id in tournament_ids:
        tournament = await session.get(Tournament, tournament_id)
        if tournament is not None:
            await tournament_engine.cancel_tournament(
                session, tournament, reason="demo reset"
            )

    # 5. Restore the wallet to the starting funded balance ($1,000, zero escrow).
    #    Refunds above have already released escrow back to available; a ledger
    #    adjustment (booked against platform:promo) squares the balance.
    await session.flush()
    wallet = await wallet_service.get_wallet(session, user.id)
    delta = SIGNUP_GRANT_CENTS - wallet.available_cents
    if delta > 0:
        await wallet_service.credit(
            session, user.id, delta, memo="demo reset", created_by="demo-reset"
        )
    elif delta < 0:
        await wallet_service.debit(
            session, user.id, -delta, memo="demo reset", created_by="demo-reset"
        )

    # 6. Re-apply the seed (idempotent) so fixtures/history/social are present.
    await _ensure_demo_fixture(session, user)
    await _ensure_demo_history(session, user)
    await _ensure_demo_social(session, user)


@router.post("/reset", response_model=DemoResetResponse)
async def demo_reset(
    user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> DemoResetResponse:
    """Reset the shared demo account to its fresh-login state (demo user only)."""
    if user.auth_id != DEMO_AUTH_ID:
        raise APIError("not_found", "Not found.", status_code=404)
    await _reset_demo_state(session, user)
    await session.commit()
    return DemoResetResponse()


# --------------------------------------------------------------------------- #
# Demo escape hatch (IMPLEMENTATION_PROMPT phase 0).
#
# A live demo of a wager product has to show a contest settling, and settlement
# reads real match history from a game host. For CS2 that is a 40-minute FaceIt
# match with ten people in it, and for a tournament it is a 48-hour window.
# Neither is schedulable around an audience.
#
# Both endpoints below are admin-only *and* behind `DEMO_SIMULATE_ENABLED`, and
# both shout in the logs and in their own response body, because an injected
# result is deliberately indistinguishable everywhere else.
# --------------------------------------------------------------------------- #


class SimulateResultRequest(BaseModel):
    game: str = GAME_CS2_STEAM
    user_id: uuid.UUID | None = None  # defaults to the demo user
    metrics: dict[str, float] = {}
    rounds: int = 0
    moves: int = 0
    won: bool | None = True
    drawn: bool = False
    played_at: datetime | None = None


class SimulateResultResponse(BaseModel):
    simulated: bool = True
    warning: str = (
        "This is an injected result, not a real match. It is indistinguishable "
        "from a real one downstream by design."
    )
    id: uuid.UUID
    game: str
    host_account_id: str
    user_id: uuid.UUID
    created_at_ms: int
    metrics: dict[str, float]


class ForceSettleRequest(BaseModel):
    contest_id: uuid.UUID


class ForceSettleResponse(BaseModel):
    simulated: bool = True
    warning: str = "Settlement was forced by an admin, not by the contest window."
    kind: str
    contest_id: uuid.UUID
    state: str
    detail: dict | None = None


def _assert_simulation_enabled(settings: Settings) -> None:
    if not settings.demo_simulate_enabled:
        raise APIError("not_found", "Not found.", status_code=404)


async def _demo_or_named_user(session: AsyncSession, user_id: uuid.UUID | None) -> User:
    if user_id is not None:
        target = await session.get(User, user_id)
        if target is None:
            raise APIError("not_found", "No such user.", status_code=404)
        return target
    target = await session.scalar(select(User).where(User.auth_id == DEMO_AUTH_ID))
    if target is None:
        raise APIError(
            "not_found", "The demo user does not exist yet.", status_code=404
        )
    return target


@router.post("/simulate_result", response_model=SimulateResultResponse)
async def simulate_result(
    body: SimulateResultRequest,
    admin: AdminUser,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> SimulateResultResponse:
    """Inject a finished match so a wager can settle without playing one.

    The row is written against the target's **linked host account**, and the
    adapter merges it into `poll_eligible_games` alongside real history. So the
    settlement worker, the pool engine and the payout path all read it through
    the same call they use for a real match, and none of them has a branch for
    it. That is the point: a demo that proves the real path works.
    """
    _assert_simulation_enabled(settings)

    target = await _demo_or_named_user(session, body.user_id)
    link = await linking_service.get_link(session, target.id, body.game)
    if link is None:
        raise APIError(
            "not_linked",
            f"{target.username or target.id} has no {body.game} account linked.",
            status_code=409,
        )

    row = await demo_simulation.record(
        session,
        user_id=target.id,
        game=body.game,
        host_account_id=link.host_account_id,
        metrics=body.metrics,
        won=body.won,
        drawn=body.drawn,
        rounds=body.rounds,
        moves=body.moves,
        played_at=body.played_at,
        created_by=f"admin:{admin.username or admin.id}",
    )
    await session.commit()

    return SimulateResultResponse(
        id=row.id,
        game=row.game,
        host_account_id=row.host_account_id,
        user_id=target.id,
        created_at_ms=int(row.created_at_ms),
        metrics=row.metrics,
    )


@router.post("/force_settle", response_model=ForceSettleResponse)
async def force_settle(
    body: ForceSettleRequest,
    admin: AdminUser,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> ForceSettleResponse:
    """Settle one pool or tournament now, instead of at its window close.

    Runs the worker's own grade-then-settle sequence for a single contest. It
    does not shortcut grading: the contest is graded from whatever match history
    the adapters return, so a forced settlement still reflects real (or injected)
    results rather than a fabricated outcome.
    """
    _assert_simulation_enabled(settings)

    pool = await session.get(SoloPool, body.contest_id)
    if pool is not None:
        entries = list(
            await session.scalars(select(SoloEntry).where(SoloEntry.pool_id == pool.id))
        )
        grades = await telemetry_fetch.grade_pool(session, pool, entries)
        settled = await pool_engine.settle_pool(session, pool, grades)
        await session.commit()
        log.warning(
            "demo.force_settled",
            simulated=True,
            kind="pool",
            contest_id=str(pool.id),
            state=settled.state,
            by=str(admin.id),
        )
        return ForceSettleResponse(
            kind="pool",
            contest_id=pool.id,
            state=settled.state,
            detail={str(uid): {"cleared": g.cleared} for uid, g in grades.items()},
        )

    tournament = await session.get(Tournament, body.contest_id)
    if tournament is not None:
        # Distinct names from the pool branch above: the two grade maps and the
        # two contest types are different shapes, and reusing one name for both
        # is how a settle path ends up passing the wrong one.
        field = list(
            await session.scalars(
                select(TournamentEntry).where(
                    TournamentEntry.tournament_id == tournament.id
                )
            )
        )
        standings = await telemetry_fetch.grade_tournament(session, tournament, field)
        finished = await tournament_engine.settle_tournament(
            session, tournament, standings
        )
        await session.commit()
        log.warning(
            "demo.force_settled",
            simulated=True,
            kind="tournament",
            contest_id=str(tournament.id),
            state=finished.state,
            by=str(admin.id),
        )
        return ForceSettleResponse(
            kind="tournament",
            contest_id=tournament.id,
            state=finished.state,
        )

    raise APIError("not_found", "No pool or tournament with that id.", status_code=404)
