"""CS2 match share codes: `CSGO-xxxxx-xxxxx-xxxxx-xxxxx-xxxxx`.

A share code is a base-57 encoding of 144 bits, which unpack little-endian into
three fields:

    match_id    u64   the match, as the Game Coordinator knows it
    outcome_id  u64   the outcome/reservation id
    token_id    u16   a short token that authorises the lookup

All three are needed to ask the GC for a match; the code is the only thing a
player can copy out of the game (Watch -> Your Matches -> Copy share code), so
it is the unit of intake.

Two properties worth knowing before trusting this for money:

- **A share code is not a claim of identity.** It says a match happened, not
  that the person pasting it played in it. The roster check at settlement is
  what ties it to a user.
- **Codes only exist for Premier, Competitive and Wingman.** Casual, Deathmatch
  and Arms Race produce none at all, which means mode filtering is free: if a
  code resolves, it was a real matchmaking match.

The alphabet omits `I`, `l`, `0`, `1` and `g` to avoid characters that are easy
to confuse when read aloud or retyped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DICTIONARY = "ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789"
BASE = len(DICTIONARY)  # 57

#: `CSGO-` then five groups of five, from the alphabet above.
SHARECODE_RE = re.compile(
    r"^CSGO(-[" + DICTIONARY + r"]{5}){5}$",
)

_BITS = 144
_MASK64 = 0xFFFFFFFFFFFFFFFF
_MASK16 = 0xFFFF


class ShareCodeError(ValueError):
    """A share code that is not well formed. Carries a user-facing message."""


@dataclass(frozen=True)
class ShareCode:
    """The three ids a share code carries, plus the code it came from."""

    code: str
    match_id: int
    outcome_id: int
    token_id: int


def _swap_endianness(number: int) -> int:
    """Reverse the byte order of a 144-bit integer.

    The encoding is little-endian across the whole 18 bytes, but the base-57
    accumulation naturally produces a big-endian integer, so the bytes are
    reversed once rather than each field being unpacked separately.
    """
    result = 0
    for offset in range(0, _BITS, 8):
        result = (result << 8) + ((number >> offset) & 0xFF)
    return result


def normalize(code: str) -> str:
    """Trim and upper-case the prefix, leaving the payload untouched.

    The payload is case-sensitive (`A` and `a` are different symbols), so only
    the literal `CSGO-` prefix is normalised. A user pasting `csgo-...` is a
    common enough slip to absorb; anything else is a genuine error.
    """
    trimmed = code.strip()
    if trimmed[:5].upper() == "CSGO-":
        return "CSGO-" + trimmed[5:]
    return trimmed


def is_valid(code: str) -> bool:
    return bool(SHARECODE_RE.match(normalize(code)))


def decode(code: str) -> ShareCode:
    """Decode a share code, or raise `ShareCodeError` with a usable message."""
    cleaned = normalize(code)
    if not SHARECODE_RE.match(cleaned):
        raise ShareCodeError(
            "That does not look like a CS2 share code. It should look like "
            "CSGO-ABCDE-FGHJK-LMNOP-QRSTU-VWXYZ, copied from Watch -> Your "
            "Matches in game."
        )

    payload = cleaned.replace("CSGO-", "").replace("-", "")
    number = 0
    for character in reversed(payload):
        number = number * BASE + DICTIONARY.index(character)

    number = _swap_endianness(number)
    return ShareCode(
        code=cleaned,
        match_id=number & _MASK64,
        outcome_id=(number >> 64) & _MASK64,
        token_id=(number >> 128) & _MASK16,
    )


def encode(match_id: int, outcome_id: int, token_id: int) -> str:
    """The inverse of `decode`. Exists so the codec can be round-trip tested.

    Nothing in the product encodes a share code; Valve does. But a decoder with
    no encoder can only be tested against codes someone hands you, and a codec
    that silently drifts is the sort of bug that surfaces as "settlement graded
    the wrong match".
    """
    if not 0 <= match_id <= _MASK64:
        raise ShareCodeError("match_id out of range")
    if not 0 <= outcome_id <= _MASK64:
        raise ShareCodeError("outcome_id out of range")
    if not 0 <= token_id <= _MASK16:
        raise ShareCodeError("token_id out of range")

    number = (token_id << 128) | (outcome_id << 64) | match_id
    number = _swap_endianness(number)

    symbols = []
    for _ in range(25):
        number, remainder = divmod(number, BASE)
        symbols.append(DICTIONARY[remainder])

    payload = "".join(symbols)
    groups = [payload[i : i + 5] for i in range(0, 25, 5)]
    return "CSGO-" + "-".join(groups)


__all__ = [
    "DICTIONARY",
    "ShareCode",
    "ShareCodeError",
    "decode",
    "encode",
    "is_valid",
    "normalize",
]
