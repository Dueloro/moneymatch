"""Phase 6 test gate — same-human / collusion co-entry (pure, `nodb`)."""

from __future__ import annotations

import pytest

from moneymatch_api.services import collusion as col

pytestmark = pytest.mark.nodb


def test_shared_device_blocks_co_entry():
    a = col.make_fingerprint(device_id="DEV1", ip="1.1.1.1")
    b = col.make_fingerprint(device_id="dev1", ip="2.2.2.2")  # same device, diff IP
    assert col.shares_signal(a, b) is True
    assert col.can_co_enter(b, [a]) is False


def test_shared_ip_blocks_co_entry():
    a = col.make_fingerprint(ip="9.9.9.9")
    b = col.make_fingerprint(ip="9.9.9.9")
    assert not col.can_co_enter(b, [a])


def test_distinct_players_can_co_enter():
    a = col.make_fingerprint(device_id="d1", ip="1.1.1.1")
    b = col.make_fingerprint(device_id="d2", ip="2.2.2.2")
    assert col.can_co_enter(b, [a]) is True


def test_unknown_fingerprints_never_match():
    # Two accounts we know nothing about are NOT auto-flagged as the same human.
    empty1 = col.make_fingerprint()
    empty2 = col.make_fingerprint()
    assert col.shares_signal(empty1, empty2) is False
    assert col.can_co_enter(empty2, [empty1]) is True


def test_kinds_do_not_cross_collide():
    # A device id equal to an IP string must not be treated as a match.
    a = col.make_fingerprint(device_id="1.2.3.4")
    b = col.make_fingerprint(ip="1.2.3.4")
    assert col.shares_signal(a, b) is False


def test_can_co_enter_against_a_room():
    room = [
        col.make_fingerprint(device_id="d1"),
        col.make_fingerprint(device_id="d2"),
    ]
    ok = col.make_fingerprint(device_id="d3")
    bad = col.make_fingerprint(device_id="d2")  # dup of a room member
    assert col.can_co_enter(ok, room) is True
    assert col.can_co_enter(bad, room) is False


def test_colluding_players_lists_each_pair_once_deterministically():
    fps = {
        "alice": col.make_fingerprint(device_id="shared", ip="1.1.1.1"),
        "bob": col.make_fingerprint(device_id="shared", ip="2.2.2.2"),  # same device
        "carol": col.make_fingerprint(device_id="unique", ip="3.3.3.3"),
    }
    pairs = col.colluding_players(fps)
    assert pairs == [("alice", "bob")]


def test_payment_instrument_match():
    a = col.make_fingerprint(payment_id="card_abc")
    b = col.make_fingerprint(payment_id="card_abc")
    assert col.shares_signal(a, b)
