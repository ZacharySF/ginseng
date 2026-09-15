# Experimental initial-block conditional Monte Carlo

The offline historical-bootstrap CLI can now average cash-failure outcomes over every possible initial historical day. Sampler and estimator are independent choices:

```sh
uv run ginseng simulate --fixture tiny --sampler mc --estimator initial-block-cmc --paths 2048
uv run ginseng simulate --input /path/to/finances.json --sampler sobol --estimator initial-block-cmc --paths 2048
```

Use your own version-1 historical input path in the second command. `--estimator path` remains the default. Legacy MC, prospective/scheduled paths and supplied stress weights are unsupported by CMC and rejected at the relevant estimator boundary. Application services and funding optimizers retain their existing path behavior.

## Target and mechanism

The target is the probability that opening cash plus cumulative flow is strictly negative on at least one forecast day. Exactly zero survives; negative opening cash alone is not a failure unless an end-of-day balance is negative. This matches `cash_risk_summary`, the offline numerical baseline. The application's separate severity reduction uses a money tolerance and is not changed by this release.

Let J be the independent uniform initial historical index, and V all later restart choices. Each CMC observation is `g(V) = sum_j I(j,V) / n`. Conditional expectation preserves the mean, and total variance gives `Var(g) <= Var(I)` for independent MC observations. This guarantees neither equal-runtime improvement nor finite-net Sobol variance reduction. [Asmussen's conditional Monte Carlo treatment](https://www.cambridge.org/core/journals/annals-of-actuarial-science/article/conditional-monte-carlo-for-sums-with-applications-to-insurance-and-finance/3FC4A576C75607F46F9B7FF0238C5A94) provides the research foundation; the block-specific implementation below is this project's adaptation.

For every initial start j and length k, preparation stores total flow `S_k(j)` and running minimum `A_k(j)`. It includes deterministic bills on their forecast dates. For a sampled first-block length K and remainder minimum m, the complete minimum is `min(A_K(j), S_K(j)+m)`. Eligible starts satisfy `C+A_K(j)>=0`; sorted eligible totals count survivors with `S_K(j)>=-C-m`. Divide by all n historical starts. When K equals the horizon, only the initial minimum matters.

The sampler records actual restart branches: a restart can pick the continuation index. Optional tracing does not alter indices, seed derivation, coordinate mapping or dimension. With material horizon M, dimension remains `2*M-1` and lengths are capped to the visible horizon. CMC ignores the initial-index coordinate without dropping any points. Scrambled Sobol retains the baseline's 30 bits and power-of-two requirement, consistent with [SciPy's Sobol documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.Sobol.html).

## API and numerical details

- `prepare_conditional` returns immutable totals, minima, sorted eligible totals, history and deterministic flows. Preparation costs O(nH), plus sorting O(H n log n); the two core tables occupy 16nH bytes, with additional sorted arrays and temporary storage.
- `failure_probability` validates any explicitly reused preparation against a content identity covering net history, deterministic daily flows, horizon and opening cash. There is no hidden global cache. Different joint histories with identical net flows are equivalent for this metric.
- `conditional_contributions` groups traces by K, builds remainder minima and performs vectorized binary searches. It avoids N-by-n-by-H arrays. Near a floating-point threshold it evaluates that row directly using the baseline's accumulation order. This protects zero boundaries but can cost O(nH) per ambiguous trace; timings include it.
- `slow_contributions` independently constructs all-start paths for small validation cases. It is limited to ten million path-days.
- The low-level contribution functions accept prepared tables and matching sampler bundles; callers must preserve that pairing. The public `failure_probability` function checks preparation identity against supplied current inputs. Arbitrarily manufactured traces are not a supported modeling interface.

Only `cash_shortfall_probability` is replaced. Reserve, funding gap, expected deficit and average deficit conditional on failure retain path estimates. Consequently, dividing displayed expected deficit by displayed CMC failure probability need not reproduce the displayed conditional average. `manifest.metric_estimators` identifies each method. CLI diagnostics continue to describe the real path sample. No conditional averages are represented as invented financial scenarios.

## Validation and evidence

The tiny fixture's 64 weighted branch traces yield exactly `10846/27783` under rational weighting of all-start failure counts. The ordinary/conditional observation-variance ratio is approximately 9.54. This is an exact variance result, not a speedup measurement. Tests also cover same-index restarts, material-horizon prefixes, immutable traces, circular histories, single days, bills at both ends, negative cash, zero boundaries, stale tables, rejected modes and unchanged other metrics.

Reproduce the full experiment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python -m ginseng.conditional_benchmark --config benchmarks/conditional.json --out artifacts/conditional
uv run pytest
```

The frozen config declares RMSE 0.005 before measurement, N=256 through 16384, 32 independent replicates, and five fixtures. Within each sampler/replicate, path and CMC use identical seeds and index paths. Across Sobol replicates, scrambles are independent; uncertainty is assessed across whole nets. Larger fixtures use independent million-path MC references and marginal binomial intervals. Tiny uses exact truth. The repair case is declared in advance, alongside quiet and stressed baseline fixtures.

The [generated report](../artifacts/conditional/results.md) includes favorable, unfavorable and undefined comparisons. Raw observations, reference intervals, frozen financial states, input identities, environment and separate setup costs are adjacent. Cost selection conservatively requires meeting RMSE across the reference interval. It does not account for uncertainty in finite-replicate RMSE or timing rankings. A repeated-call comparison is valid only when its explicit preparation is reusable; amortize its recorded setup cost over the actual number of calls.

**Adoption: retain as experimental opt-in.** Any observed advantage is specific to a fixture, error target, tested sample-size grid and machine. The numerical release's earlier results remain in `artifacts/standard`. Reserve inversion, mean-deficit conditioning, automatic precision stopping and compiled kernels remain separate future work.
