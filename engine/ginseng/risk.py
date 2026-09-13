"""Empirical probabilities and exact fractional tails, including tied losses."""

from __future__ import annotations

import hashlib
import numpy as np


def probabilities(n: int, weights: np.ndarray | None = None) -> np.ndarray:
    if n < 1:
        raise ValueError("At least one scenario is required.")
    w = np.full(n, 1.0 / n) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != (n,) or not np.all(np.isfinite(w)) or np.any(w < 0) or w.sum() <= 0:
        raise ValueError("Scenario weights must be finite, nonnegative, and have positive mass.")
    total = float(w.sum())
    # Re-normalizing an already normalized vector can alternate its last
    # floating-point bit, giving identical comparisons different hashes.
    return w.copy() if abs(total - 1.0) <= 1e-14 else w / total


def weight_hash(weights: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(weights, dtype="<f8").tobytes()).hexdigest()


def quantile(values: np.ndarray, q: float, weights: np.ndarray | None = None) -> float:
    """Smallest observed value whose cumulative probability reaches q.

    Unlike linear interpolation, this preserves the advertised empirical
    coverage even with a small sample or a large probability atom.
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or not np.all(np.isfinite(x)) or not 0 <= q <= 1:
        raise ValueError("Quantiles require finite one-dimensional losses and q in [0, 1].")
    w = probabilities(len(x), weights)
    order = np.argsort(x[w > 0], kind="stable")
    positive_x, positive_w = x[w > 0][order], w[w > 0][order]
    cumulative = np.cumsum(positive_w)
    index = min(int(np.searchsorted(cumulative, q - 1e-14)), len(order) - 1)
    return float(positive_x[max(0, index)])


def tail_probabilities(values: np.ndarray, q: float, weights: np.ndarray | None = None) -> np.ndarray:
    """Normalize exactly 1-q tail mass; split boundary ties proportionally.

    At q=1 this is the empirical maximum, with tied maxima sharing mass.
    Ties may give a tail ENS above (1-q)*n; that is intentional, and avoids
    selecting arbitrary scenario indices to break an atom.
    """
    x = np.asarray(values, dtype=float)
    w = probabilities(len(x), weights)
    cutoff = quantile(x, q, w)
    if q == 1:
        tail = w * (x == cutoff)
    else:
        above = x > cutoff
        tail = w * above
        boundary = x == cutoff
        remaining = max(0.0, 1.0 - q - float(tail.sum()))
        tail += w * boundary * (remaining / float(w[boundary].sum()))
    return probabilities(len(x), tail)


def cvar(values: np.ndarray, q: float, weights: np.ndarray | None = None) -> float:
    return float(np.dot(np.asarray(values), tail_probabilities(values, q, weights)))


def effective_scenarios(weights: np.ndarray) -> float:
    positive = weights[weights > 0]
    return float(np.exp(-np.dot(positive, np.log(positive))))


def concentration(values: np.ndarray, q: float, weights: np.ndarray) -> dict:
    w = probabilities(len(values), weights)
    tail = tail_probabilities(values, q, w)
    return {
        "ens_overall": effective_scenarios(w),
        "ens_tail": effective_scenarios(tail),
        "max_weight": float(w.max()),
        "tail_mass": 1.0 - q,
        "tail_definition": "Exact upper-tail mass with proportional allocation at tied losses; q=1 uses maxima.",
    }
