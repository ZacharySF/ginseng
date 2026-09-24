# Ginseng / soft club

Launch the terminal workspace:

```sh
uv sync --locked --extra tui --extra optimization --extra research
uv run --no-sync ginseng tui
```

The TUI has one fixed dark Gen-X young-adult contemporary / soft club identity:
near-black surfaces, silver text, restrained mint accents and fine rules.
The layout uses a narrow navigation rail, a central workbench, a right-hand stack of
simulation/exact readouts and a bottom session log. Home pairs a decorative wireframe
water study (explicitly not model output) with a keyboard-operable workflow table.
Research places evidence beside findings; simulation groups source and method controls;
results lead with cash-path and draw-bundle canvases. The design extends across
startup, home, forms, the research editor, charts, tables, archives and command search.
There is no theme selector or palette shortcut. `--coord` has been removed;
`GINSENG_COORD` does not change the workspace.

`Ctrl+W` opens the portrait, `Ctrl+P` searches workflows, `Ctrl+R` opens research, `Ctrl+B` toggles the navigation and inspector, and Escape
returns home. Small terminals collapse decoration; `GINSENG_MOTION=0` disables
motion. The fullscreen command clears `NO_COLOR` and defaults `COLORTERM` to
`truecolor`. Direct application tests also cover monochrome rendering.

## Original artwork

The supplied **cyberpunk portrait** is the sole artwork. Its original glyphs remain in
`engine/ginseng/art/cyberpunk.txt`, and the ASCII boot wordmark is unchanged.
The inspector, portrait viewer and boot all show the same artwork. Alternate assets,
the picker, cycling shortcut and art-selection commands have been removed.

Artwork uses the same dark aquatic palette as the rest of the workspace. It renders at its original character size in scrollable panels; no Nerd Font or terminal image
support is required. Use a font with Braille glyphs. High-risk results still reduce
decorative clutter, and risk states retain explicit labels alongside their colors.

