# Ginseng model card — model version 0.3.0

**More simulations improve numerical precision. They do not create more historical evidence.** The demonstration still has 730 days of synthetic history, whatever the requested simulation count.

## Purpose and data

This model compares hypothetical ways to fund future expenses. It does not execute trades or borrowing, compute a final tax return, or establish validated coverage for a real household. The personal workspace supports scheduled, prospective assumption-based, and historical-bootstrap forecasts from its own inputs. The demo and published numerical benchmarks use clearly labeled synthetic histories; the offline CLI also accepts a complete local input window. Both surfaces use the same funding evaluator, tax assumptions, risk acceptance rules and comparison-horizon construction.

Funding recommendations must satisfy the selected probability of preserving the buffer throughout the common evaluation period, in addition to the cash, utilization, mean-deficit and optional tail-deficit limits. Feasibility, policy acceptance and solver status are separate fields. Existing utilization above a ceiling does not prohibit a plan that takes on no new debt.

The optimizer imposes a conservative convex coverage constraint: `CVaR_q(max_t(buffer - balance_t)) <= 0`. The margin is signed, so paths that remain above the buffer contribute negative values. This implies the requested empirical no-breach coverage; it does not guarantee future household outcomes. Named plans are checked against the same observed coverage requirement. A micro-dollar numerical tolerance is used for breach counts and boundary checks; raw severity remains available.

The optimizer selects account and lot amounts by withdrawal cost. The named taxable plans follow the saved FIFO/HIFO rule. The interface discloses this difference; rates, scenario weights, evaluation horizon and discretionary-reduction horizon agree across the comparison.

Personal cash advances require an explicit available limit, APR and fee. A purchase limit alone supplies no cash. Fees are withheld from proceeds today, interest has no purchase grace period, and principal plus interest is repaid at the saved statement due date. This models an advance available today, not paying an arbitrary bill directly by card. Only one eligible credit account is selected, using capacity after the utilization ceiling.

In assumptions mode, payment arrival and payment size are separate. The default two expected payment days per month is a visible policy assumption. Independent daily Bernoulli arrivals retain zero-pay days; mean-preserving lognormal payment sizes are scaled so the stated monthly income remains its expectation. Monthly income is not guaranteed. Persistent size shocks and their correlations remain explicit assumptions. Known invoice dates belong in scheduled events.

The income-history helper uses complete declared calendar months, including months with no variable income. It estimates monthly mean income and payment-day frequency separately from variability in positive daily payment totals. Monthly total variability is shown descriptively and is never applied as payment-size variability. Multiple payments on one day are combined. With only one observed payment day the existing size assumption is retained; otherwise size variability is capped at 200%. Frequency is rounded to 0.01 and capped at 30 days per month. Applying these estimates is an explicit draft edit; it does not switch the model source or establish future calibration.

Personal historical validation measures the starting-cash reserve needed throughout each held-out period, with routine fixed flows inferred only from earlier records. It starts with 90 training days, reports at most 48 non-overlapping primary windows, exact binomial reference intervals, pinball loss, CRPS and randomized PIT. Overlapping windows are descriptive only. Non-overlap does not establish independence, and formal tests remain disabled when underpowered. The synthetic demonstration retains its 365-day initial training window.

Personal scenario edits coalesce while a request is running and obsolete results cannot become ready. The personal client allows 45 seconds for baseline plus preview, each with a 10-second solver budget; historical diagnostics allow 60 seconds. Personal and demo endpoints share a two-request admission limit. Unavailable optimization leaves named plans and a readable reason on screen.

Apply `0005_unified_funding_inputs.sql` before using the new personal input fields. It extends the existing validators without replacing ownership or revision controls. Old records remain readable; unclassified retirement holdings stay restricted and missing cash-advance limits default to zero. The personal editor records Roth contributions separately from investment purchase basis. No tax constants are fetched at runtime.

The persona contains daily variable income, routine essential and discretionary spending, monthly fixed flows, credit terms, taxable lots, and market history. Added asset histories are also synthetic. Their common market component and idiosyncratic components are explicit simulation assumptions, not measured relationships in a user's bank data.

The API returns the actual historical window, simulation count, model version, assumptions, limitations, and fingerprints with every scenario. Missing or duplicate asset-return dates disable the asset-level analysis. Missing aggregate observations are not silently filled with zero returns.

## Reserve and coverage

For each future, the predicted quantity is the starting cash needed to preserve the operating buffer at every modeled end-of-day balance:

`R = max(0, max_t(buffer - cumulative_net_flow_t))`.

The reserve is the inverse empirical CDF at the chosen coverage target. It selects an observed requirement whose cumulative probability reaches the target. This replaces linear interpolation, which could advertise a reserve below the requested empirical coverage in a small or discontinuous sample. Quantiles may stay constant over several target settings.

