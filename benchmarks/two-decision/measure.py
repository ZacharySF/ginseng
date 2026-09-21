"""Frozen synthetic cases, including ties, poor holdout outcomes and delayed settlement."""

import json
import resource
import statistics
import tempfile
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from ginseng.numerical import environment
from ginseng.two_decision import Model, run_experiment
from ginseng.two_decision_artifact import capture, replay

config = json.loads(Path("benchmarks/two-decision/config.json").read_text())
out = Path("artifacts/two-decision")
out.mkdir(parents=True, exist_ok=True)
rows = []
reports = {}
for case in config["cases"]:
    times = []
    capture_times = []
    replay_times = []
    phase = []
    for r in range(config["warm_repeats"] + 1):
        t = perf_counter()
        report, payload = run_experiment(
            model=replace(Model(), **case["model"]),
            training_paths=case["training_paths"],
            validation_paths=case["validation_paths"],
            replications=case["replications"],
            root_seed=config["root_seed"],
        )
        compute = perf_counter() - t
        with tempfile.TemporaryDirectory(prefix="ginseng-two-decision-bench-") as temp:
            start = perf_counter()
            cap = capture(Path(temp) / "capture", payload)
            capture_times.append(perf_counter() - start)
            start = perf_counter()
            result = replay(Path(temp) / "capture")
            replay_times.append(perf_counter() - start)
            assert result["match"], result["mismatches"]
        times.append(compute)
        phase.append(report["timings"])
    reports[case["name"]] = report
    rows.append(
        dict(
            case=case["name"],
            training_paths=case["training_paths"],
            validation_paths=case["validation_paths"],
            replications=case["replications"],
            unique_support_leaves=4,
            material_days=report["summary"]["material_horizon"],
            first_compute_seconds=times[0],
            warm_compute_seconds=times[1:],
            capture_seconds=capture_times,
            replay_seconds=replay_times,
            phases=phase,
            artifact_bytes=cap["bytes"],
            peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            / 1024,
        )
    )
    print(case["name"], report["stability"], flush=True)
(out / "measurements.json").write_text(
    json.dumps(
        dict(
            config=config, environment=environment(), measurements=rows, reports=reports
        ),
        indent=2,
    )
    + "\n"
)
lines = [
    "# Two-decision synthetic comparison",
    "",
    "All cases and parameter changes are in benchmarks/two-decision/config.json. These are constructed simulator experiments, not market evidence. Replication zero is selected in advance; remaining training fits diagnose instability. Three frozen policies use the same independent holdout draws. Hindsight is not executable. No case is dropped for unfavorable outcomes.",
    "",
    "| Case | Policy | Training objective $ | Holdout objective $ | Holdout cash failure | Root units sold / credit $ | Mean review units / credit $ |",
    "|---|---|---:|---:|---:|---|---|",
]
for case, report in reports.items():
    for kind in ("static", "nonanticipative", "hindsight"):
        tr = next(
            r
            for r in report["comparison"]
            if r["policy"] == kind and r["collection"] == "training"
        )
        v = next(
            r
            for r in report["comparison"]
            if r["policy"] == kind and r["collection"] == "independent_validation"
        )
        lines.append(
            f"| {case} | {kind} | {tr['objective_dollars']:.6f} | {v['objective_dollars']:.6f} | {v['cash_failure_probability']:.4%} | {v['root_sale_units']} / {v['root_credit_dollars']:.0f} | {v['expected_review_sale_units']:.6f} / {v['expected_review_credit_dollars']:.4f} |"
        )
lines += [
    "",
    "| Case | First compute ms | Warm median compute ms | Median capture ms | Median replay ms | Cumulative process peak MiB |",
    "|---|---:|---:|---:|---:|---:|",
]
for row in rows:
    lines.append(
        f"| {row['case']} | {row['first_compute_seconds'] * 1000:.3f} | {statistics.median(row['warm_compute_seconds']) * 1000:.3f} | {statistics.median(row['capture_seconds'][1:]) * 1000:.3f} | {statistics.median(row['replay_seconds'][1:]) * 1000:.3f} | {row['peak_process_rss_mib']:.2f} |"
    )
lines += [
    "",
    "Timings include input preparation, draw generation, finite-grid selection, frozen validation, ledger reports and provenance; capture and replay are separate. First calls follow imports, not fresh-process startup. Warm calls recompute everything. Memory is Linux process high-water RSS including libraries, not incremental Python allocations. Repeated categorical leaves are compressed to counts: stress has 4,096 training/32,768 validation draws but only four unique futures. This is not a large scenario-tree scalability benchmark. Three warm runs are descriptive, not a p99 estimate or CI speed gate.",
    "",
    "Cash-negative states are allowed with an explicit dollar-day penalty; budget-feasible policies can still fail the cash policy. Same-sample hindsight ≤ nonanticipative ≤ static follows finite-grid feasible-set inclusion. Frozen holdout ordering is not guaranteed. Training action changes can reflect a different empirical distribution or a near-flat objective, and are reported without claiming a bug or universal improvement.",
    "",
    "| Case | Policy | Distinct root controls | Distinct full policies | Training objective min / max $ |",
    "|---|---|---:|---:|---|",
]
for case, report in reports.items():
    for r in report["stability"]:
        lines.append(
            f"| {case} | {r['policy']} | {r['distinct_root_actions']} | {r['distinct_policies']} | {r['training_objective_min']:.6f} / {r['training_objective_max']:.6f} |"
        )
(out / "results.md").write_text("\n".join(lines) + "\n")
