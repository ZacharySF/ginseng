# Measured MC versus scrambled Sobol results

**Sobol improves some targets, but there is no general computational-cost win for this bootstrap.** The strongest exact-reference result is the tiny fixture's failure-probability target: at predefined RMSE .005, Sobol's fastest qualifying observed point cost **2.34× less** than the best measured ordinary-MC option. Ordinary MC was cheaper for several reserve or already-easy targets. Existing HTTP defaults remain legacy MC; the offline CLI defaults to the new MC stream for its nesting contract.

The complete standard run contains **3,136 replicate observations**, N=256..16,384, 32 independent replicates per method/case, and **1,048,576 independent MC reference paths per larger financial case**. The tiny case uses rational exact truth; the smooth case uses analytic truth. All profiles, seed schedules and raw observations are saved. Machine: Intel(R) Core(TM) Ultra 7 256V; Python 3.12.14; one BLAS/OpenMP thread. This is CPU evidence on one environment, not hardware-portability evidence.

## All financial targets at N=16,384

RMSE is across independent replicates. Tiny is exact; larger-case errors are relative to the numerical MC reference, with uncertainty below. Zero is reported as observed, without a manufactured small denominator.

| Case | Target | Legacy MC RMSE | Fixed MC RMSE | Sobol RMSE |
|---|---|---:|---:|---:|
| tiny | Reserve ($) | 0 | 0 | 0 |
| tiny | Failure probability | 0.00380813 | 0.00325069 | 0.000384556 |
| tiny | Mean deficit ($) | 0.195934 | 0.194556 | 0.0174604 |
| canonical | Reserve ($) | 7.52049 | 6.48092 | 3.31754 |
| canonical | Failure probability | 0 | 0 | 0 |
| canonical | Mean deficit ($) | 0 | 0 | 0 |
| zero-heavy | Reserve ($) | 0 | 0 | 0 |
| zero-heavy | Failure probability | 0.00032796 | 0.000254259 | 0.000257077 |
| zero-heavy | Mean deficit ($) | 0.0175436 | 0.0168638 | 0.0152432 |
| drought-heavy | Reserve ($) | 0 | 0 | 0 |
| drought-heavy | Failure probability | 0.00385058 | 0.00366506 | 0.0015692 |
| drought-heavy | Mean deficit ($) | 7.59265 | 5.94078 | 2.41211 |

## What these observations support

- **Tiny exact case:** Sobol markedly lowers failure and mean-deficit RMSE. The reserve is already $90 in every largest-N replicate for all methods. At the predeclared tolerances, lower same-N error does not always translate into lower runtime: sampler initialization is material for this tiny workload. The failure target's cost comparison is exact-reference evidence, scoped to this grid.
- **Canonical history:** at N=16,384, reserve RMSE is $3.32 for Sobol versus $6.48 for new MC and $7.52 for legacy. Their reference-sensitive RMSE ranges remain separated. Core costs are 14.70, 14.12, and 11.60 ms respectively. At the looser predefined $50 tolerance, ordinary MC is cheaper. No failure occurred in the million-path reference or benchmark replicates; that observation is insufficient to establish a zero-risk financial model.
- **Zero-heavy history:** reserve stays on a $110 plateau. Sobol's failure RMSE is essentially tied with fixed-coordinate MC. Mean-deficit differences are small relative to reference uncertainty, so a ranking there is unresolved. Ordinary MC meets these loose tolerances with less cost; the large zero mass is a property of the fixture.
- **Drought-heavy history:** the $3,900 reserve is at a high-probability support point and has zero observed RMSE across this grid. Failure and mean-deficit estimates show a Sobol precision advantage at N=16,384. Its mean deficit reaches the $5 target while both ordinary methods fail to reach it on this grid, so no finite cost speedup is reported. The fastest apparent failure-target comparison is marked unresolved because shifting the reference within its interval changes the selected point's attainment.
- **Smooth positive control:** at N=16,384 the analytic-integral RMSE is 7.64e-08 for Sobol versus 0.00185 for MC. Only Sobol reaches the .0001 target on the tested grid. This validates useful QMC behavior on a smooth four-dimensional integrand; it does not establish a financial-model speedup or an asymptotic rate.

## Reference limitations

Canonical reserve reference is $1,351.7623, with 95% order-statistic interval [$1,350.2912, $1,352.6550]. Zero observed failures gives a binomial probability interval [0, 0.000003518] and a conservative expected-deficit interval [0, $0.013383], using the maximum feasible deficit and binomial upper bound instead of a false zero-error claim.

Drought failure reference is .59272194 with interval [.59178079, .59366257]. Mean deficit reference is $774.64455 with interval [$772.95386, $776.33524]. These uncertainties are material for small differences. The report retains each target's intervals and reference-sensitive RMSE range; no largest Sobol result serves as truth. Intervals are marginal, not simultaneous, and replicate RMSE/cost rankings themselves have sampling and timing variability.

## Why stable reserves do not imply broken randomness

At N=16,384 the diagnostic tiny sample contains 65 distinct index paths and 11 distinct reserves. The zero-heavy sample has 14,354 distinct index paths but only six reserve values; 86.4% require zero reserve and 99.9% have no cash deficit. Drought-heavy has 61 distinct reserves, yet its q=.95 reserve selects the $3,900 atom. Exact CDF errors at the tiny reserve and neighboring support points remain informative when the quantile is unchanged.

The paired $100 day-17 diagnostic bill leaves the zero-heavy reserve unchanged, moves canonical reserve by about $49.89, and moves drought reserve by exactly $100. These all satisfy the deterministic-payment bounds. The unmodified canonical staged $1,500/day-3 and $3,000/day-17 repair remains available: the diagnostic MC bundle estimates reserve $5,787.22, failure probability .34558, and unconditional deficit $340.26 for that paired scenario. It was not substituted into the benchmark after results were observed.

## Inspect and reproduce

- [Full generated tables, selected N/costs, CDF diagnostics and plots](../artifacts/report/results.md)
- [Raw replicate observations](../artifacts/standard/observations.json), [manifest](../artifacts/standard/manifest.json), [references](../artifacts/standard/references.json), [seed schedule](../artifacts/standard/schedule.json)
- [Executed notebook](../notebooks/numerical-validation.ipynb) and [exported figures](../notebooks/assets/)
- [Methodology and commands](benchmark-methodology.md), [model/input definitions](numerical-model.md), [implementation record](implementation-notes.md)

These results distinguish numerical correctness from fixed-history precision, historical-data uncertainty, and held-out forecast calibration. They support keeping all three samplers available and choosing by the quantity and cost target rather than changing the application's default universally.
