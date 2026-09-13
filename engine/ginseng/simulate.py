"""Stationary block bootstrap over the joint income/spending series
(spec sections 15-17, 20).

The joint series
    Y_t = [variable income_t, essential variable spending_t, discretionary
    spending_t]
is resampled with shared time indices so cross-series dependence between
uncertain income and spending survives the resample (spec 15). Fixed known
flows (fixed income, fixed obligations, inserted future obligations) are
added deterministically and are never resampled (spec 12, 20).

Every consumer of the stochastic forecast takes a `DrawBundle` so that
paired plan comparisons can later reuse identical draws under common random
numbers (spec 20).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from ginseng.state import FinancialState, Obligation, TransactionType

MIN_MEAN_BLOCK_LENGTH = 7
MAX_MEAN_BLOCK_LENGTH = 28


@dataclass(frozen=True)
class DrawBundle:
    """A reusable set of bootstrap draws (spec section 20).

    `index_matrix` has shape `(n_paths, horizon_days)`; entry `[j, t]` is the
    historical day index resampled for path `j` at forecast day `t + 1`.
    `bootstrap_draw_id` is a stable hex digest of `index_matrix`, so any two
    consumers holding the same bundle are provably evaluating identical
    stochastic realizations.
    """

    seed: int
    horizon_days: int
    n_paths: int
    mean_block_length: int
    mean_block_length_was_clipped: bool
    history_length: int
    index_matrix: np.ndarray
    bootstrap_draw_id: str


def _joint_history(state: FinancialState) -> pd.DataFrame:
    """The daily joint series Y_t (spec 15) over the full recorded ledger
    window. Irregular expenses are excluded, per spec 10."""
    start = min(t.txn_date for t in state.transactions)
    end = state.as_of
    return pd.DataFrame(
        {
            "variable_income": state.daily_series(TransactionType.INCOME_VARIABLE, start, end),
            "essential_variable_spending": state.daily_series(
                TransactionType.EXPENSE_ESSENTIAL_VARIABLE, start, end
            ),
            "discretionary_spending": state.daily_series(
                TransactionType.EXPENSE_DISCRETIONARY_VARIABLE, start, end
            ),
        }
    )


def _fallback_block_length(z: np.ndarray) -> float:
    """Documented fallback mean block length when `arch`'s Politis-White
    estimator is unavailable: convert the lag-1 autocorrelation of the
    composite net-flow series into an expected geometric block length,
    `1 / (1 - |rho_1|)`, the mean run length of an AR(1)-equivalent process
    with that autocorrelation.
    """
    centered = z - z.mean()
    denom = float(np.sum(centered * centered))
    if denom <= 0.0:
        return 14.0
    rho1 = float(np.sum(centered[:-1] * centered[1:]) / denom)
    rho1 = min(max(rho1, -0.95), 0.95)
    return 1.0 / (1.0 - abs(rho1))


def _estimate_mean_block_length(z: np.ndarray) -> tuple[int, bool]:
    """Return the usable mean block length and whether the data estimate
    exceeded Ginseng's supported [7, 28]-day window."""
    try:
        from arch.bootstrap import optimal_block_length

        block_lengths = optimal_block_length(z)
        stationary_column = "stationary" if "stationary" in block_lengths.columns else "b_sb"
        estimate = float(block_lengths[stationary_column].iloc[0])
    except (ImportError, ValueError, FloatingPointError):
        estimate = _fallback_block_length(z)
    if not np.isfinite(estimate) or estimate <= 0:
        estimate = 14.0
    rounded = round(estimate)
    resolved = int(np.clip(rounded, MIN_MEAN_BLOCK_LENGTH, MAX_MEAN_BLOCK_LENGTH))
    return resolved, resolved != rounded


def estimate_mean_block_length(z: np.ndarray) -> int:
    """Estimate `L` (spec 17): the Politis-White optimal Stationary Bootstrap
    block length for the composite net-flow series `Z_t`, clipped to
    `[7, 28]` for hackathon stability."""
    return _estimate_mean_block_length(z)[0]


def _stationary_bootstrap_indices(
    rng: np.random.Generator,
    n_hist: int,
    n_paths: int,
    horizon_days: int,
    mean_block_length: int,
) -> np.ndarray:
    """Vectorized Stationary Bootstrap (spec 16): geometric block lengths
    with mean `mean_block_length`, wrapping circularly through the `n_hist`
    historical days so every path stays fully defined."""
    continuation_probability = 1.0 - 1.0 / mean_block_length
    index_matrix = np.empty((n_paths, horizon_days), dtype=np.int64)
    index_matrix[:, 0] = rng.integers(0, n_hist, size=n_paths)
    continue_draws = rng.random((n_paths, horizon_days))
    restart_indices = rng.integers(0, n_hist, size=(n_paths, horizon_days))
    for t in range(1, horizon_days):
        continues = continue_draws[:, t] < continuation_probability
        index_matrix[:, t] = np.where(
            continues, (index_matrix[:, t - 1] + 1) % n_hist, restart_indices[:, t]
        )
    return index_matrix


def _compute_draw_id(index_matrix: np.ndarray) -> str:
    payload = np.ascontiguousarray(index_matrix, dtype=np.int64).tobytes()
    return hashlib.sha256(payload).hexdigest()


