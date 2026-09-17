import re

from ..dress import COORDS
from ..skins import ansi16, ghostty, kitty
from ..terminal import DARK_DEFAULT, LIGHT_DEFAULT, is_dark, parse_osc11, pick_coord


def test_parse_osc11_replies():
    assert parse_osc11(b"\x1b]11;rgb:0d0d/0b0b/1111\x07") == "#0D0B11"
    assert parse_osc11(b"\x1b]11;rgb:f8/fa/fe\x1b\\") == "#F8FAFE"
    assert parse_osc11(b"\x1b]11;rgb:ffff/ffff/ffff\x1b\\") == "#FFFFFF"
    assert parse_osc11(b"no reply") is None


def test_is_dark():
    assert is_dark("#0D0B11")
    assert not is_dark("#F8FAFE")


def test_pick_coord_precedence():
    assert pick_coord({"GINSENG_COORD": "stage"}, query=lambda: "#FFFFFF") == "stage"
    assert pick_coord({"GINSENG_COORD": "nope"}, query=lambda: "#FFFFFF") == LIGHT_DEFAULT
    assert pick_coord({}, query=lambda: "#0D0B11") == DARK_DEFAULT
    assert pick_coord({}, query=lambda: None) == DARK_DEFAULT


def test_skins_cover_all_sixteen_colors():
    for coord in COORDS.values():
        colors = ansi16(coord)
        assert len(colors) == 16 and all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in colors)
        assert ghostty(coord).count("\npalette = ") == 16
        assert "\ncolor15 " in kitty(coord)
