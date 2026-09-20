# Decision Verification Lab — Prompt A

Implemented against the audited checkout, using the existing prepared engine and funding optimizer. **Prompts B and C are not part of this change.** Earlier precision/conditional-MC modules already in the repository were not modified. [Before-edit audit](decision-verification-audit.md).

## Behavior and integration

Previously, a successful funding solve went through production arithmetic and post-processing checks, but had no independent execution verifier or replayable decision manifest. Now:

- `optimizer.optimize_funding` independently checks the executable post-processed plan before returning `OptimalPlan`. `scenario_service.evaluate_funding` checks named candidates and gates optimized results again at the consumer boundary, so a mocked, altered or stale successful solve cannot become a recommended plan. A rejected plan carries `OptimizationFailure(reason="invalid_solution", verification=...)`; API/personal forecast consumers receive compatible verification/policy fields and diagnostics.
- `verification.py` has explicit `RiskContract`, `ExecutablePlan`, `RiskMetrics`, `ConstraintCheck`, `PlanVerification`, `SolverEvidence`, and `EvaluationIdentity` contracts. Its day-loop path arithmetic, account capacities, taxes/penalties, cash adjustments, weighted quantiles/tails and cost reconstruction do not call the solver, funding evaluator, quote calculator, production risk reducer or execution backend. It shares validated date primitives and immutable prepared inputs. Named-plan lot selection is resolved first, then its execution is independently checked.
- The verifier checks credit/withdrawal bounds and eligibility, remaining Roth contributions, earmarked charges, spending reductions, settlement, repayment through the material horizon, no invented cash, actual risk limits, cost and reported amounts, and executable-plan identity. Missing evidence is `unavailable`, not a zero residual. It also checks that post-processing did not increase cost beyond the declared numerical allowance and that an exported lower bound does not exceed independently executed cost.
- Existing web panels show numerical checks, probability policy, finite-scenario bound availability and frozen-holdout evidence. No new page was added. Shared response types were extended. `decision.funding_analysis` independently executes the frozen selection on fresh MC paths, and supplies a named fixed-size interval only for ordinary unweighted MC. Weighted stress reports explicitly omit that interval.

### Risk and compatibility decisions

| Quantity | Definition / unit |
|---|---|
| Cash failure | Probability of **any** end-of-day cash strictly below zero; recovery later does not undo failure |
| Buffer breach | Probability of any end-of-day cash strictly below the operating buffer; equality is not a breach |
| Mean buffer deficit | Expected sum of `max(buffer - cash, 0)` over modeled days, **dollar-days** |
| Tail buffer deficit | Weighted empirical CVaR of each path's largest nonnegative buffer deficit, **dollars** |
| Reserve | Existing inverse empirical CDF of required reserve from cumulative funded future flows **excluding opening cash**, dollars |
| Optimized loss | Mean or CVaR of interest, fees, earmarked taxes/penalties, spending forgone and APR-priced overdraft dollar-days; principal is not a cost |

The direct optimizer's intentional default remains `buffer × evaluation horizon × policy cash-shortfall probability`. The shared scenario service retains its existing coverage-based allowance and optional conservative signed-margin CVaR coverage requirement. Neither is silently replaced by a cash-failure chance constraint. Mean allowance, named tail limit and signed-margin CVaR are reported as separate mathematical constraints.

Legacy application `meets_policy` and probability fields retain their existing **$0.000001** cash/buffer threshold. New verification metrics and strict probability checks use **strict zero / strict buffer** boundaries and separately expose the legacy-boundary checks. Near-zero results may therefore have different strict and legacy statuses; this is deliberate, tested and labeled, not a changed historical field meaning.

The required adversarial example has buffer $100, 30 days and allowance 150 dollar-days. Every path is at -$1 for one day and $100 otherwise: mean deficit **101 dollar-days passes**, cash failure **100% fails**. A numerical `verified` label applies only to the specified finite-input checks and tolerances. It is not formal verification or a safety claim.

## Solver evidence

The existing HiGHS supporting-plane solver now retains iterations, termination reason, full-path candidate cost, master primal/complementarity residuals, numerical tolerances and a conservative Lagrangian lower bound. For the scaled minimization master `min c'x, Ax ≤ b, 0 ≤ x ≤ u`, nonpositive inequality multipliers give a bound `b'y + min(c-A'y, 0)'u` over bounded controls. The unbounded nonnegative epigraph requires nonnegative reduced cost; invalid evidence is unavailable. Financial values are converted back to dollars. These are floating-point numerical diagnostics, not interval-arithmetic proofs.

