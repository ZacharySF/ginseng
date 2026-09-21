# Prompt B audit — 20 September 2026

Scope: Prompt B in the downloaded `Ginseng-Professional-Quant-Dev-Codex-Plan(1).md`. Prompt A and the earlier Sakura TUI edits are preserved. No Prompt C work. No applicable AGENTS.md was found. Build configuration and lockfiles remain those of the audited checkout.

Baseline command: `.venv/bin/pytest -q engine/tests/test_precision.py engine/tests/test_conditional.py engine/tests/test_numerical.py engine/tests/test_risk_explorer.py`: **83 passed**, two dependency deprecations, 4.79 s. Raw output: `artifacts/precision-b/baseline-tests.txt`.

Already working:

- `precision.py`: stable bounded moments; Maurer–Pontil Theorem 4, two-sided empirical-Bernstein intervals with telescoping `alpha/[k(k+1)]` spending; predetermined doubling looks, partial final cap, conservative distance-to-endpoints stopping. This is already valid under the stated iid assumptions; it is not an ordinary repeatedly inspected binomial interval.
- `sampling.py`: ordinary MC and complete scrambled Sobol nets; fixed material coordinate width, immutable draws, seed domain separation. Existing advancing PCG64 precision batches preserve the stream for a fixed material layout. Changing material width changes layout; it must not be presented as an invariant extension.
- `conditional.py`: initial-start conditioning integrates over the complete historical start distribution, retains actual restart lengths, handles strict boundaries and has independent all-start tests. Independent ordinary-MC rows give independent fractional observations of the same target. Sobol points are not iid observations.
- CLI `precision`, authenticated `/demo/numerics` and `/finance/numerics`, `NumericalRiskPanel.svelte`, and TUI/studio adapters already consume precision results. The web consumer currently hardcodes CMC, 95% confidence and its checkpoint/batch plan.
- Existing precision benchmarks and exact-Bernoulli recursion tests are implementation evidence. Their old documentation incorrectly says web integration is absent; do not repeat that finding as current.

Gaps to address: standardized supported/unsupported statuses and model identity; time/resource budgets and cooperative cancellation; explicit running-intersection/numerical-failure handling; decoupled execution chunks from declared looks; tested versioned random-access/prefix contract and vectors; bounded exact-input precision capture/replay; caller-specified web controls; fixed-budget versus adaptive comparisons including rare events and difficult probabilities.

Design decision: retain the existing empirical-Bernstein construction after checking its primary-source theorem, and retain PCG64 with its existing domain and fixed material layout. A counter-based replacement is unnecessary: `advance` can address complete float64 rows in this existing layout. Expose layout changes honestly. Reuse prepared engine artifacts and kernels; no optimizer or forecasting-model rewrite.

Completion evidence: `artifacts/precision-b/final-tests.txt` records 538 passing tests and 37 snapshots; `final-focused-tests.txt` records 69 passing precision/consumer checks. `final-web.txt` is the final successful web check/build/store/browser run. Earlier `browser.txt` records a regression-test discovery: the new select controls needed explicit accessible names for exact label lookup; those names were added and the final browser test passed. The original 1 KiB memory test allowed one observation per chunk and correctly exhausted time; its final fixture uses a 512-byte execution budget to exercise immediate memory exhaustion. See `docs/precision-b.md` for measured results and remaining limits.
