"""The live wardrobe for the user-supplied Braille art collection."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Button, Select, Static

from ginseng.ginseng_rice.dress import COORDS
from ginseng.scene_art import SCENES, THEME_SCENES, fit_scene


def active_scene(app) -> str:
    choice = getattr(app, "art_choice", "auto")
    return THEME_SCENES.get(app.coord.name, "anya") if choice == "auto" else choice


def scene_content(
    name: str, width: int, tone: str = "focus", max_height: int | None = None
) -> Content:
    rows = fit_scene(name, width, max_height)
    if not rows:
        return Content("")
    pad = " " * max(0, (width - len(rows[0])) // 2)
    return Content.assemble(("\n".join(pad + row for row in rows), f"$g-{tone}"))


class AnimeScene(Static):
    DEFAULT_CLASSES = "g-glyphs"

    def render(self):
        height = max(6, self.app.size.height - 22) if self.has_class("rice-gallery") else 16
        return scene_content(
            active_scene(self.app), self.content_size.width or 28, max_height=height
        )


class RiceIdentity(Static):
    """Fastfetch-inspired identity card. Every counter describes this app."""

    DEFAULT_CLASSES = "g-glyphs"

    def render(self):
        coord = self.app.coord
        scene = SCENES[active_scene(self.app)]
        parts = [
            ("ginseng@atelier\n", "bold $g-focus"),
            ("──────────────────────────\n", "$g-rule"),
            (f"outfit   {coord.name}\n", "$g-ink"),
            (f"art      {scene.label}\n", "$g-ink"),
            (f"wardrobe {len(COORDS)} palettes / {len(SCENES)} scenes\n", "$g-muted"),
            ("keys     t palette / a art / Ctrl+W wardrobe\n", "$g-muted"),
            ("\n", ""),
        ]
        for role in ("focus", "accent", "safe", "thin", "short", "ink"):
            parts.append(("   ", f"on $g-{role}"))
        parts.extend([("\n\n", ""), (scene.caption, "$g-accent")])
        return Content.assemble(*parts)


class RiceHero(Horizontal):
    def compose(self) -> ComposeResult:
        yield AnimeScene(classes="rice-scene")
        yield RiceIdentity(classes="rice-identity")


class WardrobePanel(VerticalScroll):
    DEFAULT_CLASSES = "g-dressable"

    def compose(self) -> ComposeResult:
        yield Static("✦  W A R D R O B E  /  dress your terminal", classes="rule")
        yield Static(
            f"{len(COORDS)} outfits. {len(SCENES)} portraits. Your own late-night anime workstation.",
            classes="welcome-copy",
        )
        with Horizontal(classes="wardrobe-controls"):
            with Vertical(classes="field-col"):
                yield Static("COLOR PALETTE", classes="field-label")
                yield Select(
                    [(f"{c.name} / {c.label}", c.name) for c in COORDS.values()],
                    value=self.app.coord.name,
                    allow_blank=False,
                    id="rice-coord",
                )
            with Vertical(classes="field-col"):
                yield Static("BRAILLE ART", classes="field-label")
                yield Select(
                    [("Match the outfit", "auto")]
                    + [(s.label, k) for k, s in SCENES.items()],
                    value="auto",
                    allow_blank=False,
                    id="rice-art",
                )
        yield AnimeScene(classes="rice-gallery")
        yield RiceIdentity(classes="wardrobe-identity")
        yield Static("", id="rice-palette-strip")
        yield Static("THE SIGNAL STAYS READABLE", classes="rule")
        yield Static(
            Content.assemble(
                ("LOW  ▰▰▱▱  ", "$g-safe"),
                ("MODERATE  ▰▰▰▱  ", "$g-thin"),
                ("HIGH  ▰▰▰▰", "$g-short"),
                (
                    "\nState colors always carry words. Charts keep the same meaning in every outfit.",
                    "$g-muted",
                ),
            ),
            classes="welcome-copy",
        )
        yield Static(
            "t  next palette     a  next scene     Ctrl+P  search outfits\n"
            "Choose “Match the outfit” to restore automatic art.\n"
            "Launch in your favorite palette with: ginseng tui --coord miku",
            classes="welcome-copy",
        )
        yield Button("Back to the atelier", id="rice-home")

    def dress(self, coord) -> None:
        selector = self.query_one("#rice-coord", Select)
        if selector.value != coord.name:
            selector.value = coord.name
        self.query_one("#rice-art", Select).value = getattr(
            self.app, "art_choice", "auto"
        )
        parts = []
        for role in (
            "paper",
            "panel",
            "focus",
            "accent",
            "safe",
            "thin",
            "short",
            "ink",
        ):
            parts.extend([("  ██ ", f"$g-{role}"), (role + " ", "$g-muted")])
        self.query_one("#rice-palette-strip", Static).update(Content.assemble(*parts))

    @on(Select.Changed, "#rice-coord")
    async def choose_coord(self, event: Select.Changed) -> None:
        if event.value in COORDS and event.value != self.app.coord.name:
            await self.app.wear(str(event.value))

    @on(Select.Changed, "#rice-art")
    def choose_art(self, event: Select.Changed) -> None:
        if event.value == "auto" or event.value in SCENES:
            self.app.set_art(str(event.value))

    @on(Button.Pressed, "#rice-home")
    def go_home(self) -> None:
        self.app.action_go_welcome()
