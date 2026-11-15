"""Every "what time is it" goes through `clock.now()`, so tests can control time."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.nodb

SRC = Path(__file__).resolve().parents[1] / "src" / "moneymatch_api"


def test_only_clock_reads_the_system_time():
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "clock.py" and "datetime.now(" in path.read_text()
    ]
    assert offenders == []
