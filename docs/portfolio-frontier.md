# Portfolio frontier laboratory

The demo **Research** page (`/demo/research`) asks: **how does an allocation behave when bank cash first comes under pressure?** This portfolio experiment complements the existing Cash events 3D surfaces.

Each point allocates across VTI, VXUS and a hypothetical zero-yield CASH sleeve. These ticker labels use **generated demonstration returns, not actual ETF market history**. Allocations are hypothetical and do not place trades.

## Why three dimensions help

| Axis | Quantity | Preferred direction |
|---|---|---|
| X | Standard deviation of portfolio return over the forecast horizon | Lower |
| Y | Mean portfolio return over that same horizon | Higher |
| Z | 95% expected shortfall of portfolio loss at the first cash-buffer breach, conditional on a breach occurring | Lower |

Two portfolios can have similar average returns and volatility while behaving differently when cash is needed. Rotating the cloud separates points that overlap in a two-axis projection. Selecting a point exposes its weights and exact metrics.

The third metric can be redundant for some histories. In the canonical repair run inspected during development, it added no nondominated allocations beyond return and volatility alone. A [deterministic mechanism test](../engine/tests/test_frontier.py) shows where it matters: an asset with equal mean return and lower terminal volatility loses 50% at cash pressure, while another preserves its value then. Including pressure loss retains both candidates. This demonstrates the mechanism, not additional optimal allocations in the demo fixture.

Coordinates are return fractions shown as percentages, without annualization. Z measures portfolio loss, not the dollar funding gap or shortfall probability.

## Use the demo

1. Open `/demo/research` after signing in.
2. Use a 30-day horizon and **Load repair case** to add the $1,500 day-3 deposit and $3,000 day-17 balance. The bills make a cash-pressure comparison more informative.
3. Run the portfolio experiment. Drag the plot to rotate, use **Reset camera** to restore the view, and select a point for its weights and metric details.
4. Compare discovery results with the independent numerical holdout. Export JSON to inspect the underlying values and provenance outside the chart.

The existing `/demo/future` surfaces vary extra **bank cash**. Here CASH is a **portfolio sleeve**: changing its weight does not alter bank cash, bills or pressure events. It changes the portfolio return at those events, keeping all allocations comparable on the same scenarios.

## Calculation

The stationary bootstrap resamples cash flows and per-asset returns using the same historical day indices. This preserves their joint relationship within the generated history. Known bills remain on their forecast dates.

For scenario `i`, let `B[i,t]` be bank cash after forecast day `t`, including opening cash and the active obligations. With operating buffer `b`, define:

```text
tau[i] = first forecast day t for which B[i,t] < b
```

Only scenarios with a breach enter the conditional distribution. Equality with the buffer survives. A path contributes its **first** breach day, even if cash later recovers or falls further. A positive buffer means this event can precede negative bank cash.

Let `r[i,a,t]` be the sampled simple return for asset `a`. A static, buy-and-hold allocation `w` has return through day `t`:

```text
R[i,a,t] = product(1 + r[i,a,s], s=1..t) - 1
portfolio_return[i,t] = sum(w[a] * R[i,a,t], a)
w[a] >= 0; sum(w) = 1
```

The CASH column is zero. X and Y use `portfolio_return[i,H]` over all scenarios; standard deviation uses `ddof=1`. Z uses signed losses `L[i] = -portfolio_return[i,tau[i]]` over pressure scenarios. Gains remain negative losses.

For `m` equally weighted pressure scenarios and `alpha = 0.95`, empirical expected shortfall is:

```text
ES_alpha(w) = min_eta [ eta + sum(max(L[i] - eta, 0)) / ((1-alpha) * m) ]
```

