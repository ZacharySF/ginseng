# Engine review — 13 September 2026

The engine already has real quantitative structure: a dependent bootstrap, weighted empirical quantiles and fractional CVaR tails, an LP over funding controls, account-specific net proceeds, shared plan horizons, and frozen-action checks on fresh simulations. The most useful next work is to make the risk promise, available actions, and numerical evidence agree.

This is a review and proposed implementation order. It does not change the optimizer's policy or introduce new tax constants. Findings refer to the account-withdrawal implementation published in PR #6, commit `ec8cc2f`.

## 1. Give every plan the same explicit risk contract

**Finding.** `optimizer.py` minimizes CVaR of financial cost subject to a mean buffer-dollar-day limit and an optional tail-deficit limit. `policy.py` separately gates named plans at 5% cash-shortfall probability and 30% credit utilization. The coverage target also selects a reserve quantile. These are different restrictions on different quantities. A solver status of `optimal` only says that its own formulation was solved.

Reproducible example: default persona and seed 20260911; a $30,000 bill on day 7; 2,000 paths; 30-day chart and 38-day funding evaluation; 95% coverage parameter; $1,000 buffer.

| Constraint | Cost CVaR | Cash-shortfall frequency | Buffer-breach frequency | Gross withdrawal |
| --- | ---: | ---: | ---: | ---: |
| Default mean limit, no tail limit | $193.72 | 21.55% | 41.25% | $24,240.57 |
| Positive tail-deficit limit of $0 | $2,391.50 | 0% | 0.05% raw, at floating-point tolerance | $30,928.04 |

The first result is consistent with the implemented mean limit. It is not a plan satisfying 95% no-breach coverage. The second essentially protects every optimization path, which is stricter than allowing 5% failures. The tiny displayed breach in that row is discussed below.

**Proposal.** Define one `RiskPolicy` with distinct meanings for coverage, dollar severity, duration, utilization, and the policy's evaluation horizon. Apply it to both named and optimized plans. Report `solved`, `meets_policy`, and `passes_fresh_simulation_check` separately. A policy-failing solution can remain visible as a tradeoff, but should not be promoted as an acceptable recommendation.

For an LP-compatible conservative coverage constraint, use the **signed** worst buffer margin:

`L_j = max_t(buffer - balance[j,t])`

Unlike a nonnegative deficit, `L_j` is negative when a path has slack throughout. Requiring `CVaR_q(L) <= 0` implies `VaR_q(L) <= 0`, hence no breach in at least q of the weighted optimization scenarios. This is a conservative substitute for an exact scenario chance constraint; it is not a guarantee about the real world. Keep `CVaR_q(max(0,L))` separately as the severity metric. Setting this nonnegative quantity to zero instead forces every positive-weight scenario to have no deficit.

**Acceptance checks:** easy hand-calculated scenarios distinguishing frequency from severity; identical policy acceptance across both plan evaluators; q monotonicity; weighted atoms and q=1; finite-difference checks for any new constraint dual.

## 2. Make credit and dates represent actions the household can take

**Finding.** The credit lever currently adds bank cash today and prices it with the primary card's purchase APR and grace rules. A purchase credit limit does not automatically represent an available bank-cash advance. The model card discloses this simplification, but disclosure does not make every funding action executable. Monthly baseline obligations also use `recurrence_days=30`, while settlement and transfer use three calendar days.

**Proposal.** Separate a cash line/advance from paying an eligible bill by card. For the card option, constrain the amount by the eligible unpaid bill, attach the charge to its actual date, and put the resulting repayment on the correct statement. For cash advances, record the advance limit, fee, APR and availability date explicitly. Do not infer these from the purchase limit.

Represent monthly bills with a calendar recurrence and an explicit month-end convention. Use a local, versioned business-day calendar where relevant, plus a separate transfer delay. An offline calendar or a disclosed delay assumption is sufficient; no runtime tax-data request is needed.

**Acceptance checks:** a rent bill marked ineligible cannot be card-funded; an advance cannot use purchase grace terms; month ends, February, weekends and late transfers; cash before settlement cannot pay an earlier bill; every candidate still shares the resulting evaluation horizon.

## 3. Publish a numerical certificate and use one boundary convention

**Finding.** The large-scenario solver checks every path and bounds the objective gap, but the API exposes only its method/status rather than the lower bound, residuals and iteration count. The final risk metrics use strict comparisons while solver feasibility accepts a small numerical tolerance.

