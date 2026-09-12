<script lang="ts">
	interface Props {
		eyebrow: string;
		value: string;
		supporting: string;
		estimateRangeLabel?: string;
		estimateRangeValue?: string;
	}

	let { eyebrow, value, supporting, estimateRangeLabel, estimateRangeValue }: Props = $props();
</script>

<section class="hero-card">
	<p class="hero-eyebrow">{eyebrow}</p>
	<p class="hero-value numeric">{value}</p>
	<p class="hero-supporting">{supporting}</p>
	{#if estimateRangeLabel && estimateRangeValue}
		<div class="hero-estimate">
			<p class="hero-estimate-label">{estimateRangeLabel}</p>
			<p class="hero-estimate-value numeric">{estimateRangeValue}</p>
		</div>
	{/if}
</section>

<style>
	.hero-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-7) var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.hero-eyebrow {
		font-size: var(--font-size-sm);
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-dim);
	}

	.hero-value {
		font-size: var(--font-size-hero);
		font-weight: 700;
		line-height: 1.05;
		color: var(--color-text);
	}

	.hero-supporting {
		max-width: 34ch;
		font-size: var(--font-size-lg);
		color: var(--color-text-dim);
	}

	.hero-estimate {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
		margin-top: var(--space-4);
		padding-top: var(--space-4);
		border-top: 1px solid var(--color-border);
	}

	.hero-estimate-label {
		font-size: var(--font-size-sm);
		color: var(--color-text-faint);
	}

	.hero-estimate-value {
		font-size: var(--font-size-md);
		font-weight: 600;
		color: var(--color-text-dim);
	}
</style>
