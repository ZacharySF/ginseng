"""HTTP contract invariants (spec sections 13-14; section 74: Scenario
Pairing, determinism): the frozen response shape with correct types and
array lengths, byte-identical repeated evaluations, and shared draw ids
across paired evaluations of one seed.
"""

import re
from datetime import date

from fastapi.testclient import TestClient

from ginseng.api import app

client = TestClient(app)

SCENARIO_BODY_FIELDS = {
    "as_of",
    "seed",
    "bootstrap_draw_id",
    "mean_block_length",
    "immediate_funding",
    "marketable_backup_capital",
    "restricted_capital",
    "coverage_target",
    "operating_buffer",
    "required_liquidity_reserve",
    "funding_gap",
    "coverage_at_current_funding",
    "severity",
    "estimate_band",
    "coverage_curve",
    "cash_paths",
    "shortfall_distribution",
    "plans",
    "recommendation",
    "sensitivity",
    "sensitivity_verdict",
}

REPAIR = {
    "id": "repair",
    "label": "Emergency vehicle repair",
    "amount": 4500.0,
    "due_in_days": 3,
}

FLOAT_FIELDS = (
    "immediate_funding",
    "marketable_backup_capital",
    "restricted_capital",
    "coverage_target",
    "operating_buffer",
    "required_liquidity_reserve",
    "funding_gap",
    "coverage_at_current_funding",
)


def _post(**overrides):
    payload = {
        "seed": 20260911,
        "horizon_days": 30,
        "coverage_target": 0.95,
        "operating_buffer": 1000.0,
        "paths": 240,
        "mean_block_length": 12,
        "obligations": [],
    }
    payload.update(overrides)
    response = client.post("/scenario", json=payload)
    assert response.status_code == 200
    return response.json()


def test_health_returns_exactly_the_frozen_contract():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "seed_default"}
    assert body["status"] == "ok"
    assert isinstance(body["status"], str)
    assert isinstance(body["seed_default"], int) and not isinstance(body["seed_default"], bool)


def test_scenario_returns_exactly_the_frozen_field_set_with_valid_types():
    body = _post(obligations=[REPAIR])
    assert set(body) == SCENARIO_BODY_FIELDS

    date.fromisoformat(body["as_of"])  # an ISO calendar date
    assert isinstance(body["seed"], int) and body["seed"] == 20260911
    assert re.fullmatch(r"[0-9a-f]{64}", body["bootstrap_draw_id"])  # sha256 draw id
    assert isinstance(body["mean_block_length"], int) and body["mean_block_length"] == 12
    for field in FLOAT_FIELDS:
        assert isinstance(body[field], float), field

    # The hero number stays consistent with the reserve and today's funding.
    assert body["funding_gap"] == max(
        0.0, body["required_liquidity_reserve"] - body["immediate_funding"]
    )
    assert 0.0 <= body["coverage_at_current_funding"] <= 1.0

    assert body["estimate_band"] is not None
    assert set(body["estimate_band"]) == {"low", "high"}
    assert body["estimate_band"]["low"] <= body["required_liquidity_reserve"] <= body["estimate_band"]["high"]
    assert len(body["plans"]) > 0
    assert body["recommendation"] is not None
    assert set(body["recommendation"]) == {"plan_id", "explanation"}
    assert {row["block_label"] for row in body["sensitivity"]} >= {"7d", "14d", "21d"}
    assert sum(1 for row in body["sensitivity"] if row["is_estimated"]) == 1
    assert body["sensitivity_verdict"] in {
        "Reserve estimate is relatively insensitive to the persistence assumption.",
        "Reserve estimate is sensitive to income-persistence assumptions.",
    }

    severity = body["severity"]
    assert set(severity) == {
        "cash_shortfall_probability",
        "avg_cash_deficit_when_short",
        "dollar_days_below_buffer",
    }
    for value in severity.values():
        assert isinstance(value, float)
    assert 0.0 <= severity["cash_shortfall_probability"] <= 1.0
    assert severity["avg_cash_deficit_when_short"] >= 0.0
    assert severity["dollar_days_below_buffer"] >= 0.0

    curve = body["coverage_curve"]
    assert len(curve) >= 2
    for point in curve:
        assert set(point) == {"funding", "coverage"}
        assert isinstance(point["funding"], float)
        assert isinstance(point["coverage"], float)
        assert 0.0 <= point["coverage"] <= 1.0
    fundings = [point["funding"] for point in curve]
    coverages = [point["coverage"] for point in curve]
    assert fundings[0] == 0.0
    assert max(fundings) >= body["immediate_funding"]  # the chart spans today's funding
    assert all(later > earlier for earlier, later in zip(fundings, fundings[1:]))
    assert all(later >= earlier for earlier, later in zip(coverages, coverages[1:]))


def test_scenario_array_lengths_match_horizon_days_and_histogram_bins():
    body = _post(horizon_days=21)

    cash = body["cash_paths"]
    assert set(cash) == {"days", "p10", "p50", "p90", "known_income", "known_obligations"}
    assert cash["days"] == list(range(1, 22))
    for key in ("p10", "p50", "p90", "known_income", "known_obligations"):
        assert len(cash[key]) == 21
        assert all(isinstance(value, float) for value in cash[key])
    for lower, upper in (("p10", "p50"), ("p50", "p90")):
        assert all(a <= b for a, b in zip(cash[lower], cash[upper]))

    distribution = body["shortfall_distribution"]
    assert set(distribution) == {"bin_edges", "counts"}
    counts = distribution["counts"]
    edges = distribution["bin_edges"]
    assert len(counts) == 30  # frozen histogram bins
    assert len(edges) == len(counts) + 1
    assert all(isinstance(count, int) and not isinstance(count, bool) for count in counts)
    assert all(isinstance(edge, float) for edge in edges)
    assert all(later > earlier for earlier, later in zip(edges, edges[1:]))
    assert sum(counts) == 240  # every simulated path lands in exactly one bin


def test_paired_scenarios_from_one_seed_share_their_draw_id():
    unshocked = _post(obligations=[])
    shocked = _post(obligations=[REPAIR])
    # The two evaluations differ only in obligations, so they must ride the
    # same stochastic draws (common random numbers, spec section 20).
    assert shocked["bootstrap_draw_id"] == unshocked["bootstrap_draw_id"]

    other_seed = _post(seed=20260912)
    assert other_seed["bootstrap_draw_id"] != unshocked["bootstrap_draw_id"]


def test_identical_scenario_requests_return_identical_json():
    payload = {
        "seed": 20260911,
        "horizon_days": 30,
        "coverage_target": 0.95,
        "operating_buffer": 1000.0,
        "paths": 240,
        "mean_block_length": 12,
        "obligations": [REPAIR],
    }
    first = client.post("/scenario", json=payload)
    second = client.post("/scenario", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
