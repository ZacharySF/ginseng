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

	const CANONICAL_SHOCK_ID = 'repair';

	const WIDTH = 720;
	const HEIGHT = 340;
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

		const shock = obligations.find((o) => o.id === CANONICAL_SHOCK_ID) ?? null;
		const shockX = shock ? xAt(shock.due_in_days) : null;

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
			shockObligation: shock,
			shockX,
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
		<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Simulated future cash paths">
			<!-- p10-p90 uncertainty band -->
			<path d={layout.bandPath} class="band" />
			<!-- median path -->
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

			<!-- shock marker -->
			{#if layout.shockObligation && layout.shockX !== null}
				<line
					x1={layout.shockX}
					x2={layout.shockX}
					y1={MARGIN.top}
					y2={layout.flowBaseline}
					class="shock-line"
				/>
				<g class="shock-marker">
					<circle cx={layout.shockX} cy={MARGIN.top + 10} r="4" class="shock-dot" />
					<text x={layout.shockX} y={MARGIN.top + 4} class="shock-label" text-anchor="middle">
						{layout.shockObligation.label} — {formatCurrency(layout.shockObligation.amount)}
					</text>
				</g>
			{/if}

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
		<figcaption class="legend">
			<span class="legend-item"><span class="swatch swatch-band"></span>P10–P90 range</span>
			<span class="legend-item"><span class="swatch swatch-median"></span>Median path</span>
			<span class="legend-item"><span class="swatch swatch-buffer"></span>Operating buffer</span>
			<span class="legend-item"><span class="swatch swatch-zero"></span>Zero-cash floor</span>
			<span class="legend-item"><span class="swatch swatch-income"></span>Known income</span>
			<span class="legend-item"><span class="swatch swatch-obligation"></span>Known obligations</span>
			{#if layout.shockObligation}
				<span class="legend-item"><span class="swatch swatch-shock"></span>Inserted shock</span>
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

	.cash-path-chart {
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	svg {
		width: 100%;
		height: auto;
	}

	.band {
		fill: color-mix(in srgb, var(--color-accent) 22%, transparent);
		stroke: none;
	}

	.median-line {
		fill: none;
		stroke: var(--color-accent-strong);
		stroke-width: 2.5;
	}

	.buffer-line {
		stroke: var(--color-warning);
		stroke-width: 1.5;
		stroke-dasharray: 6 4;
	}

	.zero-line {
		stroke: var(--color-danger);
		stroke-width: 1.5;
		stroke-dasharray: 2 3;
	}

	.line-label {
		fill: var(--color-text-dim);
		font-size: 11px;
	}

	.shock-line {
		stroke: var(--color-danger);
		stroke-width: 1.5;
		stroke-dasharray: 4 3;
	}

	.shock-dot {
		fill: var(--color-danger);
	}

	.shock-label {
		fill: var(--color-text);
		font-size: 11px;
		font-weight: 600;
	}

	.flow-baseline {
		stroke: var(--color-border-strong);
		stroke-width: 1;
	}

	.income-mark {
		stroke: var(--color-positive);
		stroke-width: 3;
	}

	.obligation-mark {
		stroke: var(--color-danger);
		stroke-width: 3;
	}

	.axis-label {
		fill: var(--color-text-faint);
		font-size: 11px;
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

	.swatch-band {
		background: color-mix(in srgb, var(--color-accent) 40%, transparent);
	}

	.swatch-median {
		background: var(--color-accent-strong);
	}

	.swatch-buffer {
		background: var(--color-warning);
	}

	.swatch-zero {
		background: var(--color-danger);
	}

	.swatch-income {
		background: var(--color-positive);
	}

	.swatch-obligation {
		background: var(--color-danger);
	}

	.swatch-shock {
		background: var(--color-text);
	}
</style>
