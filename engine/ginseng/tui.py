"""Interactive offline terminal UI for ginseng simulate/exact.

Curses-only: no extra dependency beyond the Python standard library, matching
the project's offline, ordinary-CPU footprint. Launch with ``ginseng tui``.
"""

import curses
import json
import locale
import threading
import time
import traceback
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ginseng.exact import enumerate_exact
from ginseng.inputs import fixture, load_input
from ginseng.numerical import diagnostics, manifest, run_core
from ginseng.sampling import prepare_history

FIXTURES = ["canonical", "tiny", "zero-heavy", "drought-heavy"]
SAMPLERS = ["mc", "sobol", "legacy_mc"]
ESTIMATORS = ["path", "initial-block-cmc"]
ARTIFACT_DIR = Path("artifacts/tui")

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
MIN_W, MIN_H = 62, 18

# Color pair ids. Brand accent leans on the product's cobalt mark; ncurses
# only guarantees the 8 base colors portably, so "cobalt" is approximated
# with bold blue/cyan rather than a true-color hex.
P_RIBBON = 1   # black on cyan  -- top ribbon
P_SELECT = 2   # black on blue  -- selected row
P_ACCENT = 3   # cyan           -- borders, secondary emphasis
P_BRAND = 4    # blue, bold     -- headline numbers, wordmark
P_GOOD = 5     # green
P_BAD = 6      # red
P_WARN = 7     # yellow
P_MUTED = 8    # white (dimmed via A_DIM)


@dataclass
class Field:
    key: str
    label: str
    kind: str  # "choice", "int", "optional_int", "text"
    value: Any
    choices: Optional[list] = None
    hint: str = ""


def default_fields():
    return [
        Field("source", "Source", "choice", "fixture", ["fixture", "file"]),
        Field("fixture", "Fixture", "choice", "canonical", FIXTURES),
        Field("path", "Input file", "text", "examples/tiny-history.json"),
        Field("sampler", "Sampler", "choice", "mc", SAMPLERS),
        Field("estimator", "Estimator", "choice", "path", ESTIMATORS),
        Field("paths", "Paths", "int", 2048, hint="powers of two required for sobol"),
        Field("seed", "Seed", "int", 42),
        Field("replicate", "Replicate", "int", 0),
        Field("horizon", "Horizon (days)", "optional_int", None, hint="blank = fixture default"),
        Field("material_horizon", "Material horizon", "optional_int", None, hint="blank = none"),
        Field("block_length", "Block length", "optional_int", None, hint="blank = auto"),
    ]


def visible_fields(fields):
    by_key = {f.key: f for f in fields}
    out = [by_key["source"]]
    out.append(by_key["fixture"] if by_key["source"].value == "fixture" else by_key["path"])
    out += [by_key[k] for k in
            ("sampler", "estimator", "paths", "seed", "replicate",
             "horizon", "material_horizon", "block_length")]
    return out


def run_simulation(fields):
    by_key = {f.key: f for f in fields}
    if by_key["source"].value == "fixture":
        case = fixture(by_key["fixture"].value)
    else:
        case = load_input(Path(by_key["path"].value))
    block_length = by_key["block_length"].value
    requested = block_length if block_length is not None else (7 if case.name == "tiny" else None)
    prepared = prepare_history(case.state, requested)
    bundle, matrix, summary = run_core(
        case,
        prepared,
        by_key["sampler"].value,
        by_key["paths"].value,
        by_key["seed"].value,
        by_key["horizon"].value,
        by_key["material_horizon"].value,
        by_key["replicate"].value,
        estimator=by_key["estimator"].value,
    )
    return dict(
        summary=summary,
        manifest=manifest(case, prepared, bundle, summary, by_key["estimator"].value),
        diagnostics=diagnostics(case, prepared, bundle, matrix),
    )


def run_exact():
    from dataclasses import asdict

    from ginseng.inputs import fixture as fx
    from ginseng.numerical import environment
    from ginseng.provenance import digest

    result = enumerate_exact()
    result["manifest"] = dict(
        environment=environment(),
        input_hash=digest(asdict(fx("tiny"))),
        method="independent rational enumeration",
        block_length=7,
        horizon=4,
        result_hash=digest(result),
    )
    return result


class Job:
    """Runs a blocking callable on a background thread so the UI can animate."""

    def __init__(self, fn):
        self.fn = fn
        self.result = None
        self.error = None
        self.done = False
        self.started = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.result = self.fn()
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
            self.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        finally:
            self.done = True

    @property
    def elapsed(self):
        return time.monotonic() - self.started


