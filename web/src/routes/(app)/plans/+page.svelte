<script lang="ts">
	import ForecastAlerts from '$lib/components/ForecastAlerts.svelte';
	import FundingWorkbench from '$lib/components/FundingWorkbench.svelte';
	import PersonalForecastGate from '$lib/components/PersonalForecastGate.svelte';
	import ScenarioControls from '$lib/components/ScenarioControls.svelte';
	import { financialStore } from '$lib/finance.svelte';

	const workspace = $derived(financialStore.workspace);
	const forecast = $derived(financialStore.forecast);
	const current = $derived(forecast?.result ?? null);
	const comparisonRun = $derived(
		financialStore.comparison ?? (financialStore.comparisonStatus === 'idle' ? financialStore.baseline : null)
	);
	const comparison = $derived(comparisonRun?.result ?? null);
	const comparisonLabel = $derived(financialStore.comparisonName ?? 'saved inputs');
</script>

<svelte:head>
	<title>Ginseng — Personal funding routes</title>
	<meta name="description" content="Compare feasible personal funding routes, debt costs, taxable sales, deferral, and advanced risk outputs." />
</svelte:head>

<PersonalForecastGate>
	{#if workspace && forecast && current}
		<ScenarioControls showChanges={false} />
		<ForecastAlerts alerts={forecast.alerts} warnings={forecast.warnings} />
		<FundingWorkbench
			response={current}
			baseline={financialStore.isPreview ? comparison : null}
			comparisonLabel={comparisonLabel}
			source="personal"
			modelMode={forecast.model_mode}
			showComparison={financialStore.isPreview || financialStore.comparisonStatus === 'ready'}
			changes={financialStore.changes}
			isPreview={financialStore.isPreview}
			eventsHref="/future"
			dataHref="/data"
			hasCreditAccounts={workspace.inputs.credit_accounts.length > 0}
			hasHoldings={workspace.inputs.holdings.length > 0}
		/>
	{/if}
</PersonalForecastGate>
