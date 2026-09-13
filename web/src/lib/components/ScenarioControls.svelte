<script lang="ts">
	import { financialStore } from '$lib/finance.svelte';
	import ForecastComparison from '$lib/components/ForecastComparison.svelte';

	interface Props {
		showChanges?: boolean;
	}

	let { showChanges = true }: Props = $props();
	let name = $state('');
	let localError = $state('');
	let isSavingName = $state(false);
	let comparisonSelection = $state('');

	const workspace = $derived(financialStore.workspace);
	const scenarios = $derived(workspace?.inputs.scenarios ?? []);
	const previewActive = $derived(financialStore.isPreview);
	const interactionLocked = $derived(financialStore.saving || financialStore.requiresReconciliation);
	const staleLoadedScenario = $derived(
		financialStore.scenarioName
			? scenarios.find((scenario) => scenario.name === financialStore.scenarioName) ?? null
			: null
	);
	const comparisonValue = $derived.by(() => {
		if (!financialStore.comparisonName) return '';
		const retainedSelection = scenarios.find((scenario) => scenario.id === comparisonSelection);
		return retainedSelection?.name === financialStore.comparisonName
			? comparisonSelection
			: scenarios.find((scenario) => scenario.name === financialStore.comparisonName)?.id ?? '';
	});

	async function saveNamedScenario() {
		const trimmed = name.trim();
		if (!trimmed) {
			localError = 'Name this what-if before saving it.';
			return;
		}
		localError = '';
		isSavingName = true;
		try {
			if (await financialStore.saveScenario(trimmed)) name = '';
		} finally {
			isSavingName = false;
		}
	}

	async function loadNamedScenario(id: string) {
		localError = '';
		await financialStore.loadScenario(id);
	}

	async function compareNamedScenario(id: string) {
		comparisonSelection = id;
		await financialStore.compareScenario(id || null);
	}

	async function removeNamedScenario(id: string, label: string) {
		if (window.confirm(`Remove “${label}” from saved scenarios? Your financial records and current what-if will stay unchanged.`)) {
			await financialStore.deleteScenario(id);
		}
	}
</script>

