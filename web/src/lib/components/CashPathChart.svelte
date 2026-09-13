<script lang="ts">
	import { SvelteDate } from 'svelte/reactivity';
	import { formatCurrency } from '$lib/format';
	import type { CashPaths } from '$lib/types';

	interface CashPathChartEvent {
		id: string;
		label: string;
		amount: number;
		day: number;
		kind: 'income' | 'outflow';
		date?: string;
	}


	interface Props {
		cashPaths: CashPaths;
		operatingBuffer: number;
		events?: CashPathChartEvent[];
		asOf?: string | null;
		deterministic?: boolean;
		comparisonPaths?: CashPaths | null;
		comparisonLabel?: string;
	}

	let {
		cashPaths,
		operatingBuffer,
		events = [],
		asOf = null,
		deterministic = false,
		comparisonPaths = null,
		comparisonLabel = 'Saved inputs'
	}: Props = $props();

	let containerWidth = $state(720);
	let containerHeight = $state(360);
	let selectedIndex = $state(0);
	const WIDTH = $derived(Math.max(320, containerWidth));
	const HEIGHT = $derived(Math.max(240, containerHeight));
	const MARGIN = { top: 28, right: 68, bottom: 58, left: 18 };
	const FLOW_STRIP_HEIGHT = 42;
	const FLOW_STRIP_GAP = 19;

	const layout = $derived.by(() => {
		const days = cashPaths.days;
		if (days.length === 0) return null;

		const plotRight = WIDTH - MARGIN.right;
		const plotWidth = plotRight - MARGIN.left;
		const plotBottom = HEIGHT - MARGIN.bottom - FLOW_STRIP_HEIGHT - FLOW_STRIP_GAP;
		const plotHeight = plotBottom - MARGIN.top;
		const xMin = days[0];
		const xMax = days[days.length - 1];
		const xSpan = Math.max(1, xMax - xMin);
		const p10 = cashPaths.p10.length === days.length ? cashPaths.p10 : cashPaths.p50;
		const p90 = cashPaths.p90.length === days.length ? cashPaths.p90 : cashPaths.p50;
		const domainLow = Math.min(0, ...p10, ...(comparisonPaths?.p50 ?? []));
		const domainHigh = Math.max(operatingBuffer, ...p90, ...(comparisonPaths?.p50 ?? []));
		const padding = Math.max(1, (domainHigh - domainLow) * 0.1);
		const yMin = domainLow - padding;
		const yMax = domainHigh + padding;
		const ySpan = Math.max(1, yMax - yMin);
		const xAt = (day: number) => MARGIN.left + ((day - xMin) / xSpan) * plotWidth;
		const yAt = (value: number) => MARGIN.top + ((yMax - value) / ySpan) * plotHeight;
		const upper = days.map((day, index) => `${xAt(day)},${yAt(p90[index])}`);
		const lower = days.map((day, index) => `${xAt(day)},${yAt(p10[index])}`).reverse();
		const dailyIncome = cashPaths.known_income.map((value, index) =>
			Math.max(0, value - (index === 0 ? 0 : cashPaths.known_income[index - 1]))
		);
		const dailyOutflows = cashPaths.known_obligations.map((value, index) =>
			Math.max(0, value - (index === 0 ? 0 : cashPaths.known_obligations[index - 1]))
		);
		const flowBaseline = HEIGHT - MARGIN.bottom + FLOW_STRIP_HEIGHT / 2;
		const flowScale = (FLOW_STRIP_HEIGHT / 2 - 4) / Math.max(1, ...dailyIncome, ...dailyOutflows);
		const tickStep = Math.max(1, Math.ceil(days.length / 5));
		const xTicks = days.filter((_, index) => index === 0 || index === days.length - 1 || index % tickStep === 0);
		const yTicks = Array.from({ length: 5 }, (_, index) => {
			const value = yMin + ((4 - index) / 4) * ySpan;
			return { value, y: yAt(value) };
		});

		return {
			days,
			plotRight,
			plotBottom,
			xAt,
			yAt,
			bandPath: `M${upper.join(' L')} L${lower.join(' L')} Z`,
			median: days.map((day, index) => `${xAt(day)},${yAt(cashPaths.p50[index])}`).join(' '),
			comparison: comparisonPaths?.days.map((day, index) => `${xAt(day)},${yAt(comparisonPaths.p50[index])}`).join(' ') ?? null,
			bufferY: yAt(operatingBuffer),
			zeroY: yAt(0),
			flowBaseline,
			flowScale,
			dailyIncome,
			dailyOutflows,
			xTicks,
			yTicks
		};
	});

	const selected = $derived.by(() => {
		if (!layout) return null;
		const index = Math.min(Math.max(0, selectedIndex), layout.days.length - 1);
		const day = layout.days[index];
		let dateLabel = `Day ${day}`;
		if (asOf && /^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
			const date = new SvelteDate(`${asOf}T00:00:00Z`);
			if (!Number.isNaN(date.valueOf())) {
				date.setUTCDate(date.getUTCDate() + day - 1);
				dateLabel = new Intl.DateTimeFormat('en-US', {
					month: 'short',
					day: 'numeric',
					year: 'numeric',
					timeZone: 'UTC'
				}).format(date);
			}
		}
		return {
			index,
			day,
			dateLabel,
			x: layout.xAt(day),
			median: cashPaths.p50[index],
			comparison: comparisonPaths?.p50[index] ?? null,
			low: cashPaths.p10[index] ?? cashPaths.p50[index],
			high: cashPaths.p90[index] ?? cashPaths.p50[index],
			income: layout.dailyIncome[index] ?? 0,
			outflows: layout.dailyOutflows[index] ?? 0
		};
	});

	const visibleEvents = $derived(
		layout ? events.filter((event) => event.day >= layout.days[0] && event.day <= layout.days[layout.days.length - 1]) : []
	);

	function inspectChartDay(event: PointerEvent) {
		if (!layout) return;
		const svg = event.currentTarget as SVGSVGElement;
		const bounds = svg.getBoundingClientRect();
		const chartX = ((event.clientX - bounds.left) / bounds.width) * WIDTH;
		const progress = Math.min(1, Math.max(0, (chartX - MARGIN.left) / (layout.plotRight - MARGIN.left)));
		selectedIndex = Math.round(progress * (layout.days.length - 1));
	}

	function inspectChartDayByKey(event: KeyboardEvent) {
		if (!layout) return;
		const lastIndex = layout.days.length - 1;
		if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
			event.preventDefault();
			selectedIndex = Math.max(0, selectedIndex - 1);
		} else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
			event.preventDefault();
			selectedIndex = Math.min(lastIndex, selectedIndex + 1);
		} else if (event.key === 'Home') {
			event.preventDefault();
			selectedIndex = 0;
		} else if (event.key === 'End') {
			event.preventDefault();
			selectedIndex = lastIndex;
		}
	}
