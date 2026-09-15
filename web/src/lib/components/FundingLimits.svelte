<script lang="ts">
	import '$lib/analysis.css';
	import { scenarioStore } from '$lib/scenario.svelte';
	let tail = $state<number | undefined>(undefined);
	let mean = $state<number | undefined>(undefined);
	$effect(() => {
		tail = scenarioStore.request.tail_deficit_limit ?? undefined;
		mean = scenarioStore.request.buffer_tolerance_dollar_days ?? undefined;
	});
	function apply(event: SubmitEvent) {
		event.preventDefault();
		scenarioStore.setRiskLimits(tail ?? null, mean ?? null);
	}
</script>

<section class="analysis-panel" aria-label="Funding risk limits">
	<h2>Downside limits</h2>
	<p>Coverage sets the reserve quantile and required buffer coverage. These additional limits control the size and duration of buffer deficits for every funding comparison.</p>
	<form onsubmit={apply}>
		<label>Tail deficit limit ($)<input type="number" min="0" max="1000000" step="any" bind:value={tail} placeholder="No additional tail limit" /></label>
		<p class="analysis-note">Average of the worst per-future buffer deficits. Zero requires every positive-weight modeled future to preserve the buffer; a positive limit can allow breaches.</p>
		<label>Average buffer deficit allowance (dollar-days)<input type="number" min="0" max="1000000" step="any" bind:value={mean} placeholder="Use the model's default allowance" /></label>
		<p class="analysis-note">An average $100 deficit lasting three days uses 300 dollar-days. Blank uses (1 − coverage target) × buffer × evaluation days.</p>
		<button class="primary" type="submit">Apply downside limits</button>
	</form>
</section>
