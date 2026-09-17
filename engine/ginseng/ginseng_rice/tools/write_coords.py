"""Resolve tools/palettes.py (OKLCH specs) to hex and write them into ../coords/*.toml.

Only [palette] lines change; borders, glyphs, motion and voice are left alone.
Run from this folder:  python write_coords.py   then   python audit.py
"""
import re
from pathlib import Path

from palettes import PALETTES

COORDS = Path(__file__).resolve().parent.parent / "coords"

for name, palette in PALETTES.items():
    path = COORDS / f"{name}.toml"
    text = path.read_text(encoding="utf-8")
    head, sep, rest = text.partition("[palette]\n")
    block, nxt, tail = rest.partition("\n[")
    for role, value in palette.items():
        if role != "dark":
            block = re.sub(rf'^{role} = "#[0-9A-Fa-f]{{6}}"$', f'{role} = "{value}"', block, flags=re.M)
    path.write_text(head + sep + block + nxt + tail, encoding="utf-8")
    print("wrote", path.name)
