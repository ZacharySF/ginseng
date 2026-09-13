<script lang="ts">
	// Fan chart for the Future screen (spec section 58): p10-p90 band, the
	// median path, the operating buffer, the zero-cash floor, known income
	// and known-obligation days, and a labelled marker for the inserted
	// shock. Every number rendered here is read straight off the typed
	// props — this component computes pixel geometry only.
	import { formatCurrency } from '$lib/format';
	import type { CashPaths, Obligation } from '$lib/types';

	interface Props {
		cashPaths: CashPaths;
		operatingBuffer: number;
		obligations: Obligation[];
	}

	let { cashPaths, operatingBuffer, obligations }: Props = $props();

	let containerWidth = $state(720);
	let containerHeight = $state(340);
	const WIDTH = $derived(Math.max(360, containerWidth));
	const HEIGHT = $derived(Math.max(220, containerHeight));
	const MARGIN = { top: 20, right: 20, bottom: 26, left: 60 };
	const FLOW_STRIP_HEIGHT = 40;
	const FLOW_STRIP_GAP = 14;

	const layout = $derived.by(() => {
		const days = cashPaths.days;
		if (days.length === 0) {
			return null;
		}

		const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
		const bandHeight = HEIGHT - MARGIN.top - MARGIN.bottom - FLOW_STRIP_HEIGHT - FLOW_STRIP_GAP;

		const xMin = days[0];
		const xMax = days[days.length - 1];
		const xSpan = Math.max(1, xMax - xMin);

		const domainLow = Math.min(0, ...cashPaths.p10);
		const domainHigh = Math.max(operatingBuffer, ...cashPaths.p90);
		const pad = Math.max(1, (domainHigh - domainLow) * 0.1);
		const yMin = domainLow - pad;
		const yMax = domainHigh + pad;
		const ySpan = Math.max(1, yMax - yMin);

		const xAt = (day: number) => MARGIN.left + ((day - xMin) / xSpan) * plotWidth;
		const yAt = (value: number) => MARGIN.top + bandHeight - ((value - yMin) / ySpan) * bandHeight;

		const top = days.map((day, i) => `${xAt(day)},${yAt(cashPaths.p90[i])}`);
		const bottom = days
			.map((day, i) => `${xAt(day)},${yAt(cashPaths.p10[i])}`)
			.reverse();
		const bandPath = `M${top.join(' L')} L${bottom.join(' L')} Z`;
		const medianPoints = days.map((day, i) => `${xAt(day)},${yAt(cashPaths.p50[i])}`).join(' ');

		const shockMarkers = obligations.map((obligation) => ({
			...obligation,
			x: xAt(obligation.due_in_days)
		}));

		const flowTop = MARGIN.top + bandHeight + FLOW_STRIP_GAP;
		const flowBaseline = flowTop + FLOW_STRIP_HEIGHT / 2;
		const flowMax = Math.max(1, ...cashPaths.known_income, ...cashPaths.known_obligations);
		const flowScale = (FLOW_STRIP_HEIGHT / 2 - 4) / flowMax;

		const incomeMarks = days
			.map((day, i) => ({ day, value: cashPaths.known_income[i] }))
			.filter((mark) => mark.value > 0)
			.map((mark) => ({ x: xAt(mark.day), height: mark.value * flowScale, value: mark.value }));

		const obligationMarks = days
			.map((day, i) => ({ day, value: cashPaths.known_obligations[i] }))
			.filter((mark) => mark.value > 0)
			.map((mark) => ({ x: xAt(mark.day), height: mark.value * flowScale, value: mark.value }));

		return {
			plotWidth,
			bandHeight,
			bandPath,
			medianPoints,
			bufferY: yAt(operatingBuffer),
			zeroY: yAt(0),
			shockMarkers,
			flowTop,
			flowBaseline,
			incomeMarks,
			obligationMarks,
			firstDay: xMin,
			lastDay: xMax,
			xAtFirst: xAt(xMin),
			xAtLast: xAt(xMax)
		};
	});
</script>

