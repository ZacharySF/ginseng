"""Fitting room: a small dashboard dressed in whichever coord is active.

Run with:  python -m <package path>.ginseng_rice.demo
Keys: t next coord, s toggle a 47% shortfall, q quit.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Digits, Footer, Label, Sparkline

from .dress import COORDS, Dressable
from .tokens import Coord
from .widgets import Hanko, Soroban, Trim


class FittingRoom(Dressable, App):
    CSS_PATH = ["rice.tcss", "demo.tcss"]
    BINDINGS = [("t", "next_coord", "coord"), ("s", "stress", "stress"), ("q", "quit", "quit")]

    def __init__(self, start: str = "seifuku") -> None:
        super().__init__()
        self.start = start
        self.short_p = 0.178

    def compose(self) -> ComposeResult:
        kit = COORDS[self.start]
        yield Trim(kit.borders.get("trim", "─"), classes="g-ornament")
        with Horizontal(id="top"):
            with Vertical(id="reserve", classes="g-panel") as reserve:
                reserve.border_title = "Reserve"
                yield Label("Required reserve, p95", classes="g-muted")
                yield Digits("$294", id="rlr", classes="g-thin")
                yield Label("Shortfall odds 17.8%", id="odds", classes="g-thin")
                yield Soroban(kit.glyphs["gauge_on"], kit.glyphs["gauge_off"], id="solvent")
            with Vertical(id="paths", classes="g-panel g-hatch") as paths:
                paths.border_title = "Cash paths"
                yield Sparkline([1720, 1690, 1650, 1600, 150, 140, 900, 1500, 1800, 2200, 2100, 2300], id="median")
        with Horizontal(id="ledger", classes="g-panel"):
            yield Label("d-2 client X +$640 ")
            yield Hanko("settled")
            yield Label("   d5 rent −$1,450 ")
            yield Hanko("pending")
            yield Label("   d10 invoice A +$1,800 ")
            yield Hanko("estimate")
        yield Footer()

    def on_mount(self) -> None:
        self.dress_up(self.start)
        self.apply_state()

    def on_coord_changed(self, coord: Coord) -> None:
        self.query_one(Trim).motif = coord.borders.get("trim", "─")
        solvent = self.query_one(Soroban)
        solvent.on, solvent.off = coord.glyphs["gauge_on"], coord.glyphs["gauge_off"]
        solvent.refresh()

    def apply_state(self) -> None:
        tone = "short" if self.short_p >= 0.25 else "thin"
        self.query_one("#odds", Label).update(f"Shortfall odds {self.short_p:.1%}")
        self.query_one("#rlr", Digits).update("$694" if tone == "short" else "$294")
        for widget in (self.query_one("#odds"), self.query_one("#rlr")):
            widget.set_class(tone == "short", "g-short")
            widget.set_class(tone == "thin", "g-thin")
        solvent = self.query_one(Soroban)
        solvent.tone, solvent.days = tone, (4 if tone == "short" else 11)
        self.report_shortfall(self.short_p)

    def action_stress(self) -> None:
        self.short_p = 0.47 if self.short_p < 0.4 else 0.178
        self.apply_state()


if __name__ == "__main__":
    FittingRoom().run()
