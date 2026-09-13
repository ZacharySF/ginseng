<script lang="ts">
	import '$lib/analysis.css';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import type { ScenarioResponse } from '$lib/types';
	let { response }: { response: ScenarioResponse } = $props();
	const stress = $derived(response.stress);
	let probability = $state(15);
	$effect(() => { probability = (scenarioStore.request.drought_view?.probability ?? .15) * 100; });
	function apply(event: SubmitEvent) {
		event.preventDefault();
		scenarioStore.setStressProbability(probability / 100);
	}
</script>

<section class="analysis-panel" aria-label="Drought stress assumption">
	<h2>Income stress</h2>
	<p><strong>Stress assumption — not an estimated probability</strong></p>
	<p>Give more or less weight to futures with variable income below half its historical average over the first 14 days (or the shorter forecast window).</p>
	<form onsubmit={apply}>
		<label>Assumed probability (%)<input type="number" min="0" max="100" step="1" bind:value={probability} required /></label>
		<button class="primary" type="submit">Apply stress weights</button>
		{#if scenarioStore.request.drought_view}<button type="button" onclick={() => scenarioStore.setStressProbability(null)}>Remove stress</button>{/if}
	</form>
	{#if stress?.status === 'unsupported'}<p class="analysis-alert" role="status">{stress.message} The figures shown use the unstressed model; this stress has not been applied.</p>{/if}
	{#if stress?.status === 'active'}
		<p>{stress.definition}</p>
		<p>Historical model: {formatPercent(stress.baseline_probability ?? 0)} → assumption: {formatPercent(stress.achieved_probability ?? 0)}.</p>
		<div class="analysis-grid">
			<div><small>Unstressed reserve</small><strong>{formatCurrency(response.unstressed_summary.required_liquidity_reserve)}</strong></div>
			<div><small>Stressed reserve</small><strong>{formatCurrency(response.required_liquidity_reserve)}</strong></div>
		</div>
		<p class="analysis-note">Same futures, different weights. A certain bill can still move the reserve almost dollar for dollar.</p>
		<p class="analysis-note">The model-estimate band is omitted for this overlay. Historical checks evaluate the unstressed model.</p>
	{/if}
	{#if stress}
		<div class="analysis-grid">
			<div><small>Overall effective futures</small><strong>{stress.ens_overall.toFixed(0)}</strong></div>
			<div><small>Tail effective futures</small><strong>{stress.ens_tail.toFixed(0)}</strong></div>
			<div><small>Largest weight</small><strong>{formatPercent(stress.max_weight)}</strong></div>
		</div>
		{#if !stress.recommendation_supported}<p class="analysis-alert">Recommendations are withheld because this stress lacks sufficient scenario support.</p>{/if}
		<details><summary>How scenario support is measured</summary>
			<p>{stress.support_policy}</p><p>Effective futures measure weight concentration, not independent historical evidence. Tied losses share the tail boundary proportionally.</p>
			{#if stress.constraint_residual !== undefined}<p>Stress probability residual: {stress.constraint_residual.toFixed(8)}.</p>{/if}
		</details>
	{/if}
</section>
