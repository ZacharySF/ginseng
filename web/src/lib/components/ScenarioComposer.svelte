<script lang="ts">
	import {
		HORIZON_OPTIONS,
		scenarioStore,
		type ObligationDraft
	} from '$lib/scenario.svelte';
	import { formatCurrency } from '$lib/format';
	import type { Obligation } from '$lib/types';

	let activeId = $state<string | null>(null);
	let label = $state('');
	let amountText = $state('');
	let dueDay = $state(7);
	let formError = $state('');

	const eventCount = $derived(scenarioStore.request.obligations.length);
	const sortedObligations = $derived(
		[...scenarioStore.request.obligations].sort(
			(left, right) => left.due_in_days - right.due_in_days || left.label.localeCompare(right.label)
		)
	);

	function clearForm() {
		activeId = null;
		label = '';
		amountText = '';
		dueDay = Math.min(7, scenarioStore.request.horizon_days);
		formError = '';
	}

	function editObligation(obligation: Obligation) {
		activeId = obligation.id;
		label = obligation.label;
		amountText = String(obligation.amount);
		dueDay = obligation.due_in_days;
		formError = '';
	}

	function saveObligation(event: SubmitEvent) {
		event.preventDefault();
		const amount = Number(amountText);
		const draft: ObligationDraft = {
			label,
			amount,
			due_in_days: Number(dueDay)
		};

		if (!label.trim() || label.trim().length > 100) {
			formError = 'Name the expected obligation.';
			return;
		}
		if (!Number.isFinite(amount) || amount <= 0 || amount > 1_000_000) {
			formError = 'Enter an amount greater than zero and no more than $1,000,000.';
			return;
		}
		if (!Number.isInteger(draft.due_in_days) || draft.due_in_days < 1 || draft.due_in_days > 365) {
			formError = 'Choose a whole day from 1 to 365.';
			return;
		}

		if (activeId) {
			scenarioStore.updateObligation(activeId, draft);
		} else {
			scenarioStore.addObligation(draft);
		}
		clearForm();
	}

	function changeHorizon(event: Event) {
		const value = Number((event.currentTarget as HTMLSelectElement).value);
		scenarioStore.setHorizonDays(value);
	}
</script>

