"""Reproducibility fingerprints and a model card tied to the actual run."""

from dataclasses import asdict
from datetime import date
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path

import numpy as np

from ginseng.risk import weight_hash

MODEL_VERSION = "0.3.0"
EVIDENCE_STATEMENT = "More simulations improve numerical precision. They do not create more historical evidence."


def digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=lambda item: item.isoformat() if isinstance(item, date) else str(item),
                             allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=1)
def source_fingerprint() -> str:
    root = Path(__file__).parent
    return digest({p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob("*.py"))})


def fingerprint(state, bundle, obligations, weights, view, config, cash_matrix) -> dict:
    inputs = digest({"state": asdict(state), "obligations": [asdict(item) for item in obligations]})
    paths = sha256()
    paths.update(inputs.encode())
    paths.update(bundle.bootstrap_draw_id.encode())
    paths.update(np.ascontiguousarray(cash_matrix, dtype="<f8").tobytes())
    libraries = {}
    for name in ("numpy", "scipy", "arch", "cvxpy", "clarabel"):
        try:
            libraries[name] = version(name)
        except PackageNotFoundError:
            libraries[name] = "unavailable"
    hashes = {
        "input_hash": inputs,
        "path_hash": paths.hexdigest(),
        "weight_hash": weight_hash(weights),
        "view_hash": digest(asdict(view) if view is not None else None),
        "model_hash": digest({"version": MODEL_VERSION, "source": source_fingerprint(), "config": config,
                              "libraries": libraries}),
    }
    return {**hashes, "run_hash": digest(hashes)}


def model_card(state, bundle, config, stress, hashes) -> dict:
    start = min(t.txn_date for t in state.transactions)
    return {
        "version": MODEL_VERSION,
        "evidence_statement": EVIDENCE_STATEMENT,
        "source": "Synthetic demonstration history; not the user's bank transactions.",
        "history_start": start.isoformat(), "history_end": state.as_of.isoformat(),
        "history_days": (state.as_of - start).days + 1,
        "simulation_paths": bundle.n_paths,
        "purpose": "Compare hypothetical liquidity choices under explicit assumptions.",
        "target": "Starting cash required to preserve the operating buffer at every modeled end-of-day balance.",
        "prohibited_uses": ["Automatic trading or borrowing", "Claims of validated real-household coverage", "Final tax liability"],
        "assumptions": config,
        "limitations": [
            "A deterministic bill can correctly move the reserve almost dollar for dollar; stress weights do not remove that property.",
            "Bootstrap futures replay historical blocks; they cannot establish probabilities for unseen regimes.",
            "Non-overlapping historical windows may still be dependent; intervals assume independent windows.",
            "Market, cash-flow, and asset histories in this demo are synthetic, including their dependence.",
            "Sales execute at recorded prices; settlement plus transfer uses a three-calendar-day approximation, not a trading calendar.",
            "Taxable gains use lot holding periods. Traditional IRA withdrawals assume ordinary income plus an early penalty; Roth access is capped at remaining regular contributions.",
            "Tax and penalty reserves are earmarked from proceeds, not actual withholding or final tax bills. Losses create no rebate; Roth earnings, conversions and unclassified retirement accounts are excluded.",
            "Funding controls are chosen today and held fixed across futures; this is not an adaptive trading policy.",
            "The credit model bridges cash using the primary card's purchase APR and statement timing; real cash advances may have different fees and terms.",
            "A daily two-state Gaussian income fit could learn payday versus non-payday, rather than droughts; regime switching is not fitted.",
        ],
        "recommendation_gates": ["Unavailable funding operation", "Every named plan fails policy limits",
                                 "Unsupported stress view or concentrated stress tail", "Solver failure or failed numerical feasibility checks"],
        "active_stress": stress, "fingerprints": hashes,
        "guidance": {"name": "Federal Reserve SR 26-2 (supersedes SR 11-7)",
                     "url": "https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm",
                     "use": "Documentation reference; no claim of banking-regulation compliance."},
    }
