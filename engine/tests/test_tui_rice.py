"""Exercise the wardrobe controls and the meaning of the new visualizations."""

import asyncio
import math

import pytest
from ginseng.ginseng_rice.dress import COORDS
from ginseng.rice_charts import (
    ResearchPlot,
    TableVisual,
    dot_plot,
    numeric_columns,
    plot_points,
    spark,
)
from ginseng.rice_ui import SCENES, active_scene, scene_content
from ginseng.scene_art import fit_scene, scene_rows
from ginseng.tui import GinsengApp
from textual.widgets import ContentSwitcher, Footer, Select


@pytest.fixture(autouse=True)
def quiet_motion(monkeypatch):
    monkeypatch.setenv("GINSENG_MOTION", "0")


def test_plots_preserve_numeric_axes_and_omit_missing_values():
    rows = [
        {"day": 3, "cash": -20},
        {"day": 10, "cash": 0},
        {"day": 100, "cash": 40},
        {"day": 101, "cash": None},
        {"day": 102, "cash": math.inf},
        {"day": False, "cash": 100},
        {"day": 104, "cash": True},
    ]
    assert numeric_columns(["day", "cash", "missing"], rows) == ["day", "cash"]
    assert plot_points(rows, "day", "cash") == [
        (3.0, -20.0),
        (10.0, 0.0),
        (100.0, 40.0),
    ]
    assert plot_points(rows[:3], None, "cash") == [
        (1.0, -20.0),
        (2.0, 0.0),
        (3.0, 40.0),
    ]
    rows = dot_plot([(0, 0), (100, 100)], 10, 4)
    assert len(rows) == 4 and all(len(row) == 10 for row in rows)
    assert rows[0][-1] != "\u2800" and rows[-1][0] != "\u2800"
    assert dot_plot([], 10, 4) == []
    assert len(dot_plot([(0, 0)], 1, 1)) == 1
    assert spark([-10, 0, 10], 3) == "▁▅█"
    assert spark([0, 0, 0], 3) == "▄▄▄"


def test_art_fits_the_terminal_without_patched_fonts():
    for name, scene in SCENES.items():
        assert all(ch == "\n" or "\u2800" <= ch <= "\u28ff" for ch in scene.art)
        rows = scene_rows(name)
        assert rows and rows[0].strip("⠀") and rows[-1].strip("⠀")
        assert fit_scene(name, len(rows[0])) == rows
        for width in (8, 22, 28, 60):
            content = scene_content(name, width)
            assert all(len(row) <= width for row in content.plain.splitlines())
            fitted = fit_scene(name, width, 14)
            assert 1 <= len(fitted) <= 14
            assert any(row.strip("⠀") for row in fitted)
    assert len(SCENES) == 18
    assert fit_scene("miku", 0) == ()


@pytest.mark.parametrize("size", [(140, 48), (80, 24)])
def test_live_wardrobe_and_explicit_art_override(size):
    async def run():
        app = GinsengApp(coord="miku")
        async with app.run_test(size=size) as pilot:
            await pilot.press("space", "ctrl+w")
            await pilot.pause()
            assert app.query_one("#body", ContentSwitcher).current == "panel-wardrobe"
            assert active_scene(app) == "miku"
            selector = app.query_one("#rice-coord", Select)
            selector.value = "evangelion"
            await pilot.pause()
            assert app.theme == "ginseng-evangelion"
            assert active_scene(app) == "cyberpunk"
            app.query_one("#rice-art", Select).value = "shadow"
            await pilot.pause()
            for name in COORDS:
                await app.wear(name)
                await pilot.pause()
                assert selector.value == name
                assert active_scene(app) == "shadow"
            app.set_art("auto")
            await app.wear("moonrise")
            await pilot.pause()
            assert active_scene(app) == "starry"
            # Move focus out of Select before using app-level letter bindings.
            app.query_one("#rice-home").focus()
            await pilot.press("a")
            await pilot.pause()
            assert active_scene(app) == "black-cat"
            assert app.query_one("#rice-art", Select).value == "black-cat"
            assert not app.query_one("#panel-wardrobe").max_scroll_x
            assert not app.query_one(Footer).max_scroll_x

    asyncio.run(run())


def test_result_visual_axes_table_switch_and_empty_state():
    async def run():
        app = GinsengApp()
        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.press("space")
            app.open_studio("tails")
            visual = app.query_one(TableVisual)
            visual.show(
                ["day", "cash"], [{"day": 2, "cash": -10}, {"day": 9, "cash": 30}]
            )
            await pilot.pause()
            app.query_one("#plot-x", Select).value = "day"
            app.query_one("#plot-y", Select).value = "cash"
            await pilot.pause()
            plot = app.query_one(ResearchPlot)
            assert plot.points == [(2.0, -10.0), (9.0, 30.0)]
            assert plot.x_label == "day" and plot.y_label == "cash"
            visual.show(["label"], [{"label": "unavailable"}])
            await pilot.pause()
            assert not visual.display
            assert plot.points == []
            visual.show(["x"], [{"x": i} for i in range(5001)])
            await pilot.pause()
            assert len(plot.points) == 5000 and plot.total_rows == 5001
            assert "first 5,000 of 5,001" in plot.render().plain

    asyncio.run(run())
