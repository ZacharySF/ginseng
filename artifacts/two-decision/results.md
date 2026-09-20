# Two-decision synthetic comparison

All cases and parameter changes are in benchmarks/two-decision/config.json. These are constructed simulator experiments, not market evidence. Replication zero is selected in advance; remaining training fits diagnose instability. Three frozen policies use the same independent holdout draws. Hindsight is not executable. No case is dropped for unfavorable outcomes.

| Case | Policy | Training objective $ | Holdout objective $ | Holdout cash failure | Root units sold / credit $ | Mean review units / credit $ |
|---|---|---:|---:|---:|---|---|
| canonical | static | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| canonical | nonanticipative | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| canonical | hindsight | 6.328125 | 6.224365 | 0.0000% | 1 / 0 | 0.000000 / 48.9746 |
| no_fixed_sale_fee | static | 4.000000 | 4.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| no_fixed_sale_fee | nonanticipative | 2.481250 | 2.475684 | 9.9121% | 1 / 0 | 0.505127 / 49.4873 |
| no_fixed_sale_fee | hindsight | 2.285938 | 2.215063 | 9.9121% | 1 / 0 | 0.505127 / 39.0625 |
| late_settlement | static | 24.912500 | 24.204492 | 48.9746% | 1 / 100 | 0.000000 / 0.0000 |
| late_settlement | nonanticipative | 24.812500 | 24.104492 | 48.9746% | 1 / 0 | 0.000000 / 100.0000 |
| late_settlement | hindsight | 23.835938 | 23.089478 | 48.9746% | 1 / 0 | 0.000000 / 59.3994 |
| small_training | static | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| small_training | nonanticipative | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| small_training | hindsight | 6.250000 | 6.224365 | 0.0000% | 1 / 0 | 0.000000 / 48.9746 |
| offline_stress | static | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| offline_stress | nonanticipative | 7.000000 | 7.000000 | 0.0000% | 2 / 0 | 0.000000 / 0.0000 |
| offline_stress | hindsight | 6.243286 | 6.246719 | 0.0000% | 1 / 0 | 0.000000 / 49.8688 |

| Case | First compute ms | Warm median compute ms | Median capture ms | Median replay ms | Cumulative process peak MiB |
|---|---:|---:|---:|---:|---:|
| canonical | 46.107 | 26.379 | 4.211 | 29.154 | 128.19 |
| no_fixed_sale_fee | 26.282 | 27.097 | 4.233 | 29.806 | 128.44 |
| late_settlement | 26.984 | 27.210 | 4.150 | 30.102 | 128.69 |
| small_training | 40.532 | 40.150 | 4.346 | 43.468 | 128.94 |
| offline_stress | 45.238 | 46.294 | 19.551 | 58.585 | 135.53 |

Timings include input preparation, draw generation, finite-grid selection, frozen validation, ledger reports and provenance; capture and replay are separate. First calls follow imports, not fresh-process startup. Warm calls recompute everything. Memory is Linux process high-water RSS including libraries, not incremental Python allocations. Repeated categorical leaves are compressed to counts: stress has 4,096 training/32,768 validation draws but only four unique futures. This is not a large scenario-tree scalability benchmark. Three warm runs are descriptive, not a p99 estimate or CI speed gate.

Cash-negative states are allowed with an explicit dollar-day penalty; budget-feasible policies can still fail the cash policy. Same-sample hindsight ≤ nonanticipative ≤ static follows finite-grid feasible-set inclusion. Frozen holdout ordering is not guaranteed. Training action changes can reflect a different empirical distribution or a near-flat objective, and are reported without claiming a bug or universal improvement.

| Case | Policy | Distinct root controls | Distinct full policies | Training objective min / max $ |
|---|---|---:|---:|---|
| canonical | static | 1 | 1 | 7.000000 / 7.000000 |
| canonical | nonanticipative | 1 | 1 | 7.000000 / 7.000000 |
| canonical | hindsight | 1 | 1 | 6.035156 / 6.328125 |
| no_fixed_sale_fee | static | 1 | 1 | 4.000000 / 4.000000 |
| no_fixed_sale_fee | nonanticipative | 1 | 1 | 2.109375 / 2.750000 |
| no_fixed_sale_fee | hindsight | 1 | 1 | 1.953125 / 2.359375 |
| late_settlement | static | 1 | 1 | 21.084375 / 25.131250 |
| late_settlement | nonanticipative | 1 | 1 | 20.984375 / 25.031250 |
| late_settlement | hindsight | 1 | 1 | 19.871094 / 24.132812 |
| small_training | static | 1 | 1 | 7.000000 / 7.000000 |
| small_training | nonanticipative | 2 | 2 | 5.937500 / 7.000000 |
| small_training | hindsight | 1 | 4 | 5.625000 / 6.562500 |
| offline_stress | static | 1 | 1 | 7.000000 / 7.000000 |
| offline_stress | nonanticipative | 1 | 1 | 7.000000 / 7.000000 |
| offline_stress | hindsight | 1 | 1 | 6.237183 / 6.281128 |
