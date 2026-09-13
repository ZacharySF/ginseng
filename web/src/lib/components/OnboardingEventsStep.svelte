<script lang="ts">
	import CurrencyInput from '$lib/components/CurrencyInput.svelte';
	import type { CashBill, EventRecurrence, EventRule } from '$lib/finance';
	import { ruleForEvent } from '$lib/onboarding-finance';

	interface Props {
		kind: 'income' | 'bill';
		events: CashBill[];
		rules: EventRule[];
		asOf: string;
		disabled?: boolean;
	}

	let { kind, events = $bindable(), rules = $bindable(), asOf, disabled = false }: Props = $props();
	const singular = $derived(kind === 'income' ? 'income source' : 'bill');
	const title = $derived(kind === 'income' ? 'What income do you expect?' : 'What bills are coming up?');

	function addEvent(): void {
		if (disabled || events.length >= 200) return;
		const id = crypto.randomUUID();
		events = [...events, { id, label: '', amount_cents: Number.NaN, due_date: asOf }];
		rules = [...rules, { event_id: id, recurrence: 'none', end_date: null, settlements: [] }];
	}

	function removeEvent(id: string): void {
		const rule = ruleForEvent(rules, id);
		if (disabled || rule?.settlements.length) return;
		events = events.filter((event) => event.id !== id);
		rules = rules.filter((candidate) => candidate.event_id !== id);
	}

	function setRecurrence(id: string, recurrence: EventRecurrence): void {
		const current = ruleForEvent(rules, id);
		if (disabled || current?.settlements.length) return;
		const next: EventRule = {
			event_id: id,
			recurrence,
			end_date: recurrence === 'none' ? null : current?.end_date ?? null,
			settlements: current?.settlements ?? []
		};
		rules = [...rules.filter((rule) => rule.event_id !== id), next];
	}
</script>

<div class="step-heading">
	<p class="eyebrow">Known schedule</p>
	<h1>{title}</h1>
	<p>{kind === 'income' ? 'Add paychecks or other deposits you know are scheduled. Leave this empty if your income is not predictable yet.' : 'Add rent, utilities, subscriptions, or other payments with known dates. You can skip this step if none are scheduled.'}</p>
</div>

{#if events.length === 0}
	<div class="empty-state">
		<strong>No {kind === 'income' ? 'income' : 'bills'} added</strong>
		<span>This step is optional. Ginseng will not invent an amount or schedule.</span>
	</div>
{:else}
	<div class="event-list">
		{#each events as item, index (item.id)}
			{@const rule = ruleForEvent(rules, item.id)}
			{@const locked = Boolean(rule?.settlements.length)}
			<section class="event-row" aria-label={`${singular} ${index + 1}`}>
				<div class="row-heading">
					<div><strong>{kind === 'income' ? 'Income' : 'Bill'} {index + 1}</strong>{#if locked}<span>Schedule managed in Events</span>{/if}</div>
					<button type="button" class="remove-button" disabled={disabled || locked} onclick={() => removeEvent(item.id)}>Remove</button>
				</div>
				<label><span>{kind === 'income' ? 'Income label' : 'Bill name'}</span><input bind:value={item.label} maxlength="100" placeholder={kind === 'income' ? 'e.g. Paycheck' : 'e.g. Rent'} {disabled} required /></label>
				<div class="field-grid">
					<label><span>Amount</span><span class="money-input"><span aria-hidden="true">$</span><CurrencyInput bind:value={item.amount_cents} inputmode="decimal" {disabled} required /></span></label>
					<label><span>First date</span><input bind:value={item.due_date} type="date" min={asOf} max="2100-12-31" disabled={disabled || locked} required /></label>
					<label><span>Repeats</span><select value={rule?.recurrence ?? 'none'} disabled={disabled || locked} onchange={(event) => setRecurrence(item.id, event.currentTarget.value as EventRecurrence)}><option value="none">One time</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option><option value="yearly">Yearly</option></select></label>
				</div>
			</section>
		{/each}
	</div>
{/if}

<button type="button" class="add-button" disabled={disabled || events.length >= 200} onclick={addEvent}>Add {singular}</button>
<p class="helper">You can add end dates and mark individual occurrences paid, received, or skipped later on Events.</p>

<style>
	.step-heading { display:grid; gap:.38rem; }
	.step-heading p { margin:0; color:var(--ink-soft); font-size:.88rem; line-height:1.5; }
	.eyebrow { font-family:var(--font-mono); font-size:.63rem !important; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }
	h1 { margin:0; color:var(--ink); font-size:clamp(1.55rem,3vw,2.05rem); letter-spacing:-.025em; line-height:1.08; text-wrap:balance; }
	.empty-state { display:grid; gap:.2rem; padding:1rem; background:var(--paper-soft); border-left:3px solid var(--rule-strong); }
	.empty-state strong { color:var(--ink); font-size:.84rem; }
	.empty-state span,.helper { color:var(--ink-soft); font-size:.75rem; line-height:1.45; }
	.event-list { display:grid; gap:.7rem; }
	.event-row { display:grid; gap:.7rem; padding:.9rem; background:var(--paper-soft); border:1px solid var(--rule); }
	.row-heading { display:flex; align-items:center; justify-content:space-between; gap:.7rem; }
	.row-heading > div { display:grid; gap:.1rem; }
	.row-heading strong { color:var(--ink); font-size:.82rem; }
	.row-heading span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.58rem; letter-spacing:.04em; text-transform:uppercase; }
	label { display:grid; gap:.32rem; color:var(--ink-soft); font-size:.73rem; font-weight:650; }
	.field-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.7rem; }
	input,select { width:100%; min-height:2.75rem; padding:0 .65rem; background:var(--paper); border:1px solid var(--control-border); color:var(--ink); }
	input:focus,select:focus { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); outline:0; }
	.money-input { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; background:var(--paper); border:1px solid var(--control-border); }
	.money-input:focus-within { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); }
	.money-input > span { padding-left:.65rem; color:var(--ink-soft); }
	.money-input :global(input) { border:0; box-shadow:none; }
	.add-button,.remove-button { min-height:2.75rem; background:var(--paper); border:1px solid var(--control-border); color:var(--cobalt); font-family:var(--font-mono); font-size:.66rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; cursor:pointer; }
	.add-button { width:100%; }
	.remove-button { min-height:2.4rem; padding:0 .55rem; }
	button:disabled { cursor:not-allowed; opacity:.5; }
	.helper { margin:-.35rem 0 0; }
	@media(max-width:38rem){.field-grid{grid-template-columns:1fr 1fr}.field-grid label:first-child{grid-column:1 / -1}}
	@media(max-width:28rem){.field-grid{grid-template-columns:1fr}.field-grid label:first-child{grid-column:auto}}
</style>
