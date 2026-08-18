"""The sidecar health response must say *which* failure it is (1.5).

`ready: false` used to mean either "the process is up but has not attached to
the Game Coordinator" or "there is no process at all", with the same shape for
both — and the router then discarded the `detail` field that would have told
them apart. That is why a deployed sidecar reported `ready:false` for three days
without anyone being able to say whether it was misconfigured or missing.

The two need different people to do different things: an unattached sidecar
usually needs a fresh Steam refresh token; an unreachable one needs a deploy.
"""

from __future__ import annotations

import httpx
import pytest

from moneymatch_api.services import gc_client

pytestmark = pytest.mark.nodb


@pytest.fixture(autouse=True)
def _reset_breaker():
    gc_client.reset_breaker()
    yield
    gc_client.reset_breaker()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, *_args, **_kwargs):
        if isinstance(self._result, Exception):
            raise self._result
        return _FakeResponse(self._result)


def _patch_client(monkeypatch, result):
    monkeypatch.setattr(
        gc_client.httpx, "AsyncClient", lambda **_kw: _FakeClient(result)
    )


async def test_attached_when_the_sidecar_reports_ready(monkeypatch):
    _patch_client(monkeypatch, {"ready": True, "queueDepth": 2})
    health = await gc_client.health()
    assert health.status == "attached"
    assert health.ready is True
    assert health.queue_depth == 2
    assert health.is_healthy is True


async def test_up_but_unattached_when_it_answers_not_ready(monkeypatch):
    """The three-day case: a process is there, it just is not talking to Valve."""
    _patch_client(monkeypatch, {"ready": False, "queueDepth": 0})
    health = await gc_client.health()
    assert health.status == "up_but_unattached"
    assert health.ready is False
    assert health.is_healthy is False
    assert health.detail == {"ready": False, "queueDepth": 0}


async def test_unreachable_when_nothing_answers(monkeypatch):
    """Not deployed, wrong address, or the network path is broken."""
    _patch_client(monkeypatch, httpx.ConnectError("connection refused"))
    health = await gc_client.health()
    assert health.status == "unreachable"
    assert health.ready is False
    assert "connection refused" in health.detail["error"]
    assert health.detail["error_type"] == "ConnectError"
    # The address we actually tried, so a misconfigured URL is self-evident.
    assert "url" in health.detail


async def test_unreachable_when_the_body_is_not_json(monkeypatch):
    """A proxy or error page answering on the sidecar's port."""
    _patch_client(monkeypatch, ValueError("not json"))
    health = await gc_client.health()
    assert health.status == "unreachable"


async def test_circuit_open_is_reported_as_itself(monkeypatch):
    """When we have stopped calling, we must not blame the sidecar."""
    for _ in range(gc_client._BREAKER_THRESHOLD):
        gc_client._record_failure()

    called = False

    def _should_not_be_called(**_kw):
        nonlocal called
        called = True
        raise AssertionError("must not call the sidecar while the breaker is open")

    monkeypatch.setattr(gc_client.httpx, "AsyncClient", _should_not_be_called)
    health = await gc_client.health()
    assert health.status == "circuit_open"
    assert health.ready is False
    assert called is False


async def test_all_four_statuses_are_distinguishable(monkeypatch):
    """The property that matters: no two failure modes share a representation."""
    seen = {}

    _patch_client(monkeypatch, {"ready": True, "queueDepth": 0})
    seen["attached"] = (await gc_client.health()).status
    _patch_client(monkeypatch, {"ready": False, "queueDepth": 0})
    seen["up_but_unattached"] = (await gc_client.health()).status
    _patch_client(monkeypatch, httpx.ConnectError("boom"))
    seen["unreachable"] = (await gc_client.health()).status
    gc_client.reset_breaker()
    for _ in range(gc_client._BREAKER_THRESHOLD):
        gc_client._record_failure()
    seen["circuit_open"] = (await gc_client.health()).status

    assert seen == {
        "attached": "attached",
        "up_but_unattached": "up_but_unattached",
        "unreachable": "unreachable",
        "circuit_open": "circuit_open",
    }
    assert len(set(seen.values())) == 4
