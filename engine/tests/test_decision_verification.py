"""Independent arithmetic, hostile plans, consumer gates, and frozen holdouts."""

import json
from dataclasses import replace

import numpy as np
import pytest
from ginseng.decision_artifact import capture_decision, load_decision, replay_decision
from ginseng.decision_lab import fixed_interval, independent_streams, run_lab
from ginseng.engine_artifact import ArtifactError
from ginseng.generate import canonical_shocks
from ginseng.inputs import fixture
from ginseng.optimizer import OptimalPlan, OptimizationFailure, optimize_funding
from ginseng.simulate import draw_bundle
from ginseng.state import Obligation
from ginseng.verification import (
    ExecutablePlan,
    RiskContract,
    check,
    controls_from_state,
    measure_risk,
    reference_cvar,
    reference_quantile,
    verify_optimal,
    verify_plan,
)
from scipy.optimize import linprog

from tests.test_execution import direct
from tests.test_optimizer import _credit_account, _state, _taxable_holding


def test_dollar_day_counterexample_is_not_a_probability_contract():
    # Every path has exactly one -$1 end-of-day balance, then recovers to $100.
    balances = np.full((7, 30), 100.0)
    balances[:, 9] = -1
    daily = np.diff(np.column_stack((np.zeros(7), balances)), axis=1)
    r = verify_plan(
        direct(daily),
        controls_from_state(_state()),
        ExecutablePlan(),
        RiskContract(100, 0.95, mean_buffer_allowance=100 * 30 * 0.05),
    )
    assert r.status == "verified"
    assert r.metrics["expected_buffer_dollar_days"] == pytest.approx(101)
    assert r.metrics["cash_failure_probability"] == pytest.approx(1)
    assert r.policy_status == "fail"
    assert (
        next(c for c in r.constraints if c.name == "mean_buffer_dollar_days").status
        == "pass"
    )


def test_exact_zero_recovery_and_strict_versus_legacy_micro_boundary():
    r = measure_risk(
        np.array([[0.0, 0.0], [-1.0, 100.0], [-1e-8, 2.0]]), 0, RiskContract(0, 0.5)
    )
    assert r["cash_failure_probability"] == pytest.approx(2 / 3)
    assert r["legacy_cash_failure_probability"] == pytest.approx(1 / 3)
    assert r["expected_buffer_dollar_days"] == pytest.approx((1 + 1e-8) / 3)
    assert check("missing", "dollars", None, 1).status == "unavailable"


def test_weighted_tail_ties_and_inverse_cdf_hand_oracle():
    x = np.array([0.0, 10, 10, 40, 999])
    w = np.array([0.2, 0.3, 0.4, 0.1, 0])
    assert reference_quantile(x, 0.9, w) == 10
    assert reference_quantile(x, 1, w) == 40
    assert reference_cvar(x, 0.8, w) == pytest.approx(25)
    assert reference_cvar(x, 1, w) == 40
    assert reference_cvar(x, 0, w) == pytest.approx(11)


def test_independent_late_repayment_and_earmarked_withdrawal_arithmetic():
    state = _state(
        cards=(_credit_account("card", 100, grace_period_eligible=True),),
        holdings=(_taxable_holding(1000, 0),),
    )
    controls = controls_from_state(state)
    p = ExecutablePlan("card", 100, (("taxable:test-lot", 100),), spending_days=5)
    contract = RiskContract(0, 0.95)
    short = verify_plan(direct(np.zeros((2, 5))), controls, p, contract)
    assert short.status == "failed" and "repayment_within_material" in short.reason
    long = verify_plan(direct(np.zeros((2, 30))), controls, p, contract)
    # At exactly one year the existing tax contract uses the ordinary rate .24.
    assert long.execution["withdrawal_net"] == 76
    assert long.execution["withdrawal_tax"] == 24
    assert long.execution["repayment"] == 100
    assert long.execution["repayment_day"] == 24
    assert long.metrics["objective"] == 24
    assert long.status == "verified"
    # Sale cannot fund a day-one bill before settlement (day 3).
    daily = np.zeros((1, 5))
    daily[0, 0] = -50
    r = verify_plan(direct(daily), controls, replace(p, credit_draw=0), contract)
    assert r.metrics["cash_failure_probability"] == 1
    assert r.metrics["expected_max_cash_deficit"] == 50


