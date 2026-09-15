# Precision-driven stopping for cash-failure probability

The optional `ginseng precision` command runs independent Monte Carlo until it reaches a requested absolute numerical error bound or exhausts a path budget. It supports ordinary path indicators and initial-block conditional MC. It returns the cash-failure estimate, numerical probability interval, actual sample count, checkpoint history and an explicit stopping reason.

```sh
uv run ginseng precision --fixture tiny --absolute-error 0.005 --confidence 0.95 --max-paths 262144
uv run ginseng precision --fixture tiny --estimator initial-block-cmc --absolute-error 0.005
uv run ginseng precision --input /path/to/finances.json --max-paths 131072 --batch-size 1024
```

`0.005` means half a percentage point of probability. Confidence describes coverage of the numerical interval under repeated simulation of the fixed historical model. It is distinct from the financial reserve coverage target and the application's historical-data uncertainty bands. It does not measure forecast calibration or uncertainty about whether history represents the future.

## Why repeated checks are valid

At predetermined cumulative sample counts, the command uses a two-sided empirical Bernstein bound for independent observations X in [0,1]. Ordinary failure indicators and conditional failure contributions both satisfy that range and have the same target mean p.

For look k, allocate `delta_k = (1-confidence)/(k*(k+1))`. With unbiased sample variance s² and count n, use

```
L_k = log(4/delta_k)
r_k = sqrt(2*s²*L_k/n) + 7*L_k/(3*(n-1))
interval = [max(0, mean-r_k), min(1, mean+r_k)]
```

[Maurer and Pontil (2009), Theorem 4](https://arxiv.org/pdf/0907.3740) gives the one-sided bound. Applying it to X and 1-X, assigning delta_k/2 to each tail, gives the factor 4 above. This is a variance-sensitive bound, so conditional MC's smaller variance can reduce the required sample count.

The allowances telescope: `sum_{k>=1} delta_k = 1-confidence`. A union bound therefore controls the probability of **any** interval missing p across the predetermined checkpoints. The command can stop after inspecting those intervals. This is a conservative checkpoint construction; the broader [confidence-sequence literature](https://arxiv.org/abs/1810.08240) develops more sophisticated time-uniform methods.

The implementation checks counts `batch_size, 2*batch_size, 4*batch_size, ...`, capped at the predeclared `max_paths`, including a final partial count if needed. All checks use all observations collected so far. Between checkpoints, the last reported interval remains the available interval; this release does not claim a freshly calculated interval is valid at every individual sample count. Users must fix the estimator, input model, confidence and checkpoint plan before running. This guarantee does not cover selecting the best of many runs, seeds, or models after seeing results.

Stop when the greater distance from the sample mean to either clipped endpoint is at most the requested absolute error. That makes the criterion apply to the **reported sample mean**, even near zero or one. Width alone would need a different center convention. The sample mean at a data-dependent stopping time is not generally unbiased; interval validity and the stopping guarantee still hold.

## Outputs and limits

- `precision_met=true`, `stop_reason=precision_reached`: the reported interval meets the requested error criterion.
- `precision_met=false`, `stop_reason=max_paths_reached`: the budget was exhausted. The estimate and wider valid interval are returned. This is a completed computation, so the CLI exits successfully; automation should inspect `precision_met`.
- No observed failures still gives a positive upper endpoint. Zero empirical variance retains the additive term in the bound; it cannot produce a false zero-width interval.
- The cap is an observation count, not a wall-clock deadline. CMC observations each average over initial starts. Batch processing bounds sample-array memory; table preparation has its own memory guard.
- Only independent `mc` is accepted. Sobol points within a net are dependent; applying this IID formula to individual Sobol points would not be justified. Legacy MC and supplied weights are also rejected.
- This command takes historical version-1 inputs. It does not accept prospective path bundles, generate reserve precision intervals, or replace the existing `simulate` command or website.

## Reproducibility and implementation

`engine/ginseng/precision.py` owns the statistical bound, stable online mean/variance accumulation and streaming orchestration. A single PCG64 generator advances through bounded chunks in the existing fixed-coordinate mapping. It never repeatedly adds a nested sample prefix as if it were fresh data. Its independent seed domain is 400, separate from earlier experiments (100) and numerical references (200). With a fixed material horizon, changing batch size preserves the generated stream, although it changes checkpoint locations and can change when a run stops.

The sampler still consumes the complete material-horizon coordinate width and CMC still records actual first-restart lengths. The visible horizon is fixed before sampling. Conditional tables are prepared once per run and remain tied to that run's immutable historical model. Only online moments and logarithmically many checkpoint records are retained; paths from prior batches are released.

The manifest records input and index hashes, CMC trace/table identity when applicable, seed derivation, block resolution, coordinate mapping, interval version, stopping configuration and environment. The result hash covers the summary and checkpoints but excludes elapsed time. `core_seconds` includes input preparation, sampling, conditional preparation and interval checks; it excludes environment/provenance collection and JSON serialization.

## Validation and measured results

Tests compare chunked output with an independent one-shot reduction, verify material-horizon handling and partial budgets, compare CMC against all-start enumeration, and check first qualifying stops, reproducibility, CLI behavior, endpoint cases and rejected modes. An independent count-probability recursion calculates the chance of ever missing the truth across six checkpoints for five Bernoulli probabilities; it removes paths at their first miss, so it checks simultaneous coverage rather than just the final interval. These checks supplement the proof; finite experiments do not establish a universal guarantee.

Run:

```sh
uv run pytest
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python -m ginseng.precision_benchmark --config benchmarks/precision.json --out artifacts/precision
```

The [generated report](../artifacts/precision/results.md), raw checkpoint observations and budget-exhaustion example accompany the frozen config. There are 32 independent replicates for each of four cases and two estimators. Tiny has exact truth; larger cases retain the earlier independent numerical reference intervals and checked fixture identities. Their reference-point inclusion counts are not true-coverage measurements.

**Adoption:** retain this as an optional offline capability. It provides an explicit precision or budget outcome. Its bound is conservative and its timing measurements do not establish an optimal stopping rule or justify replacing existing defaults. The previous CMC benchmark measured full-output RMSE, which is a different accuracy criterion and computational workload.
