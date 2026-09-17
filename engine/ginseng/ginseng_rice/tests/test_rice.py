import asyncio

from ..budget import OrnamentBudget
from ..demo import FittingRoom
from ..dress import COORDS
from ..lint import check
from ..tokens import ROLES
from ..widgets import Hanko, Trim


def test_every_coord_passes_lint():
    for coord in COORDS.values():
        problems = [p for p in check(coord) if not p.startswith("note")]
        assert not problems, (coord.name, problems)


def test_every_coord_becomes_a_theme_with_all_roles():
    assert len(COORDS) == 9
    for coord in COORDS.values():
        theme = coord.to_theme()
        assert theme.name == f"ginseng-{coord.name}"
        for role in ROLES:
            assert theme.variables[f"g-{role.replace('_', '-')}"] == coord.palette[role]


def test_budget_strips_immediately_and_restores_past_margin():
    budget = OrnamentBudget()
    odds = [0.03, 0.06, 0.24, 0.26, 0.24, 0.225, 0.41, 0.39, 0.37, 0.10, 0.04, 0.02]
    assert [budget.update(p) for p in odds] == [3, 2, 2, 1, 1, 2, 0, 0, 1, 2, 2, 3]


def test_fitting_room_dresses_changes_coord_and_undresses():
    async def run():
        app = FittingRoom()
        async with app.run_test(size=(86, 18)) as pilot:
            await pilot.pause()
            assert app.theme == "ginseng-seifuku"
            assert "-ornate-2" in app.screen.classes
            assert [h.get_content_width(None, None) for h in app.query(Hanko)] == [2, 4, 4]

            await pilot.press("t")
            await pilot.pause(0.6)
            assert app.theme == "ginseng-stage"
            assert not any(name.startswith("henshin-") for name in app.available_themes)
            assert app.query_one(Trim).motif == COORDS["stage"].borders["trim"]

            await pilot.press("s")
            await pilot.pause()
            assert "-ornate-0" in app.screen.classes
            assert app.query_one(Trim).styles.display == "none"

    asyncio.run(run())
