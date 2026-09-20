# Prompt B — Precision-Controlled Failure Estimation

20 September 2026. Describes **Prompt B**, on top of the existing Decision Verification Lab. The subsequently implemented [Prompt C experiment](two-decision.md) is separate. [Before-edit audit](precision-b-audit.md) distinguishes working earlier features from this release.

## What changed

The checkout already had a valid empirical-Bernstein checkpoint method, MC and initial-block CMC, precision CLI commands, and authenticated forecast consumers. This release reuses those implementations. It adds running intersections with explicit numerical-failure handling, structured outcomes, caller-specified limits, cancellation, a versioned random-input extension contract, and exact-input precision capture/replay. No optimizer, forecasting model, sampler law or native kernel was rewritten.

The existing `/finance/numerics` and `/demo/numerics` consumers now accept error, confidence, observation cap, estimator, time and array-memory budgets. The existing web panel exposes the first five controls, displays exhaustion distinctly from success, handles an unestimated probability without displaying zero, and cancels requests. HTTP disconnects reach a cooperative cancellation event in the worker; the worker retains its concurrency lease until computation ends. No personal calculations are persisted by this endpoint. The existing TUI precision recipe now exposes the resource/chunk/backend controls and exact-input capture; its dedicated precision replay recipe checks evidence offline. Cancel cooperatively stops precision work and retains the result in the notebook. See [TUI instructions](tui-studio.md#prompt-b-in-the-tui).

Compatibility decisions: legacy `run_precision` still rejects unsupported modes with `ValueError`; the opt-in public `estimate_failure` wrapper returns `unsupported_estimator`. Legacy summary fields and normal stopping reasons are retained. New `status`, `method`, `model_identity` and `interval_observations` fields are additive. No-observation estimates/error bounds are now **null**. The interactive default is ordinary MC; previously the web endpoint hardcoded CMC. Callers can explicitly select CMC. `batch_size` retains its old first-checkpoint meaning; new `chunk_size` controls execution independently.

## Statistical contract and method

The target is the fixed historical stationary-bootstrap model's probability of at least one **strictly negative end-of-day available cash balance** over the declared visible evaluation horizon. Exactly zero is not failure; later recovery does not erase a failure. Opening cash, deterministic future flows and obligations retain their existing meanings. This API estimates the base historical cash scenario; it does not optimize funding or automatically attach sequential intervals to Prompt A's selected funding plan.

For independent identically distributed observations in [0,1], reuse the existing method: at predeclared doubling looks (including the final sample cap), allocate `delta_k = alpha/[k(k+1)]` and compute

```
L_k = log(4/delta_k)
r_k = sqrt(2*s²*L_k/n) + 7*L_k/[3*(n-1)]
raw interval = [max(0, mean-r_k), min(1, mean+r_k)]
reported interval = intersection of raw intervals through look k
```

Here s² is the unbiased sample variance. The one-sided [Maurer–Pontil Theorem 4](https://arxiv.org/pdf/0907.3740), applied to X and 1−X with half the allowance per tail, gives the factor 4. A union bound and `sum delta_k = alpha` give simultaneous coverage at the declared looks; intersection preserves it. This is the existing conservative checkpoint construction, **not** an implementation of the sharper [Howard et al. confidence sequences](https://arxiv.org/abs/1810.08240).

Stop only at those looks, when the maximum distance from the current sample mean to either intersected endpoint meets the requested tolerance. `0.005` means **0.5 percentage points**. The stopped sample mean need not be unbiased. Zero observed failures retains a positive upper endpoint; zero sample variance retains the additive term. Invalid/nonfinite, empty or zero-width intersections cannot become a precision success. Spending is calculated in log space, retaining log allowances when their floating-point exponent underflows.

Cancellation/time limits between looks retain the last checkpoint interval, or [0,1] if none exists. `actual_n` counts all completed observations; `interval_observations` identifies the certified checkpoint. No extra unbudgeted interval is inspected. Marginal per-run coverage does not cover selecting a seed/model after inspecting multiple runs; the benchmark does not claim simultaneous coverage across comparisons.

| Mode / quantity | Supported behavior |
|---|---|
| Ordinary MC, unweighted independent path indicators | Supported; default |
| Initial-block CMC under independent ordinary-MC rows | Supported fractional [0,1] observations; integrates uniform initial starts and retains actual restart lengths; existing independent all-start reference tests reused |
| Scrambled Sobol individual points / partial nets | Unsupported for this interval; existing complete-net numerical experiments remain separate |
| Legacy MC, supplied weights (even uniform), self-normalized/importance-weighted estimates, adaptive proposals | Unsupported |
| Reserve quantile, CVaR, modeled cost, prospective supplied paths | No sequential precision contract in this release |
| Forecast/model uncertainty or real-world calibration | Not measured by these numerical intervals |

Outcomes are `precision_met`, `budget_exhausted`, `cancelled`, `unsupported_estimator` or `numerical_failure`. Exhaustion reasons distinguish observations, time and memory. A failure to reach precision is a valid reported outcome, not a suppressed run.

## Streams, resources and evidence

`PrecisionStream` preserves PCG64, seed domain 400 and the earlier fixed-material-width layout. A row consumes `2*material_horizon−1` float64 uniforms; `advance(start*dimension)` addresses a path prefix. This is deliberately limited to float64 uniforms: [NumPy's advance documentation](https://numpy.org/doc/stable/reference/random/bit_generators/generated/numpy.random.PCG64.advance.html) warns that other distribution samplers can consume variable numbers of raw outputs. Tests check published NumPy PCG64 raw vectors, float64 conversion, the Ginseng stream vector, arbitrary row offsets, chunk/count changes and 1/2/4 workers.

Changing the visible horizon within a fixed material layout preserves its per-path prefix. **Changing the material horizon changes the layout** and has no prefix guarantee. Sampler, estimator, model identity and selected/actual execution backend are separate metadata. Native execution records the actual loaded binary/build identity; CMC honestly records NumPy execution even if a different backend was requested. Identical random inputs do not promise bitwise floating-point reductions across machines.

The API retains 1,024–65,536 observation limits, 60-day interactive horizon and ten-year history limits, a maximum 30-second cooperative deadline and 128 MiB array budget. Offline config accepts up to 2^30 observations subject to bounded chunks, memory and deadline; the default CLI deadline is 30 seconds. Python callers may explicitly remove the deadline for offline experiments. These are not process RSS limits: preparation, imports, provenance serialization and a running batch are not preempted. Array estimates reserve history, CMC tables, per-worker scratch and optional captured indices. A stricter execution budget takes precedence. No asynchronous job registry is introduced.

`precision_artifact.py` wraps the **existing prepared engine artifact**, adding the interval configuration/checkpoints, versioned stream, exact initial-block trace when needed, model identity and output integrity. It stores exact materialized history, schedule, indices and opening cash, rather than relying on a seed. Atomic publication, bounded manifests, safe fixed member paths, byte counts, shapes, content digests and pickle-disabled NumPy loading reuse existing protections. Personal capture requires explicit consent; committed examples are synthetic.

Replay makes no network calls and draws no new random numbers. It recomputes path indicators or conditional contributions and every declared interval from exact prepared inputs. It distinguishes exact integrity checks from tight probability arithmetic comparison (`atol=2e-14`, `rtol=2e-13`). It rejects incompatible stream/method contracts and reports stale numerical outputs even when their manifest digests have been recomputed. Cancellation/deadline timing is recorded, not reproduced; the captured completed observations and certified checkpoints are replayed. Code/version provenance is evidence, not a formal verification certificate.

## Reproduce

From the repository root with the existing dev environment. Capture destinations must not exist:

```sh
.venv/bin/ginseng precision --fixture tiny --block-length 7 --absolute-error 0.05 --confidence 0.95 --max-paths 4096 --batch-size 256 --chunk-size 257 --capture /tmp/ginseng-b-path --out /tmp/ginseng-b-path.json
.venv/bin/ginseng precision-replay /tmp/ginseng-b-path
.venv/bin/ginseng precision-replay /tmp/ginseng-b-path --backend native --workers 2

.venv/bin/ginseng precision --fixture tiny --block-length 7 --estimator initial-block-cmc --absolute-error 0.05 --max-paths 4096 --batch-size 256 --chunk-size 257 --capture /tmp/ginseng-b-cmc
.venv/bin/ginseng precision-replay /tmp/ginseng-b-cmc

# Already captured synthetic evidence:
.venv/bin/ginseng precision-replay examples/precision-b/path
.venv/bin/ginseng precision-replay examples/precision-b/cmc

# Fixed observation count, with the same predeclared interval looks:
.venv/bin/ginseng precision --fixture tiny --block-length 7 --max-paths 65536 --fixed-budget

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python benchmarks/precision-b/measure.py
# Replace before/after, numpy/native, normal/stress to reproduce each performance row:
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python benchmarks/precision-b/measure.py --performance after numpy stress

.venv/bin/pytest -q engine/tests engine/ginseng/ginseng_rice/tests
nix shell nixpkgs#bun nixpkgs#nodejs --command sh -c 'cd web && bun run check && bun run test:numerics && bun run build'
CHROMIUM_PATH=/etc/profiles/per-user/xelo/bin/chromium nix shell nixpkgs#bun nixpkgs#nodejs --command sh -c 'cd web && bun run test:risk-browser'
```

CLI precision returns a successful command exit for a valid exhaustion outcome; inspect `status`. Replay exits 0 for match, 2 for invalid capture/input and 3 for a numerical mismatch. `--input` capture requires `--allow-personal-capture`. No service/network is needed for replay. The optional native wheel must already be installed for native commands.

## Results and limitations

[Raw 512-run diagnostics and table](../artifacts/precision-b/diagnostics.md) use 32 independent replications for each of four exact-truth fixtures, two estimators and fixed/adaptive modes. Every run's checkpoints included its exact truth. This finite diagnostic supplements the theorem; it does not prove coverage. Existing exact Bernoulli recursion checks simultaneous failure probability at six checkpoints for five probabilities, and CMC retains independently enumerated target-law tests.

At p=0.001, adaptive ordinary MC used median **8,192** observations versus **65,536** fixed. At p=0.05 it used the full cap. At p=0.5 and the four-day tiny fixture, **0/32** ordinary-MC runs reached 0.005 error at the cap. CMC reached the target in all 32 tiny replications with median **32,768** observations. Its one-day contributions equal the exact probability by integrating every initial start; that deliberately simple example is not a universal speed claim.

The committed ordinary capture stopped at 2,048 observations: estimate **0.380859375**, 95% interval **[0.33122133, 0.43049742]**. CMC stopped at 1,024: **0.392578125**, interval **[0.35854567, 0.42661058]**. Both replay with zero mismatches; ordinary replay also passes on native with two workers. These demonstrations request the looser 0.05 tolerance to keep captures small; the 512-run benchmark tests 0.005.

[Before/after performance and memory](../artifacts/precision-b/performance.md) reports normal 8,192×30 and offline 65,536×180 workloads, including unfavorable timings. The frozen pre-B precision module runs against the same primitive engine and inputs. After uses chunk-local contexts so prior chunks do not accumulate in the cache. Process peak RSS includes imports and native allocations; no native-only allocation attribution or hard RSS enforcement is claimed. Warm measurements still prepare inputs and include provenance. No performance gate, percentile claim or native rewrite was added.

Validation: [full suite](../artifacts/precision-b/final-tests.txt) **538 passed**, including **37 snapshots**, with two upstream deprecation warnings. The [focused precision suite](../artifacts/precision-b/final-focused-tests.txt) passed all **69** tests. [Final web validation](../artifacts/precision-b/final-web.txt) passed type checks (zero errors/warnings), all three numerical-store tests, the browser scenario including confidence/time controls and no-estimate exhaustion, and the production build. Native boundary tests/replay ran; sanitizers were not rerun because native source was unchanged. The implementation retains conservative intervals, fixed material-coordinate layout, cooperative rather than hard cancellation, and bounded optional capture. These limitations are explicit; no real-world safety, calibration, production deployment or population-optimality claim follows.

## Files

New production modules: `precision_stream.py`, `precision_artifact.py`, `precision_replay_cli.py`. Existing changes: `precision.py`, the narrow exact-array table entry in `conditional.py`, `cli.py`, `risk_explorer.py`, `resources.py`, `api.py`, `forecast_api.py`; follow-up TUI adapters and presentation in `studio.py` and `studio_ui.py`. Web: `numerics.svelte.ts`, existing `NumericalRiskPanel.svelte`, store/browser tests. Tests: `test_precision_b.py` and TUI integration coverage in `test_studio.py`, alongside reused precision/conditional/API suites. Reproducible evidence: `benchmarks/precision-b`, `artifacts/precision-b`, `examples/precision-b`; audit and method notes in `docs`. Prompt A and Sakura TUI changes remain intact.
