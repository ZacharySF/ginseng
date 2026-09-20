import asyncio
import json
import math
from dataclasses import replace
from hashlib import sha256

import numpy as np
import pytest
from ginseng.execution import ExecutionConfig, native_info
from ginseng.inputs import fixture
from ginseng.precision import (
    BoundedMoments,
    PrecisionConfig,
    checkpoint_interval,
    estimate_failure,
    intersect_checkpoint,
    run_precision,
)
from ginseng.precision_artifact import load_precision, replay_precision
from ginseng.precision_stream import PrecisionStream
from ginseng.resources import cancellable_calculation
from ginseng.sampling import derive_seed, map_indices


def test_interval_matches_independent_formula_and_extreme_spending():
    x = np.tile([0.0, 0.25, 0.75, 1.0, 1.0], 200)
    m = BoundedMoments()
    m.update(x)
    pairwise = sum((a - b) ** 2 for i, a in enumerate(x) for b in x[i + 1 :]) / (
        len(x) * (len(x) - 1)
    )
    delta = 0.01 / (3 * 4)
    radius = math.sqrt(2 * pairwise * math.log(4 / delta) / len(x)) + 7 * math.log(
        4 / delta
    ) / (3 * (len(x) - 1))
    assert 0 < x.mean() - radius < x.mean() + radius < 1
    r = checkpoint_interval(m, 3, 0.99)
    assert r["sample_variance"] == pytest.approx(pairwise)
    assert r["interval"] == pytest.approx(
        [max(0, x.mean() - radius), min(1, x.mean() + radius)]
    )
    extreme = checkpoint_interval(
        BoundedMoments(10**8, 0, 0), 10**200, np.nextafter(1.0, 0.0)
    )
    assert math.isfinite(extreme["absolute_error_bound"]) and extreme["interval"][1] > 0
    assert math.isfinite(extreme["log_error_allowance"])
    for bad in [
        BoundedMoments(5, float("nan"), 0),
        BoundedMoments(5, 0.2, -1),
        BoundedMoments(2.1, 0.2, 0),
    ]:
        with pytest.raises(ValueError):
            checkpoint_interval(bad, 1, 0.95)


def test_intersection_is_nested_but_empty_or_zero_width_is_not_precision():
    current = dict(estimate=0.5, interval=[0.2, 0.8])
    result = intersect_checkpoint(current, [0.3, 0.7])
    assert result["interval"] == [0.3, 0.7]
    for interval in ([0.8, 0.9], [0.9, 1.0], [float("nan"), 1.0]):
        # Explicit nonfinite previous intervals cannot masquerade as valid evidence.
        with pytest.raises(ArithmeticError):
            intersect_checkpoint(current, interval)


def test_versioned_stream_vector_and_random_access_prefixes():
    stream = PrecisionStream(42, 0, 6)
    expected = [
        0.09514387801658053,
        0.961660108245526,
        0.9187152339537481,
        0.06428296009901835,
        0.4682254486911869,
        0.007452314862900655,
        0.24002918462661726,
        0.2710648447281554,
        0.35342659871379045,
        0.5543384960680485,
        0.17051787370027294,
    ]
    np.testing.assert_array_equal(stream.points(0, 1)[0], expected)
    oracle = np.random.Generator(np.random.PCG64(derive_seed(42, "mc", 0, 400))).random(
        (91, 11)
    )
    np.testing.assert_array_equal(stream.points(0, 91), oracle)
    for start, count in [(0, 9), (9, 1), (10, 67), (77, 14)]:
        np.testing.assert_array_equal(
            stream.points(start, count), oracle[start : start + count]
        )
    assert (
        stream.identity()["version"] == 1
        and stream.identity()["purpose"] == "cash_failure_precision"
    )
    assert (
        stream.identity() != PrecisionStream(42, 0, 7).identity()
    )  # A new material width explicitly changes layout.
    for start, count in [(-1, 1), (0, 0), (True, 1), (2**30, 1)]:
        with pytest.raises(ValueError):
            stream.points(start, count)


