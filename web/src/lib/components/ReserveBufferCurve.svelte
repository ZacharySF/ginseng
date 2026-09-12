<script lang="ts">
	import { formatCurrency } from '$lib/format';
	import type { ReserveBufferCurvePoint } from '$lib/types';

	interface Props {
		points: ReserveBufferCurvePoint[];
		operatingBuffer: number;
		requiredReserve: number;
	}

	let { points, operatingBuffer, requiredReserve }: Props = $props();

	let containerWidth = $state(640);
	let containerHeight = $state(240);
	const WIDTH = $derived(Math.max(360, containerWidth));
	const HEIGHT = $derived(Math.max(190, containerHeight));
	const MARGIN = { top: 20, right: 24, bottom: 36, left: 64 };

	const layout = $derived.by(() => {
		if (points.length === 0) return null;

		const sorted = [...points].sort((left, right) => left.operating_buffer - right.operating_buffer);
		const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
		const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
		const xMax = Math.max(1, operatingBuffer, ...sorted.map((point) => point.operating_buffer));
		const yMax = Math.max(1, requiredReserve, ...sorted.map((point) => point.required_liquidity_reserve));
		const xAt = (value: number) => MARGIN.left + (value / xMax) * plotWidth;
		const yAt = (value: number) => MARGIN.top + plotHeight - (value / yMax) * plotHeight;
		const current =
			sorted.find((point) => point.operating_buffer === operatingBuffer) ??
			{ operating_buffer: operatingBuffer, required_liquidity_reserve: requiredReserve };
		const xTicks = Array.from({ length: 4 }, (_, index) => {
			const value = (xMax * index) / 3;
			return { value, x: xAt(value) };
		});
		const yTicks = Array.from({ length: 4 }, (_, index) => {
			const value = (yMax * index) / 3;
			return { value, y: yAt(value) };
		});

		return {
			plotRight: WIDTH - MARGIN.right,
			plotBottom: HEIGHT - MARGIN.bottom,
			line: sorted
				.map((point) => `${xAt(point.operating_buffer)},${yAt(point.required_liquidity_reserve)}`)
				.join(' '),
			currentX: xAt(current.operating_buffer),
			currentY: yAt(current.required_liquidity_reserve),
			xTicks,
			yTicks
		};
	});
</script>

{#if layout === null}
	<p class="empty-state">No reserve-buffer curve for this scenario yet.</p>
{:else}
	<figure class="reserve-buffer-curve">
		<div class="chart-frame" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
			<svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="reserve-buffer-title reserve-buffer-description">
				<title id="reserve-buffer-title">Reserve sensitivity to operating buffer</title>
				<desc id="reserve-buffer-description">Required liquidity reserve for each operating-buffer choice. The highlighted point is the active policy.</desc>
				{#each layout.yTicks as tick (tick.y)}
					<line x1={MARGIN.left} x2={layout.plotRight} y1={tick.y} y2={tick.y} class="grid-line" />
					<text x={MARGIN.left - 8} y={tick.y + 4} text-anchor="end" class="axis-label">{formatCurrency(tick.value)}</text>
				{/each}
				{#each layout.xTicks as tick (tick.x)}
					<line x1={tick.x} x2={tick.x} y1={MARGIN.top} y2={layout.plotBottom} class="grid-line grid-line--vertical" />
					<text x={tick.x} y={layout.plotBottom + 19} text-anchor="middle" class="axis-label">{formatCurrency(tick.value)}</text>
				{/each}
				<polyline points={layout.line} class="curve-line" />
				<line x1={layout.currentX} x2={layout.currentX} y1={MARGIN.top} y2={layout.plotBottom} class="active-guide" />
				<line x1={MARGIN.left} x2={layout.currentX} y1={layout.currentY} y2={layout.currentY} class="active-guide" />
				<circle cx={layout.currentX} cy={layout.currentY} r="4.5" class="active-point">
					<title>Active policy: {formatCurrency(operatingBuffer)} buffer requires {formatCurrency(requiredReserve)} reserve</title>
				</circle>
				<text x={layout.currentX + 8} y={layout.currentY - 8} class="active-label">Active policy</text>
				<text x={MARGIN.left} y={12} class="measure-label">Required reserve</text>
				<text x={layout.plotRight} y={HEIGHT - 4} text-anchor="end" class="measure-label">Operating buffer</text>
			</svg>
		</div>
		<figcaption>Every point uses this scenario's same modeled cash paths and coverage target.</figcaption>
	</figure>
{/if}

<style>
	.reserve-buffer-curve {
		display: flex;
		flex: 1;
		flex-direction: column;
		min-height: 0;
		margin: 0;
	}

	.chart-frame {
		flex: 1;
		min-height: 11.875rem;
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
	}

	.grid-line {
		stroke: #242428;
		stroke-dasharray: 2 3;
	}

	.grid-line--vertical {
		stroke: #1b1b1e;
	}

	.axis-label,
	.measure-label,
	.active-label {
		font-family: var(--font-mono);
		font-size: 10px;
	}

	.axis-label {
		fill: #898990;
	}

	.measure-label {
		fill: #aaaab0;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.curve-line {
		fill: none;
		stroke: #d8a84e;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2.5;
	}

	.active-guide {
		stroke: #d8a84e;
		stroke-dasharray: 3 4;
		stroke-opacity: 0.65;
	}

	.active-point {
		fill: #050505;
		stroke: #f0c56d;
		stroke-width: 2;
	}

	.active-label {
		fill: #f0c56d;
		font-weight: 700;
	}

	figcaption,
	.empty-state {
		margin: 0;
		padding-top: 0.35rem;
		color: #828288;
		font-size: 0.68rem;
		line-height: 1.35;
	}
	/* Cobalt ledger skin */
	.grid-line { stroke: var(--rule); }
	.grid-line--vertical { stroke: var(--paper-deep); }
	.axis-label, figcaption, .empty-state { color: var(--ink-muted); fill: var(--ink-muted); }
	.measure-label { fill: var(--ink-soft); }
	.curve-line { stroke: var(--cobalt); }
	.active-guide { stroke: var(--cobalt); }
	.active-point { fill: var(--paper); stroke: var(--cobalt); }
	.active-label { fill: var(--cobalt); }
</style>
