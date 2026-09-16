"""Checkpoint-valid empirical Bernstein intervals for IID bounded MC outputs.

Maurer & Pontil (2009), Theorem 4, applied to X and 1-X, then a
union bound over predetermined looks with delta_k = alpha/(k*(k+1)).
This interval describes numerical uncertainty under a fixed historical model.
"""

import math
from dataclasses import asdict, dataclass
from hashlib import sha256
from time import perf_counter

import numpy as np

from ginseng.conditional import conditional_contributions, prepare_conditional
from ginseng.numerical import environment
from ginseng.provenance import digest
from ginseng.sampling import derive_seed, map_indices, prepare_history, validate_size
from ginseng.simulate import DrawBundle, _compute_draw_id, cash_paths


@dataclass(frozen=True)
class PrecisionConfig:
    absolute_error: float = 0.005
    confidence: float = 0.95
    max_paths: int = 262144
    batch_size: int = 1024

    def __post_init__(self):
        for name in ("absolute_error", "confidence"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 < value < 1
            ):
                raise ValueError(
                    f"{name} must be a finite number strictly between 0 and 1."
                )
        for name in ("max_paths", "batch_size"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 2:
                raise ValueError(f"{name} must be an integer at least 2.")
        if self.max_paths > 2**30:
            raise ValueError("max_paths exceeds the supported limit 2^30.")

    def checkpoints(self):
        n = min(self.batch_size, self.max_paths)
        while n < self.max_paths:
            yield n
            n = min(2 * n, self.max_paths)
        yield self.max_paths


@dataclass
class BoundedMoments:
    n: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def update(self, values):
        x = np.asarray(values, dtype=float)
        if (
            x.ndim != 1
            or len(x) == 0
            or not np.all(np.isfinite(x))
            or np.any((x < 0) | (x > 1))
        ):
            raise ValueError(
                "Precision observations must be a nonempty finite vector in [0,1]."
            )
        count = len(x)
        mean = float(x.mean())
        delta = mean - self.mean
        total = self.n + count
        self.m2 += (
            float(np.sum((x - mean) ** 2)) + delta * delta * self.n * count / total
        )
        self.mean += delta * count / total
        self.n = total

    @property
    def variance(self):
        return self.m2 / (self.n - 1) if self.n > 1 else 0.0


def checkpoint_interval(moments, look, confidence):
    if moments.n < 2 or type(look) is not int or look < 1 or not 0 < confidence < 1:
        raise ValueError(
            "Interval requires n>=2, a positive look and confidence in (0,1)."
        )
    # log(4/delta_k) avoids underflow when alpha or delta is small.
    log_term = (
        math.log(4) - math.log1p(-confidence) + math.log(look) + math.log(look + 1)
    )
    radius = math.sqrt(
        2 * max(0.0, moments.variance) * log_term / moments.n
    ) + 7 * log_term / (3 * (moments.n - 1))
    low = max(0.0, moments.mean - radius)
    high = min(1.0, moments.mean + radius)
    return dict(
        n=moments.n,
        look=look,
        estimate=moments.mean,
        sample_variance=moments.variance,
        interval=[low, high],
        absolute_error_bound=max(moments.mean - low, high - moments.mean),
        error_allowance=(1 - confidence) / (look * (look + 1)),
    )


def _bundle_from_points(points, prepared, horizon, seed, trace):
    mapped = map_indices(
        points,
        len(prepared.joint),
        prepared.resolved_length,
        return_initial_lengths=trace,
    )
    indices, lengths = mapped if trace else (mapped, None)
    visible = indices[:, :horizon]
    return DrawBundle(
        seed,
        horizon,
        len(points),
        prepared.resolved_length,
        prepared.clipped,
        len(prepared.joint),
        visible,
        _compute_draw_id(visible),
        "mc",
        indices,
        (),
        prepared.requested_length,
        np.minimum(lengths, horizon) if trace else None,
    )


def run_precision(
    case,
    config=None,
    *,
    estimator="path",
    sampler="mc",
    seed=42,
    replicate=0,
    horizon=None,
    material_horizon=None,
    block_length=None,
    weights=None,
):
    """Failure-only sequential run; no stopped-sample reserve is returned.

    A single PCG64 stream advances across chunks. The plan, estimator and
    checkpoint schedule are fixed before drawing; no reuse of nested prefixes.
    """
    config = PrecisionConfig() if config is None else config
    if not isinstance(config, PrecisionConfig):
        raise ValueError("config must be a PrecisionConfig.")
    if sampler != "mc":
        raise ValueError(
            "Precision stopping supports independent mc only; Sobol and legacy_mc are unsupported."
        )
    if estimator not in ("path", "initial-block-cmc"):
        raise ValueError("Unknown precision estimator.")
    if weights is not None:
        raise ValueError("Precision stopping does not support supplied stress weights.")
    h = case.state.forecast_horizon if horizon is None else horizon
    material = h if material_horizon is None else material_horizon
    dimension = validate_size("mc", min(config.batch_size, config.max_paths), material)
    if type(h) is not int or not 1 <= h <= material:
        raise ValueError("Visible horizon must lie within material horizon.")
    derived = derive_seed(seed, "mc", replicate, 400)
    start = perf_counter()
    prepared = prepare_history(case.state, block_length)
    trace = estimator == "initial-block-cmc"
    tables = (
        prepare_conditional(prepared, case.state, case.obligations, h)
        if trace
        else None
    )
    rng = np.random.Generator(np.random.PCG64(derived))
    moments = BoundedMoments()
    index_hash, trace_hash = sha256(), sha256()
    history = []
    for look, checkpoint in enumerate(config.checkpoints(), 1):
        while moments.n < checkpoint:
            count = min(config.batch_size, checkpoint - moments.n)
            points = rng.random((count, dimension))
            bundle = _bundle_from_points(points, prepared, h, derived, trace)
            index_hash.update(bundle.index_matrix.tobytes())
            if trace:
                values = conditional_contributions(tables, bundle)
                trace_hash.update(bundle.initial_block_lengths.tobytes())
            else:
                x = cash_paths(
                    case.state,
                    bundle,
                    case.obligations,
                    prepared_history=prepared.joint,
                )
                if not np.all(np.isfinite(x)):
                    raise ValueError("Precision cash paths overflowed float64.")
                values = (case.state.immediate_funding + x.min(axis=1) < 0).astype(
                    float
                )
            moments.update(values)
        current = checkpoint_interval(moments, look, config.confidence)
        history.append(current)
        if current["absolute_error_bound"] <= config.absolute_error:
            break
    elapsed = perf_counter() - start
    met = current["absolute_error_bound"] <= config.absolute_error
    summary = dict(
        cash_shortfall_probability=moments.mean,
        numerical_probability_interval=current["interval"],
        absolute_error_bound=current["absolute_error_bound"],
        requested_absolute_error=config.absolute_error,
        confidence=config.confidence,
        precision_met=met,
        stop_reason="precision_reached" if met else "max_paths_reached",
        actual_n=moments.n,
    )
    metadata = dict(
        version=1,
        interval_method="empirical-bernstein-alpha-spending-v1",
        checkpoint_schedule="min(batch_size * 2^j, max_paths), j=0,1,...; unique",
        error_spending="alpha/(k*(k+1)), k=1,2,...",
        scope="numerical uncertainty of fixed historical model; not historical-data uncertainty or forecast calibration",
        config=asdict(config),
        sampler="mc",
        estimator=estimator,
        metric_estimators={"cash_shortfall_probability": estimator},
        root_seed=seed,
        replicate=replicate,
        domain=400,
        derived_seed=derived,
        seed_scheme="SeedSequence([root, 400, 1, replicate]).uint64",
        bit_generator="PCG64",
        mapping_version=1,
        dimension=dimension,
        material_horizon=material,
        visible_horizon=h,
        stream_layout="continuous C-order fixed-width float64; chunks advance one RNG",
        block_requested=prepared.requested_length,
        block_resolved=prepared.resolved_length,
        block_clipped=prepared.clipped,
        block_resolution=prepared.resolution,
        input_hash=digest(asdict(case)),
        synthetic_data_seed=case.data_seed,
        index_hash=index_hash.hexdigest(),
        initial_block_trace_hash=trace_hash.hexdigest() if trace else None,
        conditional_table_identity=tables.identity if trace else None,
        environment=environment(),
    )
    metadata["result_hash"] = digest(
        dict(manifest=metadata, summary=summary, checkpoints=history)
    )
    return dict(
        summary=summary, checkpoints=history, manifest=metadata, core_seconds=elapsed
    )
