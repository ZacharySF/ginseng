<script lang="ts">
	import type { ForecastAlert } from '$lib/finance';

	interface Props {
		alerts: ForecastAlert[];
		warnings?: string[];
	}

	let { alerts, warnings = [] }: Props = $props();
	const actionable = $derived(alerts.filter((alert) => alert.severity !== 'info'));
	const informational = $derived(alerts.filter((alert) => alert.severity === 'info'));
</script>

{#if alerts.length > 0 || warnings.length > 0}
	<section class="alerts" aria-label="Forecast notices">
		{#if actionable.length > 0}
			<ul>
				{#each actionable as alert (alert.id)}
					<li class:critical={alert.severity === 'critical'} class:warning={alert.severity === 'warning'}>
						<strong>{alert.title}</strong><span>{alert.detail}</span>
					</li>
				{/each}
			</ul>
		{/if}
		{#if warnings.length > 0 || informational.length > 0}
			<details>
				<summary>Source & model notes <span>{warnings.length + informational.length}</span></summary>
				<p class="monitoring-note">These checks describe the current forecast, not background monitoring.</p>
				<ul>
					{#each informational as alert (alert.id)}
						<li><strong>{alert.title}</strong><span>{alert.detail}</span></li>
					{/each}
					{#each warnings as warning (`warning:${warning}`)}
						<li><span>{warning}</span></li>
					{/each}
				</ul>
			</details>
		{/if}
	</section>
{/if}

<style>
	.alerts {
		display: grid;
		gap: 0.6rem;
		padding: 0.4rem 1rem;
		background: var(--paper);
		border-bottom: 1px solid var(--rule);
	}

	summary {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		min-height: 2.75rem;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.7rem;
		font-weight: 700;
		cursor: pointer;
	}

	summary::before { content: '+'; color: var(--cobalt); }
	details[open] summary::before { content: '−'; }
	summary span { font-weight: 400; }
	.monitoring-note { margin: 0 0 0.6rem; color: var(--ink-soft); font-size: 0.8rem; }

	ul {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
		gap: 1px;
		padding: 0;
		margin: 0;
		background: var(--rule);
		border: 1px solid var(--rule);
		list-style: none;
	}

	li {
		display: grid;
		gap: 0.25rem;
		padding: 0.65rem;
		background: var(--paper-soft);
		border-left: 2px solid var(--cobalt);
	}

	li.warning {
		border-left-color: var(--warning);
	}

	li.critical {
		background: var(--negative-soft);
		border-left-color: var(--negative);
	}

	li strong {
		font-size: 0.76rem;
	}

	li span {
		color: var(--ink-soft);
		font-size: 0.72rem;
		line-height: 1.4;
	}

</style>
