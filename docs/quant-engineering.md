# Quant execution engine

## Inspection map (September 15, 2026)

Baseline: `891f9e1c922c5f868715315fe24c0b08e4b3d872`; initially clean tracked tree, with unrelated `ginseng-source.txt` left intact. Previous MC/Sobol, initial-block CMC, exact enumeration, precision, benchmark and API work is retained.

`simulate` owns shared bootstrap indices, direct prospective bundles, schedule interpretation and history alignment. `metrics` repeats scalar chart sorts and reserve matrix reductions. `scenario_service` computes metrics then rematerializes paths for provenance; funding candidates and optimizer also request baseline/discretionary arrays. `forecast_api` evaluates baseline and preview synchronously under the existing two-slot admission gate. `personal_forecast` retains history, assumptions and scheduled modes. `provenance` previously identified only Python sources. Existing CLI numerical estimators remain separate from execution backend selection.

The current quantile oracle uses normalized long-double cumulative weights rounded once to float64, **without** the older `q - 1e-14` convention. Existing app severity uses a micro-dollar tolerance while the numerical cash summary uses strict zero. Both contracts must remain unchanged.

Baseline cProfile observations (one warm-up, synthetic canonical fixture, seed 20260911, block length 14, q=.95, buffer=1000, no added obligations): 2,000×30: 32.06 ms; 32,768×60: 755.07 ms. These include profiler overhead and are not benchmark claims. Raw profiles and source identity are in `benchmarks/quant-engineering`.

## Build and short offline demonstration

Python 3.12, a C++20 compiler, CMake and Ninja are required for the optional native build. The core Hatchling wheel remains pure Python. Run from the repository root:

```bash
uv sync --locked --extra dev --extra native-build
uv build native --wheel --out-dir /tmp/ginseng-wheels
uv pip install --no-deps /tmp/ginseng-wheels/ginseng_native-*.whl
uv run --no-sync ginseng engine inspect
uv run --no-sync ginseng engine capture --fixture canonical --output /tmp/ginseng-run
uv run --no-sync ginseng engine replay /tmp/ginseng-run --backend numpy
uv run --no-sync ginseng engine replay /tmp/ginseng-run --backend native --workers 2 --output /tmp/ginseng-native-run
uv run --no-sync ginseng engine diff /tmp/ginseng-run /tmp/ginseng-native-run
uv run --no-sync pytest -q
cmake -S native -B /tmp/ginseng-sanitize -DGINSENG_SANITIZE=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build /tmp/ginseng-sanitize
/tmp/ginseng-sanitize/kernel_sanitize
uv run --no-sync ginseng engine benchmark --suite quant-engineering --output /tmp/ginseng-results
```

Capture destinations must not already exist. `examples/engine/canonical` is a small synthetic capture; it can be replayed without data generation. `--summary-only` omits full paths and chart outputs explicitly. Replay accepts `--block-size`, `--workers` (1–4), and `--memory-budget` (bytes). Exit codes: 0 match/success, 2 invalid input/artifact or resource error, 3 unexpected numerical mismatch, 4 intentional input/configuration difference. Comparison identifies input differences before comparing implementation outputs. Summary-only divergences reconstruct the affected reference row from recorded inputs.

## Contracts, ownership and reuse

`PreparedScenario` contains owned, immutable float64 histories/direct flows, int64 bootstrap indices, deterministic schedule, and separate visible/material horizons. Python interprets schedules and generates futures; the backend does neither. `EvaluationContext` owns caches, counters and at most one bounded executor, and clears them on success or failure. Existing synchronous consumers enter a context through `execution_scope`; an optional `context=` argument or an outer `with EvaluationContext(config):` supplies an explicit developer configuration. Nested metrics/funding/optimizer calls share that scope. Public financial response schemas are unchanged.