{#if layout === null}
	<p class="empty-state">No simulated cash paths for this scenario yet.</p>
{:else}
	<figure class="cash-path-chart">
		<div class="chart-frame" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
		<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Simulated future cash-position range">
			<!-- Per-day p10-p90 cash-position range and median. -->
			<path d={layout.bandPath} class="band" />
			<polyline points={layout.medianPoints} class="median-line" />

			<!-- operating buffer -->
			<line
				x1={MARGIN.left}
				x2={MARGIN.left + layout.plotWidth}
				y1={layout.bufferY}
				y2={layout.bufferY}
				class="buffer-line"
			/>
			<text x={MARGIN.left + layout.plotWidth} y={layout.bufferY - 6} class="line-label" text-anchor="end">
				Operating buffer {formatCurrency(operatingBuffer)}
			</text>

			<!-- zero-cash floor -->
			<line
				x1={MARGIN.left}
				x2={MARGIN.left + layout.plotWidth}
				y1={layout.zeroY}
				y2={layout.zeroY}
				class="zero-line"
			/>
			<text x={MARGIN.left} y={layout.zeroY - 6} class="line-label" text-anchor="start">
				Zero-cash floor
			</text>

			<!-- Inserted obligation markers -->
			{#each layout.shockMarkers as shock (shock.id)}
				<line
					x1={shock.x}
					x2={shock.x}
					y1={MARGIN.top}
					y2={layout.flowBaseline}
					class="shock-line"
				/>
				<circle cx={shock.x} cy={MARGIN.top + 10} r="4" class="shock-dot">
					<title>{shock.label} — {formatCurrency(shock.amount)}</title>
				</circle>
			{/each}

			<!-- known income / obligation flow strip -->
			<line
				x1={MARGIN.left}
				x2={MARGIN.left + layout.plotWidth}
				y1={layout.flowBaseline}
				y2={layout.flowBaseline}
				class="flow-baseline"
			/>
			{#each layout.incomeMarks as mark (mark.x)}
				<line
					x1={mark.x}
					x2={mark.x}
					y1={layout.flowBaseline}
					y2={layout.flowBaseline - mark.height}
					class="income-mark"
				>
					<title>Known income {formatCurrency(mark.value)}</title>
				</line>
			{/each}
			{#each layout.obligationMarks as mark (mark.x)}
				<line
					x1={mark.x}
					x2={mark.x}
					y1={layout.flowBaseline}
					y2={layout.flowBaseline + mark.height}
					class="obligation-mark"
				>
					<title>Known obligation {formatCurrency(mark.value)}</title>
				</line>
			{/each}
			<text x={MARGIN.left} y={layout.flowTop + FLOW_STRIP_HEIGHT + 12} class="axis-label" text-anchor="start">
				Day {layout.firstDay}
			</text>
			<text
				x={MARGIN.left + layout.plotWidth}
				y={layout.flowTop + FLOW_STRIP_HEIGHT + 12}
				class="axis-label"
				text-anchor="end"
			>
				Day {layout.lastDay}
			</text>
		</svg>
		</div>
		<figcaption class="legend">
			<span class="legend-item"><span class="swatch swatch-band"></span>P10–P90 cash-position range</span>
			<span class="legend-item"><span class="swatch swatch-median"></span>Median cash position</span>
			<span class="legend-item"><span class="swatch swatch-buffer"></span>Operating buffer</span>
			<span class="legend-item"><span class="swatch swatch-zero"></span>Zero-cash floor</span>
			<span class="legend-item"><span class="swatch swatch-income"></span>Known income</span>
			<span class="legend-item"><span class="swatch swatch-obligation"></span>Known obligations</span>
			{#if layout.shockMarkers.length > 0}
				<span class="legend-item"><span class="swatch swatch-shock"></span>Inserted obligations</span>
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

	.cash-path-chart {
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

	.band {
		fill: rgb(46 190 172 / 13%);
		stroke: none;
	}

	.median-line {
		fill: none;
		stroke: #42d3ba;
		stroke-width: 2.5;
	}

	.buffer-line {
		stroke: #d8a84e;
		stroke-width: 1.5;
		stroke-dasharray: 6 4;
	}

	.zero-line {
		stroke: #a74252;
		stroke-width: 1;
		stroke-dasharray: 3 4;
	}

	.line-label {
		fill: #c7c7cc;
		font-size: 11px;
	}

	.shock-line {
		stroke: #f45d77;
		stroke-width: 1;
		stroke-dasharray: 3 4;
	}

	.shock-dot {
		fill: #f45d77;
	}

	.flow-baseline {
		stroke: #37373b;
		stroke-width: 1;
	}

	.income-mark {
		stroke: #2c8f81;
		stroke-width: 3;
	}

	.obligation-mark {
		stroke: #a74354;
		stroke-width: 3;
	}

	.axis-label {
		fill: #8b8b91;
		font-size: 11px;
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

	.swatch-band {
		background: rgb(46 190 172 / 40%);
	}

	.swatch-median {
		background: #42d3ba;
	}

	.swatch-buffer {
		background: #d8a84e;
	}

	.swatch-zero {
		background: #a74252;
	}

	.swatch-income {
		background: #2c8f81;
	}

	.swatch-obligation {
		background: #a74354;
	}

	.swatch-shock {
		background: #f45d77;
	}
	/* Cobalt ledger skin */
	.empty-state { color: var(--ink-muted); }
	.band { fill: var(--chart-band); }
	.median-line { stroke: var(--cobalt); }
	.buffer-line { stroke: var(--warning); }
	.zero-line, .shock-line { stroke: var(--negative); }
	.line-label, .axis-label { fill: var(--ink-soft); }
	.shock-dot { fill: var(--negative); }
	.flow-baseline { stroke: var(--rule-strong); }
	.income-mark { stroke: var(--cobalt-bright); }
	.obligation-mark { stroke: var(--negative); }
	.legend { color: var(--ink-muted); }
	.swatch-band { background: var(--chart-band-key); }
	.swatch-median { background: var(--cobalt); }
	.swatch-buffer { background: var(--warning); }
	.swatch-zero, .swatch-obligation, .swatch-shock { background: var(--negative); }
	.swatch-income { background: var(--cobalt-bright); }
</style>
