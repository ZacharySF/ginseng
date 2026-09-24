# Ginseng — reproducible liquidity-risk simulation

A stationary-bootstrap cash-flow engine with exact small-case validation and measured Monte Carlo versus scrambled-Sobol comparisons.

The offline engine reports **required liquidity reserve ($)**, **cash-shortfall probability (0–1)**, and **expected maximum cash deficit ($, averaged over all paths)**. It uses the existing end-of-day financial model and runs on an ordinary CPU without an account, server, paid data feed, or optimizer.

```sh
uv sync --locked
uv run ginseng simulate --fixture canonical --sampler sobol --paths 2048 --seed 42 --horizon 30 --out artifacts/sobol.json
```

Python 3.12 is required. The canonical history is frozen at synthetic-data seed **20260911**, independently of `--seed`. Sobol requires a power-of-two path count; use 1,024 or 2,048 instead of 2,000.

Measured tiny-fixture RMSE at N=16,384 over 32 independent replicates, against the independent exact 81-sequence distribution:

| Target | Fixed MC | Scrambled Sobol |
|---|---:|---:|
| Reserve ($) | 0 | 0 |
| Failure probability | 0.003251 | 0.000385 |
| Mean maximum deficit ($) | 0.19456 | 0.01746 |

**The result is mixed:** Sobol met the tiny failure-error target at 2.34× lower measured cost than the best ordinary baseline. Ordinary MC was cheaper for several reserve/easy targets. Some larger-case comparisons remain reference-limited. A zero reserve RMSE can reflect a probability plateau, not convergence of the entire distribution. See [all measured results](docs/benchmark-results.md), [exact definitions and validation](docs/numerical-model.md), [methodology](docs/benchmark-methodology.md), and the [executed notebook](notebooks/numerical-validation.ipynb).

## Offline commands

```sh
uv run ginseng simulate --fixture canonical --sampler mc --paths 2048 --seed 42 --horizon 30 --out artifacts/mc.json
uv run ginseng exact --fixture tiny --out artifacts/exact.json
uv run ginseng simulate --input examples/tiny-history.json --block-length 7 --sampler sobol --paths 2048 --out artifacts/local.json
uv sync --locked --extra dev
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --no-sync ginseng benchmark --config benchmarks/standard.json --out artifacts/standard
uv run --no-sync ginseng report --input artifacts/standard --out artifacts/report
uv run --no-sync python notebooks/execute.py
```

`python -m ginseng` is equivalent to the installed command. Omit `--out` for simulation/exact JSON on stdout; diagnostics use stderr and failures return nonzero status. `uv sync --extra tui --extra optimization --extra research && uv run ginseng tui` opens the [soft club research workspace](docs/tui-studio.md): a Gen-X soft club terminal workspace with simulation/exact dashboards, 27 research recipes, funding and portfolio analysis, personal forecasts, engine replay, cash-risk heatmaps, a notebook and JSON/CSV export. One fixed near-black theme covers a dense instrument layout: a narrow navigation rail, central canvas and workflow table, right-hand session readouts, silver text and restrained mint accents. Its portrait viewer (`Ctrl+W`) displays the sole supplied cyberpunk artwork, preserving every original glyph. Cash-signal sparklines, funding bars and selectable research scatter plots add more ways to inspect each run. Press `Ctrl+P` to search every workflow. `--material-horizon 60 --horizon 30` predeclares a plan whose earlier days remain stable when the visible horizon grows. New bundles reject extensions beyond that plan. `--sampler legacy_mc` exposes the original generator for comparison; existing HTTP callers retain it by default.

The complete [local-input example](examples/tiny-history.json) records explicit joint daily rows, declared history boundaries, separate opening cash and one-indexed future bills. Missing dates, duplicate rows, negative spending and nonfinite values are rejected. No observations are invented between history end and the opening date.

The `research` extra supplies plotting/notebook tools; `app` supplies API dependencies; `optimization` supplies CVXPY. The `dev` extra includes all three plus pytest. A minimal core installation needs none of those extras. Without research dependencies the report command explains how to install them; without CVXPY the existing optimizer reports `cvxpy_unavailable`.

## Verification and provenance

Untouched baseline: **227 tests passed**. Updated suite: **255 tests passed**, with the same two dependency deprecations. All five existing frontend suites passed (**22 tests**), the Svelte type check reported zero errors/warnings, and the production build passed. A separately installed wheel ran outside the repository without app/optimizer/research dependencies; SciPy 1.14.1 compatibility and missing-dependency behavior were exercised. The standard run completed **3,136 observations**, all three million-path references, and report/notebook execution. [Implementation and verification record](docs/implementation-notes.md).

```sh
uv sync --locked --extra dev
uv run --no-sync pytest -q
bun run --cwd web check
bun run --cwd web build
```

