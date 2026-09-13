<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { financialStore } from '$lib/finance.svelte';
	import ForecastState from '$lib/components/ForecastState.svelte';
	import ScenarioControls from '$lib/components/ScenarioControls.svelte';

	interface Props {
		children: Snippet;
		allowIncomplete?: boolean;
	}

	let { children, allowIncomplete = false }: Props = $props();

	onMount(() => {
		void financialStore.load();
	});
</script>

{#if financialStore.requiresReconciliation}
	{#if financialStore.isPreview}<ScenarioControls />{/if}
	<ForecastState
		kind="error"
		title="Reconcile your saved workspace"
		detail={`${financialStore.error ?? 'Reload the current saved inputs before another change.'}${financialStore.isPreview ? ' Reloading discards this unsaved what-if.' : ''}`}
		onRetry={() => financialStore.reload()}
		retryLabel={financialStore.isPreview ? 'Discard preview and reload' : 'Reload saved plan'}
	/>
{:else if (financialStore.status === 'idle' || financialStore.status === 'loading') && !financialStore.workspace}
	<ForecastState kind="loading" title="Loading your saved financial inputs" detail="Reading the cash workspace and supplemental planning inputs for this signed-in account." />
{:else if financialStore.status === 'error' && !financialStore.workspace}
	<ForecastState kind="error" title="Your saved financial inputs are unavailable" detail={financialStore.error ?? 'Check your connection and retry loading this account.'} onRetry={() => financialStore.reload()} retryLabel="Retry loading" />
{:else if !financialStore.workspace}
	<ForecastState kind="empty" title="There is no personal financial workspace to forecast" detail="Add your opening cash and timing data in Data before running a personal forecast." />
	{:else if allowIncomplete}
		{@render children()}
	{:else if financialStore.forecastStatus === 'error'}
		{#if financialStore.isPreview}<ScenarioControls />{/if}
		<ForecastState kind="error" title="This personal forecast could not be calculated" detail={financialStore.forecastError ?? 'Your staged inputs are retained. Retry the forecast or discard the preview.'} onRetry={() => financialStore.refresh()} retryLabel="Retry forecast" />
{:else if financialStore.forecast?.status === 'needs-input'}
	{#if financialStore.isPreview}<ScenarioControls />{/if}
	<ForecastState kind="needs-input" title="Complete the inputs this forecast needs" detail="Ginseng will not replace missing personal information with a synthetic assumption. Add the requested data, then return to this forecast." requirements={financialStore.forecast.requirements} onRetry={() => financialStore.refresh()} retryLabel="Refresh forecast" />
{:else if financialStore.forecast?.status === 'ready' && financialStore.forecast.result}
	{@render children()}
{:else}
	<ForecastState kind="loading" title="Preparing the personal forecast" detail="Applying the current saved plan and any active what-if to the selected horizon." />
{/if}
