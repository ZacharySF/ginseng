<script lang="ts">
    import StressControls from '$lib/components/StressControls.svelte';
    import ModelEvidencePanel from '$lib/components/ModelEvidencePanel.svelte';

	import { onMount } from 'svelte';
	import ReserveWorkbench from '$lib/components/ReserveWorkbench.svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import type { PlanningPolicy } from '$lib/finance';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});

	function applyDemoPolicy(patch: Partial<PlanningPolicy>) {
		if (patch.operating_buffer_cents !== undefined) {
			scenarioStore.setOperatingBuffer(patch.operating_buffer_cents / 100);
		}
		if (patch.coverage_target !== undefined) {
			scenarioStore.setCoverageTarget(patch.coverage_target);
		}
	}
</script>

<svelte:head>
	<title>Ginseng — Synthetic reserve demo</title>
	<meta name="description" content="Adjust the reserve policy in a synthetic example without changing personal financial data." />
</svelte:head>

{#if scenarioStore.response}
	<ReserveWorkbench
		response={scenarioStore.response}
		source="demo"
		modelMode="demo"
		policy={{
			operating_buffer_cents: Math.round(scenarioStore.request.operating_buffer * 100),
			coverage_target: scenarioStore.request.coverage_target
		}}
		onPolicyPreview={applyDemoPolicy}
		saving={scenarioStore.loadState === 'loading'}
	/>
<StressControls response={scenarioStore.response} />
    <ModelEvidencePanel response={scenarioStore.response} />
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Sizing the synthetic reserve…</p>
{/if}

<style>
	.terminal-state,.terminal-loading { display:grid; place-content:center; gap:.5rem; min-height:calc(100dvh - 3rem); padding:2rem; background:var(--paper); color:var(--ink-soft); font-family:var(--font-mono); font-size:.72rem; text-transform:uppercase; }.terminal-state p { color:var(--negative); }.terminal-state span { max-width:44ch; color:var(--ink-soft); font-family:var(--font-sans); font-size:.82rem; text-transform:none; }.terminal-state button { justify-self:start; min-height:2.75rem; padding:0 .75rem; background:var(--cobalt); border:1px solid var(--cobalt); color:var(--paper); font:inherit; cursor:pointer; }
</style>