<section class:scenario-controls--preview={previewActive} class="scenario-controls" aria-labelledby="scenario-controls-title">
	<div class="scenario-summary">
		<p id="scenario-controls-title" class="eyebrow">{previewActive ? 'Unsaved what-if' : 'Personal workspace'}</p>
		<strong>{previewActive ? (financialStore.scenarioName ?? 'Uncommitted preview') : 'Saved plan'}</strong>
	</div>

	<div class="scenario-actions">
		{#if previewActive}
			<button class="secondary" type="button" onclick={() => void financialStore.discardScenario()} disabled={interactionLocked}>
				Discard preview
			</button>
			<button class="primary" type="button" onclick={() => void financialStore.commitScenario()} disabled={interactionLocked || financialStore.forecastStatus !== 'ready'}>
				{financialStore.saving ? 'Committing…' : financialStore.forecast?.status === 'needs-input' ? 'Save staged records' : 'Commit preview'}
			</button>
		{/if}
		{#if scenarios.length > 0}
		<label class="comparison-select" for="scenario-comparison">
			<span>Compare with</span>
			<select
				id="scenario-comparison"
				value={comparisonValue}
				disabled={interactionLocked || financialStore.comparisonStatus === 'loading'}
				onchange={(event) => void compareNamedScenario((event.currentTarget as HTMLSelectElement).value)}
			>
				<option value="">Saved inputs</option>
				{#each scenarios as scenario (scenario.id)}
					<option value={scenario.id}>{scenario.name}</option>
				{/each}
			</select>
		</label>
			{#if financialStore.comparisonStatus === 'loading'}<span class="comparison-loading" role="status">Updating comparison…</span>{/if}
		{/if}
		<details class="scenario-library">
			<summary>Named scenarios ({scenarios.length})</summary>
			<div class="scenario-library-body">
				{#if scenarios.length > 0}
					<ul>
						{#each scenarios as scenario (scenario.id)}
							<li class:stale={workspace && scenario.base_revision !== workspace.revision}>
								<div>
									<strong>{scenario.name}</strong>
									<span>
										{#if workspace && scenario.base_revision !== workspace.revision}
											Built from an older saved plan — review before committing.
										{:else}
											Ready to preview against the current saved plan.
										{/if}
									</span>
								</div>
								<div class="scenario-row-actions">
									<button type="button" onclick={() => void loadNamedScenario(scenario.id)} disabled={interactionLocked}>Preview</button>
									<button type="button" onclick={() => void removeNamedScenario(scenario.id, scenario.name)} disabled={interactionLocked}>Remove</button>
								</div>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="library-empty">There are no named what-ifs yet.</p>
				{/if}
				<form onsubmit={(event) => { event.preventDefault(); void saveNamedScenario(); }}>
					<label for="scenario-name">Save {previewActive ? 'this what-if' : 'the current plan'}</label>
					<div>
						<input id="scenario-name" bind:value={name} maxlength="100" placeholder="e.g. Base case or delayed repair" disabled={isSavingName || interactionLocked} />
						<button type="submit" disabled={isSavingName || interactionLocked}>{isSavingName ? 'Saving…' : 'Save scenario'}</button>
					</div>
				</form>
			</div>
		</details>
	</div>
	{#if previewActive && financialStore.forecast?.status === 'needs-input'}
		<p class="stale-note">More input is needed for a cash forecast. Saving commits only the staged records, not a validated funding plan.</p>
	{/if}

	{#if previewActive && staleLoadedScenario && workspace && staleLoadedScenario.base_revision !== workspace.revision}
		<p class="stale-note" role="status">This named what-if was built from an older saved plan. Its preview uses your current data; commit only after reviewing the change list.</p>
	{/if}

	{#if showChanges && previewActive && financialStore.changes.length > 0}
		<div class="change-heading">
			<p>Changes versus saved inputs</p>
			{#if financialStore.comparisonStatus === 'loading'}<span role="status">Loading comparison…</span>{/if}
		</div>
		<ul class="change-list" aria-label="Forecast changes reported by the model">
			{#each financialStore.changes as change (`${change.label}:${change.before}:${change.after}`)}
				<li><span>{change.label}</span><strong>{change.before} → {change.after}</strong></li>
			{/each}
		</ul>
	{/if}

	{#if localError || financialStore.forecastError || financialStore.error || financialStore.comparisonError}
		<p class="scenario-error" role="alert">{localError || financialStore.forecastError || financialStore.error || financialStore.comparisonError}</p>
	{/if}

</section>
{#if financialStore.forecastStatus === 'ready' && financialStore.forecast?.result}
	<ForecastComparison
		current={financialStore.forecast.result}
		comparison={financialStore.comparisonForCurrent?.result ?? null}
		comparisonLabel={financialStore.comparisonName ?? 'Saved inputs'}
		deterministic={financialStore.forecast.model_mode === 'scheduled'}
		currentLabel={previewActive ? (financialStore.scenarioName ?? 'Current what-if') : 'Saved plan'}
	/>
{/if}

<style>
	.scenario-controls {
		display: grid;
		grid-template-columns: minmax(13rem, 1fr) auto;
		gap: 0.5rem 1rem;
		align-items: center;
		padding: 0.55rem 1rem;
		background: var(--paper-soft);
		border-bottom: 1px solid var(--rule);
		color: var(--ink);
	}

	.scenario-controls--preview {
		box-shadow: inset 3px 0 var(--cobalt);
	}

	.scenario-summary {
		display: grid;
		gap: 0.15rem;
		min-width: 0;
	}

	.eyebrow,
	.scenario-library summary,
	.scenario-library label,
	.comparison-select > span,
	.comparison-loading,
	.change-list span,
	.change-heading p,
	.change-heading span {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.64rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.scenario-summary strong {
		font-size: 0.98rem;
		letter-spacing: -0.025em;
	}

	.scenario-library li span,
	.library-empty,
	.stale-note {
		color: var(--ink-soft);
		font-size: 0.72rem;
		line-height: 1.4;
	}

	.scenario-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: end;
		gap: 0.45rem;
	}

	.comparison-select {
		display: grid;
		grid-template-columns: auto minmax(8rem, 1fr);
		align-items: center;
		gap: 0.45rem;
		min-height: 2.75rem;
		padding: 0 0.55rem;
		background: var(--paper);
		border: 1px solid var(--control-border);
	}

	.comparison-select select {
		min-width: 0;
		min-height: 2.75rem;
		background: transparent;
		border: 0;
		color: var(--cobalt-deep);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
	}

	.comparison-loading {
		align-self: center;
		color: var(--ink-soft);
		font-size: 0.66rem;
	}

	.comparison-select:focus-within {
		border-color: var(--cobalt);
		box-shadow: 0 0 0 1px var(--cobalt);
	}

	button,
	.scenario-library summary {
		min-height: 2.75rem;
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.035em;
		text-transform: uppercase;
	}

	button {
		padding: 0 0.75rem;
		border: 1px solid var(--control-border);
		cursor: pointer;
	}

	button.primary,
	.scenario-library form button {
		background: var(--cobalt);
		border-color: var(--cobalt);
		color: var(--paper);
	}

	button.secondary,
	.scenario-library li button {
		background: var(--paper);
		color: var(--cobalt-deep);
	}

	button:hover:not(:disabled) {
		border-color: var(--cobalt);
		background: var(--cobalt-bright);
		color: var(--paper);
	}

	button:disabled {
		cursor: wait;
		opacity: 0.56;
	}

	.scenario-library {
		position: relative;
	}

	.scenario-library summary {
		display: inline-flex;
		align-items: center;
		padding: 0 0.75rem;
		border: 1px solid var(--control-border);
		background: var(--paper);
		color: var(--cobalt-deep);
		cursor: pointer;
		list-style: none;
	}

	.scenario-library summary::-webkit-details-marker {
		display: none;
	}

	.scenario-library[open] summary {
		border-color: var(--cobalt);
		background: var(--paper-deep);
	}

	.scenario-library-body {
		position: absolute;
		z-index: 4;
		right: 0;
		top: calc(100% + 0.35rem);
		display: grid;
		gap: 0.7rem;
		width: min(26rem, calc(100vw - 2rem));
		max-height: min(32rem, 70dvh);
		overflow-y: auto;
		padding: 0.8rem;
		background: var(--paper);
		border: 1px solid var(--control-border);
		box-shadow: 0 0 0 1px rgb(7 12 86 / 5%), 0 8px 18px rgb(7 12 86 / 12%);
	}

	.scenario-library ul {
		display: grid;
		gap: 1px;
		padding: 0;
		margin: 0;
		background: var(--rule);
		list-style: none;
	}

	.scenario-library li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.65rem;
		background: var(--paper-soft);
	}

	.scenario-library li.stale {
		box-shadow: inset 2px 0 var(--warning);
	}

	.scenario-library li > div {
		display: grid;
		gap: 0.15rem;
		min-width: 0;
	}

	.scenario-library li strong {
		font-size: 0.8rem;
		overflow-wrap: anywhere;
	}

	.scenario-library li button {
		flex: none;
		min-height: 2.75rem;
	}

	.scenario-library form {
		display: grid;
		gap: 0.35rem;
	}

	.scenario-library form > div {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 0.4rem;
	}

	.scenario-library input {
		min-width: 0;
		min-height: 2.75rem;
		padding: 0 0.65rem;
		background: var(--paper);
		border: 1px solid var(--control-border);
		color: var(--ink);
	}

	.scenario-library input:focus {
		border-color: var(--cobalt);
		box-shadow: 0 0 0 1px var(--cobalt);
	}

	.change-list {
		grid-column: 1 / -1;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
		gap: 1px;
		padding: 0;
		margin: 0;
		background: var(--rule);
		border: 1px solid var(--rule);
		list-style: none;
	}

	.change-list li {
		display: grid;
		gap: 0.2rem;
		padding: 0.55rem 0.65rem;
		background: var(--paper);
	}

	.change-list strong {
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
	}

	.stale-note,
	.scenario-error {
		grid-column: 1 / -1;
		margin: 0;
	}

	.stale-note {
		padding: 0.55rem 0.65rem;
		background: var(--paper-deep);
		border-left: 2px solid var(--warning);
	}

	.scenario-error {
		padding: 0.55rem 0.65rem;
		background: var(--negative-soft);
		border-left: 2px solid var(--negative);
		color: var(--negative);
		font-size: 0.75rem;
	}

	.scenario-library .scenario-row-actions { display: flex; flex: none; flex-wrap: wrap; gap: 0.4rem; }

	@media (max-width: 48rem) {
		.scenario-controls {
			grid-template-columns: 1fr;
			padding: 0.8rem;
		}

		.scenario-actions {
			justify-content: start;
		}
	}

	@media (max-width: 32rem) {
		.scenario-actions {
			display: grid;
			grid-template-columns: 1fr 1fr;
		}

		.comparison-select {
			grid-column: 1 / -1;
			grid-template-columns: auto minmax(0, 1fr);
		}

		.scenario-library {
			grid-column: 1 / -1;
		}

		.scenario-library summary {
			width: 100%;
			justify-content: center;
		}

		.scenario-library-body {
			position: static;
			width: 100%;
			max-height: none;
			margin-top: 0.35rem;
			overflow-y: visible;
			box-shadow: none;
		}
	}
</style>
