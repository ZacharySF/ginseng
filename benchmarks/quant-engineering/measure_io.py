"""Supplemental capture/validation timings. Run with the repository Python runner."""

import argparse
import json
from pathlib import Path
import tempfile
import time

from ginseng.engine_artifact import capture, load
from ginseng.engine_cli import fixture_inputs
from ginseng.execution import ExecutionConfig


def main(output):
    rows = []
    for n, h in ((2000, 30), (32768, 60)):
        prepared, scalars, extra = fixture_inputs(n, h)
        for full in (False, True):
            for backend, workers in (
                ("numpy", 1),
                ("native", 1),
                ("native", 2),
                ("native", 4),
            ):
                for repetition in range(-1, 3):
                    with tempfile.TemporaryDirectory(prefix="ginseng-io-") as directory:
                        path = Path(directory) / "run"
                        start = time.perf_counter()
                        manifest = capture(
                            path,
                            prepared,
                            scalars,
                            config=ExecutionConfig(backend, workers),
                            full=full,
                            extra_inputs=extra,
                        )
                        capture_seconds = time.perf_counter() - start
                        start = time.perf_counter()
                        load(path)
                        load_seconds = time.perf_counter() - start
                        if repetition >= 0:
                            rows.append(
                                dict(
                                    paths=n,
                                    horizon=h,
                                    full=full,
                                    backend=backend,
                                    workers=workers,
                                    repetition=repetition,
                                    capture_seconds=capture_seconds,
                                    capture_io_and_metadata_seconds=capture_seconds
                                    - manifest["execution"]["evaluation_seconds"],
                                    replay_load_validation_seconds=load_seconds,
                                    input_identity=manifest["input_identity"],
                                    artifact_bytes=sum(
                                        file.stat().st_size for file in path.iterdir()
                                    ),
                                )
                            )
    Path(output).write_text(
        json.dumps(
            dict(
                warmups=1,
                repetitions=3,
                note="Warm filesystem cache; includes explicit canonical portfolio/discretionary inputs. Capture residual includes normalization, metadata, hashing and durable writes; load includes validation and owned snapshots. No pre-release artifact format exists.",
                rows=rows,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    main(parser.parse_args().output)
