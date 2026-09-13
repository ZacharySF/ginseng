<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatCurrency, formatPercent } from '$lib/format';
	import { HORIZON_OPTIONS, scenarioStore } from '$lib/scenario.svelte';
	import type { Obligation, ScenarioResponse } from '$lib/types';

	interface Props {
		response: ScenarioResponse;
		obligations: Obligation[];
	}

	let { response, obligations }: Props = $props();
	let selectedIndex = $state(0);

	const WIDTH = 1080;
	const HEIGHT = 590;
	const MARGIN = { top: 28, right: 84, bottom: 88, left: 18 };
	const PLOT_BOTTOM_GAP = 58;

	const layout = $derived.by(() => {
		const { cash_paths: cashPaths, operating_buffer: operatingBuffer } = response;
		if (cashPaths.days.length === 0) return null;

		const days = cashPaths.days;
		const xMin = days[0];
		const xMax = days[days.length - 1];
		const xSpan = Math.max(1, xMax - xMin);
		const plotRight = WIDTH - MARGIN.right;
		const plotBottom = HEIGHT - MARGIN.bottom - PLOT_BOTTOM_GAP;
		const plotWidth = plotRight - MARGIN.left;
		const plotHeight = plotBottom - MARGIN.top;
		const domainLow = Math.min(0, ...cashPaths.p10);
		const domainHigh = Math.max(operatingBuffer, ...cashPaths.p90);
		const domainPadding = Math.max(250, (domainHigh - domainLow) * 0.09);
		const yMin = domainLow - domainPadding;
		const yMax = domainHigh + domainPadding;
		const ySpan = Math.max(1, yMax - yMin);
		const xAt = (day: number) => MARGIN.left + ((day - xMin) / xSpan) * plotWidth;
		const yAt = (value: number) => MARGIN.top + ((yMax - value) / ySpan) * plotHeight;
		const upper = days.map((day, index) => `${xAt(day)},${yAt(cashPaths.p90[index])}`);
		const lower = days
			.map((day, index) => `${xAt(day)},${yAt(cashPaths.p10[index])}`)
			.reverse();
		const median = days.map((day, index) => `${xAt(day)},${yAt(cashPaths.p50[index])}`).join(' ');
		const tickCount = 6;
		const yTicks = Array.from({ length: tickCount }, (_, index) => {
			const value = yMin + ((tickCount - 1 - index) / (tickCount - 1)) * ySpan;
			return { value, y: yAt(value) };
		});
		const xTicks = days.filter((_, index) => index === 0 || index === days.length - 1 || index % Math.max(1, Math.ceil(days.length / 6)) === 0);
		const dailyIncome = cashPaths.known_income.map((value, index) => value - (index === 0 ? 0 : cashPaths.known_income[index - 1]));
		const dailyObligations = cashPaths.known_obligations.map((value, index) => value - (index === 0 ? 0 : cashPaths.known_obligations[index - 1]));
		const flowMax = Math.max(1, ...dailyIncome, ...dailyObligations);
		const flowBaseline = HEIGHT - MARGIN.bottom + 18;
		const flowScale = 25 / flowMax;
		return {
			days,
			plotRight,
			plotBottom,
			bandPath: `M${upper.join(' L')} L${lower.join(' L')} Z`,
			median,
			yTicks,
			xTicks,
			xAt,
			yAt,
			bufferY: yAt(operatingBuffer),
			zeroY: yAt(0),
			flowBaseline,
			flowScale,
			dailyIncome,
			dailyObligations
		};
	});

	const selected = $derived.by(() => {
		if (!layout) return null;
		const index = Math.min(selectedIndex, layout.days.length - 1);
		return {
			index,
			day: layout.days[index],
			median: response.cash_paths.p50[index],
			low: response.cash_paths.p10[index],
			high: response.cash_paths.p90[index],
			income: layout.dailyIncome[index],
			obligations: layout.dailyObligations[index],
			x: layout.xAt(layout.days[index])
		};
	});

	const scheduledEvents = $derived(
		[...obligations].sort((left, right) => left.due_in_days - right.due_in_days)
	);

	function chooseHorizon(value: number) {
		scenarioStore.setHorizonDays(value);
		selectedIndex = 0;
	}

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

