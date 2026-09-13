# Ginseng model card — model version 0.2.0

**More simulations improve numerical precision. They do not create more historical evidence.** The demonstration still has 730 days of synthetic history, whatever the requested simulation count.

## Purpose and data

This model compares hypothetical ways to fund future expenses. It does not execute trades or borrowing, compute a final tax return, or establish validated coverage for a real household. The personal cash workspace remains a separate deterministic ledger; these probabilistic tools use the clearly labeled synthetic persona.

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

The cost objective includes modeled interest, assumed positive-gain tax costs, forgone discretionary spending valued dollar for dollar, and negative-cash dollar-days priced at the configured overdraft APR. Investment-sale principal is not itself a cost. A zero-cost solution can therefore involve a substantial sale. These are selected cost components, not a prediction of total future wealth or investment performance.

Sales execute today at recorded holding prices. Proceeds arrive after settlement and transfer; subsequent market moves do not reprice sold shares. Settlement plus external transfer remains an explicitly disclosed **three-calendar-day approximation**, not an exchange holiday calendar. The primary card uses purchase APR and statement timing as a cash-bridge proxy; a real cash advance may have different fees and terms.

Three separate quantities must not be confused:

- The reserve coverage target is an empirical frequency target for starting cash.
- The existing optimizer constraint limits **mean buffer deficit dollar-days**. Its default is buffer × evaluation days × 5%, independent of the simulation count.
- The optional **tail-deficit limit** constrains CVaR of each future's largest dollar deficit below the buffer. It is a severity constraint, separate from the mean dollar-day constraint and separate from the CVaR cost objective.

For nonnegative deficits, a zero tail-deficit limit requires every positive-weight scenario to preserve the buffer. A positive limit does not promise zero buffer breaches in 95% of futures. CVaR below a dollar threshold conservatively bounds VaR at that same threshold; it does not automatically bound breaches of a different threshold, such as zero.

All reported VaR and CVaR values are recomputed from the selected actions' actual losses. Fractional tail mass is used when the target cuts a scenario's probability, and ties at the cutoff share the remaining mass proportionally. At 100% the calculation reports the empirical maximum. See the original [Rockafellar–Uryasev publications](https://uryasev.github.io/publications/) for the convex formulation.

## Historical evidence

Walk-forward checks reserve the first 365 days for training. A 30-day horizon therefore has **12 non-overlapping held-out windows**, not 24. Each historical forecast reads only transactions available before its start. Monthly fixed flows are inferred from repeated same-day-of-month training records, and the forecast uses the existing cash-path engine. The realized target includes the same routine flow types. Irregular expenses, transfers, investment activity, current scenario events, and stress overlays are excluded and disclosed.

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

The original optimized mix is also evaluated on fresh simulation draws, with its credit, sale, and spending controls frozen. Those draws are never used to tune the solution. This measures simulation selection effects under the same historical model, not validation on new history. Unsupported stress in the fresh sample disables that check.

Credit-capacity and mean-buffer-allowance duals are checked with +1, +10, and +100 increments. The screen shows the finite-difference values and their range. A value is labeled stable only when all three resolves succeed and the spread is within 10% of the largest magnitude, with a $0.00001 numerical floor. No local price is multiplied by an entire resource limit.

Ordinary scenario requests allow a 10-second solver budget and a 30-second frontend deadline. Additional decision analysis is requested explicitly, shares a 40-second solve budget, and has a 60-second frontend deadline. Individual failures and uncompleted points remain labeled. Scenario edits coalesce while a request runs, and the baseline summary is returned in that same response.

## Asset and lot comparisons

Aligned per-asset returns precede covariance or contribution calculations. The portfolio's simulated value sums the individual buy-and-hold asset paths when those histories are present. Ledoit–Wolf spherical shrinkage stabilizes the covariance estimate; the small direct implementation uses the standard centered estimator described in the [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.covariance.ledoit_wolf.html).

The sale comparison includes proportional liquidation, a fractional-share sell-only tax-cost LP, and a conditional-backstop heuristic. All raise the same proceeds. Remaining volatility and conditional underperformance are recalculated after sales. The heuristic reevaluates the remaining portfolio for each slice; it does not claim a global optimum or guarantee that concentration falls.

The tax-conscious LP uses bounded lot sales and an equality for required gross proceeds, solved with [SciPy HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html). Assumed rates are displayed. Only positive lot gains contribute to its estimated tax cost; realized losses do not fund the cash path. Netting, deductions, carryforwards, state taxes, wash sales, and a final tax return are outside scope. The [IRS description of gains and losses](https://www.irs.gov/taxtopics/tc409) explains why a loss is not an immediate cash rebate.

## Deliberate exclusions and documentation guidance

The critique's cuts remain cuts: Gaussian daily regime switching, a headline household LCR including all investments, full tax-aware rebalancing relaxations, and whole-share MILP execution. A daily two-state Gaussian fit can learn payday versus non-payday; a future regime model would need an arrival/size formulation and more evidence.

Documentation refers to [Federal Reserve SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), which supersedes SR 11-7. It is a reference for documenting assumptions and limitations, not a claim that this demonstration meets banking regulation.