def draw_bundle(
    state: FinancialState,
    horizon_days: int,
    n_paths: int,
    seed: int,
    mean_block_length: int | None = None,
) -> DrawBundle:
    """Draw a reusable set of joint bootstrap indices for `state`."""
    joint = _joint_history(state)
    n_hist = len(joint)
    if mean_block_length is None:
        z = (
            joint["variable_income"]
            - joint["essential_variable_spending"]
            - joint["discretionary_spending"]
        ).to_numpy()
        resolved_block_length, mean_block_length_was_clipped = _estimate_mean_block_length(z)
    else:
        resolved_block_length = int(
            np.clip(mean_block_length, MIN_MEAN_BLOCK_LENGTH, MAX_MEAN_BLOCK_LENGTH)
        )
        mean_block_length_was_clipped = False

    rng = np.random.default_rng(seed)
    index_matrix = _stationary_bootstrap_indices(rng, n_hist, n_paths, horizon_days, resolved_block_length)
    return DrawBundle(
        seed=seed,
        horizon_days=horizon_days,
        n_paths=n_paths,
        mean_block_length=resolved_block_length,
        mean_block_length_was_clipped=mean_block_length_was_clipped,
        history_length=n_hist,
        index_matrix=index_matrix,
        bootstrap_draw_id=_compute_draw_id(index_matrix),
    )


def _recurring_days(item: Obligation, horizon_days: int) -> list[int]:
    """Forecast-day offsets (1-indexed) on which a scheduled item lands
    within `[1, horizon_days]`."""
    days: list[int] = []
    day = max(1, item.due_in_days)
    while day <= horizon_days:
        days.append(day)
        if item.recurrence_days is None or item.recurrence_days <= 0:
            break
        day += item.recurrence_days
    return days


def _deterministic_daily_flow(
    state: FinancialState, obligations: Sequence[Obligation], horizon_days: int
) -> np.ndarray:
    """The deterministic component of daily net flow (spec 12, 20): fixed
    income, fixed obligations, and any inserted future obligations. Never
    resampled."""
    flow = np.zeros(horizon_days, dtype=float)
    for item in state.fixed_income_schedule:
        for day in _recurring_days(item, horizon_days):
            flow[day - 1] += abs(item.amount)
    for item in state.fixed_obligations:
        for day in _recurring_days(item, horizon_days):
            flow[day - 1] -= abs(item.amount)
    for obligation in obligations:
        day = max(1, obligation.due_in_days)
        if day <= horizon_days:
            flow[day - 1] -= abs(obligation.amount)
    return flow


def known_flows(
    state: FinancialState, obligations: Sequence[Obligation], horizon_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative deterministic income and obligation series for charting
    context, each of length `horizon_days`."""
    income_daily = np.zeros(horizon_days, dtype=float)
    for item in state.fixed_income_schedule:
        for day in _recurring_days(item, horizon_days):
            income_daily[day - 1] += abs(item.amount)

    obligation_daily = np.zeros(horizon_days, dtype=float)
    for item in state.fixed_obligations:
        for day in _recurring_days(item, horizon_days):
            obligation_daily[day - 1] += abs(item.amount)
    for obligation in obligations:
        day = max(1, obligation.due_in_days)
        if day <= horizon_days:
            obligation_daily[day - 1] += abs(obligation.amount)

    return np.cumsum(income_daily), np.cumsum(obligation_daily)


def discretionary_resampled_paths(state: FinancialState, bundle: DrawBundle) -> np.ndarray:
    """Per-path, per-day resampled discretionary spending, shape
    `(n_paths, horizon_days)`, selected by the same joint bootstrap
    indices `cash_paths` uses for its discretionary column (spec 15), so
    funding plans defer exactly the spending the cash forecast spent."""
    disc = _joint_history(state)["discretionary_spending"].to_numpy()
    return disc[bundle.index_matrix]


def portfolio_value_paths(state: FinancialState, bundle: DrawBundle) -> np.ndarray | None:
    """Per-path market value of the marketable portfolio at each forecast
    day, shape `(n_paths, horizon_days)`, grown from today's
    `marketable_backup_capital` by the market returns on the same joint
    bootstrap day indices the cash forecast resamples (spec 8.3, 15).

    Returns None when the state carries no market history or no marketable
    assets, so no portfolio-dependent metric is fabricated from a flat or
    zero-valued market.
    """
    initial_value = state.marketable_backup_capital
    if not state.portfolio_daily_returns or initial_value <= 0.0:
        return None
    joint = _joint_history(state)
    returns_by_date = dict(state.portfolio_daily_returns)
    market_history = np.array(
        [returns_by_date.get(ts.date(), 0.0) for ts in joint.index]
    )
    daily_returns = market_history[bundle.index_matrix]
    return initial_value * np.cumprod(1.0 + daily_returns, axis=1)


def cash_paths(
    state: FinancialState, bundle: DrawBundle, obligations: Sequence[Obligation] = ()
) -> np.ndarray:
    """`X_{j,t}` (spec 21): cumulative future net cash flow, excluding
    today's starting immediate funding. Shape `(n_paths, horizon_days)`."""
    joint = _joint_history(state)
    income = joint["variable_income"].to_numpy()
    essential = joint["essential_variable_spending"].to_numpy()
    discretionary = joint["discretionary_spending"].to_numpy()

    idx = bundle.index_matrix
    stochastic_daily = income[idx] - essential[idx] - discretionary[idx]
    deterministic_daily = _deterministic_daily_flow(state, obligations, bundle.horizon_days)

    daily_net = stochastic_daily + deterministic_daily[np.newaxis, :]
    return np.cumsum(daily_net, axis=1)