def money(x):
    return f"${x:,.2f}"


def fmt_value(f: Field):
    if f.kind == "choice":
        return f.value
    if f.kind == "optional_int":
        return "" if f.value is None else str(f.value)
    return str(f.value)


def bar(width, fraction):
    """Two-tone gauge string; caller colors the filled/empty spans separately."""
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(width * fraction))
    return "█" * filled, "░" * (width - filled)


def risk_tier(probability):
    if probability < 0.02:
        return "LOW RISK", P_GOOD
    if probability < 0.15:
        return "MODERATE RISK", P_WARN
    return "HIGH RISK", P_BAD


MENU = [
    ("Simulate", "configure and run a stationary-bootstrap cash simulation"),
    ("Exact (tiny fixture)", "independent rational enumeration oracle"),
    ("History", "browse previously saved runs in artifacts/tui/"),
    ("Quit", "exit ginseng tui"),
]


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.state = "menu"
        self.menu_index = 0
        self.fields = default_fields()
        self.field_index = 0
        self.editing = False
        self.edit_buffer = ""
        self.job = None
        self.job_label = ""
        self.result = None
        self.error = None
        self.message = ""
        self.history_items = []
        self.history_index = 0
        self.frame = 0
        curses.curs_set(0)
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        try:
            curses.init_pair(P_RIBBON, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(P_SELECT, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(P_ACCENT, curses.COLOR_CYAN, -1)
            curses.init_pair(P_BRAND, curses.COLOR_BLUE, -1)
            curses.init_pair(P_GOOD, curses.COLOR_GREEN, -1)
            curses.init_pair(P_BAD, curses.COLOR_RED, -1)
            curses.init_pair(P_WARN, curses.COLOR_YELLOW, -1)
            curses.init_pair(P_MUTED, curses.COLOR_WHITE, -1)
        except curses.error:
            pass
        self.stdscr.keypad(True)
        self.stdscr.timeout(80)

    # ---- low-level rendering helpers --------------------------------------
    def addstr(self, y, x, text, attr=0):
        h, w = self.stdscr.getmaxyx()
        if 0 <= y < h and 0 <= x < w:
            try:
                self.stdscr.addstr(y, x, text[: max(0, w - x - 1)], attr)
            except curses.error:
                pass

    def hline(self, y, ch="─", attr=None):
        _, w = self.stdscr.getmaxyx()
        self.addstr(y, 0, ch * w, attr if attr is not None else curses.color_pair(P_ACCENT) | curses.A_DIM)

    def ribbon(self, label):
        _, w = self.stdscr.getmaxyx()
        left = " ⟡ GINSENG "
        right = f" {label.upper()} "
        pad = max(0, w - len(left) - len(right))
        self.addstr(0, 0, (left + " " * pad + right)[:w], curses.color_pair(P_RIBBON) | curses.A_BOLD)

    def chip(self, y, x, key, label):
        self.addstr(y, x, f" {key} ", curses.color_pair(P_SELECT) | curses.A_BOLD)
        self.addstr(y, x + len(key) + 3, f" {label} ", curses.color_pair(P_MUTED) | curses.A_DIM)
        return x + len(key) + len(label) + 5

    def footer(self, chips):
        h, _ = self.stdscr.getmaxyx()
        self.hline(h - 2)
        x = 1
        for key, label in chips:
            x = self.chip(h - 1, x, key, label)

    def frame_header(self, title):
        self.ribbon(title)
        self.hline(1)

    # ---- main loop ----------------------------------------------------------
    def run(self):
        while self.state != "done":
            self.frame += 1
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            if h < MIN_H or w < MIN_W:
                self.draw_too_small(h, w)
            else:
                getattr(self, f"draw_{self.state}")()
            self.stdscr.refresh()
            if self.state == "running":
                if self.job.done:
                    if self.job.error:
                        self.error = self.job.error
                        self.state = "error"
                    else:
                        self.result = self.job.result
                        self.state = "result"
                    self.job = None
                continue
            ch = self.stdscr.getch()
            if ch == -1:
                continue
            if h < MIN_H or w < MIN_W:
                if ch == ord("q"):
                    self.state = "done"
                continue
            getattr(self, f"input_{self.state}")(ch)

    def draw_too_small(self, h, w):
        msg = f"resize terminal (need {MIN_W}x{MIN_H}, have {w}x{h})"
        try:
            self.stdscr.addstr(max(0, h // 2), max(0, (w - len(msg)) // 2), msg[: max(0, w - 1)])
        except curses.error:
            pass

    # ---- menu ----------------------------------------------------------------
    def draw_menu(self):
        self.frame_header("main menu")
        h, w = self.stdscr.getmaxyx()
        box_w = min(w - 6, 64)
        self.addstr(3, 3, "┌" + "─" * (box_w - 2) + "┐", curses.color_pair(P_ACCENT))
        self.addstr(4, 3, "│" + " stationary-bootstrap liquidity simulator".ljust(box_w - 2) + "│",
                    curses.color_pair(P_ACCENT))
        self.addstr(5, 3, "│" + " offline · reproducible · ordinary CPU".ljust(box_w - 2) + "│",
                    curses.color_pair(P_ACCENT) | curses.A_DIM)
        self.addstr(6, 3, "└" + "─" * (box_w - 2) + "┘", curses.color_pair(P_ACCENT))

        top = 8
        for i, (item, _desc) in enumerate(MENU):
            y = top + i
            selected = i == self.menu_index
            marker = "▸ " if selected else "  "
            attr = curses.color_pair(P_SELECT) | curses.A_BOLD if selected else 0
            text = f"{marker}{item}"
            self.addstr(y, 4, text.ljust(box_w - 2), attr)
        desc_y = top + len(MENU) + 1
        self.addstr(desc_y, 4, MENU[self.menu_index][1], curses.color_pair(P_ACCENT) | curses.A_ITALIC)
        self.footer([("↑↓", "move"), ("⏎", "select"), ("q", "quit")])

    def input_menu(self, ch):
        if ch in (curses.KEY_UP, ord("k")):
            self.menu_index = (self.menu_index - 1) % len(MENU)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.menu_index = (self.menu_index + 1) % len(MENU)
        elif ch in (curses.KEY_ENTER, 10, 13):
            choice = MENU[self.menu_index][0]
            if choice == "Simulate":
                self.field_index = 0
                self.state = "form"
            elif choice.startswith("Exact"):
                self.job = Job(run_exact)
                self.job_label = "exact"
                self.state = "running"
            elif choice == "History":
                self.load_history()
                self.state = "history"
            elif choice == "Quit":
                self.state = "done"
        elif ch in (ord("q"), 27):
            self.state = "done"

    # ---- simulate form ---------------------------------------------------
    def current_fields(self):
        return visible_fields(self.fields)

    def draw_form(self):
        self.frame_header("simulate")
        rows = self.current_fields()
        for i, f in enumerate(rows):
            y = 3 + i
            selected = i == self.field_index
            marker = "▸" if selected else " "
            label_attr = (curses.color_pair(P_BRAND) | curses.A_BOLD) if selected else (curses.A_DIM)
            self.addstr(y, 2, marker, curses.color_pair(P_ACCENT) | curses.A_BOLD if selected else 0)
            self.addstr(y, 4, f"{f.label:<18}", label_attr)
            if selected and self.editing:
                shown = f"[ {self.edit_buffer}▌ ]"
                value_attr = curses.color_pair(P_WARN) | curses.A_BOLD
            else:
                v = fmt_value(f)
                shown = f"‹ {v} ›" if f.kind == "choice" else (v if v else "—")
                value_attr = (curses.color_pair(P_SELECT) | curses.A_BOLD) if selected else curses.A_BOLD
            self.addstr(y, 23, shown, value_attr)
            if f.hint and selected and not self.editing:
                self.addstr(y, 44, f"· {f.hint}", curses.color_pair(P_ACCENT) | curses.A_DIM)
        run_row = 3 + len(rows) + 1
        selected = self.field_index == len(rows)
        attr = curses.color_pair(P_SELECT) | curses.A_BOLD if selected else curses.color_pair(P_GOOD) | curses.A_BOLD
        marker = "▸ " if selected else "  "
        self.addstr(run_row, 2, f"{marker}▶ RUN SIMULATION", attr)
        if self.editing:
            self.footer([("⏎", "commit"), ("esc", "cancel")])
        else:
            self.footer([("↑↓", "move"), ("←→", "change"), ("⏎", "edit/run"), ("b", "back"), ("q", "quit")])

    def input_form(self, ch):
        rows = self.current_fields()
        n = len(rows) + 1  # + Run row
        if self.editing:
            f = rows[self.field_index]
            if ch in (curses.KEY_ENTER, 10, 13):
                self.commit_edit(f)
                self.editing = False
            elif ch == 27:
                self.editing = False
                self.edit_buffer = ""
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                self.edit_buffer = self.edit_buffer[:-1]
            elif 32 <= ch < 127:
                self.edit_buffer += chr(ch)
            return
        if ch in (curses.KEY_UP, ord("k")):
            self.field_index = (self.field_index - 1) % n
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.field_index = (self.field_index + 1) % n
        elif ch in (ord("b"), 27):
            self.state = "menu"
        elif ch in (ord("q"),):
            self.state = "done"
        elif self.field_index == n - 1 and ch in (curses.KEY_ENTER, 10, 13):
            self.launch_simulation()
        elif self.field_index < len(rows):
            f = rows[self.field_index]
            if ch in (curses.KEY_LEFT, curses.KEY_RIGHT) and f.kind == "choice":
                delta = -1 if ch == curses.KEY_LEFT else 1
                idx = f.choices.index(f.value)
                f.value = f.choices[(idx + delta) % len(f.choices)]
            elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT) and f.key == "paths":
                f.value = max(1, f.value * 2 if ch == curses.KEY_RIGHT else max(1, f.value // 2))
            elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT) and f.kind in ("int", "optional_int"):
                step = 1
                base = f.value or 0
                f.value = base + (step if ch == curses.KEY_RIGHT else -step)
            elif ch in (curses.KEY_ENTER, 10, 13) and f.kind in ("int", "optional_int", "text"):
                self.editing = True
                self.edit_buffer = fmt_value(f)

    def commit_edit(self, f: Field):
        text = self.edit_buffer.strip()
        try:
            if f.kind == "int":
                f.value = int(text)
            elif f.kind == "optional_int":
                f.value = None if text == "" else int(text)
            else:
                f.value = text
        except ValueError:
            pass  # keep prior value; malformed edits are silently discarded
        self.edit_buffer = ""

    def launch_simulation(self):
        snapshot = [Field(**vars(f)) for f in self.fields]
        self.job = Job(lambda: run_simulation(snapshot))
        self.job_label = "simulate"
        self.state = "running"

    # ---- running spinner ---------------------------------------------------
    def draw_running(self):
        self.frame_header("working")
        h, w = self.stdscr.getmaxyx()
        frame = SPINNER[int(self.job.elapsed * 12) % len(SPINNER)]
        label = f"{frame}  running {self.job_label}…"
        self.addstr(4, 4, label, curses.color_pair(P_BRAND) | curses.A_BOLD)
        self.addstr(4, 4 + len(label) + 2, f"{self.job.elapsed:0.1f}s", curses.A_DIM)

        track_w = min(w - 10, 40)
        span = max(1, track_w - 6)
        period = span * 2
        pos = int(self.job.elapsed * 24) % period
        pos = pos if pos <= span else period - pos
        track = ["─"] * track_w
        for i in range(6):
            if 0 <= pos + i < track_w:
                track[pos + i] = "█"
        self.addstr(6, 4, "".join(track), curses.color_pair(P_ACCENT) | curses.A_BOLD)
        self.footer([("…", "please wait")])

    def input_running(self, ch):
        pass

    # ---- result --------------------------------------------------------------
    def draw_result(self):
        self.frame_header("result")
        r = self.result
        summary = r["summary"]
        y = 3

        def metric(label, value, attr=curses.A_BOLD):
            nonlocal y
            self.addstr(y, 4, label, curses.A_DIM)
            self.addstr(y, 40, value, attr)
            y += 1

        metric("Required liquidity reserve", money(summary["required_liquidity_reserve"]),
                curses.color_pair(P_BRAND) | curses.A_BOLD)

        prob = summary["cash_shortfall_probability"]
        tier_label, tier_pair = risk_tier(prob)
        metric("Cash shortfall probability", f"{prob:.4f}", curses.color_pair(tier_pair) | curses.A_BOLD)
        filled, empty = bar(28, prob)
        self.addstr(y, 4, filled, curses.color_pair(tier_pair) | curses.A_BOLD)
        self.addstr(y, 4 + len(filled), empty, curses.A_DIM)
        self.addstr(y, 34, tier_label, curses.color_pair(tier_pair) | curses.A_BOLD)
        y += 2

        deficit = summary["expected_max_cash_deficit"]
        metric("Expected max cash deficit", money(deficit),
               (curses.color_pair(P_GOOD) if deficit == 0 else curses.color_pair(P_BAD)) | curses.A_BOLD)
        metric("Avg deficit when short", money(summary["avg_cash_deficit_when_short"]))
        gap = summary["funding_gap"]
        metric("Funding gap", money(gap),
               (curses.color_pair(P_GOOD) if gap == 0 else curses.color_pair(P_WARN)) | curses.A_BOLD)

        y += 1
        m = r.get("manifest", {})
        if m:
            self.addstr(y, 4, "── manifest ──", curses.color_pair(P_ACCENT))
            y += 1
            candidates = ("fixture", "sampler", "estimator", "actual_n", "visible_horizon",
                          "method", "block_length", "horizon")
            shown = [k for k in candidates if k in m]
            line = "   ".join(f"{k}={m[k]}" for k in shown)
            self.addstr(y, 4, line, curses.A_DIM)
            y += 1
        if self.message:
            self.addstr(y + 1, 4, self.message, curses.color_pair(P_GOOD) | curses.A_BOLD)
        self.footer([("s", "save json"), ("b", "menu"), ("q", "quit")])

    def input_result(self, ch):
        if ch == ord("s"):
            self.save_result(self.result)
        elif ch in (ord("b"), 27, curses.KEY_ENTER, 10, 13):
            self.message = ""
            self.state = "menu"
        elif ch == ord("q"):
            self.state = "done"

    def save_result(self, payload):
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ARTIFACT_DIR / f"{stamp}.json"
        out.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        self.message = f"✓ saved {out}"

    # ---- error -----------------------------------------------------------
    def draw_error(self):
        self.frame_header("error")
        self.addstr(3, 4, "✕ the run failed", curses.color_pair(P_BAD) | curses.A_BOLD)
        for i, line in enumerate(self.error.splitlines()[:12]):
            self.addstr(5 + i, 4, line, curses.color_pair(P_BAD))
        self.footer([("b", "back"), ("q", "quit")])

    def input_error(self, ch):
        if ch in (ord("b"), 27, curses.KEY_ENTER, 10, 13):
            self.state = "form" if self.job_label == "simulate" else "menu"
        elif ch == ord("q"):
            self.state = "done"

    # ---- history -----------------------------------------------------------
    def load_history(self):
        self.history_items = []
        if ARTIFACT_DIR.exists():
            for p in sorted(ARTIFACT_DIR.glob("*.json"), reverse=True):
                try:
                    self.history_items.append((p, json.loads(p.read_text())))
                except (ValueError, OSError):
                    continue
        self.history_index = 0

    def draw_history(self):
        self.frame_header("history · artifacts/tui")
        if not self.history_items:
            self.addstr(3, 4, "No saved runs yet — save one from a result screen with 's'.", curses.A_DIM)
        for i, (path, payload) in enumerate(self.history_items):
            selected = i == self.history_index
            marker = "▸ " if selected else "  "
            attr = curses.color_pair(P_SELECT) | curses.A_BOLD if selected else 0
            m = payload.get("manifest", {})
            s = payload.get("summary", {})
            reserve = money(s["required_liquidity_reserve"]) if "required_liquidity_reserve" in s else "-"
            label = (
                f"{marker}{path.name}   {m.get('fixture', m.get('method', '?')):<12}"
                f"{m.get('sampler', ''):<8}reserve={reserve}"
            )
            self.addstr(3 + i, 4, label, attr)
        self.footer([("↑↓", "move"), ("⏎", "view"), ("b", "back"), ("q", "quit")])

    def input_history(self, ch):
        if not self.history_items:
            if ch in (ord("b"), 27, ord("q")):
                self.state = "menu"
            return
        if ch in (curses.KEY_UP, ord("k")):
            self.history_index = (self.history_index - 1) % len(self.history_items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.history_index = (self.history_index + 1) % len(self.history_items)
        elif ch in (curses.KEY_ENTER, 10, 13):
            self.result = self.history_items[self.history_index][1]
            self.job_label = "history"
            self.message = ""
            self.state = "result"
        elif ch in (ord("b"), 27):
            self.state = "menu"
        elif ch == ord("q"):
            self.state = "done"


def _main(stdscr):
    App(stdscr).run()


def main(argv=None):
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    # A stray warnings.warn() writes straight to the terminal and corrupts the
    # curses screen; the interactive UI has no channel to show it anyway.
    warnings.simplefilter("ignore")
    curses.wrapper(_main)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
