# Numerical model and offline input contract

All amounts are dollars. Historical income and spending are nonnegative magnitudes; spending and future obligations are subtracted exactly once. The three variable-flow columns share one historical index at each simulated day. Fixed income, fixed obligations, and scenario obligations remain deterministic. Aligned market returns retain the same indices in application consumers.

For cumulative future net flow `X[j,t]`, opening cash `C`, operating buffer `b`, and normalized nonnegative scenario weights `w[j]`, the three primary outputs are:

| Output | Definition | Units |
|---|---|---|
| `required_liquidity_reserve` | Inverse empirical q-quantile of `R[j] = max(0, b - min_t X[j,t])` | Dollars |
| `cash_shortfall_probability` | `sum_j w[j] * (min_t(C + X[j,t]) < 0)` | Probability |
| `expected_max_cash_deficit` | `sum_j w[j] * max(0, -min_t(C + X[j,t]))` | Dollars over all paths |

`funding_gap = max(0, reserve-C)`. The existing conditional mean deficit is expected maximum deficit divided by failure probability when it is positive, otherwise zero. It is distinct from daily-average deficits and dollar-days below the buffer. Compute deficits directly from minimum available cash, especially when opening cash is negative.

Days are end-of-day offsets 1 through H. There is no opening-instant t=0 observation: `X=[[1200]], b=1000` needs no reserve, and `C=-50, X=[[100]]` has no modeled deficit. Exactly zero cash does not fail. A mid-horizon failure followed by recovery still fails.

The quantile selects the smallest positive-weight observation whose CDF reaches q, without percentile interpolation. At q=0 it selects the minimum positive-weight observation; at q=1 it selects the maximum, however small its positive weight. CDF sums use extended precision and round once to float64 probability boundaries; there is no unconditional probability epsilon. Fractional CVaR boundary mass remains proportional across ties. Arrays, scalars, coverage and weights are validated at the shared `cash_risk_summary` boundary.

## Historical model and sampling plan

`prepare_history` owns a read-only joint daily history for one run. It freezes L before any replicate is timed. Automatic L retains the existing arch Politis–White stationary estimator, lag-1 fallback, default 14 for degenerate histories, rounding and clipping to 7–28. Explicit requests are also clipped, with requested/resolved values and clipping status recorded. Benchmarks explicitly use L=7 for tiny and L=14 for the larger cases, without fitting different models per method.

Declare material horizon M before comparing visible horizons H<=M. The fixed dimension is `d=1+2(M-1)`. Start at `floor(n*u[0])`. At day t>=1 (zero-indexed array day), continue to `(idx[t-1]+1)%n` if `u[2*t-1] < 1-1/L`; otherwise restart at `floor(n*u[2*t])`. Both coordinates are reserved even when the restart coordinate is unused. Threshold equality restarts. Both new methods call this exact map, vectorized over paths, then the existing `cash_paths` function.

MC uses PCG64 float64 uniforms in a fixed-width C-order matrix. Sobol uses SciPy's public `seed=Generator` interface, supported by the declared SciPy >=1.14 range, LMS plus digital-shift scrambling, 30 bits, no optimization, and `random_base2`. N must be a power of two: 2,000 is rejected with examples 1,024 and 2,048. No skipped points, thinning, rounding, fallback or appended IID points are allowed. The public SciPy API and limitations are documented in the [Sobol reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.Sobol.html).

Seed derivation is `SeedSequence([root, domain, method_id, replicate]).generate_state(1, dtype=uint64)[0]`. Domains are 100 for experiments, 200 for independent references and 300 for execution ordering; method IDs are 1=MC, 2=Sobol, 3=legacy MC. Synthetic canonical data use seed 20260911 regardless of the simulation root seed. Replicate seeds do not depend on N. Shared numeric seeds across different algorithms do not imply common random numbers. Cross-case streams may reuse seeds; inference here is per case, with independent replicate streams within each case.

In a fixed environment, repeating a plan reproduces indices and estimates; increasing N preserves path prefixes; changing H while retaining M preserves day prefixes. Arrays are copied into immutable bytes-backed storage. A caller cannot mutate them or re-enable writes to invalidate the identity. Changing C, b or deterministic bills does not regenerate paths. Direct and staged funding extensions within M agree. Beyond M, funding raises an actionable error requiring a new plan. The research `legacy_mc` option rejects a distinct material horizon, and records dimension as null because it does not use the fixed-coordinate cube. Existing legacy callers retain their generator and extension behavior; prospective `PathBundle` retains its own material-horizon model. There is no new global ceiling on outer-bootstrap history lengths.

Changing M changes the sampling plan, even with the same seed. Reproducibility does not promise cross-version, cross-CPU or arbitrary reduction-order bit identity; see [NumPy's compatibility policy](https://numpy.org/doc/stable/reference/random/compatibility.html) and [SeedSequence guidance](https://numpy.org/doc/stable/reference/random/parallel.html). CLI plans limit dimension to 21,201 and estimated simultaneous array storage to 512 MiB; these limits do not alter HTTP resource limits. Reference MC is generated sequentially in bounded batches. Sobol nets are not independently rescrambled by chunk.

## Version 1 local JSON

The complete example is [tiny-history.json](../examples/tiny-history.json). Required fields:

| Field | Contract |
|---|---|
| `version` | Integer 1 |
| `as_of` | ISO calendar opening date, strictly after recorded history end |
| `opening_cash` | Separately supplied finite settled cash; may be negative |
| `history_start`, `history_end` | Inclusive ISO dates of a complete recording window |
| `history` | Exactly one explicit row per date in the window, including zero days |
| each history row | `date`, `variable_income`, `essential_spending`, `discretionary_spending`; amounts finite and nonnegative |
| `buffer` | Finite nonnegative dollars |
| `coverage_target` | Finite probability in [0,1] |
| `horizon` | Positive integer forecast days |
| `obligations` | Optional list of `{day, amount, label?}`; positive integer one-indexed offsets and finite nonnegative dollar amounts |

Duplicate dates, invalid calendar dates, absent daily rows, out-of-window rows and invalid numeric inputs are rejected. No missing historical day is silently filled; no observations are invented between history end and opening date. A signed transfer reconciles the ledger to separately specified opening cash and is excluded from the variable series. The history window remains distinct from the forecast window. Core library `FinancialState` continues to support recurring fixed schedules and aligned portfolios; the initial local JSON format describes variable history and one-off obligations.

Run the exact-equivalent example with `ginseng simulate --input examples/tiny-history.json --block-length 7 --horizon 4 --sampler sobol --paths 2048`. CLI flags override sampler, path count, root seed, replicate, visible horizon, material horizon and requested L. Local JSON inputs are never copied into public benchmark artifacts; benchmark workloads are named synthetic fixtures only.

## Independent oracle

The tiny model enumerates all 81 index sequences, using exact rational probabilities. A transition has probability `(1-1/L)*I[z=(a+1)%n] + 1/(L*n)`: the successor gets continuation plus restart mass. The oracle independently sums integer cash flows, computes minima, aggregates equal reserves and selects the exact inverse CDF. It imports no production quantile, metric or sampler implementation. Enumeration above 100,000 sequences is rejected before allocation.

For joint history `(0,30,10), (50,30,10), (100,20,10)`, H=4, L=7, C=30, b=10, q=19/20 and deterministic net `[0,-50,0,-20]`, it derives reserve $90, failure probability 10846/27783, mean deficit 574790/27783 dollars, conditional mean 287395/5423 dollars and funding gap $60. Tests construct a real `FinancialState` and compare every production cash trajectory and weighted reduction with that independent oracle.
