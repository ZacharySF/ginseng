# Precision-driven MC stopping experiment

Predeclared absolute error 0.01, confidence 0.95, cap 131,072, batch size 1,024. 32 independent replicates per case/estimator. Both estimators use the same advancing MC streams up to their stopping times.

| Case | Estimator | Precision reached | Median N | Median core ms | Interval contains reference point |
|---|---|---|---|---|---|
| tiny | path | 32/32 | 65536 | 11.432 | 32/32 |
| tiny | initial-block-cmc | 32/32 | 8192 | 7.281 | 32/32 |
| canonical | path | 32/32 | 2048 | 4.623 | 32/32 |
| canonical | initial-block-cmc | 32/32 | 2048 | 5.896 | 32/32 |
| repair | path | 32/32 | 65536 | 60.119 | 32/32 |
| repair | initial-block-cmc | 32/32 | 16384 | 24.472 | 32/32 |
| drought-heavy | path | 32/32 | 65536 | 54.462 | 32/32 |
| drought-heavy | initial-block-cmc | 32/32 | 16384 | 22.530 | 32/32 |

Only tiny has exact truth (10846/27783); other reference points are independent million-path MC estimates with stored binomial intervals. Inclusion counts for those points are diagnostics, not measured coverage of the unknown true probability. Even exact-reference inclusion across 32 runs does not prove the coverage theorem. The mathematical guarantee comes from the bound and union argument documented in docs/precision-stopping.md.

A separate tiny run requests error 0.000001 with a 2,048-path cap and reports `max_paths_reached`, `precision_met=false`; see budget-exhausted.json.

This experiment measures the opt-in failure-only command. Its error target is a high-probability absolute numerical error, whereas the earlier CMC benchmark used replicate RMSE for full metric-returning calls. Timings and sample requirements from those two reports are not directly comparable.

Recommendation: retain precision stopping as an optional offline MC capability. The conservative bound can require substantial work; no claim of optimal stopping or universal speedup is made. Sobol, reserve precision, model uncertainty and application integration remain outside this release.