def test_bounds_missing_evidence_and_double_counting_are_rejected():
    controls = controls_from_state(_state(holdings=(_taxable_holding(100, 100),)))
    prepared = direct([[0.0, 0.0, 0.0]])
    for plan in (
        ExecutablePlan(credit_draw=1),
        ExecutablePlan(withdrawals=(("bad", 1),)),
        ExecutablePlan(withdrawals=(("taxable:test-lot", 101),)),
        ExecutablePlan(
            withdrawals=(("taxable:test-lot", 101), ("taxable:test-lot", -1))
        ),
        ExecutablePlan(spending_fraction=1.1),
        ExecutablePlan(unfunded_cash=1),
    ):
        assert (
            verify_plan(
                prepared,
                controls,
                plan,
                RiskContract(0, 0.95),
                discretionary=np.zeros((1, 3)),
            ).status
            == "failed"
        )
    with pytest.raises(ValueError, match="Missing discretionary"):
        verify_plan(
            prepared,
            controls,
            ExecutablePlan(spending_fraction=0.5),
            RiskContract(0, 0.95),
        )


def solved():
    state = _state(holdings=(_taxable_holding(1000, 0),))
    bundle = draw_bundle(state, 30, 8, 1)
    bills = (Obligation("bill", "Bill", 100, 3),)
    plan = optimize_funding(
        state, bundle, bills, operating_buffer=0, buffer_tolerance_dollar_days=0
    )
    assert isinstance(plan, OptimalPlan)
    return state, bundle, bills, plan


def test_independent_tiny_lp_and_honestly_unavailable_global_bound():
    state, bundle, bills, plan = solved()
    # Independently formulated one-variable LP: .76*x >= $100; minimize .24*x.
    oracle = linprog(
        [0.24], A_ub=[[-0.76]], b_ub=[-100], bounds=[(0, 1000)], method="highs"
    )
    assert oracle.success
    assert plan.expected_cost == pytest.approx(oracle.fun, abs=1e-5)
    assert plan.liquidation_amount == pytest.approx(oracle.x[0], abs=1e-5)
    assert plan.verification["status"] == "verified"
    assert plan.solver_evidence["global_lower_bound"] is None
    assert (
        plan.solver_evidence["lower_bound"] is None
    )  # Clarabel path has no exported bound.


def test_stale_postsolve_plan_detected_even_if_still_feasible():
    state, bundle, bills, plan = solved()
    altered = replace(
        plan,
        withdrawal_allocations=tuple(
            replace(a, gross=a.gross + 1) for a in plan.withdrawal_allocations
        ),
    )
    r = verify_optimal(
        state, bundle, bills, altered, RiskContract(0, 0.95, mean_buffer_allowance=0)
    )
    assert r.status == "failed"
    assert "frozen_plan_identity" in r.reason and "reported_objective" in r.reason


def test_actual_consumer_rejects_mocked_successful_infeasible_plan(monkeypatch):
    from ginseng.scenario_service import evaluate_funding

    state, bundle, bills, plan = solved()
    bad = replace(
        plan, withdrawal_allocations=(), liquidation_amount=0, solver_status="optimal"
    )
    monkeypatch.setattr(
        "ginseng.scenario_service.optimize_funding", lambda *a, **kw: bad
    )
    response = evaluate_funding(
        state, bundle, bills, 100, coverage_target=0.95, operating_buffer=0
    )
    assert isinstance(response[2], OptimizationFailure)
    assert response[2].reason == "invalid_solution"
    assert response[2].verification["status"] == "failed"


def test_nonunique_free_withdrawals_compared_by_cost_and_feasibility():
    controls = controls_from_state(_state(holdings=(_taxable_holding(1000, 1000),)))
    daily = np.zeros((1, 5))
    daily[:, 2] = -100
    p = direct(daily)
    c = RiskContract(0, 0.95, mean_buffer_allowance=0)
    a = verify_plan(
        p, controls, ExecutablePlan(withdrawals=(("taxable:test-lot", 100),)), c
    )
    b = verify_plan(
        p, controls, ExecutablePlan(withdrawals=(("taxable:test-lot", 150),)), c
    )
    assert a.status == b.status == "verified"
    assert a.metrics["objective"] == b.metrics["objective"] == 0
    assert a.identity.plan != b.identity.plan


def small_run():
    c = fixture("canonical")
    run = run_lab(
        c.state, canonical_shocks(), paths=16, validation_paths=32, replications=2
    )
    run.report.update(synthetic=True, fixture="synthetic canonical")
    return run