<div class="cash-terminal">
	<header class="terminal-toolbar">
		<div class="terminal-identity">
			<p class="terminal-name">Cash account</p>
			<span>Projected balance</span>
		</div>
		<div class="toolbar-separator" aria-hidden="true"></div>
		<div class="horizon-switcher" role="group" aria-label="Forecast horizon">
			{#each HORIZON_OPTIONS as option (option)}
				<button
					type="button"
					class:active={scenarioStore.request.horizon_days === option}
					aria-pressed={scenarioStore.request.horizon_days === option}
					onclick={() => chooseHorizon(option)}
				>
					{option}D
				</button>
			{/each}
		</div>
		<p class="model-state"><span aria-hidden="true"></span>{scenarioStore.request.paths.toLocaleString()} paths / local model</p>
		<div class="toolbar-actions">
			<a href={resolve('/future')}>Edit events</a>
			<a href={resolve('/liquidity')}>Reserve policy</a>
		</div>
	</header>

	<div class="terminal-grid">
		<main class="chart-workspace">
			<header class="chart-header">
				<div class="decision-lead">
					<p class="chart-instrument">Liquidity decision · {scenarioStore.request.horizon_days}-day projection</p>
					<p class:decision-value--risk={response.funding_gap > 0} class="decision-value numeric">
						{formatCurrency(response.funding_gap)}
					</p>
					<p class="decision-context">
						{response.funding_gap > 0
							? `additional funding required to maintain the ${formatCurrency(response.operating_buffer)} buffer`
							: `current funding clears the ${formatCurrency(response.operating_buffer)} buffer`}
						<span>in {formatPercent(response.coverage_target)} of modeled paths</span>
					</p>
					{#if response.estimate_band}
						<p class="estimate-readout">
							Model estimate range
							<strong class="numeric">{formatCurrency(response.estimate_band.low)}–{formatCurrency(response.estimate_band.high)}</strong>
						</p>
					{/if}
					{#if response.optimal_plan && response.stress?.status !== 'unsupported'}
						<p class="estimate-readout">Optimized funding cost · average <strong>{formatCurrency(response.optimal_plan.expected_cost)}</strong> / worst-tail average <strong>{formatCurrency(response.optimal_plan.cvar_cost)}</strong> · <a href={resolve('/plans')}>View funding mix</a></p>
					{/if}
					{#if response.stress?.status === 'active'}<p class="estimate-readout">Stress assumption active — not an estimated probability. <a href={resolve('/liquidity')}>Inspect weights</a></p>{/if}
					{#if response.stress?.status === 'unsupported'}<p class="estimate-readout">Stress not applied: this view has no supporting futures. These figures use baseline weights.</p>{/if}
					{#if response.excluded_obligations?.length}<p class="estimate-readout">{response.excluded_obligations.length} scheduled events fall after this chart window. Their dates have been preserved.</p>{/if}
				</div>
				<div class="chart-side">
					{#if selected}
						<p class="selected-path-label">Selected projection / day {selected.day}</p>
						<p class="selected-path-value numeric">{formatCurrency(selected.median)}</p>
						<p class:selected-risk={selected.low < response.operating_buffer} class="selected-path-range">
							Downside {formatCurrency(selected.low)} · upside {formatCurrency(selected.high)}
						</p>
					{/if}
					<div class="chart-key" aria-label="Chart legend">
						<span><i class="key-range"></i>P10–P90 range</span>
						<span><i class="key-median"></i>Median</span>
						<span><i class="key-buffer"></i>Operating buffer</span>
					</div>
				</div>
			</header>

			{#if layout && selected}
				<figure class="cash-graph">
					<svg
						viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
						role="slider"
						tabindex="0"
						aria-label="Projected cash day"
						aria-valuemin={layout.days[0]}
						aria-valuemax={layout.days[layout.days.length - 1]}
						aria-valuenow={selected.day}
						aria-valuetext={`Day ${selected.day}: median ${formatCurrency(selected.median)}`}
						onpointermove={inspectChartDay}
						onpointerdown={inspectChartDay}
						onkeydown={inspectChartDayByKey}
					>
						<title id="cash-graph-title">Projected cash account balance</title>
						<desc id="cash-graph-description">Median projected cash balance with a P10 to P90 range. Move across the chart or use arrow keys to inspect an individual projected day.</desc>
						{#each layout.yTicks as tick (tick.y)}
							<line x1={MARGIN.left} x2={layout.plotRight} y1={tick.y} y2={tick.y} class="grid-line" />
							<text x={layout.plotRight + 12} y={tick.y + 4} class="axis-value">{formatCurrency(tick.value)}</text>
						{/each}
						{#each layout.xTicks as day (day)}
							<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={MARGIN.top} y2={layout.plotBottom} class="grid-line grid-line--vertical" />
							<text x={layout.xAt(day)} y={layout.plotBottom + 22} class="axis-day" text-anchor="middle">D{day}</text>
						{/each}

						<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.zeroY} y2={layout.zeroY} class="zero-line" />
						<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.bufferY} y2={layout.bufferY} class="buffer-line" />
						<text x={layout.plotRight - 8} y={layout.bufferY - 7} class="buffer-label" text-anchor="end">Buffer {formatCurrency(response.operating_buffer)}</text>

						<path d={layout.bandPath} class="cash-range" />
						<polyline points={layout.median} class="cash-median" />

						{#each scheduledEvents as event (event.id)}
							{#if event.due_in_days <= scenarioStore.request.horizon_days}
								<line x1={layout.xAt(event.due_in_days)} x2={layout.xAt(event.due_in_days)} y1={MARGIN.top} y2={layout.flowBaseline + 30} class="event-line" />
								<circle cx={layout.xAt(event.due_in_days)} cy={MARGIN.top + 12} r="4" class="event-dot"><title>{event.label}: {formatCurrency(event.amount)} on day {event.due_in_days}</title></circle>
							{/if}
						{/each}

						<line x1={MARGIN.left} x2={layout.plotRight} y1={layout.flowBaseline} y2={layout.flowBaseline} class="flow-line" />
						{#each layout.days as day, index (day)}
							{#if layout.dailyIncome[index] > 0}
								<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={layout.flowBaseline} y2={layout.flowBaseline - layout.dailyIncome[index] * layout.flowScale} class="income-bar" />
							{/if}
							{#if layout.dailyObligations[index] > 0}
								<line x1={layout.xAt(day)} x2={layout.xAt(day)} y1={layout.flowBaseline} y2={layout.flowBaseline + layout.dailyObligations[index] * layout.flowScale} class="obligation-bar" />
							{/if}
						{/each}

						<line x1={selected.x} x2={selected.x} y1={MARGIN.top} y2={layout.flowBaseline + 31} class="cursor-line" />
						<text
							x={selected.x}
							y={MARGIN.top + 18}
							class="cursor-day-label"
							text-anchor={selected.index === 0 ? 'start' : selected.index === layout.days.length - 1 ? 'end' : 'middle'}
						>D{selected.day}</text>
						<circle cx={selected.x} cy={layout.yAt(selected.median)} r="4.5" class="cursor-dot" />
					</svg>
					<figcaption>Upper/lower bars: known income and obligations. The graph shows scenario outcomes, not a bank account statement.</figcaption>
				</figure>
			{/if}

			{#if selected}
				<p class="chart-inspection-hint">Move across the chart to inspect a day. <kbd>←</kbd><kbd>→</kbd> also work when it is focused.</p>
			{/if}
		</main>

		<aside class="terminal-inspector" aria-label="Scenario inspector">

			<section class="inspector-block">
				<div class="inspector-heading">
					<p class="inspector-label">Scenario events</p>
					<a href={resolve('/future')}>Edit</a>
				</div>
				{#if scheduledEvents.length > 0}
					<ul class="event-watchlist">
						{#each scheduledEvents as event (event.id)}
							<li>
								<span>D{String(event.due_in_days).padStart(2, '0')}</span>
								<p>{event.label}</p>
								<strong class="numeric">{formatCurrency(event.amount)}</strong>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="empty-inspector">No added future costs. Add one to see its cash-path impact.</p>
				{/if}
			</section>

			<section class="inspector-block policy-readout">
				<div class="inspector-heading">
					<p class="inspector-label">Active guardrails</p>
					<a href={resolve('/liquidity')}>Adjust</a>
				</div>
				<div><span>Operating buffer</span><strong class="numeric">{formatCurrency(response.operating_buffer)}</strong></div>
				<div><span>Coverage target</span><strong>{formatPercent(response.coverage_target)}</strong></div>
				<div><span>Required reserve</span><strong class="numeric">{formatCurrency(response.required_liquidity_reserve)}</strong></div>
			</section>

			<section class="inspector-block capital-readout">
				<p class="inspector-label">Capital position</p>
				<div><span>Available cash</span><strong class="numeric">{formatCurrency(response.immediate_funding)}</strong></div>
				{#if response.immediate_cash_coverage_ratio != null}<div><span>Cash / required reserve</span><strong>{formatPercent(response.immediate_cash_coverage_ratio)}</strong></div>{/if}
				<div><span>Taxable investments</span><strong class="numeric">{formatCurrency(response.marketable_backup_capital)}</strong></div>
				<div><span>Retirement account value</span><strong class="numeric">{formatCurrency(response.restricted_capital)}</strong></div>
				{#if response.account_liquidity}<div><span>Net investment access</span><strong class="numeric">{formatCurrency(response.account_liquidity.total_net_accessible)}</strong></div>{/if}
				<p>Only available cash counts toward the reserve. Investment access requires a withdrawal, an availability delay, and any tax or penalty reserve. <a href={resolve('/plans')}>See account assumptions</a>.</p>
			</section>

			<section class:funding-readout--risk={response.funding_gap > 0} class="inspector-block funding-readout">
				<p class="inspector-label">Gap to reserve</p>
				<p class="numeric">{formatCurrency(response.funding_gap)}</p>
				<a href={resolve('/plans')}>{response.funding_gap > 0 ? 'Review funding plans' : 'Funding covered'}</a>
			</section>
		</aside>
	</div>
</div>

<style>
	.cash-terminal { min-height: calc(100dvh - 3.5rem); background: var(--paper); color: var(--ink); font-size: 0.8125rem; }
	.terminal-toolbar { display: flex; align-items: center; gap: 1rem; min-height: 3.1rem; padding: 0 0.9rem; border-bottom: 1px solid var(--rule); background: var(--paper); }
	.terminal-identity { display: flex; align-items: baseline; gap: 0.55rem; white-space: nowrap; }
	.terminal-name { font-size: 1rem; font-weight: 800; letter-spacing: -0.035em; }
	.terminal-identity span, .model-state { color: var(--ink-muted); font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.05em; text-transform: uppercase; }
	.toolbar-separator { width: 1px; height: 1.45rem; background: var(--rule); }
	.horizon-switcher { display: flex; border: 1px solid var(--rule-strong); overflow: hidden; }
	.horizon-switcher button { min-width: 2.7rem; height: 1.85rem; padding: 0 0.55rem; background: var(--paper); border: 0; border-right: 1px solid var(--rule); color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.68rem; font-weight: 700; cursor: pointer; }
	.horizon-switcher button:last-child { border-right: 0; }
	.horizon-switcher button:hover { background: var(--paper-deep); color: var(--ink); }
	.horizon-switcher button.active { background: var(--cobalt); color: var(--on-accent); }
	.model-state { display: inline-flex; align-items: center; gap: 0.4rem; }
	.model-state span { width: 0.38rem; height: 0.38rem; background: var(--cobalt-bright); border-radius: 50%; }
	.toolbar-actions { display: flex; align-items: center; gap: 0.4rem; margin-left: auto; }
	.toolbar-actions a, .inspector-heading a, .funding-readout a { color: var(--link); text-decoration: none; }
	.toolbar-actions a { min-height: 2rem; display: inline-flex; align-items: center; padding: 0 0.55rem; border: 1px solid var(--rule-strong); font-size: 0.72rem; font-weight: 750; }
	.toolbar-actions a:hover, .inspector-heading a:hover, .funding-readout a:hover { background: var(--cobalt); border-color: var(--cobalt); color: var(--on-accent); }

	.terminal-grid { display: grid; grid-template-columns: minmax(0, 1fr) 19rem; min-height: calc(100dvh - 6.6rem); }
	.chart-workspace { min-width: 0; padding: 1.35rem 1.15rem 1rem; border-right: 1px solid var(--rule); }
	.chart-header { display: flex; align-items: start; justify-content: space-between; gap: 1.5rem; padding: 0 0.3rem 0.9rem; }
	.decision-lead { display: grid; gap: 0.3rem; min-width: 0; }
	.chart-instrument, .selected-path-label, .estimate-readout { color: var(--ink-muted); font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
	.decision-value { margin: 0; color: var(--cobalt); font-size: clamp(2.3rem, 4.5vw, 3.8rem); font-weight: 800; letter-spacing: -0.08em; line-height: 0.9; }
	.decision-value--risk { color: var(--negative); }
	.decision-context { max-width: 48ch; color: var(--ink-soft); font-size: 0.78rem; line-height: 1.4; }
	.decision-context span { display: block; color: var(--ink-muted); }
	.estimate-readout { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.25rem; }
	.estimate-readout strong { color: var(--warning); font-size: 0.68rem; letter-spacing: 0; }
	.chart-side { display: grid; justify-items: end; gap: 0.25rem; min-width: 13rem; padding-top: 0.15rem; }
	.selected-path-value { margin: 0; color: var(--ink); font-size: 1.1rem; font-weight: 800; letter-spacing: -0.04em; }
	.selected-path-range { margin: 0; color: var(--ink-muted); font-size: 0.66rem; text-align: right; }
	.selected-path-range.selected-risk { color: var(--negative); }
	.chart-key { display: flex; flex-wrap: wrap; justify-content: end; gap: 0.75rem; margin-top: 0.45rem; color: var(--ink-muted); font-size: 0.66rem; }
	.chart-key span { display: inline-flex; align-items: center; gap: 0.35rem; }
	.chart-key i { width: 0.85rem; height: 2px; display: block; }
	.key-range { background: var(--cobalt-bright); opacity: 0.45; }.key-median { background: var(--cobalt); }.key-buffer { background: var(--warning); }

	.cash-graph { margin: 0; }
	.cash-graph svg { width: 100%; height: auto; min-height: 25rem; display: block; cursor: crosshair; touch-action: none; }
	.cash-graph svg:focus-visible { outline: 2px solid var(--cobalt-bright); outline-offset: 4px; }
	.cash-graph figcaption, .chart-inspection-hint { padding: 0.35rem 0.3rem 0; color: var(--ink-muted); font-family: var(--font-mono); font-size: 0.64rem; }
	.chart-inspection-hint kbd { display: inline-grid; place-items: center; min-width: 1.2rem; margin-left: 0.18rem; padding: 0.06rem 0.2rem; border: 1px solid var(--rule-strong); color: var(--ink); font: inherit; }
	.grid-line { stroke: var(--rule); stroke-width: 1; stroke-dasharray: 2 3; }.grid-line--vertical { stroke: var(--paper-deep); }
	.axis-value, .axis-day { fill: var(--ink-muted); font-family: var(--font-mono); font-size: 11px; }.axis-day { fill: var(--ink-soft); }
	.zero-line { stroke: var(--negative); stroke-width: 1; stroke-dasharray: 3 4; }.buffer-line { stroke: var(--warning); stroke-width: 1; stroke-dasharray: 6 4; }.buffer-label { fill: var(--warning); font-family: var(--font-mono); font-size: 10px; }
	.cash-range { fill: var(--chart-band); stroke: none; }.cash-median { fill: none; stroke: var(--cobalt); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }
	.event-line { stroke: var(--negative); stroke-width: 1; stroke-dasharray: 3 4; }.event-dot { fill: var(--negative); }.flow-line { stroke: var(--rule-strong); stroke-width: 1; }.income-bar { stroke: var(--cobalt-bright); stroke-width: 4; }.obligation-bar { stroke: var(--negative); stroke-width: 4; }.cursor-line { stroke: var(--ink); stroke-width: 1; stroke-dasharray: 2 3; opacity: 0.65; }.cursor-day-label { fill: var(--ink); font-family: var(--font-mono); font-size: 10px; font-weight: 700; }.cursor-dot { fill: var(--paper); stroke: var(--ink); stroke-width: 1.75; }

	.terminal-inspector { display: grid; align-content: start; background: var(--paper-soft); }
	.inspector-block { display: grid; gap: 0.7rem; padding: 1rem; border-bottom: 1px solid var(--rule); }
	.inspector-label { color: var(--ink-muted); font-family: var(--font-mono); font-size: 0.63rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
	.inspector-heading { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }.inspector-heading a { font-size: 0.68rem; }
	.event-watchlist { display: grid; gap: 1px; padding: 0; margin: 0; background: var(--rule); list-style: none; }.event-watchlist li { display: grid; grid-template-columns: 2.5rem minmax(0, 1fr) auto; align-items: center; gap: 0.45rem; padding: 0.5rem; background: var(--paper); }.event-watchlist li > span { color: var(--negative); font-family: var(--font-mono); font-size: 0.64rem; }.event-watchlist p { overflow: hidden; color: var(--ink); font-size: 0.7rem; text-overflow: ellipsis; white-space: nowrap; }.event-watchlist strong { color: var(--ink); font-size: 0.69rem; }.empty-inspector { color: var(--ink-muted); font-size: 0.72rem; line-height: 1.45; }
	.capital-readout { background: var(--paper-deep); }.capital-readout > div, .policy-readout > div { display: flex; align-items: baseline; justify-content: space-between; gap: 0.75rem; color: var(--ink-soft); font-size: 0.72rem; }.capital-readout strong, .policy-readout strong { color: var(--ink); font-size: 0.78rem; }.capital-readout > p:last-child { margin: 0; color: var(--ink-muted); font-size: 0.67rem; line-height: 1.4; }
	.funding-readout { background: var(--cobalt); color: var(--on-accent); }.funding-readout--risk { background: var(--negative-soft); }.funding-readout > p:nth-child(2) { color: var(--on-accent); font-size: 1.45rem; font-weight: 800; letter-spacing: -0.05em; }.funding-readout a { color: var(--on-accent); font-size: 0.72rem; }.funding-readout--risk > p:nth-child(2), .funding-readout--risk .inspector-label, .funding-readout--risk a { color: var(--negative); }

	@media (max-width: 64rem) { .terminal-grid { grid-template-columns: minmax(0, 1fr) 16rem; }.chart-key { max-width: 15rem; }.toolbar-actions a:last-child { display: none; } }
	@media (max-width: 48rem) { .cash-terminal { min-height: auto; }.terminal-toolbar { flex-wrap: wrap; gap: 0.55rem; padding: 0.6rem 0.75rem; }.toolbar-separator, .model-state { display: none; }.terminal-identity { width: 100%; }.toolbar-actions { margin-left: auto; }.terminal-grid { grid-template-columns: 1fr; }.chart-workspace { padding: 0.9rem 0.65rem; border-right: 0; }.terminal-inspector { grid-template-columns: 1fr 1fr; border-top: 1px solid var(--rule); }.inspector-block { min-width: 0; }.funding-readout { grid-column: 1 / -1; }.chart-header { display: grid; gap: 0.65rem; }.chart-key { justify-content: start; max-width: none; }.cash-graph svg { min-height: 17rem; }.event-watchlist li { grid-template-columns: 2.2rem minmax(0, 1fr); }.event-watchlist strong { grid-column: 2; }.chart-side { justify-items: start; min-width: 0; }.selected-path-range { text-align: left; } }
	@media (max-width: 27rem) { .terminal-inspector { grid-template-columns: 1fr; }.funding-readout { grid-column: auto; }.toolbar-actions a { padding: 0 0.4rem; }.cash-graph svg { min-height: 14rem; } }
</style>
