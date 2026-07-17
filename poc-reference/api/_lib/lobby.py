"""Lobby generation + shared contest building.

``build_contract`` is the single place a draft becomes a fully-built, matched
contest (entry → pot/prize/rake, plus a bracketed opponent). Both the Lobby
generator and the Builder's /price endpoint go through it so the two surfaces
always produce identical shapes (roadmap §1.4).
"""

from __future__ import annotations

import random
import uuid

from _lib import matchmaking, skill_rating
from _lib.schemas import (
    Bracket,
    Contract,
    ContractDraft,
    Objective,
    Opponent,
    SkillProfile,
    Speed,
)

_SPEED_LABEL = {
    "bullet": "Bullet",
    "blitz": "Blitz",
    "rapid": "Rapid",
    "classical": "Classical",
}
_MEDIAN_MOVES = {"bullet": 32, "blitz": 38, "rapid": 44, "classical": 52}

# Entry tiers offered in the lobby (within the Phase-1 $1–$100 caps, overview §7.3).
_ENTRY_TIERS = [1.0, 5.0, 10.0, 25.0]

_round2 = lambda x: round(x, 2)  # noqa: E731


def title_for(objective: Objective, speed: str) -> str:
    if speed == "cs2":
        return "Win your CS2 match"
    if speed == "dota2":
        return "Win your Dota 2 match"
    s = _SPEED_LABEL.get(speed, speed.title()).lower()
    if objective.kind == "win_under_moves":
        return f"Win the {s} match in under {objective.moves} moves"
    return f"Win the {s} match"


def build_contract(
    profile: SkillProfile,
    draft: ContractDraft,
    rng: random.Random | None = None,
) -> Contract:
    """Match an opponent and build a full, OPEN head-to-head contest.

    Opponent + rating come from the game's own skill signal: chess uses the
    per-time-control rating, CS2 uses the FaceIt elo on the profile.
    """
    if draft.game == "cs2.faceit":
        opponent = matchmaking.find_cs2_opponent(profile, rng=rng)
        your_rating = profile.rating or 1000
        bracket = skill_rating.make_bracket(your_rating, opponent.rating, band=150)
    elif draft.game == "dota2.opendota":
        opponent = matchmaking.find_dota_opponent(profile, rng=rng)
        your_rating = profile.rating or 3000
        bracket = skill_rating.make_bracket(your_rating, opponent.rating, band=800)
    else:
        opponent = matchmaking.find_opponent(profile, draft.speed, rng=rng)
        your_rating = skill_rating.rating_for_speed(profile, draft.speed)
        bracket = skill_rating.make_bracket(your_rating, opponent.rating)

    rake_pct = skill_rating.rake_for(draft.objective.kind)
    entry = _round2(draft.entry)
    entrants = 2
    pot = _round2(entry * entrants)
    rake = _round2(pot * rake_pct)
    prize = _round2(pot - rake)

    return Contract(
        id=uuid.uuid4().hex,
        game=draft.game,
        speed=draft.speed,
        format=draft.format,
        title=title_for(draft.objective, draft.speed),
        objective=draft.objective,
        window_hours=draft.window_hours,
        entry=entry,
        entrants=entrants,
        rake_pct=rake_pct,
        pot=pot,
        prize=prize,
        rake=rake,
        bracket=bracket,
        opponent=opponent,
        state="OPEN",
    )


def _top_speeds(profile: SkillProfile, n: int = 2) -> list[Speed]:
    if not profile.formats:
        return [profile.primary_speed]
    ranked = sorted(profile.formats, key=lambda f: f.games, reverse=True)
    return [f.speed for f in ranked[:n]]


# Non-chess H2H titles: win your next real match, across entry tiers. Keyed by
# adapter id → (speed/game-mode, human format label).
_MATCH_GAMES = {
    "cs2.faceit": ("cs2", "Competitive"),
    "dota2.opendota": ("dota2", "Ranked"),
}


def _generate_match_lobby(profile: SkillProfile, game: str, count: int) -> list[Contract]:
    """OPEN head-to-head contests (win your next real match) across entry tiers."""
    mode, fmt = _MATCH_GAMES[game]
    rng = random.Random()
    tiers = (_ENTRY_TIERS[1], _ENTRY_TIERS[2], _ENTRY_TIERS[0], _ENTRY_TIERS[3], _ENTRY_TIERS[2], _ENTRY_TIERS[1])
    drafts = [
        ContractDraft(game=game, speed=mode, format=fmt,
                      objective=Objective(kind="win_h2h"), window_hours=12, entry=tier)
        for tier in tiers
    ]
    return [build_contract(profile, d, rng=rng) for d in drafts][:count]


def generate(profile: SkillProfile, count: int = 6) -> list[Contract]:
    """Produce a varied lobby of OPEN head-to-head contests for the user."""
    if profile.game in _MATCH_GAMES:
        return _generate_match_lobby(profile, profile.game, count)
    speeds = _top_speeds(profile, 2)
    primary = speeds[0]
    secondary = speeds[1] if len(speeds) > 1 else primary
    # Deterministic-ish variety per user so a refresh re-rolls opponents.
    rng = random.Random()

    def label(speed: Speed) -> str:
        return f"Rated {_SPEED_LABEL.get(speed, speed.title())}"

    drafts: list[ContractDraft] = []

    # Win-the-match contests across speeds and entry tiers — the bread and butter.
    drafts.append(ContractDraft(
        speed=primary, format=label(primary),
        objective=Objective(kind="win_h2h"), window_hours=6, entry=_ENTRY_TIERS[1],
    ))
    drafts.append(ContractDraft(
        speed=primary, format=label(primary),
        objective=Objective(kind="win_h2h"), window_hours=6, entry=_ENTRY_TIERS[2],
    ))
    drafts.append(ContractDraft(
        speed=primary, format=label(primary),
        objective=Objective(kind="win_h2h"), window_hours=6, entry=_ENTRY_TIERS[0],
    ))
    if secondary != primary:
        drafts.append(ContractDraft(
            speed=secondary, format=label(secondary),
            objective=Objective(kind="win_h2h"), window_hours=6, entry=_ENTRY_TIERS[1],
        ))
    drafts.append(ContractDraft(
        speed=secondary, format=label(secondary),
        objective=Objective(kind="win_h2h"), window_hours=6, entry=_ENTRY_TIERS[3],
    ))

    # Win-quickly contests around the format median (higher variance, higher rake).
    med = _MEDIAN_MOVES.get(primary, 40)
    drafts.append(ContractDraft(
        speed=primary, format=label(primary),
        objective=Objective(kind="win_under_moves", moves=med), window_hours=8,
        entry=_ENTRY_TIERS[1],
    ))
    drafts.append(ContractDraft(
        speed=primary, format=label(primary),
        objective=Objective(kind="win_under_moves", moves=med - 10), window_hours=8,
        entry=_ENTRY_TIERS[2],
    ))
    drafts.append(ContractDraft(
        speed=secondary, format=label(secondary),
        objective=Objective(kind="win_under_moves", moves=_MEDIAN_MOVES.get(secondary, 40)),
        window_hours=8, entry=_ENTRY_TIERS[0],
    ))

    contracts = [build_contract(profile, d, rng=rng) for d in drafts]
    return contracts[:count]
