# ginseng_rice

Coords and a finished dashboard for the Ginseng TUI. A coord is one complete outfit: 22 color roles, a border and glyph kit, transition settings and voice lines, stored as a TOML file and turned into a Textual theme at startup. The dashboard draws one engine run: reserve card, cash-path fan chart, trough histogram, funding options, ledger and a voice line.

The integrated TUI has sixteen coords, an ASCII wardrobe, cash-signal and funding charts, and research scatter plots. See [the TUI guide](../../../docs/tui-studio.md) for controls, terminal skins and Unixporn references. Palette lint checks contrast, color-vision separation and glyph widths for every coord.

## Run it

```bash
uv run python -m ginseng.ginseng_rice.dashboard.app   # t: next coord   1/2/3: calm/thin/short   q: quit
uv run pytest engine/ginseng/ginseng_rice/tests
uv run python -m ginseng.ginseng_rice.lint
```

The dashboard app runs on `dashboard/fixture.py`, a seeded toy simulation. Its numbers are not Ginseng's.

## What's inside

| Path | What it does |
|---|---|
| `coords/*.toml` | Sixteen coords. The original eight have OKLCH specs in `tools/palettes.py`; later palettes are authored in TOML. |
| `tokens.py` | Loads a coord, fails if a role is missing, builds a Textual `Theme` with `$g-*` variables. |
| `dress.py` | `Dressable` mixin: registers coords, switches between them, runs the ornament budget. |
| `henshin.py` | Transition through in-between themes mixed in OKLab, cleaned up afterward. |
| `budget.py` | Ornament budget: decoration shrinks as shortfall odds grow, with hysteresis. |
| `dashboard/` | `DashboardData` model, `Dashboard` widget, charts, panels, fixture, demo app, layout. |
| `terminal.py` | Asks the terminal for its background color and picks a light or dark coord. |
| `skins.py`, `skins/` | Ghostty and kitty themes generated from the coords, plus a home-manager example. |
| `widgets.py` | `Trim`, `Soroban` (bead gauge), `Hanko` (済 settled, [未] scheduled, 見込 estimate). |
| `rice.tcss` | Role classes and ornament-budget rules, all prefixed `g-`. |
| `lint.py` | Contrast, color-blind separation, glyph widths, voice placeholders. Exits 1 on failure. |
| `demo.py`, `demo.tcss` | Smaller fitting-room demo. |
| `tests/` | Behavior tests and per-palette snapshot SVGs in `tests/__snapshots__`. |
| `tools/` | OKLCH palette specs, audit, and a writer that pushes specs into the TOMLs. |

## The coords

| Coord | Paper | Ink | Wear it for |
|---|---|---|---|
| seifuku 制服 | #F8FAFE | #0100F4 | README screenshots, daylight, print. Brand ink plus one spot red. |
| gothpunk ゴスパン | #0D0B11 | #E9E6EF | Late sessions. The mascot's fit; crimson only when money runs out. |
| dojima 堂島 | #0F1D38 | #F1EBDE | Chart review. Indigo, vermilion seals, beads for days. |
| techwear テック | #090A0C | #CBCED1 | Triage. Tonal black, one signal orange, dense. |
| mori 森ガール | #141F16 | #E6E1D1 | Daily driver. Low chroma for long sessions. |
| decora デコラ | #FFF3FA | #352053 | Good months. Maximal, and the first to undress when numbers turn. |
| stage ヴィジュアル系 | #000000 | #FFFFFF | Projectors and demo day. Okabe–Ito colors, safest for color-blind viewers. |
| rococo ロリータ | #FAF3E3 | #4A291A | Month-end review. Lace edges, courteous voice. |
| gosurori ゴスロリ | #01050F | #E0E9F1 | Gothic atelier. |
| sakura 桜 | #14111F | #F4EAF5 | The default rose-and-lavender research atelier. |
| moonrise 月光 | #101426 | #F4EAF5 | Lunar gold and magical-girl starlight. |
| evangelion 初号機 | #14101F | #F4EAF5 | Violet mecha armor and acid lime. |
| miku ミク | #0C1B22 | #F4EAF5 | Teal digital-idol studio. |
| catppuccin 猫 | #1E1E2E | #F4EAF5 | Mocha, mauve, peach and a neko cafe. |
| akira 新東京 | #191416 | #F4EAF5 | Coral neon over dark city streets. |
| lain 接続 | #0C1918 | #F4EAF5 | Phosphor-green wired terminal. |

## Ornament budget