def test_counts_chunks_workers_and_visible_horizon_preserve_draws():
    c = fixture("tiny")
    cfg = PrecisionConfig(1e-8, 0.95, 77, 16, chunk_size=7)
    a = run_precision(c, cfg, material_horizon=6, block_length=7)
    b = run_precision(
        c,
        replace(cfg, chunk_size=23),
        material_horizon=6,
        block_length=7,
        execution=ExecutionConfig("numpy", 4),
    )
    assert a["manifest"]["index_hash"] == b["manifest"]["index_hash"]
    assert a["summary"]["cash_shortfall_probability"] == pytest.approx(
        b["summary"]["cash_shortfall_probability"]
    )
    h = run_precision(c, cfg, material_horizon=6, horizon=2, block_length=7)
    indices = map_indices(PrecisionStream(42, 0, 6).points(0, 77), 3, 7)[:, :2]
    assert h["manifest"]["index_hash"] == sha256(indices.tobytes()).hexdigest()
    if native_info()["available"]:
        d = run_precision(
            c,
            cfg,
            material_horizon=6,
            block_length=7,
            execution=ExecutionConfig("native", 2),
        )
        assert d["manifest"]["index_hash"] == a["manifest"]["index_hash"]
        assert d["summary"] == a["summary"]


def test_cancellation_and_time_budget_do_not_add_extra_looks(monkeypatch):
    import ginseng.precision as mod

    c = fixture("tiny")
    cfg = PrecisionConfig(1e-8, 0.95, 200, 16, chunk_size=7)
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        return checks == 7

    r = run_precision(c, cfg, cancelled=cancel, block_length=7)
    assert r["summary"]["status"] == "cancelled"
    assert r["summary"]["actual_n"] > r["summary"]["interval_observations"]
    assert r["summary"]["interval_observations"] == 16
    assert len(r["checkpoints"]) == 1
    assert not r["summary"]["precision_met"]
    r = run_precision(c, cfg, cancelled=lambda: True, block_length=7)
    assert (
        r["summary"]["actual_n"] == 0
        and r["summary"]["cash_shortfall_probability"] is None
    )
    times = iter([0.0, 100.0, 101.0, 102.0])
    monkeypatch.setattr(mod, "perf_counter", lambda: next(times, 103.0))
    r = run_precision(c, replace(cfg, time_limit_seconds=1), block_length=7)
    assert r["summary"]["stop_reason"] == "time_budget_exhausted"
    assert r["summary"]["interval_observations"] == 0 and r["summary"][
        "numerical_probability_interval"
    ] == [0, 1]


def test_memory_and_unsupported_modes_are_explicit():
    c = fixture("tiny")
    r = estimate_failure(
        c,
        PrecisionConfig(memory_budget_bytes=1024),
        estimator="initial-block-cmc",
        block_length=7,
    )
    assert (
        r["summary"]["status"] == "budget_exhausted"
        and r["summary"]["stop_reason"] == "memory_budget_exhausted"
    )
    for kw in [
        dict(sampler="sobol"),
        dict(sampler="legacy_mc"),
        dict(weights=[1]),
        dict(metric="CVaR"),
        dict(metric="reserve_quantile"),
        dict(estimator="adaptive_importance"),
    ]:
        r = estimate_failure(c, **kw)
        assert (
            r["summary"]["status"] == "unsupported_estimator"
            and r["summary"]["actual_n"] == 0
        )


@pytest.mark.parametrize("estimator", ["path", "initial-block-cmc"])
def test_capture_offline_replay_and_corruption(estimator, tmp_path, monkeypatch):
    import socket

    cfg = PrecisionConfig(0.05, 0.95, 4096, 256)
    with pytest.raises(ValueError, match="consent"):
        run_precision(
            fixture("tiny"), cfg, capture_path=tmp_path / "private", block_length=7
        )
    run_precision(
        fixture("tiny"),
        cfg,
        estimator=estimator,
        block_length=7,
        capture_path=tmp_path / "run",
        synthetic=True,
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **kw: pytest.fail("Replay accessed network"),
    )
    assert replay_precision(tmp_path / "run")["match"]
    if estimator == "path" and native_info()["available"]:
        assert replay_precision(tmp_path / "run", ExecutionConfig("native", 2))["match"]
    m = json.loads((tmp_path / "run" / "engine" / "manifest.json").read_text())
    (tmp_path / "run" / "engine" / m["members"]["input:indices"]["path"]).write_bytes(
        b"bad"
    )
    with pytest.raises(ValueError):
        load_precision(tmp_path / "run")


def test_http_disconnect_reaches_cooperative_worker():
    from time import sleep

    class Request:
        async def is_disconnected(self):
            return True

    def work(cancelled):
        for _ in range(100):
            if cancelled():
                return "cancelled"
            sleep(0.005)
        return "not_cancelled"

    assert asyncio.run(cancellable_calculation(Request(), work)) == "cancelled"