<section class="composer" aria-labelledby="composer-title">
	<header class="composer-header">
		<div>
			<p class="panel-kicker">Live scenario</p>
			<h2 id="composer-title">Put real timing into the forecast.</h2>
		</div>
		<p class="event-count"><strong>{eventCount}</strong> {eventCount === 1 ? 'event' : 'events'} active</p>
	</header>

	<div class="scenario-settings">
		<label class="horizon-control" for="forecast-horizon">
			<span class="data-label">Forecast window</span>
			<select id="forecast-horizon" value={scenarioStore.request.horizon_days} onchange={changeHorizon}>
				{#each HORIZON_OPTIONS as option (option)}
					<option value={option}>{option} days</option>
				{/each}
			</select>
		</label>
		<p>Added obligations are one-off future costs. Every saved change re-runs the local model.</p>
	</div>

	<div class="composer-grid">
		<form class="event-form" onsubmit={saveObligation}>
			<div class="form-heading">
				<p class="data-label">{activeId ? 'Edit event' : 'Add an event'}</p>
				{#if activeId}
					<button class="text-button" type="button" onclick={clearForm}>Cancel edit</button>
				{/if}
			</div>

			<label>
				<span>What is due?</span>
				<input bind:value={label} maxlength="80" placeholder="e.g. insurance renewal" />
			</label>
			<div class="split-inputs">
				<label>
					<span>Amount</span>
					<div class="money-input"><span aria-hidden="true">$</span><input bind:value={amountText} inputmode="decimal" type="number" min="0.01" step="0.01" placeholder="0.00" /></div>
				</label>
				<label>
					<span>Due on day</span>
					<input bind:value={dueDay} type="number" min="1" max="365" step="1" />
				</label>
			</div>
			{#if formError}
				<p class="form-error" role="alert">{formError}</p>
			{/if}
			<button class="button-primary" type="submit" disabled={scenarioStore.loadState === 'loading'}>
				{activeId ? 'Save event' : 'Run with this event'} <span aria-hidden="true">↗</span>
			</button>
		</form>

		<div class="event-list-wrap">
			<div class="event-list-heading">
				<p class="data-label">Scheduled events</p>
				{#if eventCount > 0}
					<button class="text-button" type="button" onclick={() => scenarioStore.clearObligations()}>Clear all</button>
				{/if}
			</div>

			{#if sortedObligations.length > 0}
				<ul class="event-list">
					{#each sortedObligations as obligation (obligation.id)}
						<li>
							<div class="event-row-top">
								<span class="event-day">D{String(obligation.due_in_days).padStart(2, '0')}{obligation.due_in_days > scenarioStore.request.horizon_days ? ' · outside chart window' : ''}</span>
								<strong class="event-label">{obligation.label}</strong>
							</div>
							<div class="event-row-bottom">
								<span class="event-amount numeric">{formatCurrency(obligation.amount)}</span>
								<div class="event-actions">
									<button class="icon-button" type="button" onclick={() => editObligation(obligation)} aria-label={`Edit ${obligation.label}`}>Edit</button>
									<button class="icon-button icon-button--danger" type="button" onclick={() => scenarioStore.removeObligation(obligation.id)} aria-label={`Remove ${obligation.label}`}>Remove</button>
								</div>
							</div>
						</li>
					{/each}
				</ul>
			{:else}
				<div class="empty-events">
					<p>No future obligations yet.</p>
					<span>Start from your own event, or use the repair case below.</span>
				</div>
			{/if}
		</div>
	</div>

	<footer class="composer-footer">
		<div>
			<p class="data-label">Quick start</p>
			<p>Load the staged repair case: $1,500 on day 3, then $3,000 on day 17.</p>
		</div>
		<button class="button-secondary" type="button" onclick={() => scenarioStore.applyShock()} disabled={scenarioStore.hasShock || scenarioStore.loadState === 'loading'}>
			{scenarioStore.hasShock ? 'Repair case loaded' : 'Load repair case'}
		</button>
	</footer>
</section>

<style>
	.composer {
		display: grid;
		gap: 0.85rem;
		color: #e3e3e6;
	}

	.composer-header,
	.scenario-settings,
	.composer-footer,
	.event-list-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 0.65rem;
	}

	.composer-header {
		align-items: start;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid #29292d;
	}

	.composer-header h2 {
		margin: 0.25rem 0 0;
		color: #e5e5e7;
		font-size: 0.95rem;
		letter-spacing: -0.02em;
		line-height: 1.15;
	}

	.panel-kicker,
	.data-label,
	.form-heading p,
	.event-list-heading p {
		color: #898990;
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.event-count {
		padding: 0.3rem 0.4rem;
		border: 1px solid #343438;
		color: #9e9ea3;
		font-family: var(--font-mono);
		font-size: 0.62rem;
		text-transform: uppercase;
		white-space: nowrap;
	}

	.event-count strong {
		color: #42d3ba;
		font-size: 0.72rem;
	}

	.scenario-settings {
		align-items: center;
		padding: 0.7rem;
		border: 1px solid #29292d;
		background: #101011;
	}

	.scenario-settings > p {
		max-width: 43ch;
		color: #939399;
		font-size: 0.7rem;
		line-height: 1.4;
	}

	.horizon-control {
		display: grid;
		gap: 0.4rem;
	}

	select,
	input {
		min-height: 2.5rem;
		background: #070708;
		border: 1px solid #45454b;
		border-radius: 0;
		color: #e8e8ea;
	}

	select {
		min-width: 8rem;
		padding: 0 0.65rem;
	}

	select:focus,
	input:focus {
		border-color: #42d3ba;
		box-shadow: 0 0 0 1px #42d3ba;
	}

	.composer-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1px;
		border: 1px solid #29292d;
		background: #29292d;
	}

	.event-form,
	.event-list-wrap {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		align-content: start;
		gap: 0.85rem;
		min-width: 0;
		padding: 0.85rem;
		background: #0d0d0e;
	}

	.form-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.event-form label {
		display: grid;
		gap: 0.35rem;
		color: #a7a7ad;
		font-size: 0.7rem;
	}

	.event-form input {
		width: 100%;
		padding: 0 0.7rem;
	}

	.split-inputs {
		display: grid;
		grid-template-columns: 1.35fr 0.65fr;
		gap: 0.6rem;
	}

	.money-input {
		display: flex;
		align-items: center;
		padding-left: 0.7rem;
		background: #070708;
		border: 1px solid #45454b;
		border-radius: 0;
		color: #8f8f95;
	}

	.money-input:focus-within {
		border-color: #42d3ba;
		box-shadow: 0 0 0 1px #42d3ba;
	}

	.money-input input {
		border: 0;
		outline: 0;
		box-shadow: none;
		background: transparent;
	}

	.event-form input:focus-visible,
	select:focus-visible,
	.icon-button:focus-visible,
	.text-button:focus-visible {
		outline-offset: 1px;
	}

	.form-error {
		color: #ff7186;
		font-size: 0.72rem;
	}

	.event-form .button-primary {
		justify-self: start;
		gap: 0.5rem;
	}

	.event-list-wrap {
		gap: 0.6rem;
	}

	.event-list {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1px;
		padding: 0;
		margin: 0;
		background: #29292d;
		border: 1px solid #29292d;
		list-style: none;
	}

	.event-list li {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0.35rem;
		padding: 0.6rem;
		background: #101011;
	}

	.event-row-top {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
	}

	.event-day {
		flex: none;
		padding: 0.15rem 0.35rem;
		background: #133f3b;
		color: #bafff4;
		font-family: var(--font-mono);
		font-size: 0.64rem;
		font-weight: 700;
	}

	.event-label {
		overflow: hidden;
		min-width: 0;
		color: #e7e7e9;
		font-size: 0.76rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.event-row-bottom {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.5rem;
	}

	.event-amount {
		flex: none;
		margin-right: auto;
		color: #d8a84e;
		font-size: 0.72rem;
		font-weight: 700;
	}

	.event-actions {
		display: flex;
		flex: none;
		gap: 0.25rem;
	}


	.icon-button,
	.text-button {
		min-height: 1.9rem;
		padding: 0.3rem 0.45rem;
		background: transparent;
		border: 0;
		border-radius: 0;
		color: #8f8f95;
		font-family: var(--font-mono);
		font-size: 0.64rem;
		font-weight: 700;
		letter-spacing: 0.02em;
		cursor: pointer;
	}

	.icon-button:hover,
	.text-button:hover {
		background: #1c1c1f;
		color: #e8e8ea;
	}

	.text-button {
		color: #42d3ba;
	}

	.icon-button--danger:hover {
		color: #ff8194;
	}

	.empty-events {
		display: grid;
		gap: 0.3rem;
		min-height: 9rem;
		place-content: center start;
		padding: 0.85rem;
		background: #101011;
		border: 1px dashed #343438;
		color: #a1a1a7;
	}

	.empty-events span {
		color: #84848a;
		font-size: 0.7rem;
	}

	.button-primary,
	.button-secondary {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 2.4rem;
		padding: 0.55rem 0.8rem;
		border-radius: 0;
		font-family: var(--font-mono);
		font-size: 0.67rem;
		font-weight: 700;
		letter-spacing: 0.02em;
		line-height: 1;
		text-decoration: none;
		cursor: pointer;
		transition: background-color 160ms ease, border-color 160ms ease;
	}

	.button-primary {
		background: #1a5650;
		border: 1px solid #42d3ba;
		color: #d4fff8;
	}

	.button-primary:hover:not(:disabled) {
		background: #226b64;
	}

	.button-secondary {
		background: #151517;
		border: 1px solid #45454b;
		color: #c8c8cc;
	}

	.button-secondary:hover:not(:disabled) {
		background: #1c1c1f;
		border-color: #55555c;
	}

	.button-primary:disabled,
	.button-secondary:disabled {
		cursor: not-allowed;
		opacity: 0.45;
	}

	.composer-footer {
		align-items: center;
		padding: 0.75rem;
		border: 1px solid #29292d;
		background: #101011;
	}

	.composer-footer > div {
		display: grid;
		gap: 0.25rem;
	}

	.composer-footer > div > p:last-child {
		color: #95959a;
		font-size: 0.7rem;
		line-height: 1.4;
	}

	.event-form {
		border-bottom: 1px solid #29292d;
	}

	@media (max-width: 42rem) {
		.composer-header,
		.scenario-settings,
		.composer-footer {
			display: grid;
			align-items: start;
			gap: 0.5rem;
		}
	}
	/* Cobalt ledger skin */
	.composer { color: var(--ink); }
	.composer-header, .event-form { border-color: var(--rule); }
	.composer-header h2, .event-label { color: var(--ink); }
	.panel-kicker, .data-label, .form-heading p, .event-list-heading p { color: var(--ink-muted); }
	.event-count { border-color: var(--rule-strong); color: var(--ink-soft); }
	.event-count strong, .text-button { color: var(--cobalt); }
	.scenario-settings, .composer-footer { background: var(--paper-soft); border-color: var(--rule); }
	.scenario-settings > p, .composer-footer > div > p:last-child, .empty-events, .empty-events span { color: var(--ink-muted); }
	select, input, .money-input { background: var(--paper); border-color: var(--rule-strong); color: var(--ink); }
	select:focus, input:focus, .money-input:focus-within { border-color: var(--cobalt); box-shadow: 0 0 0 1px var(--cobalt); }
	.event-form label { color: var(--ink-soft); }
	.composer-grid, .event-list { background: var(--rule); border-color: var(--rule); }
	.event-form, .event-list-wrap, .event-list li { background: var(--paper); }
	.event-day { background: var(--cobalt); color: var(--paper); }
	.event-amount { color: var(--warning); }
	.icon-button, .text-button { color: var(--cobalt-deep); }
	.icon-button:hover, .text-button:hover { background: var(--paper-deep); color: var(--cobalt); }
	.icon-button--danger:hover, .form-error { color: var(--negative); }
	.empty-events { background: var(--paper-soft); border-color: var(--rule-strong); }
	.button-primary { background: var(--cobalt); border-color: var(--cobalt); color: var(--paper); }
	.button-primary:hover:not(:disabled) { background: var(--cobalt-bright); }
	.button-secondary { background: var(--paper); border-color: var(--rule-strong); color: var(--ink); }
	.button-secondary:hover:not(:disabled) { background: var(--paper-deep); border-color: var(--cobalt); }
</style>
