<script lang="ts">
	// Liquidity coverage curve (spec section 32): immediate funding on the
	// x-axis, probability of staying above the operating buffer on the
	// y-axis. Renders the current funding point, the coverage target line,
	// the required-reserve intersection, and — only when the engine
	// actually returned one — the outer-bootstrap estimate band. A null
	// `estimateBand` renders nothing; this component never invents a band.
	import { formatCurrency, formatPercent } from '$lib/format';
	import type { CoverageCurvePoint, EstimateBand } from '$lib/types';

	interface Props {
		points: CoverageCurvePoint[];
		currentFunding: number;
		coverageTarget: number;
		requiredReserve: number;
		estimateBand: EstimateBand | null;
	}

	let { points, currentFunding, coverageTarget, requiredReserve, estimateBand }: Props = $props();

	let containerWidth = $state(640);
	let containerHeight = $state(280);
	const WIDTH = $derived(Math.max(360, containerWidth));
	const HEIGHT = $derived(Math.max(200, containerHeight));
	const MARGIN = { top: 20, right: 20, bottom: 32, left: 56 };

	const layout = $derived.by(() => {
		if (points.length === 0) {
			return null;
		}

		const sorted = [...points].sort((a, b) => a.funding - b.funding);
		const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
		const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;

		const xMax = Math.max(
			currentFunding,
			requiredReserve,
			estimateBand?.high ?? 0,
			...sorted.map((p) => p.funding)
		);
		const xSpan = Math.max(1, xMax);

		const xAt = (funding: number) => MARGIN.left + (funding / xSpan) * plotWidth;
		const yAt = (coverage: number) => MARGIN.top + plotHeight - coverage * plotHeight;

		const curvePoints = sorted.map((p) => `${xAt(p.funding)},${yAt(p.coverage)}`).join(' ');

		const band =
			estimateBand === null
				? null
				: {
						x1: xAt(estimateBand.low),
						x2: xAt(estimateBand.high)
					};

		const currentFundingLabelAnchor: 'start' | 'middle' | 'end' =
			xAt(currentFunding) < MARGIN.left + 60
				? 'start'
				: xAt(currentFunding) > MARGIN.left + plotWidth - 60
					? 'end'
					: 'middle';

		return {
			plotWidth,
			plotHeight,
			curvePoints,
			currentFundingX: xAt(currentFunding),
			currentFundingLabelAnchor,
			targetY: yAt(coverageTarget),
			reserveX: xAt(requiredReserve),
			reserveY: yAt(coverageTarget),
			band
		};
	});
</script>

{#if layout === null}
	<p class="empty-state">No coverage curve for this scenario yet.</p>
{:else}
	<figure class="coverage-curve">
		<div class="chart-frame" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
		<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Liquidity coverage curve">
			{#if layout.band}
				<rect
					x={layout.band.x1}
					y={MARGIN.top}
					width={Math.max(0, layout.band.x2 - layout.band.x1)}
					height={layout.plotHeight}
					class="estimate-band"
				/>
			{/if}

			<!-- axes -->
			<line
				x1={MARGIN.left}
				x2={MARGIN.left}
				y1={MARGIN.top}
				y2={MARGIN.top + layout.plotHeight}
				class="axis-line"
			/>
			<line
				x1={MARGIN.left}
				x2={MARGIN.left + layout.plotWidth}
				y1={MARGIN.top + layout.plotHeight}
				y2={MARGIN.top + layout.plotHeight}
				class="axis-line"
			/>

			<line
				x1={MARGIN.left}
				x2={MARGIN.left + layout.plotWidth}
				y1={layout.targetY}
				y2={layout.targetY}
				class="target-line"
			/>
			<text x={MARGIN.left} y={layout.targetY - 6} class="line-label" text-anchor="start">
				Coverage target {formatPercent(coverageTarget)}
			</text>

			<!-- curve -->
			<polyline points={layout.curvePoints} class="curve-line" />

			<!-- current funding -->
			<line
				x1={layout.currentFundingX}
				x2={layout.currentFundingX}
				y1={MARGIN.top}
				y2={MARGIN.top + layout.plotHeight}
				class="current-line"
			/>
			<text
				x={layout.currentFundingX}
				y={MARGIN.top + layout.plotHeight - 6}
				class="line-label"
				text-anchor={layout.currentFundingLabelAnchor}
			>
				Current funding {formatCurrency(currentFunding)}
			</text>

			<!-- required reserve intersection -->
			<circle cx={layout.reserveX} cy={layout.reserveY} r="4.5" class="reserve-dot" />
			<text
				x={layout.reserveX}
				y={layout.reserveY + 20}
				class="line-label reserve-label"
				text-anchor="middle"
			>
				Required reserve {formatCurrency(requiredReserve)}
			</text>
		</svg>
		</div>
		<figcaption class="legend">
			<span class="legend-item"><span class="swatch swatch-curve"></span>Coverage curve</span>
			<span class="legend-item"><span class="swatch swatch-target"></span>Coverage target</span>
			<span class="legend-item"><span class="swatch swatch-current"></span>Current funding</span>
			<span class="legend-item"><span class="swatch swatch-reserve"></span>Required reserve</span>
			{#if layout.band}
				<span class="legend-item"><span class="swatch swatch-band"></span>Model-estimate range</span>
			{/if}
		</figcaption>
	</figure>
{/if}

<style>
	.empty-state {
		padding: var(--space-6);
		color: #8b8b91;
		font-size: var(--font-size-md);
	}

	.coverage-curve {
		display: flex;
		flex-direction: column;
		height: 100%;
		margin: 0;
		gap: var(--space-3);
	}

	.chart-frame {
		flex: 1;
		min-height: 0;
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
	}

	.axis-line {
		stroke: #3a3a3f;
		stroke-width: 1;
	}

	.curve-line {
		fill: none;
		stroke: #42d3ba;
		stroke-width: 2.5;
	}

	.target-line {
		stroke: var(--warning);
		stroke-width: 1.5;
		stroke-dasharray: 5 4;
	}

	.current-line {
		stroke: #d8d8da;
		stroke-width: 1.5;
		stroke-dasharray: 3 3;
	}

	.reserve-dot {
		fill: #f45d77;
	}

	.reserve-label {
		font-weight: 600;
	}

	.line-label {
		fill: #c7c7cc;
		font-size: 11px;
	}

	.estimate-band {
		fill: rgb(200 200 204 / 14%);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		font-size: var(--font-size-xs);
		color: #9a9aa0;
	}

	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
	}

	.swatch {
		width: 12px;
		height: 12px;
		border-radius: 3px;
		display: inline-block;
	}

	.swatch-curve {
		background: #42d3ba;
	}

	.swatch-target {
		background: #d8a84e;
	}

	.swatch-current {
		background: #d8d8da;
	}

	.swatch-reserve {
		background: #f45d77;
	}

	.swatch-band {
		background: rgb(200 200 204 / 30%);
	}
	/* Cobalt ledger skin */
	.empty-state, .legend { color: var(--ink-soft); }
	.axis-line { stroke: var(--rule-strong); }
	.curve-line { stroke: var(--cobalt); }
	.current-line { stroke: var(--ink); }
	.reserve-dot { fill: var(--negative); }
	.line-label { fill: var(--ink-soft); }
	.estimate-band { fill: rgb(36 72 255 / 14%); }
	.swatch-curve { background: var(--cobalt); }
	.swatch-target { background: var(--warning); }
	.swatch-current { background: var(--ink); }
	.swatch-reserve { background: var(--negative); }
	.swatch-band { background: rgb(36 72 255 / 30%); }
</style>
