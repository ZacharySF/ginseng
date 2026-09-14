# Implementation and verification record

This release implements the numerical-engine specification from `~/Downloads/Ginseng-Codex-Implementation-Prompt.md` against checkout `90e730d26368d35ef0579a85964b546b92aada86`. There were no applicable `AGENTS.md` files. The initial working tree contained only the user's untracked `ginseng-source.txt`; it was preserved. No collaborators' changes were reverted, no commits were rewritten, and no application was deployed.

## Baseline and reproduced findings

An untouched archive of the Git checkout passed **227 Python tests**. The first sandboxed attempt stalled in application tests; the unrestricted archive run completed in 15.72 seconds. The two dependency deprecations were Starlette's httpx TestClient usage and its anyio BlockingPortal alias. The original lockfile's installed numerical versions were Python 3.12.14, NumPy 2.5.3, Pandas 3.0.5, SciPy 1.18.1 and arch 8.0.0. Dependency changes added research extras and reorganized optional packages without changing those numerical versions.

Before editing, seed 42 / L=14 / 64 paths on the canonical history confirmed: separate 30/60 horizons did not preserve day prefixes; separate 64/128 path counts did not preserve path prefixes; legacy direct versus staged extensions differed; q=1 quantile and CVaR with weights `[1-1e-15,1e-15]` returned 0 instead of 100; explicitly requested L=5 resolved to 7 but reported no clipping. The API request seed's dual role in generating history and simulation was retained for compatibility and excluded from the numerical experiment. SciPy's dimension-dependent scramble is handled by a predeclared fixed material horizon, never by claiming arbitrary dimensions share prefixes.

The actual checkout included `uv.lock`, `web/bun.lock`, dependencies and the frontend image asset omitted by the concatenated source dump. None was recreated on the assumption that it was absent. The snapshot's descriptions of existing path, portfolio, funding, prospective forecast, provenance and calibration modules matched the inspected checkout. No optimizer or authentication rewrite was needed.

## Changes

- `risk.py`, `metrics.py`: positive-weight q=1 boundary, probability-boundary tests, unconditional mean maximum deficit, and a validated lightweight summary shared across samplers. Existing fractional tails, conditional severity, dollar-days and signed minimum-cash histogram meanings remain intact.
- `sampling.py`, `simulate.py`, `funding.py`: immutable prepared history and new draw arrays, shared fixed-coordinate MC/Sobol mapping, deterministic seed domains, plan metadata, explicit clipping diagnostics, material-horizon extensions, and a prepared-history input to the existing cash builder. Legacy default draws and prospective paths retain their contracts.
- `exact.py`: independent bounded rational sequence enumeration and full weighted distributions.
- `inputs.py`, `numerical.py`, `cli.py`, `__main__.py`: strict complete-window local JSON, named fixed synthetic fixtures, opening-cash reconciliation, offline library/installed command, and provenance extending the existing digest/source identity approach.
- `benchmark.py`, saved profiles and `artifacts/`: interleaved serial runs, independent bounded MC references, uncertainty, raw replicates, aggregates, CDF diagnostics, selected costs, and regenerable reports/SVG figures.
- Scenario Pydantic/TypeScript/fixture contracts include expected deficit; funding-plan schemas retain their existing fields.
- Packaging separates `app`, `optimization`, `research`, and complete `dev` extras; the actual `uv.lock` was updated by uv. The original README is retained in [application.md](application.md), with numerical review material first in the new README.

## Evidence and limits

The final verification record and measured results are linked from the README. Tests cover end-of-day semantics, strict zero failure, negative opening cash, weighted extrema/ties, exact fixture trajectories and metrics, injected continuation/restart/wraparound, shared market indices, nested samples, immutable ownership, direct/staged extension, local parser failures, installed command behavior, batch-independent global reference quantiles, serialization, and report regeneration.

A separately built wheel installed in `/tmp/ginseng-core` ran from outside the repository with no FastAPI, Pydantic, CVXPY or matplotlib. It ran MC, Sobol, exact and local JSON commands. Missing research dependencies produced the documented actionable report error; missing CVXPY returned the existing `cvxpy_unavailable` failure. The same isolated core installation was also tested with NumPy 2.2.6 and SciPy 1.14.1, exercising the declared minimum SciPy public Sobol API and repeated/larger-N prefixes. Bitwise identity between different dependency releases is not promised.

All three named simulation methods remain available. Default HTTP behavior and path caps are unchanged; the research CLI defaults to fixed-coordinate MC for nesting. Measured evidence does not justify a universal Sobol default. Quantiles can sit on atoms, canonical no-failure samples do not establish real-world zero risk, and an MC numerical reference has uncertainty. The standard experiment measures fixed synthetic histories on one CPU; no GPU/hardware portability or household calibration claim is made.

The original HackRice application description, authorship context and existing modules remain. New numerical implementation, tests, analysis and documentation were produced by Codex at the user's request; they do not replace or reattribute the existing contributors' work.

## Final executed checks

| Check | Observed result |
|---|---|
| Untouched checkout Python suite | 227 passed, two dependency deprecations |
| Final `.venv/bin/python -m pytest -q` | 255 passed, same two dependency deprecations, 18.87 seconds |
| Frontend optimizer/scenario/analysis/history-income/onboarding suites | 9 + 4 + 2 + 4 + 3 = 22 passed |
| Svelte check / Vite production build | Zero type errors or warnings / build succeeded |
| Smoke / standard benchmark | 112 / 3,136 observations; complete manifests |
| Standard large-case references | 1,048,576 independent MC paths for each of three cases |
| Report regeneration / notebook | Tables and SVGs rebuilt from observations; six code cells executed without error |
| JSON and source identity audit | All artifact JSON finite/parseable; benchmark source fingerprints match final engine and installed wheel |
| Wheel outside repository | Core commands and missing optional dependency behavior passed; SciPy 1.14.1 nesting verified |
| Lockfile / patch hygiene | `uv lock --check` and `git diff --check` passed |

The frontend checks used the installed Node 22.22.0 and Bun 1.3.13 executables from `/nix/store`, because those binaries were not on this session's default PATH. Equivalent project commands are `bun run --cwd web test:optimizer`, `test:scenario`, `test:analysis`, `test:history-income`, `test:onboarding`, `check`, and `build`.

The wheel check used `uv build --out-dir /tmp/ginseng-dist`, `uv venv /tmp/ginseng-core --python .venv/bin/python`, and `uv pip install --python /tmp/ginseng-core/bin/python /tmp/ginseng-dist/ginseng-0.1.0-py3-none-any.whl`. Commands were then invoked with `/tmp/ginseng-core/bin/ginseng` while working in `/tmp`, independently of pytest's source-path configuration. For the minimum-SciPy check, the isolated environment installed `numpy==2.2.6` and `scipy==1.14.1`; the benchmark environment retained the real lockfile's newer versions.