Saved [observations](artifacts/standard/observations.json), [manifest](artifacts/standard/manifest.json), [configuration](benchmarks/standard.json) and [report assets](artifacts/report/results.md) identify source/input hashes, seeds, model settings, dependency versions, thread settings and timing boundaries. Regenerate reports without rerunning simulations. Published fixtures are synthetic; temporary large cash arrays are omitted.

More paths improve numerical precision under the chosen model. They do not create historical evidence or establish real-household survival probabilities. The personal 80% terminal-flow backtest and separate reserve calibration remain distinct from these numerical tests; see the [model card](docs/model-card.md).

## Optional application

Ginseng began as a HackRice 16 cash-planning app for people with uneven income. Its authenticated SvelteKit/Supabase application, scheduled and assumptions-based personal forecasts, funding policies, and CVaR optimizer remain available. The original usage and setup documentation is preserved in [application.md](docs/application.md). No live money movement is performed.

Existing contributors' work is retained. Codex implemented this numerical release, verification and measurement at the user's request; see the [change record](docs/implementation-notes.md).

### Experimental conditional estimator

The offline CLI supports `--estimator initial-block-cmc` for historical cash-failure probability with MC or Sobol. See the [method, validation and reproduction commands](docs/conditional-monte-carlo.md) and [measured comparison](artifacts/conditional/results.md). The path estimator remains the default.

### Stop Monte Carlo at a requested numerical precision

`uv run ginseng precision --fixture tiny --estimator initial-block-cmc --absolute-error 0.005` returns a cash-failure estimate and a checkpoint-valid numerical interval, stopping when the error target is met or the path budget is exhausted. See the [method and CLI contract](docs/precision-stopping.md) and [measured stopping results](artifacts/precision/results.md).

### Website risk laboratory

Cash events now includes optional precision refinement and an interactive 3D cash/time sensitivity explorer for historical forecasts. Rotate between shortfall probability and expected worst deficit, select extra opening cash, or inspect exact values in a table. See the [API, model definitions and browser verification](docs/risk-explorer.md).

The demo **Research** page adds a [liquidity-aware portfolio frontier](docs/portfolio-frontier.md): explore hypothetical allocations by expected return, volatility and tail loss at the first cash-buffer breach. Inspect portfolio weights in 3D, compare independently simulated estimates and export the experiment. Start with **Load repair case**. Demo asset returns are synthetic.

### Prepared execution engine and offline replay

The cash engine supports request-scoped reuse, batched chart quantiles, bounded summary execution, and an optional C++ backend. Existing sampler/estimator commands remain unchanged. `auto` uses NumPy; native execution is explicit.

```bash
uv sync --locked --extra dev --extra native-build
uv build native --wheel --out-dir /tmp/ginseng-wheels
uv pip install --no-deps /tmp/ginseng-wheels/ginseng_native-*.whl
uv run --no-sync ginseng engine inspect
uv run --no-sync ginseng engine replay examples/engine/canonical --backend native --workers 2
```

See [the engineering report](docs/quant-engineering.md) for capture/diff commands, ownership and memory contracts, installation verification, tests, raw benchmarks, small-workload regressions and measured native tradeoffs.

### Decision Verification Lab (Prompt A)

Independently check executable funding plans, distinguish mean dollar-day limits from cash-failure policy, evaluate frozen actions on independent MC futures, and replay captured inputs offline. The existing optimizer and execution backends are reused.

```bash
uv run --no-sync ginseng decision run --fixture canonical --paths 2000 --validation-paths 4000 --replications 3 --output /tmp/ginseng-decision-demo
uv run --no-sync ginseng decision replay /tmp/ginseng-decision-demo
uv run --no-sync ginseng decision replay examples/decision-verification/canonical
```

See the [audit](docs/decision-verification-audit.md) and [design, measured results, commands and limitations](docs/decision-verification.md). Numerical verification and simulator validation do not establish real-world safety or forecast calibration.

### Precision-Controlled Failure Estimation (Prompt B)

The existing risk panel and `ginseng precision` now accept numerical error/confidence targets, observation and resource limits, and expose precision, exhaustion and cancellation outcomes. Exact synthetic captures replay offline with `ginseng precision-replay examples/precision-b/path`. See the [implementation, method, commands and limitations](docs/precision-b.md), [audit](docs/precision-b-audit.md), and [512-run fixed/adaptive evidence](artifacts/precision-b/diagnostics.md). This workflow reuses the existing MC/conditional-MC engine; the separate Prompt C experiment is described below.

### Two-decision funding experiment (Prompt C)

Run `ginseng two-decision run --output /tmp/ginseng-two-decision`, then `ginseng two-decision replay /tmp/ginseng-two-decision`. The same experiment and replay are available in Quant Studio. It compares static, nonanticipative review and infeasible hindsight policies under a separate bounded synthetic model, with independent frozen-policy validation. See [information/accounting contracts, results and limits](docs/two-decision.md). Existing production funding recommendations remain on the single-decision model.
