<script lang="ts">
	import CashWorkbench from '$lib/components/CashWorkbench.svelte';
	import ForecastAlerts from '$lib/components/ForecastAlerts.svelte';
	import ForecastBacktest from '$lib/components/ForecastBacktest.svelte';
	import PersonalForecastGate from '$lib/components/PersonalForecastGate.svelte';
	import ScenarioControls from '$lib/components/ScenarioControls.svelte';
	import { financialStore } from '$lib/finance.svelte';
	import { chartEventsForSchedule, effectiveSchedule } from '$lib/forecast-presentation';

	const workspace = $derived(financialStore.workspace);
	const forecast = $derived(financialStore.forecast);
	const current = $derived(forecast?.result ?? null);
	const schedule = $derived(workspace ? effectiveSchedule(workspace, financialStore.scenario) : null);
	const chartEvents = $derived(
		schedule && current ? chartEventsForSchedule(schedule, current.as_of, financialStore.horizonDays) : []
	);
	const comparison = $derived(financialStore.comparisonForCurrent?.result ?? null);
	const comparisonLabel = $derived(financialStore.comparisonName ?? 'Saved inputs');
</script>

<svelte:head>
	<title>Ginseng — Personal cash forecast</title>
	<meta
		name="description"
		content="Inspect your saved cash forecast, reserve needs, scenario comparisons, alerts, and forecast accuracy."
	/>
</svelte:head>

<PersonalForecastGate>
	{#if workspace && forecast && current}
		<ScenarioControls />
		<ForecastAlerts alerts={forecast.alerts} warnings={forecast.warnings} />
		<CashWorkbench
			response={current}
			events={chartEvents}
			source="personal"
			horizonDays={financialStore.horizonDays}
			modelMode={forecast.model_mode}
			onHorizonChange={(horizon) => financialStore.setHorizonDays(horizon)}
			eventsHref="/future"
			reserveHref="/liquidity"
			fundingHref="/plans"
			dataHref="/data"
			isPreview={financialStore.isPreview}
			updating={financialStore.forecastStatus === 'loading'}
			{comparison}
			{comparisonLabel}
		/>
		<ForecastBacktest
			modelMode={forecast.model_mode}
			accuracy={financialStore.accuracy}
			error={financialStore.accuracyError}
			loading={financialStore.accuracyLoading}
			onRun={() => financialStore.backtest()}
		/>
	{/if}
</PersonalForecastGate>
