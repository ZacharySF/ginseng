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
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import Enum
from typing import Sequence

import numpy as np

from ginseng.metrics import severity_metrics
from ginseng.simulate import (
    DrawBundle,
    PathBundle,
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
    """Knobs for candidate construction and settlement timing.

    Personal forecasts enable business-day settlement and opening-day payment
    mapping. The synthetic demo retains its established calendar convention.
    A hybrid contains only actual credit, taxable-sale, and
    discretionary-deferral levers; it never claims an unowned cash
    contribution.
    """

    settlement_days: int = 1
    external_transfer_days: int = 2
    trailing_days: int = 3
    protective_spending_reduction: float = 0.30
    protective_spending_days: int | None = None
    hybrid_liquidation_fraction: float = 0.35
    hybrid_credit_fraction: float = 0.50
    hybrid_deferral_fraction: float = 0.15
    lot_selection: str = "fifo"
    specific_lot_ids: tuple[str, ...] = ()
    use_business_days: bool = False


@dataclass(frozen=True)
class PlanSpec:
    """A fully-parameterized candidate plan, ready for ``evaluate_plan``."""

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
    trailing_days: int = 3
    use_business_days: bool = False


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
    overdraft_interest_exposure: float = 0.0


# --------------------------------------------------------------------------
# Horizon extension (spec 14)
# --------------------------------------------------------------------------


def extend_draw_bundle(
    bundle: DrawBundle | PathBundle, target_horizon_days: int
) -> DrawBundle | PathBundle:
    """Extend one shared path bundle without replacing its random world."""
    if target_horizon_days <= bundle.horizon_days:
        return bundle
    if isinstance(bundle, PathBundle):
        if target_horizon_days > bundle.available_horizon_days:
            raise ValueError(
                "The prospective path bundle does not cover the plan's latest settlement or payment date."
            )
        return replace(bundle, horizon_days=target_horizon_days)

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


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _next_day_of_month(as_of: date, day_of_month: int) -> date:
    """Return the first valid configured day on or after ``as_of``."""
    candidate = date(as_of.year, as_of.month, day_of_month)
    if candidate >= as_of:
        return candidate
    year, month = _next_month(as_of.year, as_of.month)
    return date(year, month, day_of_month)


def _next_charge_payment_offset(
    as_of: date,
    account: CreditAccount,
    *,
    one_indexed: bool = False,
) -> int:
    """Forecast payment day for a charge made at the opening date.

    Personal forecasts use the corrected one-indexed calendar convention.
    The original demo convention remains available for its frozen surface.
    """
    if not one_indexed:
        close_offset = next(
            offset
            for offset in range(32)
            if (as_of + timedelta(days=offset)).day == account.statement_close_day
        )
        due_offset = next(
            offset
            for offset in range(32)
            if (as_of + timedelta(days=offset)).day == account.payment_due_day
        )
        return due_offset + 30 if due_offset <= close_offset else due_offset

    close_date = _next_day_of_month(as_of, account.statement_close_day)
    due_date = _next_day_of_month(close_date, account.payment_due_day)
    if due_date <= close_date:
        year, month = _next_month(due_date.year, due_date.month)
        due_date = date(year, month, account.payment_due_day)
    return (due_date - as_of).days + 1


def settlement_forecast_day(
    as_of: date, settlement_days: int, external_transfer_days: int, *, use_business_days: bool = False
) -> int:
    """Cash-availability day after settlement and external transfer lags."""
    total_days = max(0, settlement_days) + max(0, external_transfer_days)
    if not use_business_days:
        return max(1, total_days)
    cursor = as_of
    remaining = total_days
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            remaining -= 1
    return (cursor - as_of).days + 1


def _select_primary_credit_account(state: FinancialState) -> CreditAccount | None:
    if not state.credit_accounts:
        return None
    return max(state.credit_accounts, key=lambda account: account.available_credit)


def plan_evaluation_horizon(
    state: FinancialState,
    bundle: DrawBundle | PathBundle,
    spec: PlanSpec,
) -> int:
    """Return the full comparison horizon required by one candidate plan."""
    material_days = [bundle.horizon_days]
    if spec.credit_draw > 0 and spec.credit_account_id is not None:
        account = next(
            (item for item in state.credit_accounts if item.account_id == spec.credit_account_id),
            None,
        )
        if account is not None:
            material_days.append(
                _next_charge_payment_offset(
                    state.as_of,
                    account,
                    one_indexed=spec.use_business_days,
                )
            )
    if spec.liquidation_target > 0:
        material_days.append(
            settlement_forecast_day(
                state.as_of,
                spec.settlement_days,
                spec.external_transfer_days,
                use_business_days=spec.use_business_days,
            )
        )
    latest_material_day = max(material_days)
    return (
        latest_material_day
        if latest_material_day <= bundle.horizon_days
        else latest_material_day + spec.trailing_days
    )


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


@dataclass(frozen=True)
class LiquidationBasisSegment:
    """One exact affine branch of a pro-rata taxable liquidation."""

    lower_proceeds: float
    upper_proceeds: float
    cost_basis_intercept: float
    cost_basis_slope: float


def _disposal_order(
    lots: Sequence[TaxLot], lot_selection: str, specific_lot_ids: Sequence[str]
) -> list[TaxLot]:
    """Order selectable tax lots under the user's declared disposal policy."""
    if lot_selection == "hifo":
        return sorted(
            lots,
            key=lambda lot: (lot.cost_basis_per_share, lot.purchase_date),
            reverse=True,
        )
    if lot_selection == "specific" and specific_lot_ids:
        by_id = {lot.lot_id: lot for lot in lots}
        ordered = [by_id[lot_id] for lot_id in specific_lot_ids if lot_id in by_id]
        remaining = sorted(
            (lot for lot in lots if lot.lot_id not in specific_lot_ids),
            key=lambda lot: lot.purchase_date,
        )
        return ordered + remaining
    return sorted(lots, key=lambda lot: lot.purchase_date)


def liquidation_cost_basis(
    holdings: Sequence[Holding],
    target_proceeds: float,
    lot_selection: str = "fifo",
    specific_lot_ids: Sequence[str] = (),
) -> float:
    """Return the exact basis disposed by :func:`_liquidate`'s sale rule."""
    total_market_value = sum(holding.market_value for holding in holdings)
    if total_market_value <= 0.0 or target_proceeds <= 0.0:
        return 0.0

    to_raise = min(target_proceeds, total_market_value)
    cost_basis_disposed = 0.0
    for holding in holdings:
        remaining_allocation = to_raise * (holding.market_value / total_market_value)
        for lot in _disposal_order(holding.tax_lots, lot_selection, specific_lot_ids):
            if remaining_allocation <= 1e-9:
                break
            lot_value = lot.market_value(holding.current_price)
            if lot_value <= remaining_allocation:
                cost_basis_disposed += lot.cost_basis
                remaining_allocation -= lot_value
            else:
                cost_basis_disposed += lot.cost_basis * (remaining_allocation / lot_value)
                remaining_allocation = 0.0
    return cost_basis_disposed


def liquidation_basis_segments(
    holdings: Sequence[Holding],
    lot_selection: str = "fifo",
    specific_lot_ids: Sequence[str] = (),
    *,
    max_segments: int | None = None,
) -> tuple[LiquidationBasisSegment, ...] | None:
    """Return every exact affine basis interval for a pro-rata sale.

    Each holding receives the same global sale fraction, while its own lots
    are consumed in the selected order.  The union of those per-holding lot
    boundaries therefore makes disposed basis affine on every returned
    interval.  ``None`` means the caller's explicit resource bound was
    exceeded before a complete partition could be built.
    """
    total_market_value = sum(holding.market_value for holding in holdings)
    if total_market_value <= 0.0:
        return ()

    boundaries = {0.0, total_market_value}
    for holding in holdings:
        holding_market_value = holding.market_value
        if holding_market_value <= 0.0:
            continue
        cumulative_lot_value = 0.0
        for lot in _disposal_order(holding.tax_lots, lot_selection, specific_lot_ids):
            lot_value = lot.market_value(holding.current_price)
            if lot_value <= 0.0:
                continue
            cumulative_lot_value += lot_value
            breakpoint = min(
                total_market_value,
                cumulative_lot_value * total_market_value / holding_market_value,
            )
            if 0.0 < breakpoint < total_market_value:
                boundaries.add(breakpoint)
                if max_segments is not None and len(boundaries) - 1 > max_segments:
                    return None

    ordered_boundaries = sorted(boundaries)
    segments: list[LiquidationBasisSegment] = []
    for lower_proceeds, upper_proceeds in zip(ordered_boundaries, ordered_boundaries[1:]):
        width = upper_proceeds - lower_proceeds
        if width <= 0.0:
            continue
        lower_basis = liquidation_cost_basis(
            holdings,
            lower_proceeds,
            lot_selection,
            specific_lot_ids,
        )
        upper_basis = liquidation_cost_basis(
            holdings,
            upper_proceeds,
            lot_selection,
            specific_lot_ids,
        )
        slope = (upper_basis - lower_basis) / width
        segments.append(
            LiquidationBasisSegment(
                lower_proceeds=lower_proceeds,
                upper_proceeds=upper_proceeds,
                cost_basis_intercept=lower_basis - slope * lower_proceeds,
                cost_basis_slope=slope,
            )
        )
    return tuple(segments)


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
    cost_basis_disposed = liquidation_cost_basis(
        holdings,
        to_raise,
        lot_selection,
        specific_lot_ids,
    )
    for holding in holdings:
        allocation = to_raise * (holding.market_value / total_market_value)
        remaining_allocation = allocation
        for lot in _disposal_order(holding.tax_lots, lot_selection, specific_lot_ids):
            if remaining_allocation <= 1e-9:
                break
            lot_value = lot.market_value(holding.current_price)
            if lot_value <= remaining_allocation:
                proceeds += lot_value
                remaining_allocation -= lot_value
            else:
                proceeds += remaining_allocation
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
    start = state.history_start or min(t.txn_date for t in state.transactions)
    end = state.history_end or state.as_of
    total_days = (end - start).days + 1
    if total_days <= 0:
        return 0.0
    total_discretionary = sum(
        t.amount for t in state.discretionary_spending_history if start <= t.txn_date <= end
    )
    return total_discretionary / total_days


def _hybrid_deferral_fraction(
    state: FinancialState,
    gap: float,
    config: FundingConfig,
    average_daily_discretionary_spending: float | None = None,
) -> float:
    target = gap * config.hybrid_deferral_fraction
    avg_daily = (
        average_daily_discretionary_spending
        if average_daily_discretionary_spending is not None
        else _avg_daily_discretionary_spend(state)
    )
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
    *,
    average_daily_discretionary_spending: float | None = None,
) -> list[PlanSpec]:
    """Generate actual funding alternatives for the computed gap."""
    del obligations
    gap = max(0.0, gap)
    account = _select_primary_credit_account(state)
    account_id = account.account_id if account is not None else None
    timing = {
        "settlement_days": config.settlement_days,
        "external_transfer_days": config.external_transfer_days,
        "trailing_days": config.trailing_days,
        "use_business_days": config.use_business_days,
    }

    return [
        PlanSpec(
            id="credit",
            label="Credit Bridge",
            kind=PlanKind.CREDIT,
            credit_account_id=account_id,
            credit_draw=gap,
            pay_in_full=True,
            **timing,
        ),
        PlanSpec(
            id="liquidate",
            label="Taxable Liquidation",
            kind=PlanKind.LIQUIDATE,
            credit_account_id=account_id,
            liquidation_target=gap,
            lot_selection=config.lot_selection,
            specific_lot_ids=config.specific_lot_ids,
            **timing,
        ),
        PlanSpec(
            id="hybrid",
            label="Hybrid",
            kind=PlanKind.HYBRID,
            credit_account_id=account_id,
            credit_draw=gap * config.hybrid_credit_fraction,
            pay_in_full=True,
            liquidation_target=gap * config.hybrid_liquidation_fraction,
            lot_selection=config.lot_selection,
            specific_lot_ids=config.specific_lot_ids,
            discretionary_reduction_fraction=_hybrid_deferral_fraction(
                state,
                gap,
                config,
                average_daily_discretionary_spending,
            ),
            **timing,
        ),
        PlanSpec(
            id="protective",
            label="Protective Spending",
            kind=PlanKind.PROTECTIVE,
            credit_account_id=account_id,
            discretionary_reduction_fraction=config.protective_spending_reduction,
            discretionary_reduction_days=config.protective_spending_days,
            **timing,
        ),
    ]


