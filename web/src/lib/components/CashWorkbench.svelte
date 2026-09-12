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

	function changeSelectedDay(event: Event) {
		selectedIndex = Number((event.currentTarget as HTMLInputElement).value);
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
				<div>
					<p class="chart-instrument">Ginseng cash flow · {scenarioStore.request.horizon_days} day projection</p>
					{#if selected}
						<p class="chart-quote numeric">
							{formatCurrency(selected.median)}
							<span class:selected-risk={selected.low < response.operating_buffer}>
								{selected.low < response.operating_buffer ? 'below buffer in downside path' : 'median balance'}
							</span>
						</p>
					{/if}
				</div>
				<div class="chart-key" aria-label="Chart legend">
					<span><i class="key-range"></i>P10–P90 range</span>
					<span><i class="key-median"></i>Median</span>
					<span><i class="key-buffer"></i>Operating buffer</span>
				</div>
			</header>

			{#if layout && selected}
				<figure class="cash-graph">
					<svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="cash-graph-title cash-graph-description">
						<title id="cash-graph-title">Projected cash account balance</title>
						<desc id="cash-graph-description">Median projected cash balance with a P10 to P90 range. Use the day selector below to inspect individual projected days.</desc>
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
						<circle cx={selected.x} cy={layout.yAt(selected.median)} r="4.5" class="cursor-dot" />
					</svg>
					<figcaption>Upper/lower bars: known income and obligations. The graph shows scenario outcomes, not a bank account statement.</figcaption>
				</figure>
			{/if}

			{#if selected}
				<div class="day-control">
					<label for="projected-day">Inspect day <strong>{selected.day}</strong></label>
					<input id="projected-day" type="range" min="0" max={Math.max(0, response.cash_paths.days.length - 1)} step="1" value={selected.index} onchange={changeSelectedDay} oninput={changeSelectedDay} />
					<span>Day {scenarioStore.request.horizon_days}</span>
				</div>
			{/if}
		</main>

		<aside class="terminal-inspector" aria-label="Scenario inspector">
			{#if selected}
				<section class="inspector-block inspector-block--day">
					<p class="inspector-label">Selected projection / day {selected.day}</p>
					<p class="selected-balance numeric">{formatCurrency(selected.median)}</p>
					<div class="range-readout">
						<span>Downside <strong class="numeric">{formatCurrency(selected.low)}</strong></span>
						<span>Upside <strong class="numeric">{formatCurrency(selected.high)}</strong></span>
					</div>
					{#if selected.income > 0 || selected.obligations > 0}
						<p class="flow-readout">{selected.income > 0 ? `${formatCurrency(selected.income)} known income` : ''}{selected.income > 0 && selected.obligations > 0 ? ' · ' : ''}{selected.obligations > 0 ? `${formatCurrency(selected.obligations)} known obligations` : ''}</p>
					{/if}
				</section>
			{/if}

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

			<section class:funding-readout--risk={response.funding_gap > 0} class="inspector-block funding-readout">
				<p class="inspector-label">Gap to reserve</p>
				<p class="numeric">{formatCurrency(response.funding_gap)}</p>
				<a href={resolve('/plans')}>{response.funding_gap > 0 ? 'Review funding plans' : 'Funding covered'}</a>
			</section>
		</aside>
	</div>
</div>

<style>
	.cash-terminal {
		min-height: calc(100dvh - 3.5rem);
		background: #050505;
		color: #e8e8e8;
		font-size: 0.8125rem;
	}

	.terminal-toolbar {
		display: flex;
		align-items: center;
		gap: 1rem;
		min-height: 3.1rem;
		padding: 0 0.9rem;
		border-bottom: 1px solid #262626;
		background: #0c0c0d;
	}

	.terminal-identity {
		display: flex;
		align-items: baseline;
		gap: 0.55rem;
		white-space: nowrap;
	}

	.terminal-name {
		font-size: 0.95rem;
		font-weight: 750;
		letter-spacing: -0.025em;
	}

	.terminal-identity span,
	.model-state {
		color: #8d8d91;
		font-family: var(--font-mono);
		font-size: 0.65rem;
		letter-spacing: 0.035em;
		text-transform: uppercase;
	}

	.toolbar-separator {
		width: 1px;
		height: 1.45rem;
		background: #2b2b2e;
	}

	.horizon-switcher {
		display: flex;
		border: 1px solid #353539;
		border-radius: 0.28rem;
		overflow: hidden;
	}

	.horizon-switcher button {
		min-width: 2.7rem;
		height: 1.85rem;
		padding: 0 0.55rem;
		background: #0c0c0d;
		border: 0;
		border-right: 1px solid #353539;
		color: #96969b;
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		cursor: pointer;
	}

	.horizon-switcher button:last-child { border-right: 0; }
	.horizon-switcher button:hover { background: #1a1a1c; color: #fff; }
	.horizon-switcher button.active { background: #26262a; color: #fff; }

	.model-state { display: inline-flex; align-items: center; gap: 0.4rem; }
	.model-state span { width: 0.38rem; height: 0.38rem; background: #38d3ba; border-radius: 50%; }

	.toolbar-actions { display: flex; align-items: center; gap: 0.4rem; margin-left: auto; }
	.toolbar-actions a, .inspector-heading a, .funding-readout a { color: #b5b5bb; text-decoration: none; }
	.toolbar-actions a { min-height: 2rem; display: inline-flex; align-items: center; padding: 0 0.55rem; border: 1px solid #323237; border-radius: 0.28rem; font-size: 0.72rem; font-weight: 650; }
	.toolbar-actions a:hover, .inspector-heading a:hover, .funding-readout a:hover { color: #fff; border-color: #707078; }

	.terminal-grid { display: grid; grid-template-columns: minmax(0, 1fr) 19rem; min-height: calc(100dvh - 6.6rem); }
	.chart-workspace { min-width: 0; padding: 1.2rem 1rem 1rem; border-right: 1px solid #262626; }
	.chart-header { display: flex; align-items: start; justify-content: space-between; gap: 1rem; padding: 0 0.3rem 0.75rem; }
	.chart-instrument { color: #e8e8ea; font-size: 0.95rem; font-weight: 700; letter-spacing: -0.02em; }
	.chart-quote { margin-top: 0.25rem; color: #42d3ba; font-size: 1.15rem; font-weight: 750; letter-spacing: -0.04em; }
	.chart-quote span { margin-left: 0.35rem; color: #8c8d91; font-family: var(--font-mono); font-size: 0.62rem; font-weight: 500; letter-spacing: 0.02em; text-transform: uppercase; }
	.chart-quote span.selected-risk { color: #ff657a; }

	.chart-key { display: flex; flex-wrap: wrap; justify-content: end; gap: 0.75rem; color: #949499; font-size: 0.66rem; }
	.chart-key span { display: inline-flex; align-items: center; gap: 0.35rem; }
	.chart-key i { width: 0.85rem; height: 2px; display: block; }
	.key-range { background: #3a9f96; opacity: 0.7; }.key-median { background: #42d3ba; }.key-buffer { background: #d4a958; }

	.cash-graph { margin: 0; }
	.cash-graph svg { width: 100%; height: auto; min-height: 25rem; display: block; }
	.cash-graph figcaption { padding: 0.25rem 0.3rem; color: #77777c; font-size: 0.64rem; }
	.grid-line { stroke: #222225; stroke-width: 1; stroke-dasharray: 2 3; }.grid-line--vertical { stroke: #171719; }
	.axis-value, .axis-day { fill: #8b8b91; font-family: var(--font-mono); font-size: 11px; }.axis-day { fill: #a1a1a6; }
	.zero-line { stroke: #a74252; stroke-width: 1; stroke-dasharray: 3 4; }.buffer-line { stroke: #d8a84e; stroke-width: 1; stroke-dasharray: 6 4; }.buffer-label { fill: #d8a84e; font-family: var(--font-mono); font-size: 10px; }
	.cash-range { fill: rgb(46 190 172 / 13%); stroke: none; }.cash-median { fill: none; stroke: #42d3ba; stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }
	.event-line { stroke: #f45d77; stroke-width: 1; stroke-dasharray: 3 4; }.event-dot { fill: #f45d77; }.flow-line { stroke: #37373b; stroke-width: 1; }.income-bar { stroke: #2c8f81; stroke-width: 4; }.obligation-bar { stroke: #a74354; stroke-width: 4; }.cursor-line { stroke: #bfc0c7; stroke-width: 1; stroke-dasharray: 2 3; opacity: 0.75; }.cursor-dot { fill: #050505; stroke: #fff; stroke-width: 1.75; }

	.day-control { display: grid; grid-template-columns: auto minmax(6rem, 1fr) auto; align-items: center; gap: 0.75rem; padding: 0.7rem 0.3rem 0; color: #929298; font-family: var(--font-mono); font-size: 0.66rem; }
	.day-control strong { color: #fff; }.day-control input { accent-color: #42d3ba; min-width: 0; }

	.terminal-inspector { display: grid; align-content: start; background: #0b0b0c; }
	.inspector-block { display: grid; gap: 0.7rem; padding: 1rem; border-bottom: 1px solid #252528; }
	.inspector-block--day { background: #101011; }.inspector-label { color: #898990; font-family: var(--font-mono); font-size: 0.63rem; font-weight: 700; letter-spacing: 0.055em; text-transform: uppercase; }.selected-balance { color: #f1f1f2; font-size: 1.7rem; font-weight: 750; letter-spacing: -0.065em; line-height: 1; }
	.range-readout { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }.range-readout span { display: grid; gap: 0.18rem; color: #77777d; font-size: 0.68rem; }.range-readout strong { color: #d5d5d9; font-size: 0.78rem; }.flow-readout { color: #b7b7bc; font-size: 0.69rem; }
	.inspector-heading { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }.inspector-heading a { font-size: 0.68rem; }
	.event-watchlist { display: grid; gap: 1px; padding: 0; margin: 0; background: #29292d; list-style: none; }.event-watchlist li { display: grid; grid-template-columns: 2.5rem minmax(0, 1fr) auto; align-items: center; gap: 0.45rem; padding: 0.5rem; background: #131315; }.event-watchlist li > span { color: #f05b75; font-family: var(--font-mono); font-size: 0.64rem; }.event-watchlist p { overflow: hidden; color: #d0d0d4; font-size: 0.7rem; text-overflow: ellipsis; white-space: nowrap; }.event-watchlist strong { color: #f1f1f2; font-size: 0.69rem; }.empty-inspector { color: #838388; font-size: 0.72rem; line-height: 1.45; }
	.policy-readout > div { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; color: #929298; font-size: 0.7rem; }.policy-readout strong { color: #e3e3e5; font-size: 0.74rem; }.funding-readout { background: #101011; }.funding-readout--risk { background: #241417; }.funding-readout > p:nth-child(2) { color: #e8e8e9; font-size: 1.35rem; font-weight: 750; letter-spacing: -0.05em; }.funding-readout--risk > p:nth-child(2) { color: #ff7186; }.funding-readout a { font-size: 0.72rem; }

	@media (max-width: 64rem) { .terminal-grid { grid-template-columns: minmax(0, 1fr) 16rem; }.chart-key { max-width: 15rem; }.toolbar-actions a:last-child { display: none; } }
	@media (max-width: 48rem) { .cash-terminal { min-height: auto; }.terminal-toolbar { flex-wrap: wrap; gap: 0.55rem; padding: 0.6rem 0.75rem; }.toolbar-separator, .model-state { display: none; }.terminal-identity { width: 100%; }.toolbar-actions { margin-left: auto; }.terminal-grid { grid-template-columns: 1fr; }.chart-workspace { padding: 0.9rem 0.65rem; border-right: 0; }.terminal-inspector { grid-template-columns: 1fr 1fr; border-top: 1px solid #262626; }.inspector-block { min-width: 0; }.inspector-block--day, .funding-readout { grid-column: 1 / -1; }.chart-header { display: grid; gap: 0.65rem; }.chart-key { justify-content: start; max-width: none; }.cash-graph svg { min-height: 17rem; }.event-watchlist li { grid-template-columns: 2.2rem minmax(0, 1fr); }.event-watchlist strong { grid-column: 2; }.day-control { grid-template-columns: auto 1fr; }.day-control > span { grid-column: 2; } }
	@media (max-width: 27rem) { .terminal-inspector { grid-template-columns: 1fr; }.inspector-block--day, .funding-readout { grid-column: auto; }.toolbar-actions a { padding: 0 0.4rem; }.cash-graph svg { min-height: 14rem; } }
</style>