The native bindings accept only native-endian, aligned, C-contiguous float64/int64 arrays backed ultimately by immutable Python `bytes`. This is stronger than a read-only view of a writable array. The preparation adapter deliberately snapshots/casts floats and refuses implicit index narrowing; it can reuse already immutable aligned storage. Strict raw bindings reject negative strides, incorrect dimensions/types, non-finite values, malformed indices, writable aliases and unaligned pointers. Python outputs and pointers are acquired with the GIL held. Only array-independent pointer work releases the GIL; RAII reacquires it before exceptions or Python return objects are handled. The design follows the [pybind11 NumPy interface](https://pybind11.readthedocs.io/en/stable/advanced/pycpp/numpy.html) and [GIL rules](https://pybind11.readthedocs.io/en/stable/advanced/misc.html#global-interpreter-lock-gil); the wheel follows the [scikit-build-core build guide](https://scikit-build-core.readthedocs.io/en/stable/guide/getting_started.html). The installed build uses pinned pybind11 2.13.6 and scikit-build-core 0.10.7, not development APIs.

Full execution emits cumulative cash and six per-path statistics: minimum net flow, terminal net flow, minimum balance, maximum cash deficit, buffer dollar-days and overdraft dollar-days. Summary execution emits only those statistics; bounded NumPy blocks may materialize a block, while C++ fuses accumulation and summaries in a row loop. Neither summary implementation invokes a chart, funding or optimizer consumer. Daily charts use one stable order per column and three queries; C++ gathers only one contiguous column, never a full transpose. Scalar quantile and proportional CVaR tail semantics remain intact.

Reuse keys contain exact content identities rather than seeds or CRN draw IDs. Classified history uses transactions and coverage dates (including any opening-cash reconciliation). Draw preparation uses history and generator parameters; deterministic schedules are separate. Full paths are independent of opening cash, weights, coverage and buffer. Changing opening cash or buffer reuses cumulative paths/minima and rebuilds balance-based dollar-days. Changing weights rebuilds weighted queries. Chart keys include opening cash and weights. Schedules rebuild cumulative cash from daily components with original arithmetic grouping. Assumption components include all assumptions, seed, dimensions and market capital; deterministic previews reuse them. Funding candidates borrow immutable baseline/discretionary arrays and construct their own adjustments. Portfolio caching includes state/holdings and actual draw content. Changing backend creates a distinct calculation identity.

## Memory and concurrency limits

The budget is for arrays owned/referenced by the prepared calculation context plus conservative kernel scratch; it is not a process RSS cap. Python objects, DataFrame overhead beyond reported deep memory, allocator overhead, caller-owned source data, model generation temporaries, the optimizer and outer uncertainty can add memory. Live cached matrices are charged. Resident draws/direct input remain O(NH), full output O(NH), summaries O(N), and block scratch O(BH) for NumPy; fused C++ needs only block outputs and O(N) summaries. Chart scratch is O(N) per active sorting worker. The current chart kernel runs serially; executor workers partition path ranges only. Results are gathered in path order with at most `workers` futures outstanding. Thread counts do not change any random draw or path order.

Default API execution remains NumPy with one worker. The existing two-slot admission gate and API/solver path/horizon limits are retained. A gate is per process: two Uvicorn processes each have their own gate. Explicit multiworker contexts can therefore multiply process concurrency and should be configured with that in mind. No synchronous endpoint became `async def`.

## Replay scope and numerical tolerances

Version-1 artifacts store JSON and non-object NPY members with canonical dtypes, shapes, byte counts, file hashes, semantic input identity, calculation identity, environment/build metadata and output digests. Writers publish a complete temporary directory atomically. Readers reject partial captures, unknown members/schema, unsafe paths/symlinks, mismatched shapes/hashes and oversized content; `allow_pickle=False` is mandatory. Inputs include actual material draws/direct flows, deterministic flow, weights, scalar policy, and available known-flow/discretionary/portfolio arrays. No capture happens automatically in API calls.

Replay covers prepared cash paths, six summaries, strict cash-risk metrics and optional daily charts. Extra portfolio/discretionary inputs are retained for input diagnosis; external portfolio liquidation/LP solver outputs and authenticated application state are not replayed by this boundary. Existing estimator-specific numerical CLI/manifests remain available; this engine boundary explicitly implements the path estimator and does not claim initial-block CMC replay.

Input arrays and indices compare exactly. Selected reserves/chart quantiles and failure/breach masks compare exactly. Accumulated cash and dollar reductions compare with absolute tolerance 1e-9 dollars and relative tolerance 1e-12: native sequential dollar-day addition may differ from NumPy pairwise reduction. Broad tolerances never excuse a classification flip. Near-zero fixtures test strict cash failure separately from the existing app's 1e-6 solver-tolerance convention. Exact output hashes identify bytes within an environment; differing binary/source identity does not prevent cross-backend comparison.

Native inspection reports the actual site-packages extension path and SHA-256, API version, C++ compiler/options and source/kernel hashes. Source-tree use rejects a stale extension. Portable release flags disable fast-math and floating-point contraction; no CPU-specific tuning is enabled. Linux x86-64 is the locally validated platform; other compiler/platform combinations require their own differential and packaging checks.

## Measured results and default decision

The final run contains **180 verified records**: six synthetic workloads, full/summary outputs, old/NumPy/native-1/native-2/native-4 configurations, and three repetitions. Each fresh process performs one complete untimed warm-up. Configuration order rotates each repetition; BLAS/OpenMP thread counts are fixed to one. No timings use a profiler. [Raw repetitions](../benchmarks/quant-engineering/results/raw.jsonl), [stage summaries](../benchmarks/quant-engineering/results/summary.json), and [every workload/configuration](../benchmarks/quant-engineering/results/table.md) retain slower results as well as improvements.

Machine: Intel Core Ultra 7 256V, Linux 7.2.5 x86-64/glibc 2.42, Python 3.12.14; NumPy 2.5.3, pandas 3.0.5, SciPy 1.18.1, arch 8.0.0. Native: GCC 15.3.0, CMake 4.4.2, portable Release build, no fast-math/contraction, no additional compiler flags. Loaded binary SHA-256: `1dc76f80bcefd74633902c5ee2b8b9a03fccf4f813f9eece40a6a04b33e9003a`. Final source-content identity: `4d9cd4daeb9bd06825aa1a3f88e6443b742a0265600158fd6426a3bfc5b5822d`; the git commit alone still identifies the earlier release because these implementation changes are uncommitted.

Each cell is **median complete-evaluation milliseconds / peak process MiB**. Complete evaluation includes per-call preparation/validation/snapshots; separately timed history preparation and draw generation are listed in the raw stage data. Full outputs compare the entire `ScenarioMetrics` contract; summary outputs compare the same seven cash-risk/severity fields. The old implementation must materialize cash to supply those summary fields.

| Workload | Old | Improved NumPy | Native, one worker |
|---|---:|---:|---:|
| 2,000 × 30, normal, full | 28.15 / 143.4 | 32.69 / 142.6 | 31.83 / 142.4 |
| 2,000 × 30, normal, summary | 3.52 / 133.2 | 3.83 / 131.0 | 3.42 / 130.4 |
| 32,768 × 60, weighted, full | 747.36 / 325.0 | 330.12 / 285.6 | 306.05 / 285.6 |
| 32,768 × 60, weighted, summary | 45.09 / 279.1 | 34.00 / 222.3 | 18.99 / 222.7 |

RSS is the high-water mark across the worker's warm-up and measured stages, including what-if work and (for new implementations) capture/replay; it is **not isolated kernel memory**. Inputs/generation, Python imports and allocator retention can dominate. Explicit input/output/path-scratch bounds are in each raw row; [array bounds](../benchmarks/quant-engineering/results/array-bounds.json) also record the conservative chart bound (128 bytes per path per configured worker, although chart execution is serial).

For weighted 32,768×60 full evaluation, min–max across repetitions was 731.76–761.99 ms old, 327.73–350.74 ms NumPy, and 304.96–308.49 ms native-1. Native-2/native-4 medians were 323.45/326.87 ms: extra workers lost on that full workload. Summary medians for native-1/native-2/native-4 were 18.99/21.04/18.65 ms. These are three batch samples, not tail-latency estimates.

The 2,000×30 chart stage fell from 10.69 ms old to 3.62 ms NumPy and 2.89 ms native-1. However, owned preparation, validation and dependency bookkeeping made a **single small full evaluation slower overall**. Three compatible what-ifs took 84.24 ms old, 69.47 ms NumPy and 67.79 ms native-1. At weighted 32,768×60 those batches took 2257.88/553.32/530.06 ms. This is the observed benefit of sharing real calculation work; every implementation prepares its own inputs and each optimized implementation starts each batch with an empty context.

The original app pipeline at 2,000×30 (metrics, named funding behavior, provenance and response serialization; optimizer and outer uncertainty **off**, pre-generated draws, no HTTP) took 42.54 ms old, 48.39 ms NumPy and 48.10 ms native-1. Including history preparation and draws in full metrics evaluation took 32.00/36.64/35.72 ms. These small-workload regressions are retained. No claim is made about speeding up a solver- or uncertainty-dominated authenticated request.

**Decision:** keep `auto` on NumPy and ordinary requests at one worker. Native is a tested explicit backend with a meaningful large summary/full workload advantage; the current evidence does not justify automatically selecting it for small app requests or enabling more workers by default. The 32,768-path cases are offline scalability probes, above public API caps, not evidence of production traffic.

Supplemental [capture/I/O repetitions](../benchmarks/quant-engineering/results/io.json) include canonical portfolio/discretionary inputs. Capture I/O/metadata residual and replay load/validation medians (ms) were:

| Full artifact | NumPy capture / load | Native-1 capture / load |
|---|---:|---:|
| 2,000 × 30 | 17.93 / 4.99 | 20.99 / 5.31 |
| 32,768 × 60 | 84.70 / 53.57 | 81.06 / 47.78 |

The large full artifacts are approximately 64.8 MB. These warm-filesystem-cache measurements include hashes/metadata and owned loads; they are not storage-device throughput claims. There is no old artifact format to benchmark. Reproduce with:

```bash
uv run --no-sync python benchmarks/quant-engineering/measure_io.py --output /tmp/ginseng-io.json
```

## Validation and maintainer handoff

The initial suite passed 374 tests. The expanded suite covers independent hand calculations, exact CDF/zero boundaries, randomized history/direct inputs, 1/2/4 workers, non-divisor blocks, summary/full equivalence, native GIL progress, immutable ownership, malformed buffers/indices, memory guards, exception cleanup, actual funding/preview reuse, assumption invalidation, corrupted artifacts and deliberately perturbed path/summary/metric results. Existing authentication, API, workspace revision, scenario, funding, optimizer, Sobol, CMC and precision tests remain included. See [validation output](../benchmarks/quant-engineering/validation-tests.txt).

The standalone sanitizer command above completed with exit code 0, exercising 1,000 bounded randomized kernel cases, invalid indices and multiplication overflow under AddressSanitizer and UndefinedBehaviorSanitizer. The pure Python wheel was installed into `/tmp/ginseng-wheel-check`, replayed successfully while native was absent, then replayed successfully after installing the optional native wheel. Both packages loaded from that clean environment's `site-packages`, not a development `.so`. The checked-in [NumPy replay](../benchmarks/quant-engineering/replay-numpy.json), [native replay](../benchmarks/quant-engineering/replay-native.json) and [diff](../benchmarks/quant-engineering/replay-diff.json) agree on the synthetic example. Existing `simulate --fixture tiny --sampler sobol --estimator initial-block-cmc --paths 16` also remains runnable.

Diff array indices are zero-based: `index: [2, 4]` identifies the third path's fifth modeled day. A field-wise mismatch is reported before any large path dump; a summary-only mismatch reconstructs only its affected row. Invalid artifacts never reach numerical execution. A benchmark requires this repository checkout because its verified old-source archive is intentionally outside the installable core wheel. CI builds/tests both paths, replays the example, runs the sanitizer executable and performs a benchmark smoke test without a noisy speed threshold. No frontend files or response types changed, so no frontend build was required.

A maintainer can explain this release as follows: the financial calculation is unchanged, but preparation, execution and reduction now have explicit boundaries. One immutable set of typed inputs drives either a readable NumPy oracle or a C++ row loop that accumulates cash and summaries without creating every intermediate matrix. Batched inverse-CDF queries remove redundant sorting, and request-owned content identities let compatible policy/funding edits reuse paths safely. Bounded tasks preserve row order and input draws. Recorded arrays make a disagreement reproducible and locatable, while the measurements show where those systems choices help—and where their overhead makes a small request slower.

Final validation: **428 tests passed**, with two existing dependency deprecation warnings. Diagnostic counters describe prepared execution stages: `row_reductions` counts summary passes, and `orderings` counts managed chart/context queries. Scalar reserve/tail helpers still sort their transformed O(N) losses; the reserve sweep no longer scans the matrix. Restart Python processes after rebuilding/installing the native wheel; extensions are not hot-reloaded.

### Changed files

- Core: `execution.py`, `simulate.py`, `risk.py`, `metrics.py`.
- Consumers: `scenario_service.py`, `personal_forecast.py`, `forecast_api.py`, `api.py`, `funding.py`, `optimizer.py`, `numerical.py`.
- Offline tools and identity: `cli.py`, `engine_cli.py`, `engine_artifact.py`, `engine_benchmark.py`, `engine_benchmark_worker.py`, `provenance.py`.
- Build: `native/` (CMake, optional wheel, C++ kernels/bindings/sanitizer test), root `pyproject.toml` and `uv.lock`.
- Verification: `test_execution.py`, `test_engine_artifact.py`, `.github/workflows/quant-engine.yml`, `examples/engine/`, `benchmarks/quant-engineering/`.
- Handoff: this document and `README.md`. The unrelated untracked `ginseng-source.txt` was left untouched.
