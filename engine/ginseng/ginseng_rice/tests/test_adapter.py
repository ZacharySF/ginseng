"""Adapter tests: run the real engine on its smallest deterministic inputs (the
exact oracle, and the tiny simulate fixture) and check every DashboardData
field traces back to an engine value, not an invented one."""
from __future__ import annotations

import numpy as np

from ginseng.exact import enumerate_exact
from ginseng.inputs import fixture as engine_fixture
from ginseng.numerical import run_core
from ginseng.risk import cvar, probabilities, quantile
from ginseng.sampling import prepare_history

from ..dashboard.adapter import EngineRun, from_engine


def _exact_run():
    result = enumerate_exact()
    sequences = result["sequences"]
    matrix = np.array([row["cumulative"] for row in sequences], dtype=float)
    weights = np.array([row["probability"] for row in sequences], dtype=float)
    run = EngineRun(
        kind="exact", summary=result["summary"],
        manifest=dict(method="independent rational enumeration"),
        matrix=matrix, opening_cash=30.0, weights=weights,
    )
    return result, run


def test_exact_oracle_maps_onto_dashboard_data():
    result, run = _exact_run()
    data = from_engine(run)
    summary = result["summary"]

    assert data.plan == "exact-oracle"
    assert data.sampler == "oracle"
    assert data.paths == len(result["sequences"])
    assert data.reserve_to_add == summary["funding_gap"]
    assert data.shortfall_p == summary["cash_shortfall_probability"]
    assert data.options == ()
    assert data.ledger == ()

    balance = run.opening_cash + run.matrix
    w = probabilities(balance.shape[0], run.weights)
    minima = balance.min(axis=1)

    assert data.cvar95_trough == -cvar(-minima, 0.95, w)
    assert data.deficit_dollar_days == float(w @ np.maximum(0.0, -balance).sum(axis=1))

    expected_p5 = np.array([quantile(balance[:, d], 0.05, w) for d in range(balance.shape[1])])
    np.testing.assert_allclose(data.bands.p5, expected_p5)
    expected_solvent = int(np.argmax(expected_p5 < 0)) if (expected_p5 < 0).any() else balance.shape[1]
    assert data.solvent_days == expected_solvent


def _simulate_run():
    case = engine_fixture("tiny")
    prepared = prepare_history(case.state, 7)
    bundle, matrix, summary = run_core(case, prepared, "mc", 256, 42, None, None, 0, estimator="path")
    manifest = dict(fixture=case.name, sampler=bundle.sampler, actual_n=bundle.n_paths,
                     index_hash=bundle.bootstrap_draw_id)
    run = EngineRun(
        kind="simulate", summary=summary, manifest=manifest, matrix=matrix,
        opening_cash=case.state.immediate_funding, state=case.state,
        obligations=case.obligations, bundle=bundle,
    )
    return case, run


def test_simulate_run_prices_funding_options_when_gap_exists():
    case, run = _simulate_run()
    data = from_engine(run)

    assert data.plan == case.name
    assert data.sampler == "mc"
    assert data.paths == run.matrix.shape[0]
    assert data.reserve_to_add == run.summary["funding_gap"]
    assert data.shortfall_p == run.summary["cash_shortfall_probability"]
    assert len(data.ledger) == len(case.obligations)
    assert all(entry.status == "pending" for entry in data.ledger)
    if data.reserve_to_add >= 0.5:
        assert data.options
        for option in data.options:
            assert option.kind in ("credit", "liquidate", "hybrid", "protective")
            assert 0.0 <= option.tail <= 1.0
            assert option.cost >= 0.0
            assert option.ready_days >= 0
    else:
        assert data.options == ()
