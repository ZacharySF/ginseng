# Prompt B performance comparison

| Workload | Version | Backend | First call ms | Warm median ms (3) | Peak process RSS MiB |
|---|---|---|---:|---:|---:|
| normal | before | numpy | 41.46 | 33.58 | 135.8 |
| normal | before | native | 41.90 | 31.96 | 135.2 |
| normal | after | numpy | 42.20 | 35.64 | 131.2 |
| normal | after | native | 41.34 | 33.56 | 131.0 |
| stress | before | numpy | 560.57 | 483.70 | 406.6 |
| stress | before | native | 468.38 | 387.75 | 401.7 |
| stress | after | numpy | 577.64 | 563.49 | 146.6 |
| stress | after | native | 421.71 | 428.76 | 145.9 |

Normal: canonical 8,192 × 30 days; offline stress: canonical 65,536 × 180 days. Both use 1,024-observation chunks, first look 1,024 and error 1e-9 so both versions exhaust the same cap. Same index hashes and estimates across versions/backends. One worker, native explicitly selected, existing engine kernels unchanged.

Before loads the frozen pre-B precision module from benchmarks/precision-b/baseline_precision.txt against the same current engine primitives. A single explicit EvaluationContext wraps each old run to measure actual backend execution; this retains prior chunk entries. After uses bounded chunk-local contexts. Baseline source SHA-256 is in performance.json. These are orchestration comparisons, not a new engine benchmark or a comparison against a different git revision.

Each row uses a separate process. First call follows Python/library imports; it is not process-start latency. Warm calls still prepare inputs and collect provenance. Times include preparation, conversions, sampling and computation, exclude artifact I/O and imports. RSS is Linux getrusage process high-water mark including libraries, Python and native allocations, not incremental array use or an enforced process-memory cap. Three warm observations are descriptive, not p99 or a CI speed gate. Shared-host timings are noisy. Native and NumPy regressions are retained.
