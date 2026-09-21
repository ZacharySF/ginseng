"""Snapshot tests capture one instant; the voice-line typewriter and the
henshin coord transition are real animations, so pin them to their
documented instant-reveal escape hatch for every test in this package."""
import pytest


@pytest.fixture(autouse=True)
def _no_motion(monkeypatch):
    monkeypatch.setenv("GINSENG_MOTION", "0")
    monkeypatch.delenv("NO_COLOR", raising=False)