In the zero-tail example above, reported training tail deficit is approximately `$7.28e-14`, yet raw `< buffer` counts one of 2,000 paths as breaching. This is rounding at the mathematical boundary, not an economically meaningful shortage.

**Proposal.** Return objective value and lower bound, absolute/relative gap, largest constraint residual, scale, iteration count and termination reason. Use one documented money/tolerance convention in solver checks, final policy gates and displayed breach counts. Preserve the raw residual so the tolerance cannot hide material shortfalls. Do not silently round or relax a real $1 shortage.

Retain the current full-LP-versus-supporting-plane equivalence tests. Add metamorphic checks: duplicating paths with half weights leaves the decision unchanged; increasing available resources cannot increase the optimal objective; relaxing a risk limit cannot increase it; postprocessing preserves feasibility and cost within the certificate's tolerance. Degenerate equal-cost solutions should use an explicit lexicographic rule, not a hidden penalty weight.

## 4. Separate decision stability, model uncertainty and historical validation

**Finding.** Fresh simulations currently evaluate the base optimized mix, while displayed frontier points are optimized on the training scenarios without their own fresh evaluation. The fresh result is descriptive and does not automatically gate recommendations. The outer reserve band has 50 historical resamples and is widened to include the point estimate; its stated meaning is an estimate range, not calibrated coverage.

The zero-tail $30,000 plan above breaches the buffer in 0.3% of a fresh 2,000-path draw (seed 11739), with $15.24 tail deficit. A plan that satisfies a finite scenario sample need not satisfy another sample, even from the same historical model.

**Proposal.** Evaluate the selected frontier point with its actions frozen on untouched scenarios, label the selection procedure, and avoid choosing among many points using the final evaluation sample. If validation is repeatedly used to tune choices, reserve a separate final test sample. Measure policy violations, cost differences and action variation across independent simulation seeds. Use those results to disclose stability, not to claim new historical evidence.

Separately compare walk-forward forecasts against simple baselines: recent observed-month requirements and a calendar cash schedule. Report paired pinball/CRPS differences, window counts and dependence assumptions. Record outer-bootstrap settings and Monte Carlo variability; do not label a widened percentile band as a nominal confidence interval. More numerical precision does not establish calibration.

## 5. Preserve scenario prefixes and test calendar structure

**Finding.** Using the same seed with 30 versus 60 days does not preserve the first 30 simulated days; using 2,000 versus 3,000 paths does not preserve the first 2,000 paths. `_stationary_bootstrap_indices` consumes shape-dependent random arrays. Same-bundle plan comparisons are already valid; changes to simulation controls currently mix a model change with a fresh draw.

**Proposal.** Give restart decisions and restart indices separate streams, with deterministic per-path streams or a documented maximum-size draw cache so horizon and path-count extensions preserve prefixes. Test the prefix contract explicitly and keep draw/version hashes.

The bootstrap also starts at arbitrary historical calendar positions. Test whether weekday, invoice and month-end timing matter out of sample before adding complexity. A payment-arrival model plus a conditional payment-size model is more interpretable for sparse income than fitting two Gaussian states to raw daily zeros and spikes. Fit additional structure only if it improves held-out scoring and retains adequate effective history.

## 6. Make market risk affect a decision at the time it is observed

**Finding.** Current withdrawals execute today at recorded prices, so future market returns correctly do not change their proceeds. Once the required net withdrawal is fixed and all accounts have the same availability date, selecting account/lot amounts reduces to a bounded allocation by charge per net dollar. Adding more instrument-level statistics will not by itself make that optimization respond to future market risk.

**Proposal.** After the correctness work above, compare selling now with a specified later review date. Later actions must depend only on information observed by that date. In a scenario tree, scenarios with the same observed history share the same decision; choosing a separate action for each fully revealed future would grant impossible foresight.

Track cash, remaining holdings, contributions already withdrawn, debt and earmarked tax reserves together. Use the market price at each execution date and carry proceeds through settlement. Expose liquidity cost and retained terminal resources as separate tradeoffs or an explicit utility assumption. Do not introduce an unexplained penalty on withdrawals simply to make the output look less obvious.

This is where joint cash/market scenarios can influence a timing decision in a mathematically coherent way. It is a larger follow-up, after a consistent risk policy, executable funding actions and trustworthy numerical reporting.

## Suggested next implementation

Start with the shared risk contract and boundary convention. They directly affect whether a displayed plan means what a user thinks it means. Then implement credit eligibility and calendar timing, followed by reproducible scenario prefixes and selected-plan stability checks. Adaptive liquidation is the later quantitative extension.
