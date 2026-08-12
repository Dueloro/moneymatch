"""The share-code codec, which is how a real CS2 match enters the system.

A share code is the only artifact a player can copy out of the game, so every
CS2 wager settles on one. A decoder that drifts does not fail loudly: it
produces a *different valid-looking* match id, and settlement grades the wrong
match. Hence the round-trip properties below rather than a couple of examples.

Validated on 2026-08-12 against a real share code from a real CS2 match. It
round-trips byte-identically and decodes to structurally sound ids, which is the
one assumption round-tripping alone could not cover.
"""

from __future__ import annotations

import random

import pytest

from moneymatch_api.services import sharecode
from moneymatch_api.services.sharecode import ShareCodeError

pytestmark = pytest.mark.nodb

MASK64 = 0xFFFFFFFFFFFFFFFF
MASK16 = 0xFFFF


# --------------------------------------------------------------------------- #
# Shape.
# --------------------------------------------------------------------------- #


def test_the_alphabet_is_base_57_and_omits_confusable_characters():
    assert sharecode.BASE == 57
    assert len(set(sharecode.DICTIONARY)) == 57
    for confusable in "Il01g":
        assert confusable not in sharecode.DICTIONARY, confusable


def test_an_encoded_code_has_the_shape_the_game_shows_you():
    code = sharecode.encode(1, 2, 3)
    assert code.startswith("CSGO-")
    groups = code.split("-")
    assert len(groups) == 6  # "CSGO" + five groups
    assert all(len(g) == 5 for g in groups[1:]), code
    assert sharecode.is_valid(code)


# --------------------------------------------------------------------------- #
# Round trip. This is the property that matters.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("match_id", "outcome_id", "token_id"),
    [
        (0, 0, 0),
        (1, 1, 1),
        (MASK64, MASK64, MASK16),  # all bits set
        (3_433_015_890_048_991_558, 3_433_016_308_181_073_413, 22_608),
        (1 << 63, 1 << 62, 1 << 15),
    ],
)
def test_decode_reverses_encode(match_id, outcome_id, token_id):
    code = sharecode.encode(match_id, outcome_id, token_id)
    decoded = sharecode.decode(code)
    assert decoded.match_id == match_id
    assert decoded.outcome_id == outcome_id
    assert decoded.token_id == token_id


def test_round_trip_holds_across_random_values():
    rng = random.Random(20260811)
    for _ in range(200):
        match_id = rng.getrandbits(64)
        outcome_id = rng.getrandbits(64)
        token_id = rng.getrandbits(16)
        decoded = sharecode.decode(sharecode.encode(match_id, outcome_id, token_id))
        assert (decoded.match_id, decoded.outcome_id, decoded.token_id) == (
            match_id,
            outcome_id,
            token_id,
        )


def test_encoding_is_stable():
    """Same inputs, same code. A codec that is not a function is not a codec."""
    a = sharecode.encode(123456789, 987654321, 4242)
    b = sharecode.encode(123456789, 987654321, 4242)
    assert a == b


def test_distinct_matches_produce_distinct_codes():
    codes = {sharecode.encode(i, i * 7, i % MASK16) for i in range(500)}
    assert len(codes) == 500


# --------------------------------------------------------------------------- #
# Rejection, with messages a user can act on.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not a share code",
        "CSGO-ABCDE-FGHJK-LMNOP-QRSTU",  # one group short
        "CSGO-ABCDE-FGHJK-LMNOP-QRSTU-VWXYZ-EXTRA",  # one too many
        "CSGO-ABCD-FGHJK-LMNOP-QRSTU-VWXYZ",  # short group
        "ABCDE-FGHJK-LMNOP-QRSTU-VWXYZ",  # no prefix
        "CSGO-ABCDE-FGHJK-LMNOP-QRSTU-VWXY0",  # 0 is not in the alphabet
        "CSGO-ABCDE-FGHJK-LMNOP-QRSTU-VWXYl",  # nor is lowercase L
    ],
)
def test_a_malformed_code_is_rejected(bad):
    assert sharecode.is_valid(bad) is False
    with pytest.raises(ShareCodeError):
        sharecode.decode(bad)


def test_the_rejection_message_tells_you_where_to_find_the_code():
    """ "Invalid" is not an error message a player can do anything with."""
    with pytest.raises(ShareCodeError) as excinfo:
        sharecode.decode("nonsense")
    message = str(excinfo.value)
    assert "CSGO-" in message
    assert "Your Matches" in message


# --------------------------------------------------------------------------- #
# Normalisation, kept deliberately narrow.
# --------------------------------------------------------------------------- #


def test_surrounding_whitespace_is_forgiven():
    code = sharecode.encode(42, 43, 44)
    assert sharecode.decode(f"  {code}\n").match_id == 42


def test_a_lowercase_prefix_is_forgiven():
    code = sharecode.encode(7, 8, 9)
    assert sharecode.decode(code.replace("CSGO-", "csgo-")).match_id == 7


def test_the_payload_stays_case_sensitive():
    """`A` and `a` are different symbols, so case-folding the payload would
    silently decode to a different match."""
    code = sharecode.encode(11, 22, 33)
    payload = code[5:]
    if payload.lower() != payload:
        assert (
            not sharecode.is_valid("CSGO-" + payload.lower())
            or sharecode.decode("CSGO-" + payload.lower()).match_id != 11
        )


def test_out_of_range_values_are_refused_by_the_encoder():
    with pytest.raises(ShareCodeError):
        sharecode.encode(MASK64 + 1, 0, 0)
    with pytest.raises(ShareCodeError):
        sharecode.encode(0, 0, MASK16 + 1)


# --------------------------------------------------------------------------- #
# A code Valve actually issued.
# --------------------------------------------------------------------------- #

#: From a real CS2 match. The ids below are what this codec decoded, so if a
#: refactor changes them the codec has drifted away from Valve's format, which
#: is otherwise a silent failure: settlement would grade a different match.
REAL_CODE = "CSGO-UxSfp-RRcZ4-hp5uP-9ntcq-oXc3K"
REAL_MATCH_ID = 3836574891868422813
REAL_OUTCOME_ID = 3836578720831766722
REAL_TOKEN_ID = 51138


def test_a_real_share_code_decodes_to_the_expected_ids():
    decoded = sharecode.decode(REAL_CODE)
    assert decoded.match_id == REAL_MATCH_ID
    assert decoded.outcome_id == REAL_OUTCOME_ID
    assert decoded.token_id == REAL_TOKEN_ID


def test_a_real_share_code_survives_a_round_trip():
    assert sharecode.encode(REAL_MATCH_ID, REAL_OUTCOME_ID, REAL_TOKEN_ID) == REAL_CODE


def test_the_real_ids_are_structurally_sound():
    """What a genuine GC match id looks like, as a guard on the field order.

    Swapping match_id and outcome_id, or reading the fields at the wrong
    offsets, still yields valid-looking numbers. These bounds catch that.
    """
    decoded = sharecode.decode(REAL_CODE)
    # A GC match id is a large 64-bit counter, not a small ordinal.
    assert 1e18 < decoded.match_id < 1e19
    # The outcome is allocated alongside the match, so the two stay close.
    assert abs(decoded.outcome_id - decoded.match_id) < 1e15
    assert 0 <= decoded.token_id <= MASK16
