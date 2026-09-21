# Prompt B fixed-size versus adaptive diagnostics

Predeclared 32 replications, error 0.005, confidence 95%, cap 65,536, first look 512; all later looks double. Same seed-domain rows paired across modes and estimators. One-day models have exact probabilities by enumerating 1,000 uniform historical starts. Tiny has independent exact enumeration 10846/27783. These are simulator diagnostics, not real-world calibration or a proof of coverage. Intervals are per run, not simultaneous across the 512 comparisons.

| Case | Estimator | Mode | Met /32 | Median N | Median wall ms | All looks cover /32 |
|---|---|---|---:|---:|---:|---:|
| rare | path | adaptive | 32 | 8192 | 21.400 | 32 |
| rare | path | fixed | 32 | 65536 | 43.373 | 32 |
| rare | initial-block-cmc | adaptive | 32 | 4096 | 18.526 | 32 |
| rare | initial-block-cmc | fixed | 32 | 65536 | 24.677 | 32 |
| policy_threshold | path | adaptive | 32 | 65536 | 43.658 | 32 |
| policy_threshold | path | fixed | 32 | 65536 | 43.607 | 32 |
| policy_threshold | initial-block-cmc | adaptive | 32 | 4096 | 18.744 | 32 |
| policy_threshold | initial-block-cmc | fixed | 32 | 65536 | 24.182 | 32 |
| difficult | path | adaptive | 0 | 65536 | 43.851 | 32 |
| difficult | path | fixed | 0 | 65536 | 43.754 | 32 |
| difficult | initial-block-cmc | adaptive | 32 | 4096 | 18.607 | 32 |
| difficult | initial-block-cmc | fixed | 32 | 65536 | 25.035 | 32 |
| tiny | path | adaptive | 0 | 65536 | 34.519 | 32 |
| tiny | path | fixed | 0 | 65536 | 34.777 | 32 |
| tiny | initial-block-cmc | adaptive | 32 | 32768 | 30.542 | 32 |
| tiny | initial-block-cmc | fixed | 32 | 65536 | 52.835 | 32 |

CMC integrates every initial start in a one-day model, so its contributions equal exact p. This intentionally simple case tests fractional observations; its advantage is not a general speedup. Tiny retains random restart and continuation uncertainty. No favorable cases were removed. All runs include preparation and provenance; JSON output I/O is outside the timed call.
