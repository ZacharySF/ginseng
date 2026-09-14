# Benchmark methodology

The standard experiment is specified before execution in [standard.json](../benchmarks/standard.json): N=256 through 16,384 by powers of two, 32 independent replicates, root seed 42, and fixed dollar/probability error tolerances. [smoke.json](../benchmarks/smoke.json) is an integration profile with four replicates and two N values; its evidence is labeled smoke. Neither profile selects or discards favorable scrambles.

## Fixed workloads

| Workload | Input and settings | Truth |
|---|---|---|
| tiny | Three daily joint records; H=M=4, L=7, C=30, b=10, q=.95, bills $50 on day 2 and $20 on day 4 | Independent 81-sequence rational oracle |
| smooth | `exp((u1+u2+u3+u4)/4)` in four dimensions | `[4(exp(1/4)-1)]^4` analytically |
| canonical | Unmodified `generate_persona(20260911)`, H=M=30, L=14, original opening cash/buffer/q/fixed schedules; no added scenario bill | Independent MC reference |
| zero-heavy | Fixed 60-day synthetic history: `(100,20,10)` except every fifteenth day `(0,80,20)`; H=M=30, L=14, C=100, b=10, q=.95 | Independent MC reference |
| drought-heavy | Fixed 180-day history of repeating 40 dry `(0,60,20)` and 20 busy `(400,60,20)` days; H=M=30, L=14, C=600, b=1000, q=.95, $500 bill on day 17 | Independent MC reference |

Tuples are positive income/essential/discretionary dollar magnitudes. Separate adversarial histories are disclosed in `inputs.fixture`, not tuned after observing results. All financial paths have ordinary equal scenario probability; entropy stress is a different distribution, not a variance-reduction technique. M=30 means d=59; the tiny case has d=7. A 30-versus-60-day comparison would declare M=60 and d=119 from the outset. The smooth control is a plumbing diagnostic, not a financial result.

## Reference accuracy

Each larger case uses 2^20 ordinary MC paths in consecutive batches of 16,384 from a separate domain-200 PCG64 stream. Batching preserves the C-order point sequence. The global vector of path minima is retained until reduction; batch quantiles are never averaged. No Sobol estimate is used as truth. The 512 MiB estimate limits per-run arrays; 2^20 global minima use 8 MiB before sorting/reduction temporaries. This is array-storage context, not measured peak process RSS.

Failure intervals are 95% Clopper–Pearson binomial intervals. Mean deficit uses the ordinary standard error across independent paths with a normal approximation. If no failures occur, a zero observed standard deviation is insufficient: the reported upper mean bound is the maximum possible deficit under the fixed finite history and deterministic schedule times the binomial upper probability bound. Reserve intervals select lower/upper order statistics using binomial ranks, retaining ties and zero atoms. These are marginal intervals, not simultaneous family-wise guarantees.

For estimated truth, bias and RMSE are explicitly relative to the MC numerical reference. Aggregates include the range of RMSE obtained by moving the true value through the reference interval. This is reference sensitivity, not a confidence interval for replicate RMSE. Near-tied methods remain unresolved when their differences are comparable to reference uncertainty. Cost attainment is flagged unresolved when reference half-width reaches half the tolerance, or either selected method's upper reference-sensitive RMSE exceeds the tolerance. The declared reference budget is not adaptively increased in this release.

## Errors and costs

Every method uses the same prepared historical input, financial transformations and lightweight `cash_risk_summary`. The legacy generator is measured as well as the fixed-coordinate MC baseline. Legacy uses compact integer restart draws and avoids the new bundle's full material-array ownership copies; new MC reserves both uniforms per transition. Thus legacy can legitimately be cheaper. No API, authentication, HTTP, chart reductions, outer bootstrap, funding optimization or persistence analysis is included.

Timing starts before seed derivation and sampler construction/randomization. It includes point generation, mapping, bundle copying/index hashing, existing cash-path construction and the same minimal target reductions. Input preparation, diagnostic summaries and file I/O are excluded. Imports/generators are warmed. Every N constructs its own initial design; no timed prefix slice gets generation for free. The serial task schedule is shuffled with a domain-300 seed and saved before execution. There are no competing benchmark workers; BLAS/OpenMP thread counts are fixed to one in recorded commands. Median and 10th/90th percentile core times are saved with replicate estimates.

Bias is the mean estimate minus reference. RMSE is the square root of mean squared error. SD uses the sample standard deviation across independent replicate estimates, not across dependent Sobol points. Independent randomizations are necessary for this interpretation; see the [SciPy QMC overview](https://docs.scipy.org/doc/scipy/reference/stats.qmc.html). There is no claim that every larger N or every scramble improves error, or that this discontinuous bootstrap has an O(1/N) error rate.

Cost tables select the fastest **observed** grid point meeting a predefined target for each method, then compare the best correct ordinary baseline (MC or legacy MC) with Sobol. The ratio is ordinary time / Sobol time. Missing attainment is “not reached on this grid”; no extrapolation is made. Zero RMSE at an atom stays zero, without an invented denominator or infinite speedup. The standard tolerances for large cases are $50 reserve, .005 failure probability, and $5 mean deficit. Tiny uses $5/.005/$.50; smooth uses .0001. These choices precede results in the saved config.

## Diagnostics and provenance

Each financial fixture records path-minimum quantiles/spread, distinct index paths, distinct reserves, mass at zero requirement and deficit, and minimum-day counts with earliest-day tie-breaking. A paired additional $100 bill is applied on day min(17,H); the canonical diagnostic also applies its original staged $1,500/$3,000 repair. These comparisons reuse the same bundle. Dollar-for-dollar reserve shifts can be mathematically correct: a day-1 bill D changes each requirement to `max(0,b-min(X)+D)`.

The old `shortfall_distribution` is a histogram of **signed minimum cash positions**, not deficit magnitudes. The notebook labels it accordingly and shows the deficit atom at zero separately from positive deficits. Tiny-case empirical CDFs at the exact reserve and neighboring support points expose differences hidden by a stable quantile.

Manifests include input/model/index/result identities, seeds and derivation, requested/resolved L, histories/settings, mapping/generator versions, dimension/horizons, actual N, dependency versions, CPU/platform, thread settings, dtype, Git commit and a source fingerprint covering uncommitted engine code. Config and schedule hashes/settings accompany observations. Timings are excluded from deterministic result identity. Input hashes distinguish identical index paths applied to different cash amounts. Documentation-only changes do not alter engine identity.

## Reproduction

From the repository root with Python 3.12 and uv:

```sh
uv sync --locked --extra dev
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --no-sync ginseng benchmark --config benchmarks/standard.json --out artifacts/standard
uv run --no-sync ginseng report --input artifacts/standard --out artifacts/report
uv run --no-sync python notebooks/execute.py
```

The report command recomputes aggregates, cost tables, CDF tables and exportable SVGs entirely from saved raw observations. It never launches a new simulation. The notebook calls the installed package and reads saved results; it never runs the benchmark by default. Repository artifacts are modest synthetic observations and manifests, not the large temporary index/cash arrays.

Numerical correctness, numerical precision conditional on one fixed history, sensitivity to finite historical data (the separate outer bootstrap), and held-out forecast validation are four different kinds of evidence. None substitutes for another. See the updated [model card](model-card.md).
