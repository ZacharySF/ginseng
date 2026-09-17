"""Visual regression for the integrated app (sidebar + coord + real Dashboard).

Two real, reproducible engine runs (not the fixed 88x29 the standalone
ginseng_rice tests use -- this app carries extra chrome around the
Dashboard, so 120x45 is more representative), plus one NO_COLOR check.

First run on a new machine or Textual/Rich version: pytest --snapshot-update
then open the SVGs in __snapshots__ and check them by eye before committing.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from ginseng import tui as tui_module
from ginseng.tui import GinsengApp

SIZE = (120, 45)


class _FrozenDateTime(datetime):
    """The event log and telemetry strip render wall-clock timestamps and an
    elapsed duration; freezing `datetime.now()` makes both reproducible
    (elapsed always reads 0.00s, since start and end read the same instant)."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, 12, 0, 0, tzinfo=tz)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    monkeypatch.setattr(tui_module, "datetime", _FrozenDateTime)


@pytest.fixture(autouse=True)
def _no_motion(monkeypatch):
    # The voice-line typewriter and henshin coord transitions are real
    # animations; snapshot tests capture one instant, so skip straight to it.
    monkeypatch.setenv("GINSENG_MOTION", "0")

# canonical fixture, seed 42, mc/2048 paths: reproducible, lands calm (0% shortfall).
CANONICAL = dict(source="fixture", fixture_name="canonical", path="", sampler="mc",
                  estimator="path", paths=2048, seed=42, replicate=0,
                  horizon=None, material_horizon=None, block_length=None)


async def _wait_for_result(pilot) -> None:
    app = pilot.app
    for _ in range(200):
        if app.query_one("#body").current == "panel-result":
            return
        await pilot.pause(0.05)
    raise AssertionError("run did not reach panel-result in time")


async def _dismiss_boot(pilot) -> None:
    await pilot.pause()
    await pilot.press("space")
    await pilot.pause()


async def _run_simulate(pilot) -> None:
    await _dismiss_boot(pilot)
    pilot.app.launch("simulate", dict(CANONICAL))
    await _wait_for_result(pilot)


async def _run_exact(pilot) -> None:
    # The exact oracle's own default model: reproducible, lands short (~39% shortfall).
    await _dismiss_boot(pilot)
    pilot.app.launch("exact", None)
    await _wait_for_result(pilot)


def test_boot_screen(snap_compare):
    # No run_before: capture the boot splash itself, before it's dismissed.
    assert snap_compare(GinsengApp(coord="gothpunk"), terminal_size=SIZE)


def test_boot_screen_dismisses_on_key():
    async def run():
        app = GinsengApp(coord="gothpunk")
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            assert len(app.screen_stack) == 2
            await pilot.press("space")
            await pilot.pause()
            assert len(app.screen_stack) == 1

    asyncio.run(run())


def test_calm_simulate_run(snap_compare):
    assert snap_compare(GinsengApp(coord="mori"), terminal_size=SIZE, run_before=_run_simulate)


def test_short_exact_run(snap_compare):
    assert snap_compare(GinsengApp(coord="stage"), terminal_size=SIZE, run_before=_run_exact)


def test_short_exact_run_without_color(snap_compare, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert snap_compare(GinsengApp(coord="mori"), terminal_size=SIZE, run_before=_run_exact)
