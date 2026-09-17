"""Visual regression for the dashboard: 8 coords x 3 states, plus NO_COLOR.

First run on a new machine or Textual version:  pytest --snapshot-update  then open the
SVGs in tests/__snapshots__ and check them by eye before committing.
"""
import pytest

from ..dashboard.app import DashboardApp
from ..dress import COORDS

SIZE = (88, 29)


@pytest.mark.parametrize("state", ["calm", "thin", "short"])
@pytest.mark.parametrize("coord", sorted(COORDS))
def test_dashboard(snap_compare, coord, state):
    assert snap_compare(DashboardApp(coord=coord, state=state), terminal_size=SIZE)


def test_dashboard_without_color(snap_compare, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert snap_compare(DashboardApp(coord="mori", state="short"), terminal_size=SIZE)
