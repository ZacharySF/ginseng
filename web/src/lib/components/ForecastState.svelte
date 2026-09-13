<script lang="ts">
	import { resolve } from '$app/paths';
	import type { DataRequirement } from '$lib/finance';

	interface Props {
		kind: 'loading' | 'error' | 'needs-input' | 'empty';
		title: string;
		detail: string;
		requirements?: DataRequirement[];
		onRetry?: (() => void | Promise<void>) | undefined;
		retryLabel?: string;
	}

	let {
		kind,
		title,
		detail,
		requirements = [],
		onRetry = undefined,
		retryLabel = 'Try again'
	}: Props = $props();

</script>

<section class:state--error={kind === 'error'} class:state--loading={kind === 'loading'} class="state" aria-live={kind === 'loading' ? 'polite' : 'off'}>
	<div class="state-mark" aria-hidden="true">
		{#if kind === 'loading'}
			<span></span>
		{:else if kind === 'error'}
			!
		{:else if kind === 'needs-input'}
			+
		{:else}
			—
		{/if}
	</div>
	<div class="state-copy">
		<p class="state-kicker">
			{#if kind === 'loading'}
				Preparing forecast
			{:else if kind === 'error'}
				Forecast unavailable
			{:else if kind === 'needs-input'}
				One more input
			{:else}
				Nothing to show yet
			{/if}
		</p>
		<h1>{title}</h1>
		<p>{detail}</p>
	</div>

	{#if requirements.length > 0}
		<ul class="requirements" aria-label="Required information">
			{#each requirements as requirement (requirement.code)}
				<li>
					<div>
						<strong>{requirement.label}</strong>
						<span>{requirement.section} input</span>
					</div>
					<a href={resolve(`/data?section=${requirement.section}`)}>Add in Data</a>
				</li>
			{/each}
		</ul>
	{/if}

	<div class="state-actions">
		{#if onRetry}
			<button type="button" onclick={() => void onRetry()}>{retryLabel}</button>
		{/if}
		{#if kind === 'needs-input' || kind === 'empty'}
			<a class="secondary-action" href={resolve('/data')}>Open Data</a>
		{/if}
	</div>
</section>

<style>
	.state {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 1rem;
		align-content: center;
		min-height: min(31rem, calc(100dvh - 8rem));
		padding: clamp(1.25rem, 4vw, 4rem);
		background: var(--paper);
		color: var(--ink);
	}

	.state-mark {
		display: grid;
		width: 2.75rem;
		height: 2.75rem;
		place-items: center;
		background: var(--paper-soft);
		border: 1px solid var(--control-border);
		color: var(--cobalt);
		font-family: var(--font-mono);
		font-size: 1.2rem;
		font-weight: 800;
	}

	.state--error .state-mark {
		border-color: var(--negative);
		color: var(--negative);
	}

	.state-mark span {
		width: 0.7rem;
		height: 0.7rem;
		background: var(--cobalt);
		border-radius: 50%;
		animation: pulse 900ms ease-in-out infinite alternate;
	}

	.state-copy {
		display: grid;
		gap: 0.35rem;
		max-width: 52ch;
	}

	.state-kicker,
	.requirements span {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	h1 {
		font-size: clamp(1.35rem, 2.4vw, 2rem);
		letter-spacing: -0.045em;
		line-height: 1;
		text-wrap: balance;
	}

	.state-copy > p:last-child {
		color: var(--ink-soft);
		font-size: 0.9rem;
		line-height: 1.5;
		text-wrap: pretty;
	}

	.requirements {
		grid-column: 2;
		display: grid;
		gap: 1px;
		max-width: 48rem;
		padding: 0;
		margin: 0.35rem 0 0;
		background: var(--rule);
		border: 1px solid var(--rule);
		list-style: none;
	}

	.requirements li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem;
		background: var(--paper-soft);
	}

	.requirements li > div {
		display: grid;
		gap: 0.15rem;
	}

	.requirements strong {
		font-size: 0.85rem;
	}

	.requirements a,
	.state-actions button,
	.secondary-action {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 2.75rem;
		padding: 0 0.8rem;
		border: 1px solid var(--control-border);
		background: var(--cobalt);
		color: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.67rem;
		font-weight: 700;
		letter-spacing: 0.035em;
		text-decoration: none;
		text-transform: uppercase;
		cursor: pointer;
	}

	.state-actions {
		grid-column: 2;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.25rem;
	}

	.secondary-action {
		background: var(--paper);
		color: var(--cobalt-deep);
	}

	.requirements a:hover,
	.state-actions button:hover {
		background: var(--cobalt-bright);
	}

	.secondary-action:hover {
		background: var(--paper-deep);
		border-color: var(--cobalt);
	}

	@keyframes pulse {
		to {
			transform: scale(0.72);
			opacity: 0.56;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.state-mark span {
			animation: none;
		}
	}

	@media (max-width: 42rem) {
		.state {
			grid-template-columns: 1fr;
			min-height: 0;
		}

		.requirements,
		.state-actions {
			grid-column: auto;
		}

		.requirements li {
			align-items: start;
			flex-direction: column;
		}

		.requirements a {
			width: 100%;
		}
	}
</style>