Immediate cash divided by reserve is the displayed resource ratio. Investments require a separate sale and are not added to cash to manufacture a household liquidity ratio. This is not a Basel-compliance measure.

A bill that hits every future can correctly move the reserve approximately dollar for dollar. Entropy pooling changes weights, not that identity. The generator no longer requires a non-additive repair response as an acceptance criterion.

## Funding decisions

Named plans and the optimizer share an evaluation horizon, bootstrap indices, and scenario weights. The horizon includes the available credit lever's repayment date, sale settlement, and applicable trailing days, including when a stricter deficit limit triggers optimization without a reserve gap. Credit payment dates use actual calendar occurrences after statement close instead of adding 30 days.

The hybrid adds new liquidation proceeds, credit, and actual resampled spending reductions. Existing cash has already reduced the gap and cannot fund it a second time. When every named plan violates its hard policy limits, no plan is marked recommended. The least-risky failing option may be described, but is not promoted to a recommendation.

The cost objective includes modeled interest, account-specific tax and penalty reserves, forgone discretionary spending valued dollar for dollar, and negative-cash dollar-days priced at the configured overdraft APR. Investment-sale principal is not itself a cost. A zero-cost solution can therefore involve a substantial sale. These are selected cost components, not a prediction of total future wealth or investment performance.

Sales execute today at recorded holding prices. Spendable proceeds arrive after settlement and transfer, after setting aside the assumed tax and penalty reserve; subsequent market moves do not reprice sold shares. The demo uses a disclosed **three-calendar-day approximation** for settlement plus transfer and purchase APR as a cash-bridge proxy. Personal plans use their saved settlement and transfer delays, count weekdays when selected, and require explicit cash-advance terms. Neither mode models exchange holidays.

Four separate quantities must not be confused:

- The reserve coverage target is an empirical frequency target for starting cash.
- Funding recommendations also apply the selected buffer-coverage target. The optimizer uses the conservative signed-margin CVaR constraint described above.
- The mean-deficit constraint limits **mean buffer deficit dollar-days**. Its default is buffer × evaluation days × (1 − coverage target), independent of the simulation count.
- The optional **tail-deficit limit** constrains CVaR of each future's largest dollar deficit below the buffer. It is a severity constraint, separate from the mean dollar-day constraint and separate from the CVaR cost objective.

For nonnegative deficits, a zero tail-deficit limit requires every positive-weight scenario to preserve the buffer. A positive limit does not promise zero buffer breaches in 95% of futures. CVaR below a dollar threshold conservatively bounds VaR at that same threshold; it does not automatically bound breaches of a different threshold, such as zero.

