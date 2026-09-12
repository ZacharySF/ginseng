"""CVaR-optimal funding plan (Telser safety-first + Rockafellar-Uryasev, spec 7.4).

Objective: CVaR_q of (interest + tax + deferred + overdraft_cost).
  overdraft_cost_j = (overdraft_apr/365) × sum_t max(0, –B_adj_j[t])
  No arbitrary weight — all terms in dollars.

Buffer constraint (Telser): mean dollar-days below operating_buffer ≤ tolerance.
  Dual value = implied price of liquidity ($/dollar-day); increases as tolerance tightens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ginseng.funding import _next_charge_payment_offset, _select_primary_credit_account
from ginseng.policy import FundingPolicy
from ginseng.simulate import (
    DrawBundle,
    cash_paths,
    discretionary_resampled_paths,
    portfolio_value_paths,
)
from ginseng.state import FinancialState, Obligation


@dataclass(frozen=True)
class OptimalPlan:
    credit_draw: float
    liquidation_amount: float
    deferral_fraction: float
    cvar_cost: float                      # CVaR objective value
    var_cost: float                       # eta — the VaR cutoff
    expected_cost: float                  # E[cost_j]
    cash_shortfall_probability: float     # P(min cash < 0)
    implied_liquidity_price: float | None  # dual of buffer constraint $/dollar-day
    cost_is_path_dependent: bool          # True only when portfolio_daily_returns present
    solver_status: str


def optimize_funding(
    state: FinancialState,
    bundle: DrawBundle,
    obligations: Sequence[Obligation],
    coverage_target: float = 0.95,
    operating_buffer: float = 1000.0,
    overdraft_apr: float = 0.2999,        # penalty rate for below-zero cash
    buffer_tolerance_dollar_days: float | None = None,  # None → derived from policy
    capital_gains_rate: float = 0.15,
) -> OptimalPlan | None:
    """Find the CVaR-optimal funding mix for the current scenario (spec 7.4).

    Returns None when cvxpy is unavailable, when there is nothing to optimise
    (no credit accounts and no holdings), or when the LP does not solve to
    optimality.
    """
    try:
        import cvxpy as cp
    except ImportError:
        return None

    if not state.credit_accounts and not state.holdings:
        return None

    n = bundle.n_paths
    h = bundle.horizon_days

    # --- Baseline cash paths and resampled series ---
    baseline_cash = cash_paths(state, bundle, obligations)  # (n, h)
    disc = discretionary_resampled_paths(state, bundle)      # (n, h)
    pv_mat = portfolio_value_paths(state, bundle)            # (n, h) or None
    cost_is_path_dependent = pv_mat is not None

    # --- Credit setup ---
    account = _select_primary_credit_account(state)
    available_credit = float(sum(a.available_credit for a in state.credit_accounts))

    credit_due_day = h  # fallback: repay at end of horizon
    c_interest = 0.0

    if account is not None and available_credit > 0:
        due_offset = _next_charge_payment_offset(state.as_of, account)
        credit_due_day = max(1, due_offset)
        grace_applies = (
            account.grace_period_eligible
            and account.current_balance <= 0.0
        )
        if not grace_applies:
            c_interest = account.purchase_apr / 365.0 * credit_due_day

    # A[t]: cumulative credit effect per dollar drawn (credit arrives day 0,
    # repaid with interest at credit_due_day).
    A_daily = np.zeros(h)
    if available_credit > 0:
        A_daily[0] = 1.0
        repay_col = min(credit_due_day - 1, h - 1)
        A_daily[repay_col] -= (1.0 + c_interest)
    A = np.cumsum(A_daily)  # (h,)

    # --- Liquidation setup ---
    initial_mv = state.marketable_backup_capital
    # Default settlement: T+1 + 2-day external transfer (FundingConfig defaults)
    settlement_days = 3
    settle_col = min(settlement_days - 1, h - 1)

    total_cb = sum(holding.cost_basis for holding in state.taxable_portfolio)
    cost_basis_fraction = total_cb / max(initial_mv, 1e-9)

    # B_mat[j, t]: cumulative liquidation proceeds per dollar of liq, per path.
    B_mat = np.zeros((n, h))
    if pv_mat is not None and initial_mv > 0:
        scale = pv_mat[:, settle_col] / max(initial_mv, 1e-9)  # (n,)
        B_mat[:, settle_col:] = scale[:, np.newaxis]
        c_tax_vec = (scale - cost_basis_fraction) * capital_gains_rate  # (n,)
        c_tax_scalar: float | None = None
    else:
        B_mat[:, settle_col:] = 1.0
        c_tax_scalar = (1.0 - cost_basis_fraction) * capital_gains_rate
        c_tax_vec = None

    # C_mat[j, t]: cumulative discretionary savings per unit def_frac
    C_mat = np.cumsum(disc, axis=1)  # (n, h)
    c_deferred = float(np.mean(disc)) * h  # expected total spending per unit def_frac

    # --- Buffer tolerance default ---
    policy = FundingPolicy()
    if buffer_tolerance_dollar_days is None:
        buffer_tolerance_dollar_days = (
            policy.max_cash_shortfall_probability * n * operating_buffer / 365
        )

    # --- cvxpy variables ---
    credit = cp.Variable(nonneg=True)
    liq = cp.Variable(nonneg=True)
    def_frac = cp.Variable(nonneg=True)
    eta = cp.Variable()
    u = cp.Variable(n, nonneg=True)         # CVaR overshoot per scenario
    s = cp.Variable((n, h), nonneg=True)    # buffer aux: max(0, buf - B_adj)
    v = cp.Variable((n, h), nonneg=True)    # overdraft aux: max(0, -B_adj)

    # Broadcast A to (n, h) for matrix expression
    A_bc = np.broadcast_to(A[np.newaxis, :], (n, h)).copy()

    # Adjusted balance B_adj (affine in the three control variables)
    immediate = float(state.immediate_funding)
    B_adj = immediate + baseline_cash + credit * A_bc + liq * B_mat + def_frac * C_mat

    # Per-path overdraft cost (below-zero cash is penalised at overdraft_apr)
    overdraft_cost_j = (overdraft_apr / 365) * cp.sum(v, axis=1)  # (n,)

    # Per-path tax cost (varies per path when market data is present)
    if c_tax_vec is not None:
        tax_cost_j = liq * c_tax_vec  # scalar Variable × (n,) constant → (n,)
    else:
        tax_cost_j = liq * float(c_tax_scalar)  # scalar expression

    # Per-path total cost
    cost_j = c_interest * credit + c_deferred * def_frac + tax_cost_j + overdraft_cost_j

    # CVaR objective (Rockafellar-Uryasev)
    q = coverage_target
    objective = eta + cp.sum(u) / ((1.0 - q) * n)

    # Telser buffer constraint (named for dual_value access after solve)
    buffer_constraint = cp.sum(s) / n <= buffer_tolerance_dollar_days

    constraints = [
        u >= cost_j - eta,
        s >= operating_buffer - B_adj,
        v >= -B_adj,
        credit <= available_credit,
        liq <= initial_mv,
        def_frac <= 1.0,
        buffer_constraint,
    ]

    # --- Solve ---
    prob = cp.Problem(cp.Minimize(objective), constraints)
    try:
        prob.solve(solver=cp.CLARABEL, verbose=False)
    except Exception:
        return None

    status = prob.status or ""
    if status not in ("optimal", "optimal_inaccurate"):
        return None

    # --- Extract solution (clip to valid bounds) ---
    def _safe(val: object, lo: float = 0.0, hi: float = float("inf")) -> float:
        return float(np.clip(val if val is not None else lo, lo, hi))

    credit_val = _safe(credit.value, 0.0, available_credit)
    liq_val = _safe(liq.value, 0.0, initial_mv)
    def_frac_val = _safe(def_frac.value, 0.0, 1.0)
    eta_val = float(eta.value) if eta.value is not None else 0.0
    cvar_val = float(prob.value) if prob.value is not None else 0.0

    # Expected cost (evaluated at the optimal point)
    v_vals = v.value if v.value is not None else np.zeros((n, h))
    if c_tax_vec is not None:
        tax_at_opt = liq_val * c_tax_vec  # (n,)
    else:
        tax_at_opt = np.full(n, liq_val * float(c_tax_scalar))
    cost_j_vals = (
        c_interest * credit_val
        + c_deferred * def_frac_val
        + tax_at_opt
        + (overdraft_apr / 365) * v_vals.sum(axis=1)
    )
    expected_cost = float(np.mean(cost_j_vals))

    # Cash shortfall probability at the optimal point
    B_adj_val = (
        immediate + baseline_cash
        + credit_val * A_bc
        + liq_val * B_mat
        + def_frac_val * C_mat
    )
    cash_shortfall_probability = float(np.mean(np.any(B_adj_val < 0, axis=1)))

    # Implied liquidity price: dual value of the buffer constraint
    try:
        dual_raw = buffer_constraint.dual_value
        implied_price = float(dual_raw) if dual_raw is not None and float(dual_raw) >= 0 else None
    except Exception:
        implied_price = None

    return OptimalPlan(
        credit_draw=credit_val,
        liquidation_amount=liq_val,
        deferral_fraction=def_frac_val,
        cvar_cost=cvar_val,
        var_cost=eta_val,
        expected_cost=expected_cost,
        cash_shortfall_probability=cash_shortfall_probability,
        implied_liquidity_price=implied_price,
        cost_is_path_dependent=cost_is_path_dependent,
        solver_status=status,
    )
