<script lang="ts">
	import NumericalRiskPanel from '$lib/components/NumericalRiskPanel.svelte';
	import CashPathChart from '$lib/components/CashPathChart.svelte';
	import ForecastAlerts from '$lib/components/ForecastAlerts.svelte';
	import PersonalEventsWorkbench from '$lib/components/PersonalEventsWorkbench.svelte';
	import PersonalForecastGate from '$lib/components/PersonalForecastGate.svelte';
	import ForecastState from '$lib/components/ForecastState.svelte';
	import ScenarioControls from '$lib/components/ScenarioControls.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import { financialStore } from '$lib/finance.svelte';
	import { chartEventsForSchedule, effectiveSchedule } from '$lib/forecast-presentation';

	const workspace = $derived(financialStore.workspace);
	const forecast = $derived(financialStore.forecast);
	const current = $derived(forecast?.result ?? null);
	const schedule = $derived(workspace ? effectiveSchedule(workspace, financialStore.scenario) : null);
	const chartEvents = $derived(
		schedule && current ? chartEventsForSchedule(schedule, current.as_of, financialStore.horizonDays) : []
	);
</script>

<svelte:head>
	<title>Ginseng — Personal cash events</title>
	<meta
		name="description"
		content="Stage income, bills, recurrence, and individual paid or received dates against your personal cash forecast."
	/>
</svelte:head>

<PersonalForecastGate allowIncomplete>
	<ScenarioControls />
	{#if forecast && financialStore.forecastStatus === 'ready'}
		<ForecastAlerts alerts={forecast.alerts} warnings={forecast.warnings} />
	{/if}
	<PersonalEventsWorkbench />
	{#if financialStore.forecastStatus === 'error'}
		<ForecastState kind="error" title="The staged forecast is unavailable" detail={financialStore.forecastError ?? 'Your event edits are retained. Retry before reviewing their cash effect.'} onRetry={() => financialStore.refresh()} retryLabel="Retry forecast" />
	{:else if financialStore.forecastStatus === 'loading'}
		<ForecastState kind="loading" title="Updating the cash calendar" detail="Calculating the staged event dates. Previous numbers are not shown as the current preview." />
	{:else if forecast?.status === 'needs-input'}
		<ForecastState kind="needs-input" title="More input is needed to calculate these events" detail="You can still correct event dates and reconcile paid or skipped occurrences above." requirements={forecast.requirements} onRetry={() => financialStore.refresh()} retryLabel="Refresh forecast" />
	{:else if forecast && current}
		<section class="event-forecast" aria-labelledby="event-forecast-title">
			<header>
				<div><p>Forecast consequence</p><h2 id="event-forecast-title">Timing on the cash calendar</h2></div>
				<div class="event-metrics">
					<span><strong class="numeric">{formatCurrency(current.funding_gap)}</strong> reserve gap</span>
					<span><strong class="numeric">{formatCurrency(current.required_liquidity_reserve)}</strong> reserve</span>
					{#if forecast.model_mode !== 'scheduled'}<span><strong>{formatPercent(current.severity.cash_shortfall_probability)}</strong> shortfall chance</span>{/if}
				</div>
			</header>
			<CashPathChart
				cashPaths={current.cash_paths}
				operatingBuffer={current.operating_buffer}
				events={chartEvents}
				asOf={current.as_of}
				deterministic={forecast.model_mode === 'scheduled'}
				comparisonPaths={financialStore.comparisonForCurrent?.result?.cash_paths ?? null}
				comparisonLabel={financialStore.comparisonName ?? 'Saved inputs'}
			/>
		</section>
        {#if workspace}
            {@const numericalRequest = {expected_revision: workspace.revision, horizon_days: financialStore.horizonDays, ...(financialStore.scenario ? {overrides:financialStore.scenario} : {})}}
            {#key JSON.stringify(numericalRequest)}
                <NumericalRiskPanel request={numericalRequest} endpoint="/finance/numerics" supported={forecast.model_mode === 'history'} />
            {/key}
        {/if}
	{/if}
</PersonalForecastGate>

<style>
	.event-forecast { display:grid; gap:.8rem; padding:clamp(.8rem,2vw,1.35rem); background:var(--paper); border-top:1px solid var(--rule); }.event-forecast header { display:flex; align-items:end; justify-content:space-between; gap:1rem; }.event-forecast header > div:first-child { display:grid; gap:.2rem; }.event-forecast header p { color:var(--ink-soft); font-family:var(--font-mono); font-size:.63rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }.event-forecast h2 { font-size:1rem; letter-spacing:-.025em; }.event-metrics { display:flex; flex-wrap:wrap; justify-content:end; gap:.45rem; }.event-metrics span { display:grid; gap:.1rem; padding:.4rem .5rem; background:var(--paper-soft); border:1px solid var(--rule); color:var(--ink-soft); font-family:var(--font-mono); font-size:.58rem; font-weight:700; letter-spacing:.035em; text-transform:uppercase; }.event-metrics strong { color:var(--ink); font-size:.7rem; } @media(max-width:42rem){.event-forecast{padding:.75rem}.event-forecast header{display:grid;align-items:start}.event-metrics{justify-content:start}.event-metrics span{flex:1 1 8rem}}</style>
