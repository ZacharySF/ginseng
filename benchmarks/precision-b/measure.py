"""Predeclared synthetic diagnostics. Run from repository root; no network."""

import argparse
import importlib.util
import json
import resource
import statistics
import sys
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ginseng.execution import ExecutionConfig
from ginseng.inputs import fixture, load_input
from ginseng.numerical import environment
from ginseng.precision import PrecisionConfig, run_precision

ROOT = Path(__file__).resolve().parent
OUT = Path("artifacts/precision-b")


def bernoulli(p):
    start = date(2020, 1, 1)
    return load_input(
        dict(
            version=1,
            history_start=str(start),
            history_end=str(start + timedelta(days=999)),
            as_of=str(start + timedelta(days=1000)),
            opening_cash=0,
            buffer=0,
            coverage_target=0.95,
            horizon=1,
            history=[
                dict(
                    date=str(start + timedelta(days=i)),
                    variable_income=int(i >= round(1000 * p)),
                    essential_spending=int(i < round(1000 * p)),
                    discretionary_spending=0,
                )
                for i in range(1000)
            ],
        ),
        f"p={p}",
    )


def diagnostic():
    config = dict(
        root_seed=90210,
        replicates=32,
        absolute_error=0.005,
        confidence=0.95,
        max_paths=65536,
        batch_size=512,
        chunk_size=1024,
        cases={
            "rare": 0.001,
            "policy_threshold": 0.05,
            "difficult": 0.5,
            "tiny": 10846 / 27783,
        },
        estimators=["path", "initial-block-cmc"],
        modes=["adaptive", "fixed"],
    )
    (ROOT / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    cases = {
        k: (fixture("tiny") if k == "tiny" else bernoulli(v))
        for k, v in config["cases"].items()
    }
    rows = []
    for name, case in cases.items():
        for rep in range(config["replicates"]):
            for estimator in config["estimators"]:
                for mode in config["modes"]:
                    cfg = PrecisionConfig(
                        0.005,
                        0.95,
                        65536,
                        512,
                        chunk_size=1024,
                        time_limit_seconds=None,
                        stop_when_precise=mode == "adaptive",
                    )
                    start = perf_counter()
                    r = run_precision(
                        case,
                        cfg,
                        estimator=estimator,
                        seed=90210,
                        replicate=rep,
                        block_length=7,
                    )
                    elapsed = perf_counter() - start
                    truth = config["cases"][name]
                    rows.append(
                        dict(
                            case=name,
                            replicate=rep,
                            estimator=estimator,
                            mode=mode,
                            truth=truth,
                            **r["summary"],
                            wall_seconds=elapsed,
                            checkpoints=r["checkpoints"],
                            all_looks_cover=all(
                                x["interval"][0] <= truth <= x["interval"][1]
                                for x in r["checkpoints"]
                            ),
                            input_hash=r["manifest"]["input_hash"],
                            index_hash=r["manifest"]["index_hash"],
                        )
                    )
        print(f"Diagnostics {name}: {len(rows)} / 512", flush=True)
    (OUT / "observations.json").write_text(json.dumps(rows, indent=2) + "\n")
    lines = [
        "# Prompt B fixed-size versus adaptive diagnostics",
        "",
        "Predeclared 32 replications, error 0.005, confidence 95%, cap 65,536, first look 512; all later looks double. Same seed-domain rows paired across modes and estimators. One-day models have exact probabilities by enumerating 1,000 uniform historical starts. Tiny has independent exact enumeration 10846/27783. These are simulator diagnostics, not real-world calibration or a proof of coverage. Intervals are per run, not simultaneous across the 512 comparisons.",
        "",
        "| Case | Estimator | Mode | Met /32 | Median N | Median wall ms | All looks cover /32 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for name in cases:
        for estimator in config["estimators"]:
            for mode in config["modes"]:
                g = [
                    r
                    for r in rows
                    if (r["case"], r["estimator"], r["mode"]) == (name, estimator, mode)
                ]
                lines.append(
                    f"| {name} | {estimator} | {mode} | {sum(r['precision_met'] for r in g)} | {statistics.median(r['actual_n'] for r in g):.0f} | {1000 * statistics.median(r['wall_seconds'] for r in g):.3f} | {sum(r['all_looks_cover'] for r in g)} |"
                )
    lines += [
        "",
        "CMC integrates every initial start in a one-day model, so its contributions equal exact p. This intentionally simple case tests fractional observations; its advantage is not a general speedup. Tiny retains random restart and continuation uncertainty. No favorable cases were removed. All runs include preparation and provenance; JSON output I/O is outside the timed call.",
    ]
    (OUT / "diagnostics.md").write_text("\n".join(lines) + "\n")
    (OUT / "environment.json").write_text(
        json.dumps(
            dict(
                environment=environment(),
                config=config,
                process_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                / 1024,
            ),
            indent=2,
        )
        + "\n"
    )


def performance(version, backend, workload):
    if version == "before":
        from importlib.machinery import SourceFileLoader

        name = "ginseng_precision_before_b"
        loader = SourceFileLoader(name, str(ROOT / "baseline_precision.txt"))
        spec = importlib.util.spec_from_loader(name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        loader.exec_module(module)
        config = module.PrecisionConfig(
            1e-9, 0.95, 8192 if workload == "normal" else 65536, 1024
        )
        run = module.run_precision
    else:
        config = PrecisionConfig(
            1e-9,
            0.95,
            8192 if workload == "normal" else 65536,
            1024,
            time_limit_seconds=None,
        )
        run = run_precision
    case = fixture("canonical")
    h = 30 if workload == "normal" else 180
    times = []
    values = []
    # Same existing EvaluationContext selects backend even for the original module.
    from ginseng.execution import EvaluationContext

    for rep in range(4):
        start = perf_counter()
        with EvaluationContext(ExecutionConfig(backend, 1)):
            kw = dict(horizon=h, material_horizon=h, block_length=7, seed=42)
            if version == "after":
                kw["execution"] = ExecutionConfig(backend, 1)
            r = run(case, config, **kw)
        times.append(perf_counter() - start)
        values.append(
            dict(
                p=r["summary"]["cash_shortfall_probability"],
                n=r["summary"]["actual_n"],
                index_hash=r["manifest"]["index_hash"],
            )
        )
    print(
        json.dumps(
            dict(
                version=version,
                backend=backend,
                workload=workload,
                horizon=h,
                paths=config.max_paths,
                cold_seconds=times[0],
                warm_seconds=times[1:],
                peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                / 1024,
                values=values,
                baseline_source_sha256=sha256(
                    (ROOT / "baseline_precision.txt").read_bytes()
                ).hexdigest(),
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--performance", nargs=3, metavar=("VERSION", "BACKEND", "WORKLOAD"))
    a = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.performance:
        performance(*a.performance)
    else:
        diagnostic()
