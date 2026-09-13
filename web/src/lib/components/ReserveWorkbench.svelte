<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatCurrency, formatPercent } from '$lib/format';
	import { parseUsdCents } from '$lib/workspace';
	import CoverageCurve from '$lib/components/CoverageCurve.svelte';
	import ReserveBufferCurve from '$lib/components/ReserveBufferCurve.svelte';
	import ShortfallDistribution from '$lib/components/ShortfallDistribution.svelte';
	import type { ScenarioResponse } from '$lib/types';
	import type { PlanningPolicy } from '$lib/finance';

	type ModelMode = 'scheduled' | 'assumptions' | 'history' | 'demo';

	interface Props {
		response: ScenarioResponse;
		source: 'personal' | 'demo';
		modelMode: ModelMode;
		policy: Pick<PlanningPolicy, 'operating_buffer_cents' | 'coverage_target'>;
		onPolicyPreview: (patch: Partial<PlanningPolicy>) => void | Promise<void>;
		isPreview?: boolean;
		saving?: boolean;
		onCommit?: (() => void | Promise<void>) | undefined;
		onDiscard?: (() => void | Promise<void>) | undefined;
		dataHref?: string;
	}

	let {
		response,
		source,
		modelMode,
		policy,
		onPolicyPreview,
		isPreview = false,
		saving = false,
		onCommit = undefined,
		onDiscard = undefined,
		dataHref = '/data?section=policy'
	}: Props = $props();

	let bufferError = $state('');
	const coverageOptions = [0.8, 0.9, 0.95] as const;
	const deterministic = $derived(modelMode === 'scheduled');

	function previewBuffer(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const cents = parseUsdCents(input.value, false);
		if (cents === null) {
			bufferError = 'Enter a non-negative dollar amount with at most two decimals.';
			input.value = String(policy.operating_buffer_cents / 100);
			return;
		}
		bufferError = '';
		void onPolicyPreview({ operating_buffer_cents: cents });
	}

	function submitBufferOnEnter(event: KeyboardEvent) {
		if (event.key === 'Enter') (event.currentTarget as HTMLInputElement).blur();
	}
</script>

