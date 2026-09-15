import json
import shutil
from dataclasses import replace
from hashlib import sha256

import numpy as np
import pytest
from ginseng.engine_artifact import (
    ArtifactError,
    capture,
    compare_outputs,
    diff,
    load,
    replay,
)
from ginseng.engine_cli import fixture_inputs, main
from ginseng.execution import ExecutionConfig, array_id, native_info
from ginseng.provenance import digest


def sample(path, full=True):
    p, s, extra = fixture_inputs(16, 14)
    capture(path, p, s, full=full, extra_inputs=extra)
    return p, s


@pytest.mark.parametrize("full", [False, True])
def test_round_trip(tmp_path, full):
    path = tmp_path / "a"
    sample(path, full)
    assert replay(path)["match"]
    if native_info()["available"]:
        assert replay(path, ExecutionConfig("native", 2, 7), tmp_path / "b")["match"]
        assert diff(path, tmp_path / "b")["match"]
    assert main(["replay", str(path), "--backend", "numpy"]) == 0


@pytest.mark.parametrize(
    "corruption",
    [
        "truncated",
        "hash",
        "schema",
        "unsafe",
        "header",
        "missing",
        "incomplete",
        "dtype",
        "shape",
        "oversized",
        "symlink",
    ],
)
def test_corruption(tmp_path, corruption):
    path = tmp_path / "a"
    sample(path)
    file = path / "manifest.json"
    m = json.loads(file.read_text())
    member = m["members"]["input:indices"]
    data = path / member["path"]
    if corruption == "truncated":
        data.write_bytes(data.read_bytes()[:20])
    if corruption == "hash":
        member["sha256"] = "0" * 64
    if corruption == "schema":
        m["schema"] = 999
    if corruption == "unsafe":
        member["path"] = "../escape.npy"
    if corruption == "missing":
        del m["members"]["input:indices"]
    if corruption == "incomplete":
        m["complete"] = False
    if corruption == "dtype":
        member["dtype"] = "|O"
    if corruption == "shape":
        member["shape"] = [-1, 4]
    if corruption == "oversized":
        member["shape"] = [2**62, 2**62]
    if corruption == "header":
        np.save(data, np.zeros((1, 1)))
        member["sha256"] = sha256(data.read_bytes()).hexdigest()
        member["file_bytes"] = data.stat().st_size
    if corruption == "symlink":
        target = tmp_path / "external.npy"
        data.rename(target)
        data.symlink_to(target)
    file.write_text(json.dumps(m))
    with pytest.raises(ArtifactError):
        load(path)
    assert main(["replay", str(path)]) == 2


def test_changed_input_and_first_divergence(tmp_path):
    path = tmp_path / "a"
    p, s = sample(path)
    changed = replace(p, schedule=p.schedule + 1)
    capture(tmp_path / "changed", changed, s, extra_inputs=fixture_inputs(16, 14)[2])
    report = diff(path, tmp_path / "changed")
    assert report["first_divergence"]["stage"] == "deterministic schedule"
    assert report["comparison"].startswith("intentional")
    m, p, inputs, outputs = load(path)
    altered = {**outputs, "paths": outputs["paths"].copy()}
    altered["paths"][3, 5] += 1
    d = compare_outputs(outputs, m["metrics"], altered, m["metrics"])
    assert d["stage"] == "cumulative paths" and d["index"] == [3, 5]
    d = compare_outputs(
        outputs,
        m["metrics"],
        outputs,
        {
            **m["metrics"],
            "expected_max_cash_deficit": m["metrics"]["expected_max_cash_deficit"] + 1,
        },
    )
    assert (
        d["stage"] == "aggregated metrics" and d["field"] == "expected_max_cash_deficit"
    )


def test_capture_cleanup(tmp_path, monkeypatch):
    import ginseng.engine_artifact as artifact

    p, s, _ = fixture_inputs(4, 14)

    def fail(*args, **kwargs):
        raise OSError("disk failed")

    monkeypatch.setattr(artifact.np, "save", fail)
    with pytest.raises(OSError):
        capture(tmp_path / "partial", p, s)
    assert not list(tmp_path.iterdir())


def perturb_recorded_output(path, name, index, amount):
    """Create an internally intact artifact containing a deliberately wrong result."""
    m, p, inputs, outputs = load(path)
    if name == "metric":
        m["metrics"][index] += amount
    else:
        value = outputs[name].copy()
        value[index] += amount
        outputs[name] = value
        member = m["members"]["output:" + name]
        file = path / member["path"]
        np.save(file, value, allow_pickle=False)
        member["sha256"] = sha256(file.read_bytes()).hexdigest()
        member["file_bytes"] = file.stat().st_size
    m["output_digest"] = digest(
        dict(arrays={k: array_id(a) for k, a in outputs.items()}, metrics=m["metrics"])
    )
    m["run_identity"] = digest(
        {k: m[k] for k in ("input_identity", "calculation_identity", "output_digest")}
    )
    (path / "manifest.json").write_text(json.dumps(m))


@pytest.mark.parametrize(
    "field,index,stage,full",
    [
        ("paths", (2, 4), "cumulative paths", True),
        ("stat_minima", (2,), "per-path summaries", False),
        ("metric", "expected_max_cash_deficit", "aggregated metrics", True),
    ],
)
def test_cli_diff_locates_perturbed_artifact(tmp_path, field, index, stage, full):
    sample(tmp_path / "a", full)
    shutil.copytree(tmp_path / "a", tmp_path / "b")
    perturb_recorded_output(tmp_path / "b", field, index, 1.0)
    report = diff(tmp_path / "a", tmp_path / "b")
    assert report["first_divergence"]["stage"] == stage
    assert report["comparison"] == "backend correctness comparison"
    if not full:
        assert report["first_divergence"]["reconstructed_reference_row"]["path"] == 2
    assert main(["diff", str(tmp_path / "a"), str(tmp_path / "b")]) == 3
    assert main(["replay", str(tmp_path / "b")]) == 3
