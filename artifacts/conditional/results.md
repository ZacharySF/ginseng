# Initial-block CMC measured experiment

Full metric-returning calls, 32 independent replicates; probability RMSE target 0.005. Fresh includes history preparation and CMC tables; reuse uses explicitly prepared immutable inputs. Both include point generation, mapping, real cash paths, all baseline metrics and CMC work when selected. JSON, diagnostic charts, process startup and first-import costs are excluded equally.

## Fastest observed configuration meeting the target

Only points whose RMSE meets the target across the reference probability interval qualify. Intervals are marginal 95% binomial numerical-reference intervals, not simultaneous guarantees or confidence intervals on replicate RMSE.

| Case | Cache | MC/path N; ms | MC/CMC N; ms | Sobol/path N; ms | Sobol/CMC N; ms |
|---|---|---|---|---|---|
| tiny | fresh | 8192; 2.480 | 1024; 2.149 | 1024; 1.745 | 256; 1.884 |
| tiny | reuse | 8192; 1.247 | 1024; 0.878 | 1024; 0.515 | 256; 0.669 |
| canonical | fresh | 256; 3.013 | 256; 4.068 | 256; 4.344 | 256; 5.399 |
| canonical | reuse | 256; 0.506 | 256; 1.169 | 256; 1.733 | 256; 2.417 |
| repair | fresh | 16384; 18.218 | 8192; 12.560 | 8192; 10.092 | 4096; 8.924 |
| repair | reuse | 16384; 15.280 | 8192; 9.561 | 8192; 7.433 | 4096; 6.008 |
| zero-heavy | fresh | 256; 1.878 | 256; 2.622 | 256; 3.147 | 256; 3.821 |
| zero-heavy | reuse | 256; 0.379 | 256; 0.926 | 256; 1.594 | 256; 2.110 |
| drought-heavy | fresh | 16384; 16.787 | 8192; 10.627 | 4096; 5.747 | 1024; 4.691 |
| drought-heavy | reuse | 16384; 14.609 | 8192; 8.714 | 4096; 3.965 | 1024; 2.843 |

## Same-N variance ratios at N=2048 (path / CMC)

| Case | MC | Sobol |
|---|---|---|
| tiny | 8.204 | 7.047 |
| canonical | undefined | undefined |
| repair | 1.907 | 1.249 |
| zero-heavy | 7.288 | 70.189 |
| drought-heavy | 3.871 | 2.932 |

## Interpretation

Keep CMC experimental and the path estimator as default. Consult the per-case cost table: lower observation variance does not ensure lower cost, and finite-replicate Sobol improvements have no universal variance guarantee. Quiet zero observations do not prove zero model risk. Results describe this machine, frozen synthetic inputs and tested grid; they do not establish real-world calibration. Reuse setup costs are recorded separately in manifest.json and must be amortized over actual calls.

The original numerical release is preserved in artifacts/standard. This experiment uses its explicit block length 14 (tiny: 7); it does not reproduce the supplied prototype's fitted length 15 or 52-bit Sobol. Production mapping version 1 and 30-bit scrambling are preserved.