def test_actual_personal_precision_endpoint_uses_requested_controls():
    from tests.test_forecast_api import ForecastRepositoryStub, forecast_client
    from tests.test_personal_forecast import historical_workspace

    repo = ForecastRepositoryStub(historical_workspace())
    with forecast_client(repo) as client:
        r = client.post(
            "/finance/numerics",
            json=dict(
                expected_revision=repo.workspace.revision,
                horizon_days=14,
                options=dict(
                    action="precision",
                    absolute_error=0.02,
                    confidence=0.99,
                    max_paths=1024,
                    time_limit_seconds=5.0,
                    estimator="path",
                ),
            ),
        )
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["summary"]["confidence"] == 0.99
        assert result["summary"]["requested_absolute_error"] == 0.02
        assert result["summary"]["status"] in ("precision_met", "budget_exhausted")
        assert (
            result["model_identity"]
            and result["stream"]["purpose"] == "cash_failure_precision"
        )
        assert result["resources"]["time_limit_seconds"] == 5
    assert repo.save_calls == 0


def test_numpy_published_pcg64_vectors_and_float64_conversion():
    # NumPy's pcg64-testset-1.csv, seed 0xdeadbeaf; independent raw-vector oracle.
    raw = np.array(
        [
            0x60D24054E17A0698,
            0xD5E79D89856E4F12,
            0xD254972FE64BD782,
            0xF1E3072A53C72571,
        ],
        dtype=np.uint64,
    )
    np.testing.assert_array_equal(np.random.PCG64(0xDEADBEAF).random_raw(4), raw)
    expected = (raw >> np.uint64(11)).astype(float) * 2.0**-53
    np.testing.assert_array_equal(
        np.random.Generator(np.random.PCG64(0xDEADBEAF)).random(4), expected
    )
    bitgen = np.random.PCG64(0xDEADBEAF)
    bitgen.advance(2)
    np.testing.assert_array_equal(np.random.Generator(bitgen).random(2), expected[2:])


def test_cli_capture_and_replay_reports_mismatch(tmp_path, capsys):
    from ginseng.cli import main
    from ginseng.provenance import digest

    capture = tmp_path / "capture"
    assert (
        main(
            [
                "precision",
                "--fixture",
                "tiny",
                "--block-length",
                "7",
                "--max-paths",
                "512",
                "--batch-size",
                "128",
                "--capture",
                str(capture),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["precision-replay", str(capture)]) == 0
    assert json.loads(capsys.readouterr().out)["match"]
    file = capture / "precision.json"
    m = json.loads(file.read_text())
    # Re-sign a semantically false report to exercise numerical replay beyond hashes.
    m["result"]["summary"]["cash_shortfall_probability"] += 1e-8
    r = m["result"]
    model = r["manifest"]
    model["result_hash"] = digest(
        dict(
            manifest={k: v for k, v in model.items() if k != "result_hash"},
            summary=r["summary"],
            checkpoints=r["checkpoints"],
        )
    )
    m.pop("integrity")
    m["integrity"] = digest(m)
    file.write_text(json.dumps(m))
    assert main(["precision-replay", str(capture)]) == 3
    assert (
        "summary.cash_shortfall_probability"
        in json.loads(capsys.readouterr().out)["mismatches"]
    )
    # Even re-signed incompatible metadata must fail before numerical evaluation.
    m["result"]["manifest"]["stream_layout"]["version"] = 99
    m.pop("integrity")
    m["integrity"] = digest(m)
    file.write_text(json.dumps(m))
    assert main(["precision-replay", str(capture)]) == 2
    assert "stream" in json.loads(capsys.readouterr().out)["error"]


def test_cancelled_partial_capture_keeps_only_declared_interval(tmp_path):
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == 7

    r = run_precision(
        fixture("tiny"),
        PrecisionConfig(1e-8, 0.95, 200, 16, chunk_size=7),
        block_length=7,
        cancelled=cancelled,
        capture_path=tmp_path / "partial",
        synthetic=True,
    )
    assert r["summary"]["status"] == "cancelled"
    assert r["summary"]["actual_n"] > r["summary"]["interval_observations"] == 16
    assert replay_precision(tmp_path / "partial")["match"]


def test_selected_execution_memory_limit_is_respected():
    r = run_precision(
        fixture("tiny"),
        PrecisionConfig(),
        block_length=7,
        execution=ExecutionConfig("numpy", 1, memory_budget=512),
    )
    assert r["summary"]["stop_reason"] == "memory_budget_exhausted"
    assert r["summary"]["actual_n"] == 0
    assert r["manifest"]["actual_execution"] is None
