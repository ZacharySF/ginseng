"""Funding-plan candidate generation and evaluation (spec sections 8, 14, 38-41).

Every candidate plan solves the *same* liability: the funding gap computed
by `ginseng.metrics.funding_gap` (spec 26). Plans differ only in which
funding class (spec 8) they draw on and how they time the resulting cash
flows. `evaluate_plan` is a pure function of `(state, bundle, obligations,
spec)` — every number a plan needs (settlement timing, credit-account
choice, lot-selection method, ...) is baked into its `PlanSpec` by
`build_candidates`, so paired plan comparisons only ever change the
`PlanSpec`, never the stochastic draws (spec 20, common random numbers).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Sequence

import numpy as np

from ginseng.metrics import severity_metrics
from ginseng.simulate import (
    DrawBundle,
    cash_paths,
    discretionary_resampled_paths,
    portfolio_value_paths,
)
from ginseng.state import CreditAccount, FinancialState, Holding, Obligation, TaxLot


class PlanKind(str, Enum):
    """The four spec-38 funding plans."""

    CREDIT = "credit"
    LIQUIDATE = "liquidate"
    HYBRID = "hybrid"
    PROTECTIVE = "protective"


@dataclass(frozen=True)
class FundingConfig:
    """Knobs `build_candidates` uses to size the spec-38 candidate plans.

    `settlement_days` + `external_transfer_days` model spec 40 (T+1 plus a
    configurable brokerage-to-bank transfer delay: 1-3 business days per
    finance-sources.md section 3, so the 2-day default is a realistic
    floor, not a guess). `hybrid_*_fraction` values must sum to 1.0; they
    partition the funding gap across cash, liquidation, credit, and
    deferral (spec 38 Plan C).
    """

    settlement_days: int = 1
    external_transfer_days: int = 2
    trailing_days: int = 3
    protective_spending_reduction: float = 0.30
    protective_spending_days: int | None = None
    hybrid_cash_fraction: float = 0.30
    hybrid_liquidation_fraction: float = 0.30
    hybrid_credit_fraction: float = 0.25
    hybrid_deferral_fraction: float = 0.15
    lot_selection: str = "fifo"
    specific_lot_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanSpec:
    """A fully-parameterized candidate plan, ready for `evaluate_plan`.

    Every field `evaluate_plan` needs is carried here so that function
    stays a pure, self-contained transform of `(state, bundle, obligations,
    spec)` with no external configuration object.
    """

    id: str
    label: str
    kind: PlanKind
    credit_account_id: str | None = None
    credit_draw: float = 0.0
    pay_in_full: bool = True
    liquidation_target: float = 0.0
    settlement_days: int = 1
    external_transfer_days: int = 2
    lot_selection: str = "fifo"
    specific_lot_ids: tuple[str, ...] = ()
    discretionary_reduction_fraction: float = 0.0
    discretionary_reduction_days: int | None = None
    unfunded_cash_amount: float = 0.0
    trailing_days: int = 3


@dataclass(frozen=True)
class PlanResult:
    """Every spec-60 objective for one evaluated plan, plus the feasibility
    and Pareto bookkeeping `policy.py` fills in."""

    id: str
    label: str
    kind: PlanKind
    evaluation_horizon_days: int
    evaluation_draw_id: str
    cash_shortfall_probability: float
    avg_cash_deficit_when_short: float
    new_debt: float
    interest_exposure: float
    investment_sold: float
    realized_gain_loss: float
    deferred_spending: float
    credit_utilization: float
    feasible: bool
    infeasibility_reason: str | None = None
    dominated: bool = False
    dominated_by: str | None = None


# --------------------------------------------------------------------------
# Horizon extension (spec 14)
# --------------------------------------------------------------------------


def extend_draw_bundle(bundle: DrawBundle, target_horizon_days: int) -> DrawBundle:
    """Extend `bundle` to cover `target_horizon_days` without disturbing the
    already-drawn days (spec 14, 20).

    A funding plan may create a payment obligation beyond the requested
    horizon (a card payment due on day 38, for example). Ginseng must not
    let that liability look free just because it falls outside the
    standard chart, so the evaluation horizon extends to cover it:
    `H_scenario = max(bundle.horizon_days, latest material obligation)`.

    The first `bundle.horizon_days` columns of the returned bundle's
    `index_matrix` are byte-identical to `bundle.index_matrix` — no plan
    constructs its own draws, and the shared window stays under common
    random numbers. The additional columns continue the same stationary
    bootstrap Markov chain (spec 16) from the last drawn historical-day
    index per path, using a sub-seed deterministically derived from
    `bundle.seed`, `bundle.bootstrap_draw_id`, and the two horizon
    lengths — so calling this twice with the same bundle and target
    produces the identical extension, and the mechanism never needs
    `simulate.py`'s private joint-history machinery.
    """
    if target_horizon_days <= bundle.horizon_days:
        return bundle

    extra_days = target_horizon_days - bundle.horizon_days
    n_hist = bundle.history_length
    n_paths = bundle.n_paths
    continuation_probability = 1.0 - 1.0 / bundle.mean_block_length

    sub_seed_material = (
        f"{bundle.seed}:{bundle.bootstrap_draw_id}:{bundle.horizon_days}:{target_horizon_days}"
    ).encode()
    sub_seed = int(hashlib.sha256(sub_seed_material).hexdigest()[:16], 16)
    rng = np.random.default_rng(sub_seed)
    continue_draws = rng.random((n_paths, extra_days))
    restart_indices = rng.integers(0, n_hist, size=(n_paths, extra_days))

    extension = np.empty((n_paths, extra_days), dtype=np.int64)
    previous = bundle.index_matrix[:, -1]
    for t in range(extra_days):
        continues = continue_draws[:, t] < continuation_probability
        previous = np.where(continues, (previous + 1) % n_hist, restart_indices[:, t])
        extension[:, t] = previous

    full_index_matrix = np.concatenate([bundle.index_matrix, extension], axis=1)
    draw_id = hashlib.sha256(
        np.ascontiguousarray(full_index_matrix, dtype=np.int64).tobytes()
    ).hexdigest()
    return DrawBundle(
        seed=bundle.seed,
        horizon_days=target_horizon_days,
        n_paths=n_paths,
        mean_block_length=bundle.mean_block_length,
        mean_block_length_was_clipped=bundle.mean_block_length_was_clipped,
        history_length=n_hist,
        index_matrix=full_index_matrix,
        bootstrap_draw_id=draw_id,
    )


# --------------------------------------------------------------------------
# Credit-card modeling (spec 39; CFPB grace-period rules, finance-sources #2)
# --------------------------------------------------------------------------


def _day_of_month_offset(as_of: date, day_of_month: int) -> int:
    """Days from `as_of` (0 = `as_of` itself) to the next date whose
    day-of-month is `day_of_month`. Mirrors `generate.py`'s scheduling
    convention: `CreditAccount.statement_close_day` / `payment_due_day`
    are day-of-month integers, not day offsets."""
    for offset in range(0, 32):
        if (as_of + timedelta(days=offset)).day == day_of_month:
            return offset
    raise ValueError(f"no day-of-month {day_of_month} found within a month of {as_of}")


def _next_charge_payment_offset(as_of: date, account: CreditAccount) -> int:
    """Forecast-day offset of the payment due date that will include a
    purchase made today.

    The statement covering today's purchase must close first; the payment
    for that statement is owed on the *following* occurrence of
    `payment_due_day` (CFPB: statements must be delivered at least 21 days
    before the payment is due, so a `payment_due_day` that is numerically
    earlier in the month than `statement_close_day` refers to the
    already-closing cycle's payment, not this one)."""
    close_offset = _day_of_month_offset(as_of, account.statement_close_day)
    due_offset = _day_of_month_offset(as_of, account.payment_due_day)
    if due_offset <= close_offset:
        due_offset += 30
    return due_offset


def _select_primary_credit_account(state: FinancialState) -> CreditAccount | None:
    if not state.credit_accounts:
        return None
    return max(state.credit_accounts, key=lambda account: account.available_credit)


# --------------------------------------------------------------------------
# Tax-lot liquidation (spec 40, 41; SEC T+1, IRS Tax Topic 409)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LiquidationResult:
    proceeds: float
    cost_basis_disposed: float
    shortfall: float

    @property
    def realized_gain_loss(self) -> float:
        return self.proceeds - self.cost_basis_disposed


def _disposal_order(
    lots: Sequence[TaxLot], lot_selection: str, specific_lot_ids: Sequence[str]
) -> list[TaxLot]:
    """FIFO by acquisition date is the IRS default; a caller may override
    with specific-lot identification (spec 41). Any lot not named by the
    override still disposes FIFO."""
    if lot_selection == "specific" and specific_lot_ids:
        by_id = {lot.lot_id: lot for lot in lots}
        ordered = [by_id[lot_id] for lot_id in specific_lot_ids if lot_id in by_id]
        remaining = sorted(
            (lot for lot in lots if lot.lot_id not in specific_lot_ids),
            key=lambda lot: lot.purchase_date,
        )
        return ordered + remaining
    return sorted(lots, key=lambda lot: lot.purchase_date)


def _liquidate(
    holdings: Sequence[Holding],
    target_proceeds: float,
    lot_selection: str = "fifo",
    specific_lot_ids: Sequence[str] = (),
) -> LiquidationResult:
    """Sell up to `target_proceeds` dollars of `holdings` (spec 41):
    allocated across symbols in proportion to market value, then FIFO (or
    specific-lot override) by tax lot within each symbol.
    `realized_gain_loss = proceeds - disposed cost basis` (IRS Tax Topic
    409)."""
    total_market_value = sum(h.market_value for h in holdings)
    if total_market_value <= 0.0 or target_proceeds <= 0.0:
        return LiquidationResult(0.0, 0.0, max(0.0, target_proceeds))

    to_raise = min(target_proceeds, total_market_value)
    proceeds = 0.0
    cost_basis_disposed = 0.0
    for holding in holdings:
        allocation = to_raise * (holding.market_value / total_market_value)
        remaining_allocation = allocation
        for lot in _disposal_order(holding.tax_lots, lot_selection, specific_lot_ids):
            if remaining_allocation <= 1e-9:
                break
            lot_value = lot.market_value(holding.current_price)
            if lot_value <= remaining_allocation:
                proceeds += lot_value
                cost_basis_disposed += lot.cost_basis
                remaining_allocation -= lot_value
            else:
                fraction = remaining_allocation / lot_value
                proceeds += remaining_allocation
                cost_basis_disposed += lot.cost_basis * fraction
                remaining_allocation = 0.0

    shortfall = max(0.0, target_proceeds - proceeds)
    return LiquidationResult(proceeds, cost_basis_disposed, shortfall)


# --------------------------------------------------------------------------
# Protective spending / hybrid deferral (spec 12, 38)
# --------------------------------------------------------------------------


def _avg_daily_discretionary_spend(state: FinancialState) -> float:
    """Historical average daily discretionary spending, used only to size
    the hybrid plan's discretionary-reduction fraction against its target
    dollar contribution to the gap (spec 38 Plan C). The actual evaluated
    savings always come from `simulate.discretionary_resampled_paths`."""
    if not state.transactions:
        return 0.0
    start = min(t.txn_date for t in state.transactions)
    end = state.as_of
    total_days = (end - start).days + 1
    if total_days <= 0:
        return 0.0
    total_discretionary = sum(
        t.amount for t in state.discretionary_spending_history if start <= t.txn_date <= end
    )
    return total_discretionary / total_days


def _hybrid_deferral_fraction(state: FinancialState, gap: float, config: FundingConfig) -> float:
    target = gap * config.hybrid_deferral_fraction
    avg_daily = _avg_daily_discretionary_spend(state)
    horizon = state.forecast_horizon
    if avg_daily <= 0.0 or horizon <= 0:
        return 0.0
    return float(np.clip(target / (avg_daily * horizon), 0.0, 1.0))


# --------------------------------------------------------------------------
# Candidate generation (spec 38)
# --------------------------------------------------------------------------


def build_candidates(
    state: FinancialState,
    obligations: Sequence[Obligation],
    gap: float,
    config: FundingConfig = FundingConfig(),
) -> list[PlanSpec]:
    """Generate the spec-38 candidate plans that all solve the same `gap`
    dollars of required additional funding (spec 26).

    `obligations` is accepted for interface symmetry with `evaluate_plan`
    (which needs it to reproduce the baseline cash path); the gap already
    reflects their aggregate effect on required liquidity, so plan
    construction does not need to inspect them individually.
    """
    del obligations
    gap = max(0.0, gap)
    account = _select_primary_credit_account(state)
    account_id = account.account_id if account is not None else None

    return [
        PlanSpec(
            id="credit",
            label="Credit Bridge",
            kind=PlanKind.CREDIT,
            credit_account_id=account_id,
            credit_draw=gap,
            pay_in_full=True,
            settlement_days=config.settlement_days,
            external_transfer_days=config.external_transfer_days,
            trailing_days=config.trailing_days,
        ),
        PlanSpec(
            id="liquidate",
            label="Taxable Liquidation",
            kind=PlanKind.LIQUIDATE,
            credit_account_id=account_id,
            liquidation_target=gap,
            settlement_days=config.settlement_days,
            external_transfer_days=config.external_transfer_days,
            lot_selection=config.lot_selection,
            specific_lot_ids=config.specific_lot_ids,
            trailing_days=config.trailing_days,
        ),
        PlanSpec(
            id="hybrid",
            label="Hybrid",
            kind=PlanKind.HYBRID,
            credit_account_id=account_id,
            credit_draw=gap * config.hybrid_credit_fraction,
            pay_in_full=True,
            liquidation_target=gap * config.hybrid_liquidation_fraction,
            settlement_days=config.settlement_days,
            external_transfer_days=config.external_transfer_days,
            lot_selection=config.lot_selection,
            specific_lot_ids=config.specific_lot_ids,
            discretionary_reduction_fraction=_hybrid_deferral_fraction(state, gap, config),
            unfunded_cash_amount=gap * config.hybrid_cash_fraction,
            trailing_days=config.trailing_days,
        ),
        PlanSpec(
            id="protective",
            label="Protective Spending",
            kind=PlanKind.PROTECTIVE,
            credit_account_id=account_id,
            discretionary_reduction_fraction=config.protective_spending_reduction,
            discretionary_reduction_days=config.protective_spending_days,
            trailing_days=config.trailing_days,
        ),
    ]


# --------------------------------------------------------------------------
# Evaluation (spec 42, 60)
# --------------------------------------------------------------------------


def evaluate_plan(
    state: FinancialState,
    bundle: DrawBundle,
    obligations: Sequence[Obligation],
    spec: PlanSpec,
) -> PlanResult:
    """Evaluate one `PlanSpec` on `bundle` (spec 20: the same bundle every
    candidate plan in a comparison must share) and return every spec-60
    objective."""
    reasons: list[str] = []

    credit_account = None
    if spec.credit_account_id is not None:
        credit_account = next(
            (a for a in state.credit_accounts if a.account_id == spec.credit_account_id), None
        )
        if credit_account is None and spec.credit_draw > 0:
            reasons.append(f"credit account {spec.credit_account_id!r} not found")

    new_debt = 0.0
    interest_exposure = 0.0
    credit_utilization = 0.0
    credit_due_day = 0
    credit_payment_due_amount = 0.0

    if credit_account is not None:
        credit_utilization = (
            (credit_account.current_balance + spec.credit_draw) / credit_account.credit_limit
            if credit_account.credit_limit > 0
            else 0.0
        )
        if spec.credit_draw > 0:
            if spec.credit_draw > credit_account.available_credit:
                reasons.append(
                    f"${spec.credit_draw:,.2f} credit draw exceeds ${credit_account.available_credit:,.2f} "
                    f"available on {credit_account.account_id}"
                )
            due_offset = _next_charge_payment_offset(state.as_of, credit_account)
            credit_due_day = max(1, due_offset)
            # CFPB: grace applies only when the card offers one, the
            # cardholder is not already carrying a balance, and the plan
            # intends to pay the new statement balance in full by the due
            # date (finance-sources.md section 2). Otherwise interest
            # accrues on the unpaid portion from the transaction date.
            grace_applies = (
                credit_account.grace_period_eligible
                and credit_account.current_balance <= 0.0
                and spec.pay_in_full
            )
            new_debt = spec.credit_draw
            if grace_applies:
                credit_payment_due_amount = spec.credit_draw
            else:
                daily_rate = credit_account.purchase_apr / 365.0
                interest_exposure = spec.credit_draw * daily_rate * due_offset
                owed = spec.credit_draw + interest_exposure
                credit_payment_due_amount = (
                    owed if spec.pay_in_full else min(credit_account.minimum_payment, owed)
                )

    investment_sold = 0.0
    realized_gain_loss = 0.0
    settlement_day = 1
    if spec.liquidation_target > 0:
        disposal = _liquidate(
            state.taxable_portfolio, spec.liquidation_target, spec.lot_selection, spec.specific_lot_ids
        )
        investment_sold = disposal.proceeds
        realized_gain_loss = disposal.realized_gain_loss
        # T+1 settlement (SEC Rule 15c6-1) plus a configurable external
        # transfer delay (finance-sources.md section 3): proceeds are not
        # spendable cash on the trade date.
        settlement_day = max(1, spec.settlement_days + spec.external_transfer_days)
        if disposal.shortfall > 1e-6:
            reasons.append(
                f"only ${disposal.proceeds:,.2f} of marketable backup capital available toward a "
                f"${spec.liquidation_target:,.2f} liquidation target"
            )

    # Horizon extension (spec 14): never let a plan's own obligation look
    # free just because it falls outside the requested chart.
    material_days = [bundle.horizon_days]
    if spec.credit_draw > 0 and credit_account is not None:
        material_days.append(credit_due_day)
    if spec.liquidation_target > 0:
        material_days.append(settlement_day)
    latest_material_day = max(material_days)
    evaluation_horizon = (
        latest_material_day
        if latest_material_day <= bundle.horizon_days
        else latest_material_day + spec.trailing_days
    )
    eval_bundle = extend_draw_bundle(bundle, evaluation_horizon)

    cash_matrix = cash_paths(state, eval_bundle, obligations)
    n_paths, horizon_days = cash_matrix.shape
    adjustment = np.zeros(horizon_days, dtype=float)
    if spec.credit_draw > 0 and credit_account is not None:
        adjustment[0] += spec.credit_draw
        adjustment[credit_due_day - 1] -= credit_payment_due_amount

    per_path_adjustment = np.broadcast_to(adjustment, (n_paths, horizon_days)).copy()

    if spec.liquidation_target > 0:
        # Path-scaled settlement (spec 8.3): the sale is sized at today's
        # prices, but proceeds arrive T+1 plus the transfer delay later, so
        # what each path actually receives is the nominal amount scaled by
        # that path's portfolio value on the settlement day. Without market
        # history the nominal amount is used unchanged, preserving the
        # pre-market-data evaluation.
        pv_matrix = portfolio_value_paths(state, eval_bundle)
        settle_col = min(settlement_day - 1, horizon_days - 1)
        if pv_matrix is not None:
            scale = pv_matrix[:, settle_col] / max(state.marketable_backup_capital, 1e-9)
            per_path_proceeds = investment_sold * np.clip(scale, 0.0, None)
            per_path_adjustment[:, settle_col] += per_path_proceeds
        else:
            per_path_adjustment[:, settle_col] += investment_sold

    deferred_spending = 0.0
    if spec.discretionary_reduction_fraction > 0:
        reduction_days = min(spec.discretionary_reduction_days or horizon_days, horizon_days)
        discretionary = discretionary_resampled_paths(state, eval_bundle)
        savings = spec.discretionary_reduction_fraction * discretionary[:, :reduction_days]
        per_path_adjustment[:, :reduction_days] += savings
        deferred_spending = float(np.mean(np.sum(savings, axis=1)))

    adjusted_cash = cash_matrix + np.cumsum(per_path_adjustment, axis=1)
    severity = severity_metrics(adjusted_cash, state.immediate_funding, state.operating_buffer)

    return PlanResult(
        id=spec.id,
        label=spec.label,
        kind=spec.kind,
        evaluation_horizon_days=horizon_days,
        evaluation_draw_id=eval_bundle.bootstrap_draw_id,
        cash_shortfall_probability=severity["cash_shortfall_probability"],
        avg_cash_deficit_when_short=severity["avg_cash_deficit_when_short"],
        new_debt=new_debt,
        interest_exposure=interest_exposure,
        investment_sold=investment_sold,
        realized_gain_loss=realized_gain_loss,
        deferred_spending=deferred_spending,
        credit_utilization=credit_utilization,
        feasible=not reasons,
        infeasibility_reason="; ".join(reasons) if reasons else None,
    )
