<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore, COVERAGE_TARGET_OPTIONS } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import HeroCard from '$lib/components/HeroCard.svelte';
	import CoverageCurve from '$lib/components/CoverageCurve.svelte';
	import type { SensitivityRow } from '$lib/types';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});

	function commitBuffer(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const value = Number(input.value);
		if (Number.isFinite(value) && value >= 0) {
			scenarioStore.setOperatingBuffer(value);
		} else {
			input.value = String(scenarioStore.request.operating_buffer);
		}
	}

	function commitBufferOnEnter(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			(event.currentTarget as HTMLInputElement).blur();
		}
	}
</script>

<svelte:head>
	<title>Ginseng — Liquidity</title>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="liquidity-screen">
		<header class="screen-header">
			<h1 class="screen-title">Liquidity</h1>
			<p class="screen-subtitle">Policy assumptions, the required reserve, and its uncertainty.</p>
		</header>

		<section class="policy-controls" aria-label="Policy controls">
			<div class="control">
				<label for="operating-buffer" class="control-label">Operating buffer</label>
				<input
					id="operating-buffer"
					type="number"
					class="buffer-input"
					min="0"
					step="100"
					value={scenarioStore.request.operating_buffer}
					onchange={commitBuffer}
					onkeydown={commitBufferOnEnter}
				/>
			</div>

			<div class="control">
				<span id="coverage-target-label" class="control-label">Coverage target</span>
				<div class="segmented" role="group" aria-labelledby="coverage-target-label">
					{#each COVERAGE_TARGET_OPTIONS as option (option)}
						<button
							type="button"
							class="segment"
							class:segment--active={scenarioStore.request.coverage_target === option}
							aria-pressed={scenarioStore.request.coverage_target === option}
							onclick={() => scenarioStore.setCoverageTarget(option)}
						>
							{formatPercent(option)}
						</button>
					{/each}
				</div>
			</div>

			{#if scenarioStore.loadState === 'loading'}
				<span class="updating" role="status" aria-live="polite">Updating…</span>
			{/if}
		</section>

		<HeroCard
			eyebrow="Required reserve"
			value={formatCurrency(s.required_liquidity_reserve)}
			supporting={`to stay above your ${formatCurrency(s.operating_buffer)} operating buffer in ${formatPercent(s.coverage_target)} of modeled paths`}
			estimateRangeLabel={s.estimate_band ? 'Estimate range' : undefined}
			estimateRangeValue={s.estimate_band
				? `${formatCurrency(s.estimate_band.low)} – ${formatCurrency(s.estimate_band.high)}`
				: undefined}
		/>

		<section class="chart-card" aria-label="Funding coverage curve">
			<h2>Funding coverage curve</h2>
			<CoverageCurve
				points={s.coverage_curve}
				currentFunding={s.immediate_funding}
				coverageTarget={s.coverage_target}
				requiredReserve={s.required_liquidity_reserve}
				estimateBand={s.estimate_band}
			/>
		</section>

		{#if s.sensitivity.length > 0}
			<section class="chart-card" aria-label="Persistence sensitivity">
				<h2>Persistence sensitivity</h2>
				<p class="sensitivity-intro">
					Required reserve at {formatPercent(s.coverage_target)} under different income-persistence
					assumptions (mean block length, days).
				</p>
				<table class="sensitivity-table">
					<caption class="sr-only">Required reserve by block-length assumption</caption>
					<thead>
						<tr>
							<th scope="col">Block assumption</th>
							<th scope="col">Required reserve</th>
						</tr>
					</thead>
					<tbody>
						{#each s.sensitivity as row (row.block_label)}
							<tr class:estimated={row.is_estimated}>
								<th scope="row">
									{row.block_label}{#if row.is_estimated} (data-estimated){/if}
								</th>
								<td>{formatCurrency(row.required_liquidity_reserve)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				{#if s.sensitivity_verdict}
					<p class="sensitivity-verdict">{s.sensitivity_verdict}</p>
				{/if}
			</section>
		{/if}
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="engine-down" role="alert">
		<p class="engine-down-title">Engine unavailable</p>
		<p class="engine-down-detail">{scenarioStore.errorMessage}</p>
		<button type="button" class="retry-button" onclick={() => scenarioStore.refresh()}>Retry</button>
	</div>
{:else}
	<p class="status-text" role="status" aria-live="polite">Loading your liquidity picture…</p>
{/if}

<style>
	.liquidity-screen {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.screen-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.screen-title {
		font-size: var(--font-size-xl);
		font-weight: 700;
	}

	.screen-subtitle {
		color: var(--color-text-dim);
		font-size: var(--font-size-md);
		max-width: 56ch;
	}

	.policy-controls {
		display: flex;
		align-items: flex-end;
		gap: var(--space-6);
		flex-wrap: wrap;
		padding: var(--space-5) var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	.control {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.control-label {
		font-size: var(--font-size-xs);
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}

	.buffer-input {
		width: 10ch;
		padding: var(--space-2) var(--space-3);
		background: var(--color-bg-raised);
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-sm);
		color: var(--color-text);
		font-size: var(--font-size-md);
		font-variant-numeric: tabular-nums;
	}

	.buffer-input:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
	}

	.segmented {
		display: flex;
		gap: var(--space-1);
	}

	.segment {
		padding: var(--space-2) var(--space-4);
		background: var(--color-bg-raised);
		border: 1px solid var(--color-border-strong);
		color: var(--color-text-dim);
		font-size: var(--font-size-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.segment:first-child {
		border-radius: var(--radius-sm) 0 0 var(--radius-sm);
	}

	.segment:last-child {
		border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
	}

	.segment:not(:first-child) {
		border-left: none;
	}

	.segment--active {
		background: var(--color-accent);
		border-color: var(--color-accent);
		color: var(--color-bg);
	}

	.segment:hover:not(.segment--active) {
		background: var(--color-bg-card-hover);
	}

	.segment:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
		position: relative;
		z-index: 1;
	}

	.updating {
		font-size: var(--font-size-sm);
		color: var(--color-text-faint);
	}

	.chart-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.status-text {
		color: var(--color-text-dim);
		font-size: var(--font-size-lg);
	}

	.engine-down {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-3);
		max-width: 40ch;
		padding: var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-danger);
		border-radius: var(--radius-md);
	}

	.engine-down-title {
		font-size: var(--font-size-lg);
		font-weight: 700;
		color: var(--color-danger);
	}

	.engine-down-detail {
		font-size: var(--font-size-sm);
		color: var(--color-text-dim);
	}

	.retry-button {
		padding: var(--space-2) var(--space-5);
		background: transparent;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-sm);
		color: var(--color-text);
		font-size: var(--font-size-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.retry-button:hover {
		background: var(--color-bg-card-hover);
	}

	.retry-button:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
	}

	.sensitivity-intro {
		margin: 0 0 0.75rem;
		color: var(--color-text-dim);
		font-size: var(--font-size-sm);
	}

	.sensitivity-table {
		width: 100%;
		border-collapse: collapse;
	}

	.sensitivity-table th,
	.sensitivity-table td {
		text-align: left;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid var(--color-border);
	}

	.sensitivity-table tr.estimated {
		font-weight: 600;
	}

	.sensitivity-verdict {
		margin: 0.75rem 0 0;
		color: var(--color-text-dim);
		font-style: italic;
	}
</style>
