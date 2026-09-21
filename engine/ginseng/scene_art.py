"""User-supplied Braille artwork, kept as lossless UTF-8 text assets."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from ginseng.braille import _BITS, _cells_from_canvas

ART_DIR = Path(__file__).with_name("art")


@dataclass(frozen=True)
class Scene:
    label: str
    caption: str
    art: str


def _scene(name: str, label: str, caption: str) -> Scene:
    return Scene(label, caption, (ART_DIR / f"{name}.txt").read_text(encoding="utf-8"))


SCENES = {
    "anya": _scene("anya", "Horned chibi", "a little curiosity"),
    "starry": _scene("starry", "Starry eyes", "a sky full of possibilities"),
    "black-cat": _scene("black-cat", "Black cat", "your midnight companion"),
    "wink": _scene("wink", "Winking girl", "one more discovery"),
    "study": _scene("study", "Laptop girl", "the late-night study session"),
    "soft-eyes": _scene("soft-eyes", "Soft eyes", "a quiet moment"),
    "ghost": _scene("ghost", "Little ghost", "a friendly haunting"),
    "catgirl": _scene("catgirl", "Cat-eared chibi", "welcome to the neko cafe"),
    "cyberpunk": _scene("cyberpunk", "Cyberpunk portrait", "after-hours transmission"),
    "cinnamoroll": _scene(
        "cinnamoroll", "Floppy-eared friend", "a softer kind of afternoon"
    ),
    "gojo-chibi": _scene(
        "gojo-chibi", "Blindfold chibi", "limitless little possibilities"
    ),
    "framed-eyes": _scene("framed-eyes", "Manga eyes", "between the panels"),
    "gojo": _scene("gojo", "Sunglasses portrait", "looking toward tomorrow"),
    "miku": _scene("miku", "Twin-tail idol", "a song for the late shift"),
    "bird": _scene("bird", "Little bird", "just passing through"),
    "shadow": _scene("shadow", "Shadow portrait", "a face in the neon"),
    "negative": _scene("negative", "Negative portrait", "light through the dark"),
    "twintails": _scene("twintails", "Twin-tail portrait", "the last encore"),
}
THEME_SCENES = {
    "sakura": "anya",
    "moonrise": "starry",
    "evangelion": "cyberpunk",
    "miku": "miku",
    "catppuccin": "black-cat",
    "akira": "shadow",
    "lain": "study",
    "mori": "cinnamoroll",
    "dojima": "gojo",
    "decora": "catgirl",
    "rococo": "wink",
    "gosurori": "negative",
    "gothpunk": "cyberpunk",
    "seifuku": "twintails",
    "stage": "framed-eyes",
    "techwear": "gojo-chibi",
}


@cache
def scene_rows(name: str) -> tuple[str, ...]:
    """Trim only empty outer margins; keep every internal cell and blank row."""
    rows = SCENES[name].art.splitlines()
    occupied = [i for i, row in enumerate(rows) if row.strip("⠀ ")]
    if not occupied:
        return ()
    rows = rows[occupied[0] : occupied[-1] + 1]
    left = min(len(row) - len(row.lstrip("⠀ ")) for row in rows if row.strip("⠀ "))
    right = max(len(row.rstrip("⠀ ")) for row in rows)
    return tuple(row[left:right].ljust(right - left, "⠀") for row in rows)


@lru_cache(maxsize=256)
def fit_scene(name: str, width: int, max_height: int | None = None) -> tuple[str, ...]:
    """Fit the full picture, pooling dots so thin strokes survive downsampling.

    A glyph is a 2×4 dot tile. Scaling both pixel axes by the same ratio
    preserves the terminal artwork's aspect ratio; no characters are cropped.
    """
    rows = scene_rows(name)
    if not rows or width <= 0 or (max_height is not None and max_height <= 0):
        return ()
    native_w, native_h = len(rows[0]), len(rows)
    ratio = min(1.0, width / native_w)
    if max_height is not None:
        ratio = min(ratio, max_height / native_h)
    out_w, out_h = max(1, int(native_w * ratio)), max(1, int(native_h * ratio))
    if (out_w, out_h) == (native_w, native_h):
        return rows
    canvas = [[False] * (out_w * 2) for _ in range(out_h * 4)]
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            bits = ord(char) - 0x2800
            for dy in range(4):
                for dx in range(2):
                    if bits & (1 << _BITS[dy][dx]):
                        dest_y = (y * 4 + dy) * out_h // native_h
                        dest_x = (x * 2 + dx) * out_w // native_w
                        canvas[dest_y][dest_x] = True
    return tuple(_cells_from_canvas(canvas, out_w * 2, out_h * 4))
