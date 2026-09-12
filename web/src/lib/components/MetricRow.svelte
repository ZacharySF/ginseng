<script lang="ts">
	type Tone = 'neutral' | 'warning' | 'positive';

	interface Props {
		label: string;
		value: string;
		detail?: string;
		tone?: Tone;
	}

	let { label, value, detail, tone = 'neutral' }: Props = $props();
</script>

<div class="metric-row metric-row--{tone}">
	<div class="metric-text">
		<p class="metric-label">{label}</p>
		{#if detail}
			<p class="metric-detail">{detail}</p>
		{/if}
	</div>
	<p class="metric-value numeric">{value}</p>
</div>

<style>
	.metric-row {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--space-4);
		padding: var(--space-4) 0;
		border-bottom: 1px solid var(--color-border);
	}

	.metric-row:last-child {
		border-bottom: none;
	}

	.metric-text {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.metric-label {
		font-size: var(--font-size-md);
		color: var(--color-text-dim);
	}

	.metric-detail {
		font-size: var(--font-size-xs);
		color: var(--color-text-faint);
	}

	.metric-value {
		font-size: var(--font-size-xl);
		font-weight: 600;
		color: var(--color-text);
	}

	.metric-row--warning .metric-value {
		color: var(--color-warning);
	}

	.metric-row--positive .metric-value {
		color: var(--color-positive);
	}
</style>
