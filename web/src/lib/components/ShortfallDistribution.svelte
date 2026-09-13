<script lang="ts">
	import { formatCurrency } from '$lib/format';
	import type { ShortfallDistribution as Distribution } from '$lib/types';

	interface Props {
		distribution: Distribution;
	}

	let { distribution }: Props = $props();

	let containerWidth = $state(640);
	let containerHeight = $state(180);
	const WIDTH = $derived(Math.max(360, containerWidth));
	const HEIGHT = $derived(Math.max(150, containerHeight));
	const MARGIN = { top: 16, right: 20, bottom: 32, left: 20 };

	const layout = $derived.by(() => {
		const { bin_edges: edges } = distribution;
		const weighted = distribution.probabilities?.length === distribution.counts.length;
		const counts = weighted ? distribution.probabilities! : distribution.counts;
		if (edges.length < 2 || counts.length === 0) return null;

		const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
		const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
		const low = edges[0];
		const high = edges[edges.length - 1];
		const span = Math.max(1, high - low);
		const maxCount = Math.max(1e-9, ...counts);
		const xAt = (value: number) => MARGIN.left + ((value - low) / span) * plotWidth;
		const yAt = (value: number) => MARGIN.top + plotHeight - (value / maxCount) * plotHeight;
		const zeroVisible = low <= 0 && high >= 0;
		const barGap = 1;

		return {
			plotBottom: HEIGHT - MARGIN.bottom,
			bars: counts.map((count, index) => {
				const start = xAt(edges[index]);
				const end = xAt(edges[index + 1]);
				return {
					x: start + barGap / 2,
					y: yAt(count),
					width: Math.max(1, end - start - barGap),
					height: Math.max(0, HEIGHT - MARGIN.bottom - yAt(count)),
					negative: edges[index + 1] <= 0,
					label: `${formatCurrency(edges[index])} to ${formatCurrency(edges[index + 1])}: ${weighted ? `${(count * 100).toFixed(1)}% probability` : `${count} paths`}`
				};
			}),
			zeroX: zeroVisible ? xAt(0) : null,
			ticks: [low, 0, high].filter((value, index, values) => value >= low && value <= high && values.indexOf(value) === index).map((value) => ({ value, x: xAt(value) }))
		};
	});
</script>

{#if layout === null}
	<p class="empty-state">No modeled path minima for this scenario yet.</p>
{:else}
	<figure class="shortfall-distribution">
		<div class="chart-frame" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
			<svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="shortfall-distribution-title shortfall-distribution-description">
				<title id="shortfall-distribution-title">Distribution of minimum cash positions</title>
				<desc id="shortfall-distribution-description">Each bar shows probability by the lowest available-cash position, using the active scenario weights. Red bars remain below the zero-cash floor.</desc>
				{#each layout.bars as bar (bar.label)}
					<rect x={bar.x} y={bar.y} width={bar.width} height={bar.height} class:negative={bar.negative} class="bar"><title>{bar.label}</title></rect>
				{/each}
				{#if layout.zeroX !== null}
					<line x1={layout.zeroX} x2={layout.zeroX} y1={MARGIN.top} y2={layout.plotBottom} class="zero-line" />
					<text x={layout.zeroX + 5} y={MARGIN.top + 11} class="zero-label">Zero cash</text>
				{/if}
				{#each layout.ticks as tick (tick.value)}
					<text x={tick.x} y={HEIGHT - 8} text-anchor="middle" class="axis-label">{formatCurrency(tick.value)}</text>
				{/each}
			</svg>
		</div>
		<figcaption>Each bar is one range of worst cash position across the modeled paths.</figcaption>
	</figure>
{/if}

<style>
	.shortfall-distribution {
		display: flex;
		flex: 1;
		flex-direction: column;
		min-height: 0;
		margin: 0;
	}

	.chart-frame {
		flex: 1;
		min-height: 9.375rem;
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
	}

	.bar {
		fill: #3a9f96;
		fill-opacity: 0.85;
	}

	.bar.negative {
		fill: #d05d70;
	}

	.zero-line {
		stroke: #f0c56d;
		stroke-dasharray: 3 3;
	}

	.zero-label,
	.axis-label {
		font-family: var(--font-mono);
		font-size: 10px;
	}

	.zero-label {
		fill: #f0c56d;
	}

	.axis-label {
		fill: #898990;
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
	.bar { fill: var(--cobalt); }
	.bar.negative { fill: var(--negative); }
	.zero-line { stroke: var(--warning); }
	.zero-label { fill: var(--warning); }
	.axis-label { fill: var(--ink-soft); }
	figcaption, .empty-state { color: var(--ink-soft); }
</style>