All reported VaR and CVaR values are recomputed from the selected actions' actual losses. Fractional tail mass is used when the target cuts a scenario's probability, and ties at the cutoff share the remaining mass proportionally. At 100% the calculation reports the empirical maximum. See the original [Rockafellar–Uryasev publications](https://uryasev.github.io/publications/) for the convex formulation.

## Account types and withdrawal assumptions

The optimizer distinguishes **taxable brokerage, fully pretax traditional IRA, and Roth IRA regular contributions**. The same investment can live in different wrappers; the wrapper changes how much of a withdrawal can fund a bill. Existing unclassified `retirement` holdings remain unavailable until their wrapper is known.

Constants live in `engine/ginseng/withdrawals.py`, version `ira-withdrawals-2026-v1`. They are bundled with the engine; no IRS or other rules lookup runs on the forecast path. Static source links are displayed for review, not fetched by the model.

- **Ordinary income / short-term gains: 24%.** A selected demonstration marginal federal rate, not inferred from income, filing status, or an annual tax-bracket calculation.
- **Long-term positive gains: 15% by default.** A selected marginal rate; the existing request override is displayed when supplied. Each lot must have been held more than one year. Exactly one year remains short-term. These rules are referenced to [IRS Tax Topic 409](https://www.irs.gov/taxtopics/tc409).
- **Traditional early distributions: 10% penalty in addition to ordinary income tax.** The demonstration assumes age 35, no exception, and no nondeductible IRA basis. The whole distribution is pretax, regardless of the holding's investment gain. See [IRS Tax Topic 557](https://www.irs.gov/taxtopics/tc557). A $1,000 withdrawal therefore earmarks $240 tax plus $100 penalty, leaving $660 spendable under these assumptions.
- **Roth regular contributions: 0% tax and 0% penalty within remaining contribution basis.** Access is capped by both the current Roth account value and recorded, unwithdrawn regular contributions across Roth IRAs. Investment purchase basis is a different quantity and never substitutes for this record. The synthetic persona supplies $1,200 of remaining contributions. Earnings and conversions are excluded because their qualification and ordering history is not modeled. See the distribution ordering rules in [IRS Publication 590-B](https://www.irs.gov/publications/p590b).
- **Availability: explicit settlement plus transfer delays.** The demo assumes one settlement day plus two transfer days, counted in calendar days. Personal plans use their saved delays and calendar/weekday setting; neither mode includes exchange holidays. Tax and penalty amounts are immediately earmarked from proceeds for planning; this is not a claim about actual withholding or the date a tax bill is due.

Every cash-path constraint uses **net spendable proceeds**, and the objective prices the tax/penalty charge. Named taxable plans gross up sales to raise their intended net contribution. Fresh-simulation checks keep the chosen lots and Roth contribution amount fixed, so they cannot silently choose a cheaper account when evaluating the result.

Equal-cost allocations prefer taxable funds, then Roth contributions, then traditional withdrawals. This is a disclosed tie-break; there is no invented dollar penalty for touching retirement assets. Future tax-sheltered growth is not priced. State taxes, NIIT, bracket crossings, loss netting/deductions, basis in nondeductible traditional contributions, exception eligibility, and employer-plan withdrawal rules are excluded. These are conditional planning estimates, not a final tax calculation.

## Numerical evidence and historical evidence are separate

The offline numerical release adds an independent exact 81-sequence oracle and measured MC-versus-scrambled-Sobol experiments. See [numerical definitions](numerical-model.md), [benchmark methodology](benchmark-methodology.md), and [measured results](benchmark-results.md). Exact agreement verifies the implementation on a small model. Independent simulation replicates measure numerical precision conditional on fixed history; the existing outer bootstrap instead measures sensitivity to the finite historical sample. Neither is held-out household forecast validation.

The personal-history walk-forward backtest evaluates an 80% interval for terminal variable-flow change. It is not a 95% liquidity-reserve coverage test. The separate reserve calibration module evaluates reserve-related targets as described below, with its synthetic-source and dependence qualifications. Both integrations remain present.

The busy/dry chain in `generate.py` generates synthetic history; it is not a fitted live regime model. Resampling cannot establish the probability of an unseen economic regime, although stitching observed blocks can produce drought-shaped sequences and cumulative outcomes absent from any one contiguous historical window.

## Reserve calibration on historical windows

Demonstration walk-forward checks reserve the first 365 days for training; personal checks use 90 initial training days. A 30-day horizon therefore has **12 non-overlapping held-out windows**, not 24. Each historical forecast reads only transactions available before its start. Monthly fixed flows are inferred from repeated same-day-of-month training records, and the forecast uses the existing cash-path engine. The realized target includes the same routine flow types. Irregular expenses, transfers, investment activity, current scenario events, and stress overlays are excluded and disclosed.

Personal historical checks use the currently selected preview policy when one is active. Editing or discarding a preview invalidates the old check; a late response cannot replace evidence for the new policy. The check does not persist the preview to the saved workspace.

The screen shows covered/total windows and a 95% exact binomial reference interval, with the explicit assumption that windows are independent. Non-overlap removes shared days but does not prove independence. Results at half-horizon, full-horizon, and double-horizon spacings expose sensitivity to the evaluation design. Overlapping windows enrich the descriptive chart and do not inflate the primary sample size. The interval uses [SciPy's exact binomial procedure](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html).

Randomized PIT spreads ties, including the atom at zero, across their CDF interval. The PIT histogram uses the primary non-overlapping sample. Pinball loss evaluates the selected quantile; empirical CRPS evaluates the full required-liquidity distribution. These remain descriptive scores at this sample size. Randomized transforms for discrete and mixed distributions are discussed by [Gneiting and Ranjan](https://arxiv.org/abs/1106.1638).

Formal count tests are unavailable below five expected failures or successes. This threshold is a minimum screen, not an assertion of adequate power. Kupiec results, when supported, show a statistic and p-value, never PASS. Christoffersen also requires adequate transition counts and only uses non-overlapping windows. The default 30-day demonstration cannot support any of these tail tests.

The [Acerbi–Székely Z2 test](https://www.msci.com/resources/research/articles/2014/Research_Insight_Backtesting_Expected_Shortfall_December_2014.pdf) requires at least 20 expected and observed tail events plus strictly positive predicted expected shortfalls. It uses the paper's fractional correction for boundary atoms and 1,000 conditional null simulations from archived predictive distributions. Its one-sided p-value tests underestimation and assumes independent held-out windows; it also never displays PASS.

## Stress and fingerprints

The implemented entropy view gives a user-selected probability to futures with variable income no greater than half the historical mean over the first 14 days, or the shorter chart horizon. The definition and achieved probability are displayed beside the assumption. For one binary view the minimum-KL projection has a closed form: scale probability within each group while preserving its relative weights. See [Meucci's entropy-pooling presentation](https://www.epfl.ch/schools/cdm/wp-content/uploads/2018/08/meucci_slides.pdf).

The same weights apply to reserves, chart percentiles, severity, histograms, named plans, and optimization. An unsupported view reports its failure and explicitly labels the displayed baseline fallback. Stress runs omit the unweighted estimate band and persistence table instead of presenting them as stressed uncertainty estimates.

Overall ENS, tail ENS, maximum individual weight, and view residuals are reported. Tail ENS uses exact tail mass and proportional boundary ties; tied losses can give it more effective scenarios than `(1-q) × paths`. ENS measures concentration, not historical sample size. The disclosed recommendation policy requires stress tail ENS of at least 20 and a maximum scenario weight of at most 10%. These thresholds are policy assumptions, not statistical significance tests.

Separate SHA-256 fingerprints identify inputs, paths, probability weights, views, and model source/configuration/library versions. A combined run hash distinguishes complete forecasts. Named-plan comparison rejects mismatched weight fingerprints as well as different horizons or draws.

## Additional decision analysis

The cost/downside screen solves sampled expected-cost minima under several tail-deficit limits. Named plans are evaluated using the same loss components, horizon, paths, and weights. A slider selects a solved point; it does not interpolate uncomputed funding actions or claim a complete continuous frontier.

The original optimized mix is also evaluated on fresh simulation draws, with its credit, exact account/lot withdrawal allocations, and spending controls frozen. Those draws are never used to tune the solution. This measures simulation selection effects under the same historical model, not validation on new history. Unsupported stress in the fresh sample disables that check.

Credit-capacity and mean-buffer-allowance duals are checked with +1, +10, and +100 increments. Credit increments add that much usable capacity after the utilization and cash-advance ceilings, rather than changing only the nominal card limit. The screen shows the finite-difference values and their range. A value is labeled stable only when all three resolves succeed and the spread is within 10% of the largest magnitude, with a $0.00001 numerical floor. No local price is multiplied by an entire resource limit.

Ordinary demo scenario requests allow a 10-second solver budget and a 30-second frontend deadline. Personal baseline-plus-preview requests allow 45 seconds, as described above. Additional decision analysis is requested explicitly, shares a 40-second solve budget, and has a 60-second frontend deadline. Individual failures and uncompleted points remain labeled. Scenario edits coalesce while a request runs, and the baseline summary is returned in that same response.

The optimizer uses the full CVaR LP with CLARABEL for up to 20,000 scenario-days. Larger problems use a HiGHS master LP with supporting planes for the same objective and risk constraints. Each candidate is checked against **every original path and its original weight**; no scenarios are discarded. The master gives a lower bound, and the returned plan must satisfy all risk limits and close the objective gap to the larger of $0.0001 or one ten-millionth of the cost. Monetary quantities are scaled to thousands of dollars internally; outputs and marginal prices retain their stated units. The response identifies the solver method. Equivalence tests cover weighted tails, worst-case coverage, expected-cost objectives, account capacities, and active risk limits.

## Asset and lot comparisons

Aligned per-asset returns precede covariance or contribution calculations. The portfolio's simulated value sums the individual buy-and-hold asset paths when those histories are present. Ledoit–Wolf spherical shrinkage stabilizes the covariance estimate; the small direct implementation uses the standard centered estimator described in the [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.ledoit_wolf.html).

The sale comparison includes proportional liquidation, a fractional-share sell-only tax-cost LP, and a conditional-backstop heuristic. All raise the same gross proceeds; their tax reserves can leave different net cash amounts. This taxable-only instrument comparison is separate from the account-wrapper funding optimizer. Remaining volatility and conditional underperformance are recalculated after sales. The heuristic reevaluates the remaining portfolio for each slice; it does not claim a global optimum or guarantee that concentration falls.

The tax-conscious LP uses bounded lot sales and an equality for required gross proceeds, solved with [SciPy HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html). Assumed rates are displayed. Only positive lot gains contribute to its estimated tax cost; realized losses do not fund the cash path. Netting, deductions, carryforwards, state taxes, wash sales, and a final tax return are outside scope. The [IRS description of gains and losses](https://www.irs.gov/taxtopics/tc409) explains why a loss is not an immediate cash rebate.

## Deliberate exclusions and documentation guidance

The critique's cuts remain cuts: Gaussian daily regime switching, a headline household LCR including all investments, full tax-aware rebalancing relaxations, and whole-share MILP execution. A daily two-state Gaussian fit can learn payday versus non-payday; a future regime model would need an arrival/size formulation and more evidence.

Documentation refers to [Federal Reserve SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), which supersedes SR 11-7. It is a reference for documenting assumptions and limitations, not a claim that this demonstration meets banking regulation.
