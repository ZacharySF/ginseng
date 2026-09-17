"""Toy fixture for demos and tests. Not Ginseng's engine: never present these numbers as real."""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

import numpy as np

from .model import DashboardData, FundingOption, LedgerEntry, PathBands, Validation

HORIZON, PATHS, SEED = 30, 4096, 20260916
START_CASH = {"calm": 2500.0, "thin": 2000.0, "short": 1600.0}
BILLS = ((5, 1450.0), (12, 320.0), (18, 140.0), (22, 85.0), (26, 210.0))
INVOICES = ((1800.0, 10, 3.0, 0.14), (950.0, 17, 4.0, 0.18), (2400.0, 24, 5.0, 0.25))


@lru_cache(maxsize=1)
def _daily_flows() -> np.ndarray:
    rng = np.random.default_rng(SEED)
    daily = -rng.lognormal(mean=math.log(34.0), sigma=0.55, size=(PATHS, HORIZON))
    for day, amount in BILLS:
        daily[:, day - 1] -= amount
    for amount, day, sd, p_slip in INVOICES:
        arrive = np.rint(rng.normal(day, sd, size=PATHS)).astype(int)
        slipped = rng.random(PATHS) < p_slip
        ok = np.where(~slipped & (arrive >= 1) & (arrive <= HORIZON))[0]
        daily[ok, arrive[ok] - 1] += amount
    daily += rng.poisson(0.18, size=(PATHS, HORIZON)) * rng.lognormal(math.log(120), 0.35, size=(PATHS, HORIZON))
    return daily


def _kupiec_p(n: int, x: int, p0: float = 0.05) -> float:
    ph = x / n
    lr = -2 * ((n - x) * math.log(1 - p0) + x * math.log(p0)) + 2 * ((n - x) * math.log(1 - ph) + x * math.log(ph))
    return math.erfc(math.sqrt(lr / 2))


@lru_cache(maxsize=None)
def fixture(state: str = "thin") -> DashboardData:
    bal = START_CASH[state] + np.cumsum(_daily_flows(), axis=1)
    trough = bal.min(axis=1)
    pct = {q: np.percentile(bal, q, axis=0) for q in (5, 25, 50, 75, 95)}
    reserve = max(0.0, -float(np.percentile(trough, 5)))
    below = pct[5] < 0
    deficit = float(np.maximum(0, -bal).sum(axis=1).mean())

    def residual(extra: float, delay: int = 0) -> float:
        shifted = bal.copy()
        shifted[:, delay:] += extra
        return float((shifted.min(axis=1) < 0).mean())

    options: tuple[FundingOption, ...] = ()
    if reserve >= 0.5:
        advance_fee, apr = 0.05, 0.2999
        liquidation_rate = 0.0005 + 0.20 * 0.15 + 0.07 * HORIZON / 365
        part = 0.6 * reserve
        hybrid = bal + part
        options = (
            FundingOption("credit line", "credit",
                          advance_fee * float(np.maximum(0, -trough).mean()) + apr / 365 * deficit, 0, residual(reserve)),
            FundingOption("sell ETF", "liquidate", liquidation_rate * reserve, 2, residual(reserve, 2)),
            FundingOption("hybrid", "hybrid",
                          liquidation_rate * part + advance_fee * float(np.maximum(0, -hybrid.min(axis=1)).mean())
                          + apr / 365 * float(np.maximum(0, -hybrid).sum(axis=1).mean()), 0, residual(reserve)),
        )
    edges = np.linspace(-1600, 2400, 21)
    counts, _ = np.histogram(np.clip(trough, -1599, 2399), bins=edges)
    return DashboardData(
        plan=f"fixture:{state}", paths=PATHS, sampler="mc",
        draw_id=hashlib.blake2s(f"{SEED}:{state}".encode(), digest_size=4).hexdigest(),
        reserve_to_add=reserve,
        shortfall_p=float((trough < 0).mean()),
        cvar95_trough=float(np.sort(trough)[: int(0.05 * PATHS)].mean()),
        deficit_dollar_days=deficit,
        solvent_days=int(np.argmax(below)) if below.any() else HORIZON,
        bands=PathBands(pct[5], pct[25], pct[50], pct[75], pct[95]),
        trough_edges=tuple(edges), trough_counts=tuple(counts),
        options=options,
        ledger=(LedgerEntry(-2, "client X", 640.0, "settled"), LedgerEntry(5, "rent", -1450.0, "pending"),
                LedgerEntry(10, "invoice A", 1800.0, "estimate"), LedgerEntry(12, "car", -320.0, "pending")),
        validation=Validation(oracle_ok=True, coverage=1 - 15 / 250, windows=250, kupiec_p=_kupiec_p(250, 15)),
    )