| Shortfall odds | Level | What's left |
|---|---|---|
| under 5% | 3 | everything |
| under 25% | 2 | `g-ornament-3` hidden |
| under 40% | 1 | `g-ornament-2` and `-3` hidden |
| 40% and up | 0 | trims hidden, plain titles and glyphs, heavy ink borders, same plain sentence in every coord |

Bad news drops the level immediately. Good news has to clear the threshold by 2 percentage points first, so odds hovering around 25% don't make the screen flicker.

## What the lint enforces

- Every text role reaches 4.5:1 contrast on both `paper` and `panel`.
- `safe`, `thin` and `short` stay at least 0.09 apart in OKLab under simulated deuteranomaly, protanomaly and tritanomaly. The 0.09 is a house rule, not a standard.
- No double-width glyphs in `[borders]` or `[glyphs]`, and no ambiguous-width glyphs outside box drawing and block elements (U+2500–U+259F).
- Voice lines use only `{rlr} {c0} {c0_name} {C0_NAME} {sp} {sol} {sol1} {h}`.

## Character widths

A terminal draws text on a grid of cells. The app and the terminal each decide how many cells a character takes, and when they disagree everything to its right shifts.

- **Neutral, one cell everywhere:** ✦ ✧ ✿ ⋈ ⌜ ⌝ ▸ ▰ ▱ ◠ ◡ ◉ ◌ ⬥ ⬦ ▮ ▯ ⸸ ⸙ ❦ ❧ ✓ ✗ ✕, braille, and the minus sign − (U+2212).
- **Ambiguous, one cell by default and two where the terminal treats ambiguous as wide:** ★ ♡ ● ○ ■ □ ◆ ◇ • · … – —, Nerd Font icons, nearly all box drawing and blocks, and every symbol a quant label wants: σ μ ρ Δ ∑ ± × ≈ √ ° ∞ ≤ ≥ →.
- **Always two cells:** 済 未 見込 and all CJK. Measure with `rich.cells.cell_len`, never `len`.

Keep the terminal's ambiguous-width setting on narrow, use σ and Δ freely in labels, and pick decoration from the neutral list.

## Found while testing

- Textual calls `get_theme_variable_defaults()` inside `App.__init__`, before your own attributes exist, so `dress.py` loads coords at module level.
- A border title like `[ Reserve ]` is parsed as a markup tag and disappears, even after `escape()`. Titles are set as `Content` objects.
- Sparse `░` dots in a pale band color are nearly invisible on light coords. Bands are solid background fills with the coord's texture glyph drawn on top.
- A theme swap plus full refresh averaged 58.7 ms headless on the build machine, so transitions default to 4 frames. `GINSENG_MOTION=0` switches instantly.
- Transition themes are unregistered after each switch, otherwise they pile up in the command palette.
- Textual reads `NO_COLOR` at startup and renders monochrome, so every state also carries a word or glyph.
- Light coords keep text colors near OKLCH lightness 0.40–0.55 to hold 4.5:1, which leaves little room to separate states by lightness. Decora and rococo failed the color-blind check until `safe` moved toward blue.

## Changing a coord

Quick fix: edit the hex in the TOML and run the lint. Perceptual change: edit the OKLCH triple in `tools/palettes.py` (L lightness 0–1, C chroma, h hue in degrees), then from `tools/` run `python write_coords.py` and `python audit.py`. After any coord change, regenerate skins with `python -m ...ginseng_rice.skins` and review snapshot diffs.

## Terminal skins

`skins/ghostty/ginseng-<coord>` goes in `~/.config/ghostty/themes/`, then set `theme = light:ginseng-seifuku,dark:ginseng-mori`. `skins/kitty/ginseng-<coord>.conf` can be pulled in with `include`. ANSI red, green and yellow carry short, safe and thin, so shell tools agree with the TUI. `skins/home-manager.nix` is an unevaluated example.

## Wired into the repo

`dashboard/adapter.py: from_engine()` maps a real `ginseng.tui` simulate/exact run onto `DashboardData` -- see its module docstring for exactly which fields are the engine's own numbers as-is (`shortfall_p`, `reserve_to_add`) versus new reductions of the engine's path matrix computed with `ginseng.risk`'s own primitives (`cvar95_trough`, `deficit_dollar_days`, `solvent_days`, `bands`). Funding options call `ginseng.funding.build_candidates`/`evaluate_plan` directly and are only available for simulate runs (the exact oracle has no `FinancialState`). `engine/ginseng/tui.py`'s `GinsengApp` mixes in `Dressable`, dresses with `pick_coord()` at startup, and shows every run through `Dashboard`.

## Ricing guide

See [Anime rice in the TUI guide](../../../docs/tui-studio.md#anime-rice) for the integrated wardrobe and matching terminal skins.
