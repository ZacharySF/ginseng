"""Bounded historical risk exploration for the authenticated web workspace."""

from dataclasses import asdict
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ginseng.inputs import InputCase
from ginseng.precision import PrecisionConfig, run_precision
from ginseng.provenance import digest
from ginseng.sampling import prepare_history, sample_bundle
from ginseng.simulate import cash_paths


class NumericalOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    action: Literal["precision", "surface"]
    absolute_error: Literal[0.005, 0.01] = 0.005
    max_paths: int = Field(default=65536, ge=1024, le=65536, strict=True)


def surface_from_paths(cumulative, opening_cash, additional_cash):
    """Rows=cash offsets, columns=days. Ever-negative uses the running minimum."""
    x = np.asarray(cumulative, dtype=float)
    offsets = np.asarray(additional_cash, dtype=float)
    if (
        x.ndim != 2
        or min(x.shape) < 1
        or not np.all(np.isfinite(x))
        or not np.isfinite(opening_cash)
    ):
        raise ValueError("Surface requires finite nonempty cash paths.")
    if (
        offsets.ndim != 1
        or not len(offsets)
        or np.any(offsets < 0)
        or not np.all(np.isfinite(offsets))
    ):
        raise ValueError("Cash additions must be finite and nonnegative.")
    minimum = np.minimum.accumulate(x, axis=1)
    probability, deficit = [], []
    for offset in offsets:
        losses = np.maximum(0, -(opening_cash + offset + minimum))
        probability.append(np.mean(losses > 0, axis=0).tolist())
        deficit.append(np.mean(losses, axis=0).tolist())
    return probability, deficit


def explore(case: InputCase, options: NumericalOptions, *, seed=42, block_length=None):
    h = case.state.forecast_horizon
    if not 1 <= h <= 60:
        raise ValueError(
            "Interactive risk exploration supports horizons up to 60 days."
        )
    start = case.state.history_start or min(
        (t.txn_date for t in case.state.transactions), default=case.state.as_of
    )
    end = case.state.history_end or case.state.as_of
    if (end - start).days + 1 > 3660:
        raise ValueError(
            "Interactive risk exploration supports at most ten years of history."
        )
    prepared = prepare_history(case.state, block_length)
    if len(prepared.joint) > 3660:
        raise ValueError(
            "Interactive risk exploration supports at most ten years of history."
        )
    identity = digest(
        dict(case=asdict(case), seed=seed, block_length=prepared.resolved_length)
    )
    if options.action == "precision":
        result = run_precision(
            case,
            PrecisionConfig(options.absolute_error, 0.95, options.max_paths, 512),
            estimator="initial-block-cmc",
            seed=seed,
            block_length=prepared.resolved_length,
        )
        return dict(
            kind="precision",
            input_id=identity,
            summary=result["summary"],
            method="Independent MC with initial-block conditioning",
            scope="Numerical uncertainty under the current historical model; not forecast accuracy.",
            result_id=result["manifest"]["result_hash"],
        )
    bundle = sample_bundle(prepared, h, 2048, seed, method="mc", domain=500)
    x = cash_paths(
        case.state, bundle, case.obligations, prepared_history=prepared.joint
    )
    opening = case.state.immediate_funding
    # Span is grounded in the modeled deficits, rounded to a readable dollar grid.
    worst = max(0.0, float(-(opening + x.min())))
    span = max(500.0, float(np.ceil(worst / 500) * 500))
    offsets = np.linspace(0, span, 21)
    probability, deficit = surface_from_paths(x, opening, offsets)
    return dict(
        kind="surface",
        input_id=identity,
        days=list(range(1, h + 1)),
        additional_cash=offsets.tolist(),
        opening_cash=opening,
        shortfall_probability=probability,
        expected_max_deficit=deficit,
        paths=2048,
        seed=seed,
        index_hash=bundle.bootstrap_draw_id,
        block_length=prepared.resolved_length,
        scope="Fixed 2,048-path MC sensitivity estimate. No simultaneous precision guarantee across the surface. Extra cash is available from day one; funding costs are excluded.",
    )