Bounds cover the supplied futures/weights and the **selected credit account / fixed continuous withdrawal-charge regime**. Global bounds across unexamined regimes remain unavailable. The Clarabel adapter reports its iterations and tolerances but **does not invent a lower bound or gap**. Solver/library versions, input/weight identities, resource limits, post-processing effects and local shadow-price units/signs are included. Raw solver objective is separate from executed cost.

[SciPy's `linprog` documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html) describes the negative RHS marginal convention. The synthetic sensitivity report uses exactly the same futures for each perturbation:

| Case | RHS increase | Predicted objective change | Observed change |
|---|---:|---:|---:|
| Active credit capacity | $1 | -$0.002000 | -$0.002000 |
| Credit step crosses active-set boundary | $100 | -$0.200000 | -$0.100000 |
| Inactive credit capacity | $1 | approximately $0 | $0 |
| Inactive mean-buffer allowance | 1 dollar-day | approximately $0 | approximately $0 |

The finite-step mismatch is retained. Additional tests compare the exported lower bound with the independently formulated one-variable LP: minimize `.24 x` subject to `.76 x ≥ 100`, `0 ≤ x ≤ 1000`.

## Frozen-model validation

`decision_lab.run_lab` prepares one fixed history/model, predeclares path counts and training replications, selects **training replicate 0**, freezes its actions, and only then generates validation. Independent initializations use the existing sampler's `SeedSequence([root, domain, method, replicate])` design: domain 710 for training and 711 for validation. Derivation and distinct keys/initial seeds are validated, not merely display names. This relies on PRNG stream independence; it does not assert that sampled historical blocks never coincide.

The selected plan and a predeclared no-action comparison share validation futures. No per-path reoptimization or validation winner selection occurs. Training replications report action/cost ranges without replacing the selected plan. Sampling and material horizons stay fixed within each workload, including repayment beyond the chart horizon.

Cash-failure intervals use SciPy's [fixed-sample exact Clopper–Pearson interval](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html). They are marginal per predeclared plan, not simultaneous, and never used for repeated-look stopping. Other losses are empirical estimates. Weighted/stressed estimates do not receive an iid binomial interval. Independent validation follows the distinction between sample optimization and population claims described in the [sample-average approximation guide](https://people.orie.cornell.edu/shane/pubs/SAAGuide.pdf).

The normal synthetic run has 2,000 training paths and 4,000 validation paths, 30 visible / **38 material days**. Training/validation mean deficits were **14.778 / 11.549 dollar-days**; tail buffer deficits **$144.006 / $117.100**. Both samples observed zero strict cash failures; validation's 95% interval was **[0%, 0.09218%]**. Replication withdrawals were **$3,165.32, $2,892.28 and $3,218.16**, with zero modeled training cost in each. This is consistent with a flat/nonunique optimum, not proof of an implementation error; selling principal still matters even when modeled cost is zero.

The offline stress run selects on 3,000×60 paths (180,000 optimization path-days) and validates on **32,768×60**, beyond the API's path limit. It observed **3 / 32,768** validation failures (**0.009155%**, 95% interval **[0.001888%, 0.026753%]**), despite zero training failures. Holdout mean deficit was **14.648 dollar-days**, tail buffer deficit **$131.137**. The mean modeled validation cost was **$0.00000580**. Outcomes are simulator-specific, not evidence of real-world calibration.

## Information timing

The existing historical backtest already truncated transactions by effective date and reconstructed training schedules. That logic was retained. It cannot infer when records arrived or were corrected. API and web results now explicitly say **retrospective using current records**.

`information_snapshot.py` freezes validated authorized `FinanceWorkspace` revision content into immutable bytes with an actual timezone-aware observation timestamp supplied by the caller. Selection at a cutoff only uses snapshots already observed. Tests add a late-arriving transaction with an earlier effective date, correct an old amount, and create a future bill after the decision; none changes the earlier captured information. Returned workspace copies cannot mutate the stored snapshot. This is an optional narrow capture helper, not an automatic historical archive, general bitemporal store or invented record-availability history.

## Capture and replay

`decision_artifact.py` wraps the existing `engine_artifact` format for training, validation and each successful diagnostic training replication. The root manifest preserves executable controls, risk contract, training/validation stream identities, exact prepared-input references, solver/verification results, calculation source, semantic input identity and output integrity separately. Engine members preserve actual history/indices or direct flows, schedule, weights and discretionary paths, plus dependency/backend/native binary/build/thread metadata. Incidental execution times are excluded from semantic identity.

Captures publish atomically. Personal capture requires explicit `allow_personal=True`; CLI fixtures and committed examples are synthetic. Load validates schemas, completion, hashes, sizes, safe fixed member paths, symlinks, numerical comparison contract, array headers/shapes and finite values before replay computation. Arrays use NPY with pickle disabled; manifests are bounded. All prepared captures share a 512 MiB file budget, with a separate conservative reference-array guard. Corruption is rejected before a result is computed.

Replay uses the exact stored futures and frozen actions without network calls, including successful replication plans, the paired no-action comparison and both fixed-sample intervals. It checks byte-exact identities separately from tolerance-based numerical outputs (`atol=1e-7`, `rtol=1e-10` for decision outputs; existing stricter engine conventions remain unchanged). It does **not re-solve the optimizer** or claim to reproduce nonunique coefficients, and it does not independently regenerate historical input reconciliation. Calculation version mismatch is rejected; differing source/backend provenance is retained and numerical differences are reported.

## Files and commands

New production modules: `verification.py`, `decision_lab.py`, `decision_artifact.py`, `decision_cli.py`, `information_snapshot.py`. Existing integration changes: `optimizer.py`, `funding_cuts.py`, `scenario_service.py`, `funding.py`, `policy.py`, `decision.py`, `cli.py`, `calibration.py`, `personal_forecast.py`. Web: shared `types.ts`, `analysis-types.ts`, `finance.ts` and existing `OptimalPlanPanel`, `FundingAnalysisPanel`, `ForecastBacktest` components. Tests: new verification/incremental/snapshot suites, existing optimizer/cuts tests and two web panel tests. A boot-screen visual fixture now uses fixed synthetic provenance instead of changing source hashes. Earlier Sakura TUI/studio work was preserved.

From the repository root, with existing development extras installed:

```bash
.venv/bin/ginseng decision run --fixture canonical --paths 2000 --validation-paths 4000 --replications 3 --output /tmp/ginseng-decision-demo
.venv/bin/ginseng decision replay /tmp/ginseng-decision-demo
.venv/bin/ginseng decision replay examples/decision-verification/canonical

# Separately labeled offline stress; the optimizer retains its existing cap.
.venv/bin/ginseng decision run --fixture canonical --paths 3000 --horizon 60 --validation-paths 32768 --replications 3 --output /tmp/ginseng-decision-stress

# Optional native backend, using the existing source and toolchain.
uv build native --wheel --out-dir /tmp/ginseng-a-wheels
uv pip install --no-deps /tmp/ginseng-a-wheels/ginseng_native-0.1.0-cp312-cp312-linux_x86_64.whl
.venv/bin/ginseng decision replay examples/decision-verification/canonical --backend native --workers 2

.venv/bin/pytest -q engine/tests engine/ginseng/ginseng_rice/tests
.venv/bin/python benchmarks/decision-verification/measure.py --output artifacts/decision-verification
```

Capture destinations must be new directories. CLI exit codes: **0** successful replay, **2** invalid/unsupported input or artifact, **3** numerical mismatch. A holdout policy/constraint failure is a reported scientific result, not an artifact mismatch or a suppressed outcome. API limits remain 3,000 demo paths / 365 visible days, personal 4,000-path limit and supported horizons 14/30/60, and the optimizer's 200,000 material path-day cap and time limit; the offline holdout is separately bounded by sampler/execution memory guards.

Web checks used the available Nix toolchain:

```bash
nix shell nixpkgs#bun nixpkgs#nodejs --command sh -c 'cd web && bun run test:optimizer && bun run test:analysis && bun run test:finance && bun run check && bun run build'
```

## Measurements, tests and limitations

See the following measured-results table and raw evidence links. Timings are unprofiled `perf_counter` measurements, three serial fresh processes per configuration, with BLAS/OpenMP thread counts fixed to one. Source extraction of the pre-A commit in a temporary directory makes the comparison reproducible without resetting the checkout. Each process performs both a cold solve (including solver import/initialization) and a second solve sharing its evaluation context. Process launch is outside these times. No p99 or CI speed gate is inferred from three repetitions.

Native kernels, batching, cache keys and sampling algorithms were not rewritten. Native builds and existing worker/ownership/index/stride/tie tests were actually run; sanitizers were not rerun because native source was unchanged. Prior engine benchmarks are evidence for that earlier release, not timing claims for this lab.

Limitations remain explicit: numerical tolerance checks, simulator assumptions, fixed prices/tax approximations and calendar primitives; no population-optimality/global-regime certificate; no Clarabel lower bound; iid intervals only for supported MC; retrospective legacy history; optional snapshots require actual captures; frozen-execution replay rather than solver rerun; whole-process RSS rather than isolated allocation overhead. No live finance execution, production deployment, safety or hiring claim is made.

### Measured medians (milliseconds)

| Stage | Normal NumPy | Normal native | Offline stress NumPy | Offline stress native |
|---|---:|---:|---:|---:|
| History preparation | 3.080 | 3.057 | 3.058 | 3.063 |
| Training draw generation | 2.031 | 2.077 | 4.954 | 4.944 |
| Prepared scenario + action inputs | 2.610 | 2.613 | 3.274 | 3.303 |
| Cold path summaries | 1.716 | 0.543 | 2.897 | 0.937 |
| Reused path summaries | 0.124 | 0.121 | 0.125 | 0.127 |
| Cold optimization including independent gate | 120.193 | 120.226 | 137.441 | 138.296 |
| Standalone independent verification | 4.114 | 4.153 | 8.474 | 8.533 |
| Two extra training solves, preparation and verification | 122.460 | 120.922 | 167.720 | 165.480 |
| Validation draw generation | 3.728 | 3.785 | 57.928 | 58.263 |
| Holdout preparation + selected/no-action execution | 35.424 | 35.113 | 252.908 | 255.628 |
| Artifact capture (including training replications) | 84.396 | 76.575 | 163.668 | 123.037 |
| Full offline replay | 74.627 | 77.022 | 373.470 | 360.080 |
| End to end including capture/replay | 460.411 | 451.360 | 1194.972 | 1129.748 |

| Optimizer comparison | Previous NumPy | Current NumPy + verifier | Current native + verifier |
|---|---:|---:|---:|
| supported cold | 98.939 | 123.860 | 121.875 |
| supported reused | 22.701 | 41.194 | 42.296 |
| offline_stress cold | 111.037 | 140.234 | 138.787 |
| offline_stress reused | 28.625 | 54.135 | 53.972 |

The verifier adds measurable overhead. Native summaries are faster; the full solver workflow is dominated by Python preparation, independent checking and solver work. Native losses in individual stages remain in the table. These are not claims of a new engine speedup.

| Peak whole-process RSS | Normal NumPy | Normal native | Offline stress NumPy | Offline stress native |
|---|---:|---:|---:|---:|
| Median MiB | 171.691 | 170.801 | 353.520 | 353.586 |

RSS includes interpreter/imported dependencies, NumPy, native and solver memory; allocator high-water marks are not an isolated lab-allocation measurement. All 12 complete lab measurement runs replayed without mismatches. The isolated optimizer comparison preserves objective and feasibility on byte-identical training draws.

Raw evidence: [measurements](../artifacts/decision-verification/measurements.json), [baseline tests](../artifacts/decision-verification/baseline-tests.txt), [full tests](../artifacts/decision-verification/final-tests.txt), [web checks](../artifacts/decision-verification/web-checks.txt), [actual CLI demonstration](../artifacts/decision-verification/demo-run.json), [native cross-backend replay](../artifacts/decision-verification/demo-native-replay.json), [native binary inspection](../artifacts/decision-verification/native-inspection.json), and [synthetic decision manifest](../examples/decision-verification/canonical/decision.json).

Final validation: **524 Python tests**, including **37 terminal snapshots**; **13 optimizer-panel + 3 analysis-panel + 7 finance-store tests**; Svelte check with zero errors/warnings; successful static production build. The Python suite retains two upstream dependency deprecation warnings. Targeted lint/import checks (`ruff --select I,F,E9,UP`) and `git diff --check` pass. Full raw outputs are linked above.

For the isolated optimizer workers, median whole-process RSS was supported: previous NumPy 157.34 MiB, current NumPy 159.70 MiB (difference +2.36 MiB), current native 159.38 MiB; offline_stress: previous NumPy 169.51 MiB, current NumPy 175.22 MiB (difference +5.71 MiB), current native 175.21 MiB. These differences include imports and allocator behavior; they are descriptive process overhead, not a precise causal allocation measurement.
