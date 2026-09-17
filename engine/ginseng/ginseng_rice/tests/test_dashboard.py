import asyncio
from dataclasses import replace

import pytest

from ..dashboard.app import DashboardApp
from ..dashboard.board import Dashboard
from ..dashboard.charts import FanChart, TroughHistogram
from ..dashboard.fixture import fixture
from ..dashboard.model import FundingOption, PathBands
from ..dashboard.panels import LedgerStrip, OptionsTable, VoiceLine, voice_values
from ..tokens import VOICE_FIELDS


def plain(widget) -> str:
    return widget.render().plain


def test_fixture_numbers_are_stable():
    thin = fixture("thin")
    assert round(thin.reserve_to_add) == 294
    assert round(thin.shortfall_p, 3) == 0.178
    assert round(thin.cvar95_trough) == -536
    assert round(thin.deficit_dollar_days) == 193
    assert thin.solvent_days == 11 and thin.state == "thin"
    assert fixture("calm").state == "calm" and fixture("calm").options == ()
    assert fixture("short").state == "short"


def test_model_rejects_bad_engine_output():
    good = fixture("thin")
    with pytest.raises(ValueError):
        PathBands(p5=[1, 2], p25=[0, 3], p50=[2, 4], p75=[3, 5], p95=[4, 6])
    with pytest.raises(ValueError):
        FundingOption("loan", "payday", 10.0, 0, 0.05)
    with pytest.raises(ValueError):
        replace(good, shortfall_p=1.2)
    with pytest.raises(ValueError):
        replace(good, trough_counts=good.trough_counts[:-1])
    with pytest.raises(ValueError):
        replace(good, solvent_days=31)


def test_voice_values_cover_every_placeholder():
    assert set(voice_values(fixture("thin"))) == set(VOICE_FIELDS)


def test_dashboard_draws_the_fixture_and_follows_coord_and_budget():
    async def run():
        app = DashboardApp(coord="seifuku", state="thin")
        async with app.run_test(size=(88, 29)) as pilot:
            await pilot.pause()
            fan = plain(app.query_one(FanChart))
            assert all(mark in fan for mark in ("p95", "p50", "$0", "d1", "d30", "━"))
            assert "under $400" in plain(app.query_one(TroughHistogram))
            assert "▸ credit line" in plain(app.query_one(OptionsTable))
            ledger = plain(app.query_one(LedgerStrip))
            assert "済" in ledger and "Kupiec p=0.48" in ledger
            voice = plain(app.query_one(VoiceLine))
            assert "$294" in voice and "credit line" in voice
            assert "-ornate-2" in app.screen.classes
            assert app.query_one("#g-reserve").border_title == "═╡ Reserve ╞═"

            await app.wear("gothpunk")
            await pilot.pause()
            assert app.theme == "ginseng-gothpunk"
            assert "╳" in plain(app.query_one(FanChart))
            assert app.query_one("#g-collar-trim").motif == "─o"

            await pilot.press("3")
            await pilot.pause()
            assert app.ornament_level == 0
            assert app.query_one("#g-reserve").border_title == "Reserve"
            assert plain(app.query_one(VoiceLine)).startswith("! Shortfall likely: 66.3%")
            assert app.query_one("#g-collar-trim").styles.display == "none"

            await pilot.press("1")
            await pilot.pause()
            assert app.ornament_level == 3
            assert "Nothing to fund" in plain(app.query_one(OptionsTable))

    asyncio.run(run())


def test_dashboard_stacks_when_narrow():
    async def run():
        app = DashboardApp(coord="mori", state="thin")
        async with app.run_test(size=(64, 50)) as pilot:
            await pilot.pause()
            assert "-narrow" in app.query_one(Dashboard).classes

    asyncio.run(run())
