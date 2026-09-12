<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore, COVERAGE_TARGET_OPTIONS } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import CoverageCurve from '$lib/components/CoverageCurve.svelte';
	import ReserveBufferCurve from '$lib/components/ReserveBufferCurve.svelte';
	import ShortfallDistribution from '$lib/components/ShortfallDistribution.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});

	function commitBuffer(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const value = Number(input.value);
		if (Number.isFinite(value) && value >= 0) {
			scenarioStore.setOperatingBuffer(value);
		} else {
			input.value = String(scenarioStore.request.operating_buffer);
		}
	}

	function commitBufferOnEnter(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			(event.currentTarget as HTMLInputElement).blur();
		}
	}
</script>

<svelte:head>
	<title>Ginseng — Reserve</title>
	<meta
		name="description"
		content="Set an operating buffer and coverage target, then inspect the local liquidity reserve."
	/>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="terminal-view">
		<header class="view-toolbar">
			<div><strong>Reserve policy</strong><span>minimum liquid capital under active scenario</span></div>
			<p>{formatPercent(s.coverage_target)} coverage target</p>
		</header>

		<div class="reserve-layout">
			<main class="reserve-console">
				<section class="reserve-read" aria-labelledby="reserve-title">
					<div>
						<p class="label">Required liquidity reserve</p>
						<p id="reserve-title" class="reserve-value numeric">{formatCurrency(s.required_liquidity_reserve)}</p>
						<span>Above {formatCurrency(s.operating_buffer)} in {formatPercent(s.coverage_target)} of modeled paths.</span>
					</div>
					{#if s.estimate_band}
						<div class="estimate"><p class="label">Model range</p><strong class="numeric">{formatCurrency(s.estimate_band.low)}–{formatCurrency(s.estimate_band.high)}</strong></div>
					{/if}
					<div class="reserve-facts">
						<div><p class="label">Start funding</p><strong class="numeric">{formatCurrency(s.immediate_funding)}</strong></div>
						<div><p class="label">Policy buffer</p><strong class="numeric">{formatCurrency(s.operating_buffer)}</strong></div>
						<div><p class="label">Gap to reserve</p><strong class:gap={s.funding_gap > 0} class="numeric">{formatCurrency(s.funding_gap)}</strong></div>
					</div>
				</section>

				<section class="curve-section" aria-labelledby="coverage-curve-title">
					<div class="section-heading"><div><p class="label">Coverage curve</p><h2 id="coverage-curve-title">Funding level versus confidence</h2></div><span>The target line crosses the reserve. The vertical band is model uncertainty.</span></div>
					<CoverageCurve
						points={s.coverage_curve}
						currentFunding={s.immediate_funding}
						coverageTarget={s.coverage_target}
						requiredReserve={s.required_liquidity_reserve}
						estimateBand={s.estimate_band}
					/>
				</section>

				<div class="diagnostic-grid">
					<section class="reserve-buffer-section" aria-labelledby="reserve-buffer-curve-title">
						<div class="section-heading">
							<div>
								<p class="label">Policy sensitivity</p>
								<h2 id="reserve-buffer-curve-title">Buffer drives reserve</h2>
							</div>
							<span>See the cash reserve needed if you changed the amount left untouched.</span>
						</div>
						<ReserveBufferCurve
							points={s.reserve_buffer_curve}
							operatingBuffer={s.operating_buffer}
							requiredReserve={s.required_liquidity_reserve}
						/>
					</section>

					<section class="shortfall-section" aria-labelledby="shortfall-distribution-title">
						<div class="section-heading">
							<div>
								<p class="label">Path severity</p>
								<h2 id="shortfall-distribution-title">How the downside fails</h2>
							</div>
						</div>
						<div class="severity-readout">
							<div>
								<span>Shortfall chance</span>
								<strong class="numeric">{formatPercent(s.severity.cash_shortfall_probability)}</strong>
							</div>
							<div>
								<span>Average deficit</span>
								<strong class="numeric">{formatCurrency(s.severity.avg_cash_deficit_when_short)}</strong>
							</div>
							<div>
								<span>Dollar-days below buffer</span>
								<strong class="numeric">{formatCurrency(s.severity.dollar_days_below_buffer)}</strong>
							</div>
						</div>
						<ShortfallDistribution distribution={s.shortfall_distribution} />
					</section>
				</div>

				{#if s.sensitivity.length > 0}
					<section class="sensitivity-section" aria-labelledby="sensitivity-title">
						<div class="section-heading"><div><p class="label">Stress read</p><h2 id="sensitivity-title">Income persistence</h2></div>{#if s.sensitivity_verdict}<span>{s.sensitivity_verdict}</span>{/if}</div>
						<div class="sensitivity-list">
							{#each s.sensitivity as row (row.block_label)}
								<div class:estimated={row.is_estimated}><span>{row.block_label}{#if row.is_estimated && !row.was_clipped} / estimated{/if}</span><strong class="numeric">{formatCurrency(row.required_liquidity_reserve)}</strong></div>
							{/each}
						</div>
					</section>
				{/if}
			</main>

			<aside class="policy-console" aria-label="Liquidity policy controls">
				<section>
					<p class="label">Operating buffer</p>
					<label for="operating-buffer">Amount kept untouched</label>
					<div class="currency-input"><span aria-hidden="true">$</span><input id="operating-buffer" type="number" class="numeric" min="0" step="100" value={scenarioStore.request.operating_buffer} onchange={commitBuffer} onkeydown={commitBufferOnEnter} /></div>
				</section>
				<section>
					<p class="label" id="coverage-target-label">Coverage target</p>
					<span>How often the modeled balance must remain above the buffer.</span>
					<div class="segmented" role="group" aria-labelledby="coverage-target-label">
						{#each COVERAGE_TARGET_OPTIONS as option (option)}
							<button type="button" class:active={scenarioStore.request.coverage_target === option} aria-pressed={scenarioStore.request.coverage_target === option} onclick={() => scenarioStore.setCoverageTarget(option)}>{formatPercent(option)}</button>
						{/each}
					</div>
				</section>
				<section>
					<p class="label">Policy status</p>
					<strong class:gap={s.funding_gap > 0}>{s.funding_gap > 0 ? 'Funding action required' : 'Reserve covered'}</strong>
					<span>{s.funding_gap > 0 ? 'Compare routes in Funding before committing cash.' : 'Current funding clears the chosen guardrail.'}</span>
					{#if scenarioStore.loadState === 'loading'}<p class="updating" role="status" aria-live="polite">Recomputing…</p>{/if}
				</section>
			</aside>
		</div>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Sizing local reserve…</p>
{/if}

<style>
	.terminal-view {
		display: flex;
		flex-direction: column;
		height: calc(100dvh - 3rem);
		background: #050505;
		color: #e5e5e7;
	}

	.view-toolbar {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 3.35rem;
		padding: 0 1rem;
		border-bottom: 1px solid #29292d;
		background: #0c0c0d;
	}
	.view-toolbar div { display: flex; align-items: baseline; gap: 0.6rem; }
	.view-toolbar strong { font-size: 0.86rem; letter-spacing: -0.02em; }
	.view-toolbar span, .view-toolbar p, .label {
		color: #898990;
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.reserve-layout {
		flex: 1;
		min-height: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr) 19rem;
	}
	.reserve-console { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow-y: auto; }
	.policy-console {
		display: grid;
		align-content: start;
		min-height: 0;
		overflow-y: auto;
		border-left: 1px solid #29292d;
		background: #0b0b0c;
	}
	.policy-console section { display: grid; gap: 0.65rem; padding: 1rem; border-bottom: 1px solid #29292d; }
	.policy-console label, .policy-console span { color: #9999a0; font-size: 0.73rem; line-height: 1.4; }
	.policy-console strong { color: #42d3ba; font-size: 0.9rem; }
	.policy-console strong.gap { color: #ff7186; }

	.reserve-read {
		flex: none;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 1rem;
		padding: 1rem;
		border-bottom: 1px solid #29292d;
		background: #0c0c0d;
	}
	.reserve-read > div:first-child { display: grid; gap: 0.35rem; }
	.reserve-value { margin: 0; color: #f0f0f1; font-size: 2rem; font-weight: 760; letter-spacing: -0.07em; }
	.reserve-read span { color: #96969c; font-size: 0.74rem; line-height: 1.4; }
	.estimate { display: grid; align-content: start; gap: 0.35rem; padding-left: 1rem; border-left: 1px solid #29292d; }
	.estimate strong { color: #d8a84e; font-size: 0.82rem; }
	.reserve-facts {
		grid-column: 1 / -1;
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1px;
		background: #29292d;
		border: 1px solid #29292d;
	}
	.reserve-facts div { display: grid; gap: 0.35rem; padding: 0.7rem; background: #101011; }
	.reserve-facts strong { color: #e0e0e3; font-size: 0.92rem; letter-spacing: -0.02em; }
	.reserve-facts strong.gap { color: #ff7186; }

	.curve-section {
		flex: none;
		min-height: 24rem;
		display: flex;
		flex-direction: column;
		padding: 1rem;
		border-bottom: 1px solid #29292d;
	}
	.curve-section :global(.coverage-curve) { flex: 1; min-height: 0; }
	.diagnostic-grid {
		display: grid;
		grid-template-columns: minmax(20rem, 1.1fr) minmax(20rem, 0.9fr);
		border-bottom: 1px solid #29292d;
	}
	.reserve-buffer-section,
	.shortfall-section {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 21rem;
		padding: 1rem;
	}
	.reserve-buffer-section { border-right: 1px solid #29292d; }
	.reserve-buffer-section :global(.reserve-buffer-curve),
	.shortfall-section :global(.shortfall-distribution) { flex: 1; min-height: 0; }
	.severity-readout {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1px;
		margin-bottom: 0.75rem;
		background: #29292d;
		border: 1px solid #29292d;
	}
	.severity-readout div { display: grid; gap: 0.25rem; min-width: 0; padding: 0.55rem; background: #101011; }
	.severity-readout span { color: #9a9aa0; font-size: 0.62rem; line-height: 1.25; }
	.severity-readout strong { color: #e8e8eb; font-size: 0.78rem; letter-spacing: -0.02em; }
	.sensitivity-section { flex: none; padding: 1rem; border-bottom: 1px solid #29292d; }
	.section-heading { flex: none; display: flex; justify-content: space-between; gap: 1rem; margin-bottom: 0.85rem; }
	.section-heading div { display: grid; gap: 0.25rem; }
	.section-heading h2 { margin: 0; color: #e4e4e7; font-size: 0.92rem; letter-spacing: -0.02em; }
	.section-heading > span { max-width: 40ch; color: #94949a; font-size: 0.72rem; line-height: 1.4; }
	.sensitivity-list {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
		gap: 1px;
		background: #29292d;
		border: 1px solid #29292d;
	}
	.sensitivity-list div { display: flex; justify-content: space-between; gap: 0.5rem; padding: 0.7rem; background: #0d0d0e; }
	.sensitivity-list span { color: #acacb1; font-size: 0.72rem; }
	.sensitivity-list strong { color: #e3e3e6; font-size: 0.8rem; }
	.sensitivity-list .estimated { box-shadow: inset 2px 0 #d8a84e; }

	.currency-input {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		align-items: center;
		border: 1px solid #45454b;
		background: #060607;
	}
	.currency-input span { padding-left: 0.7rem; color: #42d3ba; font-family: var(--font-mono); }
	.currency-input input { width: 100%; min-height: 2.45rem; padding: 0 0.65rem; border: 0; outline: 0; background: transparent; color: #f0f0f1; font: inherit; }
	.currency-input:focus-within { border-color: #42d3ba; }
	.segmented { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #45454b; }
	.segmented button {
		min-height: 2.3rem;
		border: 0;
		border-right: 1px solid #45454b;
		background: #101011;
		color: #a8a8ad;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		cursor: pointer;
	}
	.segmented button:last-child { border-right: 0; }
	.segmented button.active { background: #1a5650; color: #c5fff5; }
	.updating { margin: 0; color: #d8a84e; font-family: var(--font-mono); font-size: 0.66rem; text-transform: uppercase; }

	.terminal-state, .terminal-loading {
		display: grid;
		place-content: center;
		gap: 0.5rem;
		min-height: calc(100dvh - 3rem);
		padding: 2rem;
		background: #050505;
		color: #a2a2a8;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
	}
	.terminal-state p { color: #ff7186; }
	.terminal-state span { max-width: 44ch; font-family: var(--font-sans); font-size: 0.82rem; text-transform: none; }
	.terminal-state button {
		justify-self: start;
		min-height: 2.3rem;
		padding: 0 0.7rem;
		background: #18181a;
		border: 1px solid #55555c;
		color: #fff;
		font: inherit;
		cursor: pointer;
	}

	@media (max-width: 60rem) {
		.terminal-view { height: auto; min-height: calc(100dvh - 3rem); }
		.reserve-layout { flex: none; grid-template-columns: 1fr; }
		.reserve-console, .policy-console { overflow-y: visible; }
		.curve-section { min-height: 22rem; }
		.diagnostic-grid { grid-template-columns: 1fr; }
		.reserve-buffer-section { border-right: 0; border-bottom: 1px solid #29292d; }
		.policy-console { grid-template-columns: repeat(3, 1fr); border-left: 0; border-top: 1px solid #29292d; }
		.policy-console section { border-right: 1px solid #29292d; border-bottom: 0; }
	}

	@media (max-width: 42rem) {
		.view-toolbar { display: grid; gap: 0.2rem; padding: 0.6rem 0.75rem; }
		.view-toolbar div { display: grid; gap: 0.2rem; }
		.view-toolbar p { margin: 0; }
		.reserve-read { grid-template-columns: 1fr; }
		.estimate { padding: 0; border: 0; }
		.reserve-facts { grid-template-columns: 1fr; }
		.section-heading { display: grid; }
		.policy-console { grid-template-columns: 1fr; }
		.policy-console section { border-right: 0; border-bottom: 1px solid #29292d; }
		.curve-section, .reserve-buffer-section, .shortfall-section, .sensitivity-section { padding: 0.75rem; }
		.severity-readout { grid-template-columns: 1fr; }
	}
	/* Cobalt ledger skin */
	.terminal-view { background: var(--paper); color: var(--ink); }
	.view-toolbar { background: var(--paper); border-color: var(--rule); }
	.view-toolbar span, .view-toolbar p, .label { color: var(--ink-muted); }
	.policy-console { background: var(--paper-soft); border-color: var(--rule); }
	.policy-console section { border-color: var(--rule); }
	.policy-console label, .policy-console span, .reserve-read span, .section-heading > span { color: var(--ink-muted); }
	.policy-console strong { color: var(--cobalt); }
	.policy-console strong.gap, .reserve-facts strong.gap, .terminal-state p { color: var(--negative); }
	.reserve-read { background: var(--paper); border-color: var(--rule); }
	.reserve-value, .section-heading h2, .reserve-facts strong, .severity-readout strong, .sensitivity-list strong { color: var(--ink); }
	.estimate { border-color: var(--rule); }
	.estimate strong, .updating { color: var(--warning); }
	.reserve-facts, .severity-readout, .sensitivity-list { background: var(--rule); border-color: var(--rule); }
	.reserve-facts div, .severity-readout div, .sensitivity-list div { background: var(--paper-soft); }
	.reserve-facts, .curve-section, .diagnostic-grid, .reserve-buffer-section, .sensitivity-section { border-color: var(--rule); }
	.severity-readout span, .sensitivity-list span { color: var(--ink-soft); }
	.sensitivity-list .estimated { box-shadow: inset 2px 0 var(--warning); }
	.currency-input, .segmented { background: var(--paper); border-color: var(--rule-strong); }
	.currency-input span { color: var(--cobalt); }
	.currency-input input { color: var(--ink); }
	.currency-input:focus-within { border-color: var(--cobalt); }
	.segmented button { background: var(--paper); border-color: var(--rule); color: var(--ink-soft); }
	.segmented button.active { background: var(--cobalt); color: var(--paper); }
	.terminal-state, .terminal-loading { background: var(--paper); color: var(--ink-muted); }
	.terminal-state button { background: var(--cobalt); border-color: var(--cobalt); color: var(--paper); }
</style>