This averages the worst 5% of empirical losses, using fractional boundary mass and handling ties. The convex CVaR/expected-shortfall formulation follows [MOSEK's risk-measure documentation](https://docs.mosek.com/portfolio-cookbook/riskmeasures.html#conditional-value-at-risk). Conditioning on the first cash-buffer breach is Ginseng's adaptation.

## Candidate search and the displayed frontier

The engine combines 128 Dirichlet-sampled allocations with current, equal-weight and single-asset anchors. It attempts 15 convex optimizations with different weights on normalized horizon variance, negative expected return and pressure ES. Variance optimization and displayed volatility use the same empirical covariance. [MOSEK's mean–variance description](https://docs.mosek.com/portfolio-cookbook/markowitz.html) supplies the conventional return-and-risk foundation.

The highlighted frontier is **nondominance among computed candidates**: no other candidate improves an objective without worsening another, using a `1e-10` tolerance in return units. It is not the full continuous frontier. Discovery frontier membership stays fixed in the holdout view.

CVXPY/CLARABEL uses a 0.5-second solve limit and an eight-second overall scheduling budget. Setup and final evaluation can exceed that budget; it is not a strict endpoint deadline. Only successful, feasible solves add candidates. Missing solvers, failures and incomplete optimization are reported, while sampled candidates remain available.

## Discovery and numerical holdout

Two independent 2,048-path MC draws use one prepared history: seed domain 600 for discovery and 601 for evaluation. Allocation sampling uses domain 602. Candidates and discovery selections are frozen before holdout evaluation.

The holdout checks numerical selection sensitivity, **not historical out-of-sample performance or forecast calibration**. Repeatedly choosing allocations using holdout outcomes would make it another selection sample.

Both draws require at least 128 pressure scenarios. At that minimum, the 5% tail represents only 6.4 scenario-equivalents, so small ranking differences are fragile. Insufficient observations produce an unavailable result with both counts; observing none does not establish zero underlying pressure probability.

## API and scope

`POST /analysis/frontier` requires authentication and accepts the demo's `ScenarioRequest`. It uses the generated persona, including active scenario bills, and rejects stress weighting. Supported inputs have horizons of 1–60 days, 2–3,660 aligned history days and 2–8 distinct taxable assets. Shared admission control bounds concurrent expensive analyses.

The frontend clears stale results and rejects superseded replies. JSON export includes weights, discovery/evaluation metrics, pressure counts, input and draw identities, and solver diagnostics. It contains no executable orders.

The model excludes transaction costs, taxes, settlement delays, cash yield and dynamic rebalancing. The existing funding planner does not consume frontier points as funding instructions.

## Reproduce the repair experiment

From the repository root:

```sh
uv run --extra optimization python - <<'PY' > frontier-report.json
import json
from ginseng.frontier import portfolio_frontier
from ginseng.generate import generate_persona, canonical_shocks

report = portfolio_frontier(generate_persona(), canonical_shocks(), seed=42)
print(json.dumps(report, indent=2, allow_nan=False))
PY
```

`portfolio_frontier` also accepts `block_length=None`; the default resolves it from the prepared history. Each result records the resolved value. Fixed seeds reproduce sampled paths and allocations; solver availability and runtime limits can change which optimized candidates finish.

## Verification

The full Python suite passes (374 tests), including exact fractional-tail checks, first-breach timing, historical alignment, optimization feasibility, independent evaluation and API authentication/capacity checks. The 37 existing frontend tests, Svelte checks and production build pass. Existing `api.py` lint findings are unchanged; the new engine and test modules pass Ruff.

The browser harness renders the actual Svelte/Plotly components and Research page with frozen engine output, mocking HTTP transport. It checks camera rotation, keyboard selection and click-event wiring, frozen weights across samples, filtering, exact JSON export, themes/mobile, repair controls, stale-result clearing and errors. It does not exercise a real Supabase login.

```sh
uv run --extra dev pytest -q engine/tests
cd web
bun run check
bun run build
bun run test:frontier-browser
```

For an existing Chromium installation, set `CHROMIUM_PATH` to its executable. Set `FRONTIER_SCREENSHOTS` to an output directory to capture the synthetic fixture. Reviewed views: [light](../artifacts/portfolio-frontier/frontier-light.png), [dark](../artifacts/portfolio-frontier/frontier-dark.png), [mobile](../artifacts/portfolio-frontier/frontier-mobile.png).
