# Prompt A checkout audit — 20 September 2026

Source instruction: `/home/xelo/Downloads/Ginseng-Professional-Quant-Dev-Codex-Plan(1).md`, Prompt A only. B/C are excluded. Checkout base: `78b599e1508c6f8cc823762b70d9b13d874a3526`. The pre-existing uncommitted Sakura TUI, studio, dependency and snapshot changes are retained. No applicable AGENTS.md was found in the repository or ancestor directories; `.agents` and `.codex` contain no instruction files. Root/native pyproject files, uv lock, web package/lock, and `docs/quant-engineering.md` were inspected.

## Observed implementation before changes

| Area | Evidence and disposition |
|---|---|
| Bootstrap/direct execution | `simulate.py`, `sampling.py`, `execution.py`: joint history, material indices/direct prospective flows, deterministic schedules and visible/material horizons already work. Reuse them. |
| Prepared ownership/reuse | `PreparedScenario.__post_init__`, `snapshot`, `EvaluationContext`, `prepare_scenario`: bytes-backed immutable snapshots and content-based request-local caches, not just frozen dataclasses or seed keys. Covered by `test_execution.py` including scalar edits, real forecast previews, ownership and invalidation. |
| Independent execution reference | `execution.numpy_block` is independent of the optional C++ kernel; existing `test_execution.py` exercises legacy comparisons and hand cases. It is not an independent verifier of funding actions. |
| Native backend | Native source/build, hash checks, binary inspection, worker limits and tests exist. **The current environment reports native unavailable**; three baseline native tests skip. The earlier report and stored raw results describe an earlier loaded binary, not this process. Build/recheck separately; no C++ rewrite is needed. |
| Engine artifacts | `engine_artifact.py`, `engine_cli.py`, actual `cli.main`: typed NPY+JSON, atomic publication, content/shape/size/path validation, offline replay/diff. Already stores material inputs, weights and optional discretionary inputs. Tests pass. Does not yet replay decisions. |
| Risk | `risk.py`, `metrics.py`: weighted inverse CDF, tied fractional tails and q=1, dollar-days and probabilities already exist. Numerical/engine artifact failure uses strict zero; app `balance_risk` uses a 1e-6-dollar threshold. Preserve and disclose this compatibility boundary. |
| Optimizer | `optimizer.py`: existing convex continuous allocation LP, Clarabel and HiGHS supporting planes, post-solve recomputation, withdrawal reconstruction/trimming, mean-dollar-day constraint, optional signed-margin CVaR constraint and tail-deficit constraint. No new optimizer is needed. |
| Solver evidence | `funding_cuts.py` computes a master lower bound and compares full-path cost but discards the lower bound/residuals on return. Iterations do not reach `OptimalPlan`. Clarabel does not expose a validated global bound through the current adapter. Report missing evidence explicitly. |
| Funding/policy | `funding.py`, `withdrawals.py`, `policy.py`, `scenario_service.evaluate_funding`: settlement/repayment, earmarked charges, Roth remaining basis, common horizons, independent policy ranking already exist. Internal recomputation shares production helpers and is not a separate verifier. |
| Selected-plan analysis | `decision.py`: already evaluates a frozen optimized plan on a newly seeded legacy bundle, plus shadow checks/frontier. No explicit versioned train/validation stream contract, binomial interval, replication stability or decision capture. Reuse the plan semantics, strengthen this boundary. |
| Actual consumers | `scenario_service.py`, `api.py`, `personal_forecast.py`, `forecast_api.py`; frontend `types.ts`, `OptimalPlanPanel.svelte`, `PlanTable.svelte`, `FundingAnalysisPanel.svelte`. Add compatible status/evidence fields here, not a new page. |
| Historical evaluation | `calibration.training_state` already truncates transactions at the effective-date cutoff and reconstructs recurring schedules from prior observations. `personal_forecast.backtest_personal_history` uses that code. Records lack arrival/revision timelines: this is retrospective with current records, not a point-in-time archive. Workspace revision snapshots exist and can support narrowly scoped frozen-information fixtures. |

## Baseline runs, before implementation edits

`pytest -q` over execution, artifact, cuts, optimizer/contract, decision, unified funding, personal forecast and calibration tests: **129 passed, 3 skipped**, two existing dependency deprecations, 17.66 s. Full stdout: `artifacts/decision-verification/baseline-tests.txt`. No baseline test failure was observed.

Two cProfile runs covered metrics plus optimizer, synthetic canonical repair scenario: 2,000×30 returned OptimalPlan; 32,768×60 returned the expected optimizer `resource_limit` (200,000 path-day cap). Profile wall totals were 0.278 s and 0.431 s; these include profiler/import overhead and **are not benchmarks**. Draw generation preceded profiling. The larger fixture is an offline execution probe, not a supported optimizer/API size. Top costs: dataclass/content preparation/imports on the normal case; inverse-CDF orderings/charts on the large case. Raw `.prof`, text summaries and environment/source identity are in `artifacts/decision-verification/baseline-*`.

## Release boundary

Implement a separate pure reference action verifier, explicit risk/check/evidence contracts, consumer gating, fixed-size independent MC validation with frozen controls, decision manifests wrapping the existing prepared artifacts, and information-snapshot tests/retrospective labels. Retain optimizer mathematics, sampler definitions, cache ownership and native kernels. Existing sequential precision features are pre-existing work; no Prompt B changes are planned. No Prompt C model extension is planned.

## Findings resolved and remaining boundaries

The optional existing wheel was built and installed during this task; real native execution now passes ownership/index/shape/worker tests and cross-backend decision replay. Loaded binary hash/build details are recorded in `artifacts/decision-verification/native-inspection.json`. No native source changed, so sanitizers were not rerun.

The independent verifier exposed a legacy optimizer test whose mocked production cash matrix was inconsistent with its prepared inputs. That fixture now supplies equivalent genuine direct paths; a separate adversarial consumer test proves that an inconsistent mocked successful plan is rejected. There was no baseline production failure concealed by changing this test.

The first full post-change run had one boot-screen snapshot mismatch because its visible source-code hash changed with new files. The visual test now supplies fixed synthetic provenance; production hashing remains unchanged. Final full-suite output records 524 passes / 37 passing snapshots; follow-up targeted tests cover the final report/artifact checks. Two existing dependency deprecations remain.

Implemented scope and measurements are in `docs/decision-verification.md`. Missing global-regime/Clarabel bounds, real-world calibration, automatic historical availability archives, full optimizer re-solve replay, and native sanitizer reruns are explicitly not claimed. The current engine's sampler, native kernels, prepared ownership and content-based invalidation were reused. Prompt B and C work was not added.