Visual direction: [CARI’s Gen X Soft Club archive](https://cari.institute/aesthetics/gen-x-soft-club).
The earlier standalone `ginseng_rice` palette demos remain separate from the fixed
application theme, defined in `engine/ginseng/ginseng_rice/softclub.toml`.

## More ways to see a run

Below the simulation/exact dashboard, **Cash signals** plots daily p5 cash, median cash and the p95–p5 spread. Each sparkline reports its own dollar range; rows use independent scales. Negative balances carry the shortfall color. **Funding / cost & residual risk** compares expected dollar costs on a common zero-based scale, with each candidate's availability day and remaining shortfall probability. Runs without funding candidates explicitly say so. Both views work on saved dashboards as well as new runs.

Research results add **Data scope** below the selected table. Choose any numeric x and y columns to make a Braille scatter plot. The default x axis is row number, preserving the table's order; select a day/cash/etc. column for numeric spacing. Missing values, booleans and nonfinite values are omitted, with the plotted pair count shown. Dots are observations, with no interpolated curve or uncertainty claim. Tables over 5,000 rows are explicitly labeled as previews; the original tables and full exports remain available. Text-only tables hide the plot. The existing atlas, cash-path fan, histogram and path surface remain available.

## Workflows

The original simulation form retains fixture/file input, MC/Sobol/legacy sampling, conditional estimation, seeds, replicates, visible/material horizons and block length. Exact enumeration and the original cash-path dashboard remain available. Simulation archives now preserve the engine result and its manifest as well as dashboard data; older archives still open.

The research studio exposes 27 recipes:

| Area | Recipes and engine coverage |
|---|---|
| Numerics | Precision stopping; cash-buffer atlas; tail-risk microscope; sampler tournament |
| Planning | Funding candidates and policy ranking; CVaR optimizer; drought entropy stress; funding frontier/shadow checks/holdout; account withdrawal ledger |
| Portfolio | Tax-lot liquidation and covariance; liquidity-aware allocation frontier with independent evaluation |
| Validation | Walk-forward calibration; persistence sensitivity; outer-bootstrap reserve uncertainty |
| Personal | Scheduled, historical and assumptions-based forecasts; scenario overrides; history backtests; historical precision/surface exploration |
| Engineering | Numerical benchmark/report; native inspection; capture/replay/diff; quant-engineering performance suite |
| Connected | Every application API route, including workspace and finance read/save, scenario/analyses, provider data and assistant chat |

Use **Quick setup** for common source and sampling fields, then apply those values to the recipe. The JSON recipe exposes the remaining parameters. A local input path takes precedence over the fixture. Optional `opening_cash` replaces the opening balance with a separately recorded transfer. `obligations: null` retains fixture/file bills; an explicit list replaces them. Bills use `id`, `label`, dollar `amount` and one-indexed `due_in_days`. The portfolio-frontier default includes the canonical synthetic repair schedule so it has cash-pressure scenarios to inspect.

**Run experiment** starts an isolated process. You can continue browsing and editing recipes while it runs. For precision runs (including personal numerical precision), **Cancel** requests cooperative stopping between batches and retains completed observations, the last certified interval and a `cancelled` result in the notebook. Preparation and a running batch are not preempted. Other recipes retain process termination; closing the application also cleans up running subprocesses. One research experiment runs at a time. Missing inputs, unavailable solvers, unsupported stress views and engine errors are shown explicitly.

Results contain a scalar summary, selectable tables, and the complete JSON output. The atlas adds a cash/time probability heatmap; the table gives its exact values. **JSON** exports the complete experiment, inputs and environment; **CSV** exports the selected table, including rows beyond the 5,000-row display preview. Files go to `artifacts/tui/notebook/` with unique timestamps. The Notebook tab revisits session runs or imports saved experiments, restoring their recipes for rerunning. Results remain in memory until explicitly exported.

**Pin** retains a baseline. **Compare** displays current-minus-baseline scalar metrics for another run of the same experiment. These are descriptive differences, not significance tests; compare the recorded recipes before attributing a change to one assumption.

## Numerical meaning

The new tail microscope computes empirical cash-deficit VaR/CVaR, terminal cash quantiles, first-negative-day probabilities and peak-to-trough cash drawdowns (including opening cash). Dollar cash-flow drawdowns are not investment returns, so this view does not invent Sharpe ratios or annualize them.

The sampler tournament compares independent replicates. RMSE is shown only when the tiny fixture, four-day horizon, seven-day block length, opening cash and bills match the exact oracle. Other cases show replicate dispersion. One replicate has no sample standard deviation.

The atlas reuses paths across cash offsets and measures **ever** falling below zero by each day. Extra cash is available from day one; funding costs are excluded. It offers no simultaneous interval guarantee. Precision intervals describe Monte Carlo numerical uncertainty; outer-bootstrap uncertainty and historical calibration are separate recipes.

Funding adapters predeclare the longest credit/settlement horizon before sampling, preserving the initial draw prefixes when evaluating extended plans. The studio limits individual sample allocations to ten million path-days, including funding extensions; the portfolio engine retains its own limits. Long benchmarks have a one-hour subprocess timeout and can be cancelled earlier. Existing output directories are rejected for engineering exports to preserve prior runs.

## Personal and connected work

Offline personal recipes accept a canonical `FinanceWorkspace` JSON file, including `accounts`, `bills`, `revision`, `as_of`, `currency` and `inputs`. The workspace's `inputs.mode` chooses scheduled, historical or assumption forecasting; the engine validates its data requirements. `overrides` uses the existing `ScenarioOverrides` contract. The local version-1 daily-history input format is a different contract, used by fixture/input recipes.

For account-backed features, run the existing authenticated application engine and set:

```sh
export GINSENG_API_URL=https://your-engine.example
# Supply your existing access token through GINSENG_API_TOKEN.
uv run --no-sync ginseng tui
```

The local default is `http://127.0.0.1:8000`; remote connections require HTTPS. Credentials are read from the environment, omitted from experiment parameters, and never forwarded through redirects. **Connected application** has explicit route presets. **API contracts** fetches `/openapi.json` for complete request schemas. Nothing connects at startup.

GET reads a workspace; selecting its matching PUT preset populates the editable save body from the last fetched snapshot and carries `revision` into `expected_revision`. Review it before running: PUT saves the complete snapshot. Without a fetched snapshot, provide all required fields; the server enforces revision conflicts. Forecasts and analyses remain read-only. Provider features require the server's provider configuration; assistant chat requires its configured model and returns the complete NDJSON event record and assembled reply. Account data is written locally only when you explicitly export it.

## Verification

The studio tests exercise real precision parity, oracle comparison, monotonic cash sensitivity, cash-tail definitions, funding draw-prefix preservation, immutable scenario overrides, personal forecasts, credential redirect handling, cancellation, export/import, input errors and compact layouts. Snapshot tests cover the home screen, atlas, existing simulation/exact views and monochrome rendering. The Sakura palette passes the existing contrast and color-vision checks.

## Prompt B in the TUI

Open **Quant Studio → Precision stopping** (or use Ctrl+P). Its editable recipe now includes `chunk_size`, `time_limit_seconds`, `memory_budget_bytes`, `stop_when_precise`, `backend`, `workers`, `capture_path`, and `allow_personal_capture`, alongside the error, confidence, estimator and sample cap. `batch_size` defines the first declared checkpoint; `chunk_size` controls execution without adding statistical looks. Set `stop_when_precise: false` for a fixed-budget comparison. The existing CMC recipe default is retained.

For example, merge these values into the recipe and run:

```json
{
  "fixture": "tiny",
  "horizon": 4,
  "estimator": "path",
  "max_paths": 4096,
  "batch_size": 256,
  "chunk_size": 257,
  "absolute_error": 0.05,
  "confidence": 0.95,
  "time_limit_seconds": 15,
  "memory_budget_bytes": 134217728,
  "capture_path": "artifacts/tui/precision-example"
}
```

Choose a new destination each time. A local history file requires `allow_personal_capture: true`; it is never enabled implicitly. Results show the strict cash-failure estimate, numerical interval, completion/exhaustion/cancellation status, completed observation count and certified checkpoint count. Capture locations appear in the summary. If cancellation occurs before any observations, the result remains available, but capture is explicitly unavailable and no artifact directory is created.

Choose **Replay precision evidence** and set `input` to the capture directory. Backend, worker count and replay memory budget are editable. The result explicitly reports **MATCH** or **MISMATCH**, with differences in the JSON; replay uses the existing exact-input engine artifact offline. The preset `examples/precision-b/path` is a ready-to-run synthetic example. Generic **Replay artifact** remains the separate prepared-engine replay action.

**Personal numerical explorer** also exposes confidence, estimator and time/memory limits for `action: "precision"`, with the existing API bounds. These numerical intervals measure fixed-simulator uncertainty, not real-world forecast calibration.

Integration validation: `.venv/bin/pytest -q engine/tests/test_studio.py engine/tests/test_precision_b.py engine/tests/test_precision.py engine/tests/test_tui_snapshots.py` — **69 passed**, including **6 terminal snapshots**, with two existing dependency deprecations. Tests execute the real TUI subprocess capture/replay and immediate cooperative cancellation, replay a partially completed cancelled run, verify personal-input consent and preserve the existing non-precision process cancellation. [Raw results](../artifacts/precision-b/tui-integration-tests.txt).

## Prompt C in the TUI

**Two-decision funding experiment** compares static, observation-based review and explicitly infeasible hindsight policies on a small synthetic tree. The recipe exposes training/validation counts, replications, seed, settlement delay, fixed sale fee and the dollar-day liquidity penalty. `capture_path` optionally publishes exact offline evidence. Results include comparison and stability tables, review observations/actions, execution prices, and the full daily cash/debt/holdings/reserve ledger. **Replay two-decision experiment** checks the captured inputs and results; its default is `examples/two-decision/canonical`. This is separate from production recommendations. [Model, measured outcomes, limits and commands](two-decision.md).
