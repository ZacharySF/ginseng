"""Reproducible, serial, fresh-process measurements; no wall-time pass/fail gate.

Run with the project interpreter from the repository root. Baseline is the
pre-Prompt-A commit; only source is extracted in a temporary directory.
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BASE = "78b599e1508c6f8cc823762b70d9b13d874a3526"


def worker(config):
    import resource
    from time import perf_counter

    from ginseng.execution import EvaluationContext, ExecutionConfig, prepare_scenario
    from ginseng.generate import canonical_shocks
    from ginseng.inputs import fixture
    from ginseng.numerical import environment
    from ginseng.optimizer import OptimalPlan, optimize_funding
    from ginseng.sampling import prepare_history, sample_bundle

    state = fixture("canonical").state
    bills = canonical_shocks()
    n, h = config["paths"], config["material"]
    backend = "numpy" if config["backend"] == "baseline" else config["backend"]
    times = {}
    begin = perf_counter()
    t = begin
    history = prepare_history(state, 14)
    times["history_preparation"] = perf_counter() - t
    t = perf_counter()
    bundle = sample_bundle(history, h, n, 20260920, "mc", h, domain=710)
    times["draw_generation"] = perf_counter() - t
    with EvaluationContext(ExecutionConfig(backend)) as context:
        t = perf_counter()
        p = prepare_scenario(state, bundle, bills, history.joint)
        times["scenario_preparation"] = perf_counter() - t
        t = perf_counter()
        context.evaluate(p, state.immediate_funding, state.operating_buffer, full=False)
        times["path_summary_cold"] = perf_counter() - t
        t = perf_counter()
        context.evaluate(p, state.immediate_funding, state.operating_buffer, full=False)
        times["path_summary_reused"] = perf_counter() - t

        def solve():
            return optimize_funding(
                state,
                bundle,
                bills,
                operating_buffer=state.operating_buffer,
                evaluation_horizon_days=h,
                decision_horizon_days=config["visible"],
            )

        t = perf_counter()
        first = solve()
        times["optimization_cold_including_import_and_gate"] = perf_counter() - t
        t = perf_counter()
        second = solve()
        times["optimization_reused_including_gate"] = perf_counter() - t
        if not isinstance(first, OptimalPlan) or not isinstance(second, OptimalPlan):
            raise ValueError(str(first))
    times["end_to_end"] = perf_counter() - begin
    return dict(
        config=config,
        times_seconds=times,
        objective=first.cvar_cost,
        feasibility=dict(
            mean_buffer_dollar_days=first.dollar_days_below_buffer,
            allowance=first.buffer_tolerance_dollar_days,
        ),
        draw_id=bundle.bootstrap_draw_id,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        environment=environment(),
    )


def sensitivity():
    from dataclasses import replace
    from datetime import date, timedelta

    from ginseng.optimizer import OptimalPlan, optimize_funding
    from ginseng.simulate import draw_bundle
    from ginseng.state import (
        CreditAccount,
        FinancialState,
        Holding,
        Obligation,
        TaxLot,
        Transaction,
        TransactionType,
    )

    day = date(2026, 1, 1)
    card = CreditAccount("card", 50, 0, 0, 2, 25, True, 25)
    holding = Holding(
        "TEST", "taxable", 10, (TaxLot("synthetic", "TEST", 100, 10, date(2020, 1, 1)),)
    )
    state = FinancialState(
        day,
        (
            Transaction(
                day - timedelta(days=60),
                TransactionType.TRANSFER,
                0,
                "Synthetic opening",
            ),
        ),
        (),
        (),
        (),
        (card,),
        (holding,),
        0,
        0.95,
        30,
    )
    bundle = draw_bundle(state, 30, 20, 9)
    bills = (Obligation("bill", "Bill", 100, 1),)

    def solve(s, allowance=10000):
        p = optimize_funding(
            s,
            bundle,
            bills,
            operating_buffer=0,
            buffer_tolerance_dollar_days=allowance,
            overdraft_apr=0.365,
        )
        if not isinstance(p, OptimalPlan):
            raise ValueError(str(p))
        return p

    rows = []
    for label, s, bump in [
        ("active", state, 1),
        ("cross_active_set", state, 100),
        (
            "inactive",
            replace(state, credit_accounts=(replace(card, credit_limit=200),)),
            1,
        ),
    ]:
        base = solve(s)
        altered = replace(
            s,
            credit_accounts=(
                replace(
                    s.credit_accounts[0],
                    credit_limit=s.credit_accounts[0].credit_limit + bump,
                ),
            ),
        )
        new = solve(altered)
        rows.append(
            dict(
                case=label,
                resource="credit dollars",
                bump=bump,
                base_objective=base.cvar_cost,
                new_objective=new.cvar_cost,
                predicted_change=-base.implied_credit_price * bump,
                observed_change=new.cvar_cost - base.cvar_cost,
                interpretation="Local derivative need not predict a finite step crossing an active-set boundary."
                if label == "cross_active_set"
                else "Compare on exactly the same futures.",
            )
        )
    base = solve(state)
    new = solve(state, 10001)
    rows.append(
        dict(
            case="inactive",
            resource="buffer dollar-days",
            bump=1,
            predicted_change=-base.implied_liquidity_price,
            observed_change=new.cvar_cost - base.cvar_cost,
        )
    )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    script = Path(__file__).resolve()
    records = []
    labs = []
    env = dict(
        os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1"
    )
    with tempfile.TemporaryDirectory(prefix="ginseng-decision-measure-") as tmp:
        tmp = Path(tmp)
        with (tmp / "base.tar").open("wb") as f:
            subprocess.run(
                ["git", "archive", BASE, "engine"], cwd=root, stdout=f, check=True
            )
        with tarfile.open(tmp / "base.tar") as f:
            f.extractall(tmp / "base", filter="data")
        for label, n, h, visible, val in [
            ("supported", 2000, 38, 30, 4000),
            ("offline_stress", 3000, 60, 60, 32768),
        ]:
            for repetition in range(3):
                order = ["baseline", "numpy", "native"]
                order = order[repetition:] + order[:repetition]
                for backend in order:
                    source = (
                        tmp / "base" / "engine"
                        if backend == "baseline"
                        else root / "engine"
                    )
                    config = dict(
                        workload=label,
                        paths=n,
                        material=h,
                        visible=visible,
                        backend=backend,
                        repetition=repetition,
                    )
                    p = subprocess.run(
                        [sys.executable, str(script), "--worker", json.dumps(config)],
                        cwd=tmp,
                        env=dict(env, PYTHONPATH=str(source)),
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    record = json.loads(p.stdout)
                    records.append(record)
                    # Every implementation must see identical scenarios and preserve objective/feasibility.
                    equivalent = [
                        x for x in records if x["config"]["workload"] == label
                    ]
                    assert all(
                        x["draw_id"] == record["draw_id"]
                        and abs(x["objective"] - record["objective"]) < 0.001
                        for x in equivalent
                    )
                    assert (
                        record["feasibility"]["mean_buffer_dollar_days"]
                        <= record["feasibility"]["allowance"] + 0.001
                    )
                for backend in ("numpy", "native"):
                    capture = tmp / f"{label}-{backend}-{repetition}"
                    p = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "ginseng",
                            "decision",
                            "run",
                            "--paths",
                            str(n),
                            "--horizon",
                            str(visible),
                            "--validation-paths",
                            str(val),
                            "--replications",
                            "3",
                            "--backend",
                            backend,
                            "--output",
                            str(capture),
                        ],
                        cwd=root,
                        env=dict(env, PYTHONPATH=str(root / "engine")),
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    labs.append(
                        dict(
                            workload=label,
                            backend=backend,
                            repetition=repetition,
                            result=json.loads(p.stdout),
                        )
                    )
    result = dict(
        baseline_commit=BASE,
        records=records,
        lab_runs=labs,
        sensitivity=sensitivity(),
        timing_boundary="perf_counter unprofiled, single-thread BLAS, serial fresh processes, three repetitions; reused calls share one context. Import/solver initialization included in cold solve; process startup excluded.",
        memory_boundary="Linux whole-process high-water RSS, KiB. Includes Python, native, NumPy and solver. Not incremental allocation or peak live arrays.",
        statistics="Descriptive medians and raw runs; no p99 or CI speed gate.",
    )
    (args.output / "measurements.json").write_text(
        json.dumps(result, indent=2, allow_nan=False)
    )
    for label in ("supported", "offline_stress"):
        for backend in ("baseline", "numpy", "native"):
            rows = [
                r
                for r in records
                if r["config"]["workload"] == label
                and r["config"]["backend"] == backend
            ]
            print(
                label,
                backend,
                "cold solve",
                statistics.median(
                    r["times_seconds"]["optimization_cold_including_import_and_gate"]
                    for r in rows
                ),
                "reused solve",
                statistics.median(
                    r["times_seconds"]["optimization_reused_including_gate"]
                    for r in rows
                ),
            )


if __name__ == "__main__":
    main()
