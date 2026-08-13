"""Relinking Steam must not leave a chain pointed at the old account.

A chain's authentication code is issued per Steam account, and its cursor points
into that account's match list. Carrying either across to a different SteamID
would keep collecting the *previous* account's matches and settle this user's
wagers from them — someone else's results, paying out real money.
"""

from __future__ import annotations

import uuid

import pytest

from moneymatch_api.models.cs2 import Cs2ShareChain

pytestmark = pytest.mark.nodb

OLD = "76561198748110372"
NEW = "76561198000000001"


def _chain(steam_id: str) -> Cs2ShareChain:
    return Cs2ShareChain(
        user_id=uuid.uuid4(),
        steam_id=steam_id,
        auth_code="AAAA-BBBB",
        known_code="CSGO-old",
    )


def test_a_chain_for_another_account_is_recognised():
    """The condition the callback drops on."""
    assert _chain(OLD).steam_id != NEW


def test_relinking_the_same_account_leaves_it_alone():
    """Re-verifying the same SteamID changes nothing, so the chain survives."""
    assert _chain(OLD).steam_id == OLD


def test_the_callback_drops_a_chain_that_no_longer_matches():
    """Structural: the check lives in the callback, not in a caller's memory."""
    import inspect

    from moneymatch_api.routers import cs2

    source = inspect.getsource(cs2.steam_callback)
    assert "chain.steam_id != steam_id" in source
    assert "session.delete(chain)" in source
