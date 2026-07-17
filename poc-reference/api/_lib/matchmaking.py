"""Skill-bracketed matchmaking (roadmap §1.4).

In production this is a server-side queue keyed on (game, format, entry tier,
rating band) that pairs two real players with widening tolerance over time. In
the play-money demo there is no second user, so we synthesize a **bot opponent**
inside the user's rating band (overview §8.1, roadmap §1.5). The bot's rating is
drawn from the band, so ``make_bracket`` produces a genuinely close matchup.

``can_pair`` is the seam for the anti-collusion controls the peer-to-peer model
requires (overview §6): no repeated pairing of the same two accounts, no
self-pairing. It is a stub here — bots are always pairable — but the call site
exists so production can swap in real device/instrument/pair-frequency checks
without touching the lobby.
"""

from __future__ import annotations

import random

from _lib import skill_rating
from _lib.schemas import Opponent, SkillProfile, Speed

# Believable, clearly-bot handles. Suffixed with a number so the lobby can show
# several distinct opponents at once.
_BOT_HANDLES = [
    "knightfork", "enpassant", "rookroller", "pawnstorm", "zugzwanger",
    "blunderbot", "timescramble", "fianchetto", "skewered", "discoverbot",
]


def find_opponent(
    profile: SkillProfile,
    speed: Speed,
    band: int = skill_rating.DEFAULT_BAND,
    rng: random.Random | None = None,
) -> Opponent:
    """Pair the user with a bracketed opponent in their rating band."""
    r = rng or random
    your_rating = skill_rating.rating_for_speed(profile, speed)
    delta = r.randint(-band, band)
    opp_rating = max(600, min(2900, your_rating + delta))

    handle = r.choice(_BOT_HANDLES)
    suffix = r.randint(10, 99)
    username = f"{handle}{suffix}"

    return Opponent(
        username=username,
        display_name=username,
        rating=opp_rating,
        is_bot=True,
    )


# Clearly-bot CS2 handles for the FaceIt-backed lobby.
_CS2_BOT_HANDLES = [
    "propfragger", "claymore", "ecorush", "smokecriminal", "awpfish",
    "ninjadefuse", "ecofrag", "deagle5k", "spraydown", "lurklord",
]


def find_cs2_opponent(
    profile: SkillProfile,
    band: int = 150,
    rng: random.Random | None = None,
) -> Opponent:
    """Pair the user with a bracketed CS2 bot inside their FaceIt-elo band."""
    r = rng or random
    your_rating = profile.rating or 1000
    delta = r.randint(-band, band)
    opp_rating = max(100, min(5000, your_rating + delta))
    handle = r.choice(_CS2_BOT_HANDLES)
    username = f"{handle}{r.randint(10, 99)}"
    return Opponent(username=username, display_name=username, rating=opp_rating, is_bot=True)


# Clearly-bot Dota 2 handles for the OpenDota-backed lobby.
_DOTA_BOT_HANDLES = [
    "midorfeed", "tangospammer", "couriersniper", "smokegank", "rapierfarmer",
    "wardbitch", "lasthitlord", "roshanthief", "creepskip", "buybacker",
]


def find_dota_opponent(
    profile: SkillProfile,
    band: int = 800,
    rng: random.Random | None = None,
) -> Opponent:
    """Pair the user with a bracketed Dota 2 bot inside their MMR band."""
    r = rng or random
    your_rating = profile.rating or 3000
    delta = r.randint(-band, band)
    opp_rating = max(100, min(9000, your_rating + delta))
    handle = r.choice(_DOTA_BOT_HANDLES)
    username = f"{handle}{r.randint(10, 99)}"
    return Opponent(username=username, display_name=username, rating=opp_rating, is_bot=True)


def can_pair(account_a: str, account_b: str, recent_pairs: set[tuple[str, str]] | None = None) -> bool:
    """Anti-collusion gate (stub). See module docstring / overview §6.

    Production: reject self-pairing, repeated pairings inside a window, and
    accounts clustered by device / payment instrument.
    """
    if account_a == account_b:
        return False
    if recent_pairs and (account_a, account_b) in recent_pairs:
        return False
    return True
