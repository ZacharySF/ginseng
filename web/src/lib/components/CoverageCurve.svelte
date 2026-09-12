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

	const WIDTH = 640;
	const HEIGHT = 280;
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
				y={layout.reserveY + 18}
				class="line-label reserve-label"
				text-anchor="middle"
			>
				Required reserve {formatCurrency(requiredReserve)}
			</text>
		</svg>
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
		color: var(--color-text-faint);
		font-size: var(--font-size-md);
	}

	.coverage-curve {
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	svg {
		width: 100%;
		height: auto;
	}

	.axis-line {
		stroke: var(--color-border-strong);
		stroke-width: 1;
	}

	.curve-line {
		fill: none;
		stroke: var(--color-accent-strong);
		stroke-width: 2.5;
	}

	.current-line {
		stroke: var(--color-text);
		stroke-width: 1.5;
		stroke-dasharray: 3 3;
	}

	.reserve-dot {
		fill: var(--color-danger);
	}

	.reserve-label {
		font-weight: 600;
	}

	.line-label {
		fill: var(--color-text-dim);
		font-size: 11px;
	}

	.estimate-band {
		fill: color-mix(in srgb, var(--color-text-dim) 18%, transparent);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		font-size: var(--font-size-xs);
		color: var(--color-text-dim);
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
		background: var(--color-accent-strong);
	}

	.swatch-target {
		background: var(--color-warning);
	}

	.swatch-current {
		background: var(--color-text);
	}

	.swatch-reserve {
		background: var(--color-danger);
	}

	.swatch-band {
		background: color-mix(in srgb, var(--color-text-dim) 40%, transparent);
	}
</style>
