<script lang="ts">
	import ForecastAlerts from '$lib/components/ForecastAlerts.svelte';
	import PersonalForecastGate from '$lib/components/PersonalForecastGate.svelte';
	import ReserveWorkbench from '$lib/components/ReserveWorkbench.svelte';
	import ScenarioControls from '$lib/components/ScenarioControls.svelte';
	import { financialStore } from '$lib/finance.svelte';

	const workspace = $derived(financialStore.workspace);
	const forecast = $derived(financialStore.forecast);
	const current = $derived(forecast?.result ?? null);
	const activePolicy = $derived(financialStore.scenario?.policy ?? workspace?.inputs.policy ?? null);
</script>

<svelte:head>
	<title>Ginseng — Personal reserve policy</title>
	<meta name="description" content="Preview and explicitly commit your personal operating buffer and reserve coverage policy." />
</svelte:head>

<PersonalForecastGate>
	{#if workspace && forecast && current && activePolicy}
		<ScenarioControls showChanges={false} />
		<ForecastAlerts alerts={forecast.alerts} warnings={forecast.warnings} />
		<ReserveWorkbench
			response={current}
			source="personal"
			modelMode={forecast.model_mode}
			policy={activePolicy}
			onPolicyPreview={(patch) => financialStore.setPolicy(patch)}
			isPreview={financialStore.isPreview}
			saving={financialStore.saving || financialStore.forecastStatus === 'loading'}
			onCommit={async () => { await financialStore.commitScenario(); }}
			onDiscard={() => financialStore.discardScenario()}
			dataHref="/data?section=policy"
		/>
	{/if}
</PersonalForecastGate>