def test_holdout_untouched_during_selection_and_plan_frozen(monkeypatch):
    import ginseng.decision_lab as lab

    events = []
    original_sample = lab.sample_bundle
    original_solve = lab.optimize_funding

    def sample(*a, **kw):
        events.append(("sample", kw.get("domain")))
        return original_sample(*a, **kw)

    def solve(*a, **kw):
        assert ("sample", lab.VALIDATION_DOMAIN) not in events
        events.append(("solve", None))
        return original_solve(*a, **kw)

    monkeypatch.setattr(lab, "sample_bundle", sample)
    monkeypatch.setattr(lab, "optimize_funding", solve)
    r = small_run()
    assert len([e for e in events if e[0] == "solve"]) == 2
    assert (
        r.report["training"]["identity"]["plan"]
        == r.report["validation"]["identity"]["plan"]
    )
    s = r.report["streams"]
    assert s["training"]["derived_seed"] != s["validation"]["derived_seed"]
    with pytest.raises(ValueError, match="overlap"):
        independent_streams(s["training"], s["training"])
    # Zero observed failures is not certainty of no failures.
    assert fixed_interval(0, 32)["high"] > 0
    with pytest.raises(ValueError):
        fixed_interval(0.1111, 32)


def test_offline_capture_replay_corruption_and_explicit_personal_capture(
    tmp_path, monkeypatch
):
    import socket

    r = small_run()
    r.report["synthetic"] = False
    with pytest.raises(ArtifactError, match="Personal"):
        capture_decision(tmp_path / "denied", r)
    r.report["synthetic"] = True
    capture_decision(tmp_path / "run", r)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: pytest.fail("Replay attempted network"),
    )
    replayed = replay_decision(tmp_path / "run")
    assert replayed["match"]
    assert {"training_1", "no_action_validation"} <= replayed["results"].keys()
    m = json.loads((tmp_path / "run" / "validation" / "manifest.json").read_text())
    (
        tmp_path / "run" / "validation" / m["members"]["input:indices"]["path"]
    ).write_bytes(b"corrupt")
    with pytest.raises(ArtifactError):
        load_decision(tmp_path / "run")


def test_decision_manifest_rejects_unsafe_paths_even_with_recomputed_checksum(tmp_path):
    from ginseng.provenance import digest

    r = small_run()
    capture_decision(tmp_path / "run", r)
    path = tmp_path / "run" / "decision.json"
    m = json.loads(path.read_text())
    m.pop("integrity")
    m["prepared"]["training"]["path"] = "../outside"
    m["integrity"] = digest(m)
    path.write_text(json.dumps(m))
    with pytest.raises(ArtifactError, match="Unsafe"):
        load_decision(tmp_path / "run")


def test_strict_policy_and_legacy_boundary_are_both_explicit():
    r = verify_plan(
        direct([[-1e-8, 1]]),
        controls_from_state(_state()),
        ExecutablePlan(),
        RiskContract(0, 0.95, max_cash_failure_probability=0),
    )
    checks = {c.name: c for c in r.policy_checks}
    assert checks["cash_failure_probability_strict"].status == "fail"
    assert checks["cash_failure_probability_legacy_boundary"].status == "pass"
    assert r.status == "verified" and r.policy_status == "fail"


def test_remaining_roth_contributions_not_original_contributions_bound_execution():
    state = replace(
        _state(holdings=(replace(_taxable_holding(1000, 1000), account="roth"),)),
        roth_contribution_basis=30,
    )
    controls = controls_from_state(state)
    for amount, status in [(30, "verified"), (31, "failed")]:
        r = verify_plan(
            direct([[0.0, 0.0, 0.0]]),
            controls,
            ExecutablePlan(withdrawals=(("roth", amount),)),
            RiskContract(0, 0.95),
        )
        assert r.status == status


def test_actual_command_runner_selects_captures_and_replays(tmp_path, capsys):
    from ginseng.cli import main

    destination = tmp_path / "cli"
    assert (
        main(
            [
                "decision",
                "run",
                "--paths",
                "16",
                "--validation-paths",
                "32",
                "--replications",
                "1",
                "--output",
                str(destination),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["match"] and report["report"]["training"]["status"] == "verified"
    assert main(["decision", "replay", str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)["match"]
    (destination / "decision.json").write_text("{}")
    assert main(["decision", "replay", str(destination)]) == 2
    assert "error" in json.loads(capsys.readouterr().out)