</script>

{#if layout === null}
	<p class="empty-state">No forecast path is available yet.</p>
{:else if selected}
	<figure class:cash-path-chart--deterministic={deterministic} class="cash-path-chart">
		<div class="chart-frame" bind:clientWidth={containerWidth} bind:clientHeight={containerHeight}>
			<svg
				viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
				role="slider"
				tabindex="0"
				aria-label="Forecast cash day inspector"
				aria-valuemin={layout.days[0]}
				aria-valuemax={layout.days[layout.days.length - 1]}
				aria-valuenow={selected.day}
				aria-valuetext={`${selected.dateLabel}: ${formatCurrency(selected.median)}${selected.comparison !== null ? `, ${comparisonLabel} ${formatCurrency(selected.comparison)}` : ''}${selected.income > 0 ? `, known income ${formatCurrency(selected.income)}` : ''}${selected.outflows > 0 ? `, known outflow ${formatCurrency(selected.outflows)}` : ''}`}
				onpointermove={inspectChartDay}
				onpointerdown={inspectChartDay}
				onkeydown={inspectChartDayByKey}
			>
				<title>Projected cash position</title>
				<desc>Move across the chart, or use arrow keys when focused, to inspect an individual calendar day. The bars below the line are day-by-day known cash flows, calculated from cumulative engine totals.</desc>
				{#each layout.yTicks as tick (tick.y)}
					<line x1={MARGIN.left} x2={layout.plotRight} y1={tick.y} y2={tick.y} class="grid-line" />
					<text x={layout.plotRight + 10} y={tick.y + 4} class="axis-value">{formatCurrency(tick.value)}</text>
				{/each}
				{#each layout.xTicks as day (day)}
					<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={MARGIN.top} y2={layout.plotBottom} class="grid-line grid-line--vertical" />
					<text x={layout.xAt(day)} y={HEIGHT - 3} text-anchor={day === layout.days[0] ? 'start' : day === layout.days[layout.days.length - 1] ? 'end' : 'middle'} class="axis-value">Day {day}</text>
				{/each}
				<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.zeroY} y2={layout.zeroY} class="zero-line" />
				<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.bufferY} y2={layout.bufferY} class="buffer-line" />
				<text x={layout.plotRight - 6} y={layout.bufferY - 7} class="buffer-label" text-anchor="end">Buffer {formatCurrency(operatingBuffer)}</text>

				{#if !deterministic}<path d={layout.bandPath} class="cash-range" />{/if}
				<polyline points={layout.median} class="cash-median" />
				{#if layout.comparison}<polyline points={layout.comparison} class="comparison-line" />{/if}

				{#each visibleEvents as event (event.id)}
					<line x1={layout.xAt(event.day)} x2={layout.xAt(event.day)} y1={MARGIN.top} y2={layout.flowBaseline + 27} class:event-income={event.kind === 'income'} class="event-line" />
					<circle cx={layout.xAt(event.day)} cy={MARGIN.top + 11} r="3.75" class:event-income={event.kind === 'income'} class="event-dot">
						<title>{event.label} — {event.kind === 'income' ? 'income' : 'outflow'} {formatCurrency(event.amount)}{event.date ? ` on ${event.date}` : ''}</title>
					</circle>
				{/each}

				<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.flowBaseline} y2={layout.flowBaseline} class="flow-line" />
				{#each layout.days as day, index (day)}
					{#if layout.dailyIncome[index] > 0}
						<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={layout.flowBaseline} y2={layout.flowBaseline - layout.dailyIncome[index] * layout.flowScale} class="income-bar"><title>Known income {formatCurrency(layout.dailyIncome[index])}</title></line>
					{/if}
					{#if layout.dailyOutflows[index] > 0}
						<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={layout.flowBaseline} y2={layout.flowBaseline + layout.dailyOutflows[index] * layout.flowScale} class="outflow-bar"><title>Known outflow {formatCurrency(layout.dailyOutflows[index])}</title></line>
					{/if}
				{/each}
				<line x1={selected.x} x2={selected.x} y1={MARGIN.top} y2={layout.flowBaseline + 28} class="cursor-line" />
				<circle cx={selected.x} cy={layout.yAt(selected.median)} r="4.5" class="cursor-dot" />
			</svg>
		</div>
		<div class="chart-readout" aria-live="polite">
			<div>
				<span>Inspecting</span>
				<strong>{selected.dateLabel}</strong>
			</div>
			<div>
				<span>{deterministic ? 'Known cash' : 'Median cash'}</span>
				<strong class="numeric">{formatCurrency(selected.median)}</strong>
			</div>
			{#if !deterministic}
				<div>
					<span>Range</span>
					<strong class="numeric">{formatCurrency(selected.low)}–{formatCurrency(selected.high)}</strong>
				</div>
			{/if}
			{#if selected.comparison !== null}
				<div><span>{comparisonLabel}</span><strong class="numeric">{formatCurrency(selected.comparison)}</strong></div>
			{/if}
			<div>
				<span>Known flows</span>
				<strong class="numeric">+{formatCurrency(selected.income)} · −{formatCurrency(selected.outflows)}</strong>
			</div>
		</div>
		<figcaption>
			{#if deterministic}
				Known scheduled income and outflows only. No probability range is shown.
			{:else}
				Blue fan: P10–P90 cash position. Flow bars show per-day known income and outflows.
			{/if}
			{#if comparisonPaths}<span> Dashed line: {comparisonLabel} (median).</span>{/if}
			<span> Focus this chart and use <kbd>←</kbd><kbd>→</kbd>, Home, or End to inspect dates.</span>
		</figcaption>
	</figure>
{/if}

<style>
	.empty-state {
		padding: 1rem;
		color: var(--ink-soft);
		font-size: 0.84rem;
	}

	.cash-path-chart {
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
		min-width: 0;
		margin: 0;
	}

	.chart-frame {
		min-height: clamp(17rem, 38vw, 29rem);
	}

	svg {
		display: block;
		width: 100%;
		height: 100%;
		cursor: crosshair;
		touch-action: pan-y;
	}

	svg:focus-visible {
		outline: 2px solid var(--cobalt-bright);
		outline-offset: 4px;
	}

	.grid-line {
		stroke: var(--rule);
		stroke-dasharray: 2 3;
	}

	.grid-line--vertical {
		stroke: var(--paper-deep);
	}

	.axis-value {
		fill: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 10px;
	}

	.zero-line {
		stroke: var(--negative);
		stroke-dasharray: 3 4;
	}

	.buffer-line {
		stroke: var(--warning);
		stroke-dasharray: 6 4;
	}

	.buffer-label {
		fill: var(--warning);
		font-family: var(--font-mono);
		font-size: 10px;
		font-weight: 700;
	}

	.cash-range {
		fill: rgb(36 72 255 / 15%);
	}

	.comparison-line { fill: none; stroke: var(--ink-soft); stroke-width: 1.75; stroke-dasharray: 7 5; }

	.cash-median {
		fill: none;
		stroke: var(--cobalt);
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2.5;
	}

	.event-line {
		stroke: var(--negative);
		stroke-dasharray: 3 4;
	}

	.event-line.event-income {
		stroke: var(--cobalt-bright);
	}

	.event-dot {
		fill: var(--negative);
	}

	.event-dot.event-income {
		fill: var(--cobalt-bright);
	}

	.flow-line {
		stroke: var(--rule-strong);
	}

	.income-bar {
		stroke: var(--cobalt-bright);
		stroke-width: 4;
	}

	.outflow-bar {
		stroke: var(--negative);
		stroke-width: 4;
	}

	.cursor-line {
		stroke: var(--ink);
		stroke-dasharray: 2 3;
		stroke-opacity: 0.64;
	}

	.cursor-dot {
		fill: var(--paper);
		stroke: var(--ink);
		stroke-width: 1.75;
	}

	.chart-readout {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 1px;
		background: var(--rule);
		border: 1px solid var(--rule);
	}

	.chart-readout > div {
		display: grid;
		gap: 0.14rem;
		min-width: 0;
		padding: 0.45rem 0.55rem;
		background: var(--paper);
	}

	.chart-readout span {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.58rem;
		font-weight: 700;
		letter-spacing: 0.045em;
		text-transform: uppercase;
	}

	.chart-readout strong {
		overflow: hidden;
		font-size: 0.72rem;
		letter-spacing: -0.02em;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	figcaption {
		color: var(--ink-soft);
		font-size: 0.7rem;
		line-height: 1.4;
	}

	figcaption span {
		display: inline-block;
		margin-left: 0.35rem;
	}

	kbd {
		display: inline-grid;
		min-width: 1.2rem;
		place-items: center;
		margin-left: 0.18rem;
		padding: 0.04rem 0.17rem;
		background: var(--paper);
		border: 1px solid var(--control-border);
		color: var(--ink);
		font-family: var(--font-mono);
		font-size: 0.62rem;
	}

	@media (max-width: 48rem) {
		.chart-frame {
			min-height: 18rem;
		}

		.chart-readout {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		figcaption span {
			display: block;
			margin: 0.35rem 0 0;
		}
	}

</style>
