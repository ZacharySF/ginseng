# Website precision estimates and 3D liquidity surfaces

The **Cash events** pages (`/future` and `/demo/future`) now include a Risk laboratory panel. Personal analysis requires a ready historical forecast; the synthetic demo supports unweighted horizons up to 60 days. Scheduled and assumption forecasts show an explanation instead of a historical calculation.

## What the user can do

**Refine estimate** runs independent initial-block conditional MC for cash-shortfall probability. It displays a 95% numerical interval, a requested error of ±0.5 percentage points, observations used, and either “Precision target reached” or “Computation limit reached.” This is precision under the active historical model, not confidence that the model predicts the future accurately. Existing reserve and funding results remain separate.

**Explore in 3D** opens two views of the same 2,048 modeled futures:

| Axis | Meaning |
|---|---|
| X | Forecast day |
| Y | Extra opening cash, available from day one |
| Z, shortfall view | Probability of at least one negative end-of-day balance by that day |
| Z, deficit view | Expected largest cash deficit observed by that day, averaging all paths |

These surfaces answer where liquidity risk first rises, how additional cash changes it, and whether a low probability conceals a large potential deficit. They are cash sensitivity analyses, not recommended funding plans: borrowing costs, sale taxes and settlement delays are excluded.

The cash slider highlights a cross-section of the surface and shows the selected cash amount's horizon-end value. An expandable table exposes every day in that slice using the same engine values. Drag rotates the plot, touch gestures permit zooming, and Reset view restores the initial camera. Cobalt, paper, ledger typography and dark-mode colors follow the website theme. The camera adapts at mobile widths. Plotly is loaded only after a surface result is requested; it is not part of the initial page bundle. [Plotly surface documentation](https://plotly.com/javascript/3d-surface-plots/) describes the underlying rendering capability.

## Calculation

For sampled cumulative net flow X(i,t), compute its running minimum m(i,t) through each day. For opening cash C and additional cash a:

```
loss(i,t,a) = max(0, -(C + a + m(i,t)))
probability(t,a) = mean(loss(i,t,a) > 0)
deficit(t,a) = mean(loss(i,t,a))
```

Equality at zero survives. Earlier shortfalls remain counted even after cash recovers. The same sample is reused for all cells; consequently increasing cash cannot increase either quantity, and extending the visible period cannot decrease either quantity. Twenty-one cash offsets span zero to a readable $500-rounded amount covering the sample's worst deficit (minimum span $500).

The surface uses fixed-coordinate MC in seed domain 500. It is independent of precision stopping's domain 400. The surface's zero-additional-cash value may therefore differ from the refined estimate. The 95% interval applies only to the refined probability, not simultaneously to all surface cells. The plot joins sampled grid points for display; interpolation is not a precise failure boundary. An all-zero grid explicitly says that no observed shortfalls does not establish zero underlying risk.

## API and input identity

- `POST /finance/numerics`: authenticated, read-only, using saved canonical inputs plus the same scenario overrides as the personal forecast. The expected workspace revision is checked before and after computation. A save during the calculation returns 409.
- `POST /demo/numerics`: authenticated, explicitly synthetic inputs; rejects stress weighting rather than silently applying an unweighted estimator.
- Both accept `options.action` as `precision` or `surface`. Precision permits absolute errors 0.005 or 0.01 and a strict integer observation cap from 1,024 to 65,536. The website requests the default 0.005 target and 65,536 cap. Surface sampling always uses 2,048 paths.
- Horizons are capped at 60 days; history is capped at 3,660 daily observations. Existing shared admission control allows two heavy forecast/analysis calls per process and returns 503 when busy. Limits bound computation by work counts rather than promise a wall-clock deadline.
- The frontend aborts pending transport requests and discards superseded replies. Inputs key the mounted panel; a revision, scenario, horizon or mode change clears its state. The existing authenticated client also rejects replies after an account change. Aborting browser transport does not promise immediate cancellation of already-running server computation.

## Verification

Backend tests cover exact tiny matrices, zero survival, earlier failures followed by recovery, monotonicity, replay, budget exhaustion, authentication, server capacity, stale revisions, unsupported modes and preview bills without saves. Frontend store tests resolve replies out of order and verify cancellation, stale-data clearing and retry behavior.

The Playwright test mounts the actual Svelte component with frozen synthetic output generated by the engine, mocks only transport, and exercises precision rendering, WebGL rendering, camera rotation, metric selection, cash slices, exact tables, theme changes, mobile resizing and errors. API correctness/authentication are tested separately; the browser harness does not claim to exercise a real Supabase login.

```sh
uv run pytest
cd web
bun install --frozen-lockfile
bun run check
bun run build
node --test tests/*test.mjs
bunx playwright install chromium
bun run test:risk-browser
```

For an existing Chromium installation, set `CHROMIUM_PATH` to its executable. Set `RISK_SCREENSHOTS` to an output directory to capture the synthetic browser fixture. Reviewed examples: [light](../artifacts/risk-explorer/risk-light.png), [dark](../artifacts/risk-explorer/risk-dark.png), [mobile](../artifacts/risk-explorer/risk-mobile.png).