<div class:reserve-workbench--preview={isPreview} class="reserve-workbench">
	<header class="view-toolbar">
		<div>
			<strong>{source === 'personal' ? 'Reserve policy' : 'Synthetic reserve policy'}</strong>
			<span>{deterministic ? 'known scheduled liquidity' : 'minimum liquid capital under the active forecast'}</span>
		</div>
		<p>{deterministic ? 'Deterministic schedule' : `${formatPercent(response.coverage_target)} coverage target`}</p>
	</header>

	<div class="reserve-layout">
		<main class="reserve-console">
			<section class="reserve-read" aria-labelledby="reserve-title">
				<div>
					<p class="label">{deterministic ? 'Known schedule reserve' : 'Required liquidity reserve'}</p>
					<p id="reserve-title" class="reserve-value numeric">{formatCurrency(response.required_liquidity_reserve)}</p>
					<span>
						{#if deterministic}
							Cash needed to cover the known schedule and retain the {formatCurrency(response.operating_buffer)} operating buffer.
						{:else}
							Above {formatCurrency(response.operating_buffer)} in {formatPercent(response.coverage_target)} of modeled paths.
						{/if}
					</span>
				</div>
				{#if !deterministic && response.estimate_band}
					<div class="estimate"><p class="label">Bootstrap reserve interval</p><strong class="numeric">{formatCurrency(response.estimate_band.low)}–{formatCurrency(response.estimate_band.high)}</strong></div>
				{/if}
				<div class="reserve-facts">
					<div><p class="label">Start funding</p><strong class="numeric">{formatCurrency(response.immediate_funding)}</strong></div>
					<div><p class="label">Policy buffer</p><strong class="numeric">{formatCurrency(response.operating_buffer)}</strong></div>
					<div><p class="label">Gap to reserve</p><strong class:gap={response.funding_gap > 0} class="numeric">{formatCurrency(response.funding_gap)}</strong></div>
				</div>
			</section>

			{#if deterministic}
				<section class="deterministic-note" aria-label="Scheduled forecast scope">
					<strong>Known schedule only</strong>
					<p>This view does not claim a probability range or confidence band. Add classified history or explicit assumptions when you want uncertainty estimates.</p>
					{#if source === 'personal'}<a href={resolve('/data?section=history')}>Add history in Data</a>{/if}
				</section>
			{:else}
				<section class="curve-section" aria-labelledby="coverage-curve-title">
					<div class="section-heading"><div><p class="label">Coverage curve</p><h2 id="coverage-curve-title">Funding level versus coverage</h2></div><span>{response.estimate_band ? 'Shading marks the bootstrap reserve interval.' : 'Coverage is conditional on your assumptions. No bootstrap reserve interval is shown.'}</span></div>
					<CoverageCurve
						points={response.coverage_curve}
						currentFunding={response.immediate_funding}
						coverageTarget={response.coverage_target}
						requiredReserve={response.required_liquidity_reserve}
						estimateBand={response.estimate_band}
					/>
				</section>
			{/if}

			<div class="diagnostic-grid" class:diagnostic-grid--scheduled={deterministic}>
				<section class="reserve-buffer-section" aria-labelledby="reserve-buffer-curve-title">
					<div class="section-heading">
						<div>
							<p class="label">Policy sensitivity</p>
							<h2 id="reserve-buffer-curve-title">Buffer drives reserve</h2>
						</div>
						<span>Every point uses the same forecast and shows the cash reserve needed when the untouched amount changes.</span>
					</div>
					<ReserveBufferCurve
						points={response.reserve_buffer_curve}
						operatingBuffer={response.operating_buffer}
						requiredReserve={response.required_liquidity_reserve}
					/>
				</section>

				{#if !deterministic}
					<section class="shortfall-section" aria-labelledby="shortfall-distribution-title">
						<div class="section-heading"><div><p class="label">Path severity</p><h2 id="shortfall-distribution-title">How the downside fails</h2></div></div>
						<div class="severity-readout">
							<div><span>Shortfall chance</span><strong class="numeric">{formatPercent(response.severity.cash_shortfall_probability)}</strong></div>
							<div><span>Average deficit</span><strong class="numeric">{formatCurrency(response.severity.avg_cash_deficit_when_short)}</strong></div>
							<div><span>Dollar-days below buffer</span><strong class="numeric">{formatCurrency(response.severity.dollar_days_below_buffer)}</strong></div>
						</div>
						<ShortfallDistribution distribution={response.shortfall_distribution} />
					</section>
				{/if}
			</div>

			{#if !deterministic && response.sensitivity.length > 0}
				<section class="sensitivity-section" aria-labelledby="sensitivity-title">
					<div class="section-heading"><div><p class="label">Stress read</p><h2 id="sensitivity-title">Cash-flow persistence</h2></div>{#if response.sensitivity_verdict}<span>{response.sensitivity_verdict}</span>{/if}</div>
					<div class="sensitivity-list">
						{#each response.sensitivity as row (row.block_label)}
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
				<div class="currency-input"><span aria-hidden="true">$</span><input id="operating-buffer" type="text" class="numeric" inputmode="decimal" value={String(policy.operating_buffer_cents / 100)} disabled={saving} onblur={previewBuffer} onkeydown={submitBufferOnEnter} /></div>
				{#if bufferError}<p class="control-error" role="alert">{bufferError}</p>{/if}
			</section>
			<section>
				<p class="label" id="coverage-target-label">Coverage target</p>
				<span>{deterministic ? 'Saved for a future uncertainty model; the current schedule has no probability range.' : 'How often the modeled balance must remain above the buffer.'}</span>
				<div class="segmented" role="group" aria-labelledby="coverage-target-label">
					{#each coverageOptions as option (option)}
						<button type="button" class:active={policy.coverage_target === option} aria-pressed={policy.coverage_target === option} disabled={saving} onclick={() => void onPolicyPreview({ coverage_target: option })}>{formatPercent(option)}</button>
					{/each}
				</div>
			</section>
			<section>
				<p class="label">Policy status</p>
				<strong class:gap={response.funding_gap > 0}>{response.funding_gap > 0 ? 'Funding action required' : 'Reserve covered'}</strong>
				<span>{response.funding_gap > 0 ? 'Review Funding before moving cash or selling assets.' : 'Current funding clears the selected guardrail.'}</span>
				{#if saving}<p class="updating" role="status">Recomputing this policy preview…</p>{/if}
				{#if isPreview && source === 'personal'}
					<div class="preview-actions">
						{#if onDiscard}<button class="secondary" type="button" onclick={() => void onDiscard()} disabled={saving}>Discard</button>{/if}
						{#if onCommit}<button class="primary" type="button" onclick={() => void onCommit()} disabled={saving}>{saving ? 'Committing…' : 'Commit policy'}</button>{/if}
					</div>
				{:else if source === 'demo'}
					<p class="updating" role="status">Changes update the live synthetic example.</p>
				{/if}
			</section>
			{#if source === 'personal'}<a class="policy-link" href={dataHref}>More policy settings in Data</a>{/if}
		</aside>
	</div>
</div>

<style>
	.reserve-workbench { min-height: calc(100dvh - 3.25rem); background: var(--paper); color: var(--ink); }
	.reserve-workbench--preview { box-shadow: inset 3px 0 var(--cobalt); }
	.view-toolbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; min-height:3.35rem; padding:0.3rem 1rem; border-bottom:1px solid var(--rule); background:var(--paper); }
	.view-toolbar div { display:flex; align-items:baseline; gap:.6rem; min-width:0; }.view-toolbar strong { font-size:.9rem; letter-spacing:-.02em; }.view-toolbar span,.view-toolbar p,.label { color:var(--ink-soft); font-family:var(--font-mono); font-size:.63rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }.view-toolbar p { margin:0; text-align:right; }
	.reserve-layout { display:grid; grid-template-columns:minmax(0,1fr) 19rem; min-height:calc(100dvh - 6.6rem); }.reserve-console { display:flex; flex-direction:column; min-width:0; }.policy-console { display:grid; align-content:start; background:var(--paper-soft); border-left:1px solid var(--rule); }.policy-console section { display:grid; gap:.65rem; padding:1rem; border-bottom:1px solid var(--rule); }.policy-console label,.policy-console span { color:var(--ink-soft); font-size:.75rem; line-height:1.4; }.policy-console strong { color:var(--cobalt); font-size:.92rem; }.policy-console strong.gap { color:var(--negative); }
	.reserve-read { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:1rem; padding:1rem; border-bottom:1px solid var(--rule); background:var(--paper); }.reserve-read > div:first-child { display:grid; gap:.35rem; }.reserve-value { color:var(--ink); font-size:clamp(2rem,4vw,3.1rem); font-weight:800; letter-spacing:-.075em; line-height:.93; }.reserve-read span { color:var(--ink-soft); font-size:.76rem; line-height:1.4; }.estimate { display:grid; align-content:start; gap:.35rem; padding-left:1rem; border-left:1px solid var(--rule); }.estimate strong { color:var(--warning); font-size:.84rem; }.reserve-facts { grid-column:1 / -1; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; background:var(--rule); border:1px solid var(--rule); }.reserve-facts div { display:grid; gap:.35rem; padding:.7rem; background:var(--paper-soft); }.reserve-facts strong { color:var(--ink); font-size:.94rem; letter-spacing:-.025em; }.reserve-facts strong.gap { color:var(--negative); }
	.deterministic-note { display:flex; flex-wrap:wrap; align-items:baseline; gap:.55rem 1rem; padding:.85rem 1rem; background:var(--paper-deep); border-bottom:1px solid var(--rule); }.deterministic-note strong { color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.68rem; letter-spacing:.045em; text-transform:uppercase; }.deterministic-note p { flex:1 1 25rem; color:var(--ink-soft); font-size:.76rem; line-height:1.4; }.deterministic-note a,.policy-link { color:var(--cobalt-deep); font-size:.72rem; font-weight:700; }
	.curve-section { min-height:24rem; display:flex; flex-direction:column; padding:1rem; border-bottom:1px solid var(--rule); }.curve-section :global(.coverage-curve) { flex:1; min-height:0; }.diagnostic-grid { display:grid; grid-template-columns:minmax(20rem,1.1fr) minmax(20rem,.9fr); border-bottom:1px solid var(--rule); }.diagnostic-grid--scheduled { grid-template-columns:minmax(0,1fr); }.reserve-buffer-section,.shortfall-section { display:flex; flex-direction:column; min-width:0; min-height:21rem; padding:1rem; }.reserve-buffer-section { border-right:1px solid var(--rule); }.diagnostic-grid--scheduled .reserve-buffer-section { border-right:0; }.reserve-buffer-section :global(.reserve-buffer-curve),.shortfall-section :global(.shortfall-distribution) { flex:1; min-height:0; }.severity-readout { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; margin-bottom:.75rem; background:var(--rule); border:1px solid var(--rule); }.severity-readout div { display:grid; gap:.25rem; min-width:0; padding:.55rem; background:var(--paper-soft); }.severity-readout span { color:var(--ink-soft); font-size:.63rem; line-height:1.25; }.severity-readout strong { color:var(--ink); font-size:.79rem; letter-spacing:-.025em; }.sensitivity-section { padding:1rem; border-bottom:1px solid var(--rule); }.section-heading { display:flex; justify-content:space-between; gap:1rem; margin-bottom:.85rem; }.section-heading div { display:grid; gap:.25rem; }.section-heading h2 { font-size:.96rem; letter-spacing:-.025em; }.section-heading > span { max-width:40ch; color:var(--ink-soft); font-size:.73rem; line-height:1.4; }.sensitivity-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr)); gap:1px; background:var(--rule); border:1px solid var(--rule); }.sensitivity-list div { display:flex; justify-content:space-between; gap:.5rem; padding:.7rem; background:var(--paper-soft); }.sensitivity-list span { color:var(--ink-soft); font-size:.72rem; }.sensitivity-list strong { color:var(--ink); font-size:.8rem; }.sensitivity-list .estimated { box-shadow:inset 2px 0 var(--warning); }
	.currency-input { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; background:var(--paper); border:1px solid var(--control-border); }.currency-input span { padding-left:.7rem; color:var(--cobalt); font-family:var(--font-mono); }.currency-input input { width:100%; min-height:2.75rem; padding:0 .65rem; border:0; outline:0; background:transparent; color:var(--ink); }.currency-input:focus-within { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); }.control-error { margin:0; color:var(--negative); font-size:.72rem; }.segmented { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid var(--control-border); }.segmented button { min-height:2.75rem; border:0; border-right:1px solid var(--rule); background:var(--paper); color:var(--ink-soft); font-family:var(--font-mono); font-size:.72rem; font-weight:700; cursor:pointer; }.segmented button:last-child { border-right:0; }.segmented button:hover { background:var(--paper-deep); }.segmented button.active { background:var(--cobalt); color:var(--paper); }.preview-actions { display:flex; flex-wrap:wrap; gap:.4rem; }.preview-actions button { min-height:2.75rem; padding:0 .65rem; border:1px solid var(--control-border); font-family:var(--font-mono); font-size:.65rem; font-weight:700; text-transform:uppercase; cursor:pointer; }.preview-actions .primary { background:var(--cobalt); border-color:var(--cobalt); color:var(--paper); }.preview-actions .secondary { background:var(--paper); color:var(--cobalt-deep); }.preview-actions button:disabled { cursor:wait; opacity:.6; }.updating { margin:0; color:var(--warning); font-family:var(--font-mono); font-size:.66rem; text-transform:uppercase; }.policy-link { display:block; min-height:2.75rem; padding:.8rem 1rem; border-top:1px solid var(--rule); text-decoration:none; }
	@media(max-width:60rem){.reserve-workbench{min-height:0}.reserve-layout{grid-template-columns:1fr;min-height:0}.policy-console{grid-template-columns:repeat(3,minmax(0,1fr));border-left:0;border-top:1px solid var(--rule)}.policy-console section{border-right:1px solid var(--rule);border-bottom:0}.policy-link{grid-column:1 / -1}.diagnostic-grid{grid-template-columns:1fr}.reserve-buffer-section{border-right:0;border-bottom:1px solid var(--rule)}}
	@media(max-width:42rem){.view-toolbar{display:grid;gap:.2rem;padding:.6rem .75rem}.view-toolbar div{display:grid;gap:.2rem}.view-toolbar p{text-align:left}.reserve-read{grid-template-columns:1fr}.estimate{padding:0;border:0}.reserve-facts,.severity-readout,.policy-console{grid-template-columns:1fr}.policy-console section{border-right:0;border-bottom:1px solid var(--rule)}.curve-section,.reserve-buffer-section,.shortfall-section,.sensitivity-section{padding:.75rem}.section-heading{display:grid}.deterministic-note{display:grid}.deterministic-note p{flex:auto}.preview-actions{display:grid;grid-template-columns:1fr 1fr}.preview-actions button{width:100%}}
</style>