# --------------------------------------------------------------------------
# Evaluation (spec 42, 60)
# --------------------------------------------------------------------------


def evaluate_plan(
    state: FinancialState,
    bundle: DrawBundle | PathBundle,
    obligations: Sequence[Obligation],
    spec: PlanSpec,
    *,
    operating_buffer: float | None = None,
    overdraft_apr: float = 0.0,
    evaluation_horizon_days: int | None = None,
    decision_horizon_days: int | None = None,
) -> PlanResult:
    """Evaluate one `PlanSpec` on `bundle` (spec 20: the same bundle every
    candidate plan in a comparison must share) and return every spec-60
    objective."""
    reasons: list[str] = []
    decision_horizon = decision_horizon_days or bundle.horizon_days

    credit_account = None
    if spec.credit_account_id is not None:
        credit_account = next(
            (a for a in state.credit_accounts if a.account_id == spec.credit_account_id), None
        )
    if spec.credit_draw > 0 and credit_account is None:
        reasons.append("no actual credit account is available for this draw")

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
            credit_due_day = _next_charge_payment_offset(
                state.as_of,
                credit_account,
                one_indexed=spec.use_business_days,
            )
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
            if grace_applies:
                credit_payment_due_amount = spec.credit_draw
            else:
                daily_rate = credit_account.purchase_apr / 365.0
                elapsed_days = credit_due_day - 1 if spec.use_business_days else credit_due_day
                interest_exposure = spec.credit_draw * daily_rate * elapsed_days
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
        settlement_day = settlement_forecast_day(
            state.as_of,
            spec.settlement_days,
            spec.external_transfer_days,
            use_business_days=spec.use_business_days,
        )
        if disposal.shortfall > 1e-6:
            reasons.append(
                f"only ${disposal.proceeds:,.2f} of marketable backup capital available toward a "
                f"${spec.liquidation_target:,.2f} liquidation target"
            )

    # Every candidate in a comparison can receive the same horizon.  A
    # standalone evaluation still extends only far enough to price its own
    # settlement or repayment.
    plan_horizon = plan_evaluation_horizon(state, bundle, spec)
    evaluation_horizon = max(plan_horizon, evaluation_horizon_days or plan_horizon)
    try:
        eval_bundle = extend_draw_bundle(bundle, evaluation_horizon)
    except ValueError as error:
        reasons.append(str(error))
        eval_bundle = bundle

    cash_matrix = cash_paths(state, eval_bundle, obligations)
    n_paths, horizon_days = cash_matrix.shape
    adjustment = np.zeros(horizon_days, dtype=float)
    if spec.credit_draw > 0 and credit_account is not None:
        if credit_due_day > horizon_days:
            reasons.append("the credit repayment date falls beyond the available evaluation paths")
        else:
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
        if settlement_day > horizon_days:
            reasons.append("the taxable-sale settlement date falls beyond the available evaluation paths")
        else:
            pv_matrix = portfolio_value_paths(state, eval_bundle)
            settle_col = settlement_day - 1
            if pv_matrix is not None:
                scale = pv_matrix[:, settle_col] / max(state.marketable_backup_capital, 1e-9)
                per_path_proceeds = investment_sold * np.clip(scale, 0.0, None)
                per_path_adjustment[:, settle_col] += per_path_proceeds
            else:
                per_path_adjustment[:, settle_col] += investment_sold

    deferred_spending = 0.0
    if spec.discretionary_reduction_fraction > 0:
        reduction_days = min(spec.discretionary_reduction_days or decision_horizon, horizon_days)
        discretionary = discretionary_resampled_paths(state, eval_bundle)
        savings = spec.discretionary_reduction_fraction * discretionary[:, :reduction_days]
        per_path_adjustment[:, :reduction_days] += savings
        deferred_spending = float(np.mean(np.sum(savings, axis=1)))

    adjusted_cash = cash_matrix + np.cumsum(per_path_adjustment, axis=1)
    severity = severity_metrics(
        adjusted_cash,
        state.immediate_funding,
        state.operating_buffer if operating_buffer is None else operating_buffer,
    )
    available_cash = state.immediate_funding + adjusted_cash
    overdraft_interest_exposure = (
        float(np.mean(np.sum(np.maximum(0.0, -available_cash), axis=1)))
        * max(0.0, overdraft_apr)
        / 365.0
    )

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
        overdraft_interest_exposure=overdraft_interest_exposure,
        deferred_spending=deferred_spending,
        credit_utilization=credit_utilization,
        feasible=not reasons,
        infeasibility_reason="; ".join(reasons) if reasons else None,
    )
