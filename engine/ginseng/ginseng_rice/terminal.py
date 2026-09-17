"""Pick a coord from the terminal's background color, before Textual takes over the terminal."""
from __future__ import annotations

import os
import re
import select
import sys
import time
from typing import Callable, Mapping

from .oklab import hex_to_oklab
from .tokens import COORD_DIR

LIGHT_DEFAULT, DARK_DEFAULT = "seifuku", "gosurori"
_REPLY = re.compile(rb"\x1b\]11;rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})(?:\x07|\x1b\\)")


def parse_osc11(reply: bytes) -> str | None:
    """Turn an OSC 11 reply such as ESC ] 11 ; rgb:0d0d/0b0b/1111 BEL into '#0D0B11'."""
    match = _REPLY.search(reply)
    if match is None:
        return None
    channels = []
    for group in match.groups():
        maximum = (1 << (4 * len(group))) - 1
        channels.append(round(int(group, 16) * 255 / maximum))
    return "#%02X%02X%02X" % tuple(channels)


def is_dark(hex_color: str) -> bool:
    return hex_to_oklab(hex_color)[0] < 0.6


def query_background(timeout: float = 0.15) -> str | None:
    """Ask the terminal for its background with OSC 11. None when unsupported or not a TTY.

    Must run before App.run(): Textual owns stdin afterwards. TCSAFLUSH on restore drops any
    reply that arrives after the timeout, so it can't leak into the app as keystrokes.
    """
    if os.name != "posix" or not sys.stdin.isatty():
        return None
    import termios
    import tty

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        os.write(fd, b"\x1b]11;?\x07")
        reply, deadline = b"", time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            reply += os.read(fd, 128)
            if reply.endswith((b"\x07", b"\x1b\\")):
                break
        return parse_osc11(reply)
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
        os.close(fd)


def pick_coord(env: Mapping[str, str] | None = None,
               query: Callable[[], str | None] = query_background) -> str:
    """GINSENG_COORD wins. Otherwise light backgrounds get seifuku; dark or unknown get mori."""
    env = os.environ if env is None else env
    forced = env.get("GINSENG_COORD", "")
    if forced and (COORD_DIR / f"{forced}.toml").exists():
        return forced
    background = query()
    if background is not None and not is_dark(background):
        return LIGHT_DEFAULT
    return DARK_DEFAULT
