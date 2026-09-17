"""Run the dashboard on fixture data:  python -m <package path>.ginseng_rice.dashboard.app

Keys: t next coord, 1 calm, 2 thin, 3 short, q quit.
GINSENG_COORD=<name> forces a coord; otherwise it follows the terminal background.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer

from ..dress import Dressable
from ..terminal import pick_coord
from .board import Dashboard
from .fixture import fixture


class DashboardApp(Dressable, App):
    CSS_PATH = ["../rice.tcss", "dashboard.tcss"]
    BINDINGS = [
        ("t", "next_coord", "coord"),
        ("1", "fixture('calm')", "calm"),
        ("2", "fixture('thin')", "thin"),
        ("3", "fixture('short')", "short"),
        ("q", "quit", "quit"),
    ]

    def __init__(self, coord: str | None = None, state: str = "thin") -> None:
        super().__init__()
        self.start_coord = coord
        self.start_state = state

    def compose(self) -> ComposeResult:
        yield Dashboard()
        yield Footer()

    def on_mount(self) -> None:
        self.dress_up(self.start_coord)
        self.action_fixture(self.start_state)

    def action_fixture(self, state: str) -> None:
        self.query_one(Dashboard).show(fixture(state))


def main() -> None:
    DashboardApp(coord=pick_coord()).run()


if __name__ == "__main__":
    main()
