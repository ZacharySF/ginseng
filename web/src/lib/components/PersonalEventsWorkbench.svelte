<script lang="ts">
	import { resolve } from '$app/paths';
	import { financialStore } from '$lib/finance.svelte';
	import { formatCurrency } from '$lib/format';
	import { parseUsdCents } from '$lib/workspace';
	import {
		effectiveSchedule,
		hasUnresolvedHistoricalBill,
		humanDate,
		isScheduledOccurrence,
		mergeScheduleOverrides,
		ruleForEvent,
		scheduleEvents,
		type EffectiveSchedule,
		type ForecastEvent
	} from '$lib/forecast-presentation';
	import type { CashBill, EventRule, EventSettlement } from '$lib/finance';

	type EventKind = 'income' | 'outflow';
	type SettlementStatus = EventSettlement['status'];

	let editingId = $state<string | null>(null);
	let kind = $state<EventKind>('outflow');
	let label = $state('');
	let amountText = $state('');
	let dueDate = $state('');
	let recurrence = $state<EventRule['recurrence']>('none');
	let endDate = $state('');
	let eventError = $state('');
	let settlementDueDate = $state('');
	let settlementStatus = $state<SettlementStatus>('settled');
	let settledOn = $state('');
	let settlementError = $state('');

	const workspace = $derived(financialStore.workspace);
	const schedule = $derived(
		workspace ? effectiveSchedule(workspace, financialStore.scenario) : null
	);
	const events = $derived(schedule ? scheduleEvents(schedule) : []);
	const currentRule = $derived(editingId && schedule ? ruleForEvent(schedule.rules, editingId) : undefined);
	const historicalBillNeedsCorrection = $derived(schedule ? hasUnresolvedHistoricalBill(schedule, workspace?.as_of ?? null) : false);
	const previewBusy = $derived(financialStore.forecastStatus === 'loading' || financialStore.saving);

	function isCalendarDate(value: string): boolean {
		if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
		const date = new Date(`${value}T00:00:00Z`);
		return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
	}

	function clearEventForm() {
		editingId = null;
		kind = 'outflow';
		label = '';
		amountText = '';
		dueDate = workspace?.as_of ?? '';
		recurrence = 'none';
		endDate = '';
		eventError = '';
		settlementDueDate = '';
		settlementStatus = 'settled';
		settledOn = '';
		settlementError = '';
	}

	function editEvent(event: ForecastEvent) {
		if (!schedule) return;
		const rule = ruleForEvent(schedule.rules, event.id);
		editingId = event.id;
		kind = event.kind;
		label = event.label;
		amountText = String(event.amount_cents / 100);
		dueDate = event.due_date;
		recurrence = rule?.recurrence ?? 'none';
		endDate = rule?.end_date ?? '';
		eventError = '';
		settlementDueDate = '';
		settlementStatus = 'settled';
		settledOn = '';
		settlementError = '';
	}

	async function applySchedule(nextSchedule: EffectiveSchedule) {
		await financialStore.previewScenario(
			mergeScheduleOverrides(financialStore.scenario, nextSchedule)
		);
	}

	async function saveEvent(event: SubmitEvent) {
		event.preventDefault();
		if (!schedule || !workspace) return;
		const amountCents = parseUsdCents(amountText, false);
		const trimmedLabel = label.trim();
		if (!trimmedLabel) {
			eventError = 'Name the income or bill.';
			return;
		}
		if (amountCents === null || amountCents < 1) {
			eventError = 'Enter an amount greater than zero with at most two decimals.';
			return;
		}
		if (!isCalendarDate(dueDate)) {
			eventError = 'Choose a valid calendar due date.';
			return;
		}
		if (recurrence !== 'none' && endDate && !isCalendarDate(endDate)) {
			eventError = 'Choose a valid recurrence end date.';
			return;
		}
		if (recurrence !== 'none' && endDate && endDate < dueDate) {
			eventError = 'A recurrence end date cannot be before its first due date.';
			return;
		}

		eventError = '';
		const eventId = editingId ?? crypto.randomUUID();
		const nextEvent: CashBill = { id: eventId, label: trimmedLabel, amount_cents: amountCents, due_date: dueDate };
		const existingRule = ruleForEvent(schedule.rules, eventId);
		const nextRule: EventRule = {
			event_id: eventId,
			recurrence,
			end_date: recurrence === 'none' ? null : endDate || null,
			settlements: existingRule?.settlements ?? []
		};
		const nextForecastEvent: ForecastEvent = { ...nextEvent, kind };
		if (nextRule.settlements.some((settlement) => !isScheduledOccurrence(nextForecastEvent, nextRule, settlement.due_date))) {
			eventError = 'Update or remove an existing occurrence settlement before changing this event’s first date, recurrence, or end date.';
			return;
		}
		const nextSchedule: EffectiveSchedule = {
			bills: kind === 'outflow'
				? [...schedule.bills.filter((item) => item.id !== eventId), nextEvent]
				: schedule.bills.filter((item) => item.id !== eventId),
			incomeEvents: kind === 'income'
				? [...schedule.incomeEvents.filter((item) => item.id !== eventId), nextEvent]
				: schedule.incomeEvents.filter((item) => item.id !== eventId),
			rules: [...schedule.rules.filter((rule) => rule.event_id !== eventId), nextRule]
		};
		await applySchedule(nextSchedule);
		if (financialStore.forecastStatus !== 'error') clearEventForm();
	}

	async function removeEvent(event: ForecastEvent) {
		if (!schedule) return;
		await applySchedule({
			bills: schedule.bills.filter((item) => item.id !== event.id),
			incomeEvents: schedule.incomeEvents.filter((item) => item.id !== event.id),
			rules: schedule.rules.filter((rule) => rule.event_id !== event.id)
		});
		if (editingId === event.id) clearEventForm();
	}

	function startSettlementEdit(settlement: EventSettlement) {
		settlementDueDate = settlement.due_date;
		settlementStatus = settlement.status;
		settledOn = settlement.settled_on ?? '';
		settlementError = '';
	}

	async function saveSettlement(event: SubmitEvent) {
		event.preventDefault();
		if (!schedule || !editingId) return;
		if (!isCalendarDate(settlementDueDate)) {
			settlementError = 'Choose a valid occurrence due date.';
			return;
		}
		if (settlementStatus === 'settled' && !isCalendarDate(settledOn)) {
			settlementError = `Choose the date this ${kind === 'income' ? 'income was received' : 'bill was paid'}.`;
			return;
		}
		const editingEvent = events.find((item) => item.id === editingId);
		const existingRule = ruleForEvent(schedule.rules, editingId);
		if (!editingEvent || !isScheduledOccurrence(editingEvent, existingRule, settlementDueDate)) {
			settlementError = 'Choose an occurrence that belongs to this event’s schedule.';
			return;
		}
		settlementError = '';
		const settlement: EventSettlement = {
			due_date: settlementDueDate,
			status: settlementStatus,
			settled_on: settlementStatus === 'settled' ? settledOn : null
		};
		const nextRule: EventRule = {
			event_id: editingId,
			recurrence: existingRule?.recurrence ?? recurrence,
			end_date: existingRule?.end_date ?? (recurrence === 'none' ? null : endDate || null),
			settlements: [
				...(existingRule?.settlements ?? []).filter((item) => item.due_date !== settlementDueDate),
				settlement
			].sort((left, right) => left.due_date.localeCompare(right.due_date))
		};
		await applySchedule({
			...schedule,
			rules: [...schedule.rules.filter((rule) => rule.event_id !== editingId), nextRule]
		});
		if (financialStore.forecastStatus !== 'error') {
			settlementDueDate = '';
			settledOn = '';
			settlementStatus = 'settled';
		}
	}

	async function removeSettlement(settlement: EventSettlement) {
		if (!schedule || !editingId) return;
		const existingRule = ruleForEvent(schedule.rules, editingId);
		if (!existingRule) return;
		await applySchedule({
			...schedule,
			rules: [
				...schedule.rules.filter((rule) => rule.event_id !== editingId),
				{ ...existingRule, settlements: existingRule.settlements.filter((item) => item.due_date !== settlement.due_date) }
			]
		});
	}
</script>

<section class="events-workbench" aria-labelledby="events-title">
	<header class="event-toolbar">
		<div>
			<p class="eyebrow">Cash calendar</p>
			<h1 id="events-title">Bills, income, and settlement timing</h1>
			<span>Every edit is a what-if first. It remains reversible until you commit the preview.</span>
		</div>
		<div class="preview-status" aria-live="polite">
			<strong>{financialStore.isPreview ? 'What-if active' : 'Saved plan'}</strong>
			<span>{previewBusy ? 'Refreshing forecast…' : financialStore.isPreview ? 'Not saved' : 'No staged event changes'}</span>
		</div>
	</header>

	{#if historicalBillNeedsCorrection}
		<p class="correction-note" role="alert"><strong>Correct an unresolved historical bill.</strong> A one-time bill dated before the opening snapshot is not moved into day one. Mark that occurrence Paid or Skipped, or correct its due date.</p>
	{/if}

	<div class="event-layout">
		<section class="event-editor" aria-labelledby="event-editor-title">
			<div class="section-heading">
				<div><p class="eyebrow">{editingId ? 'Editing event' : 'New event'}</p><h2 id="event-editor-title">{editingId ? 'Change timing without changing the saved plan' : 'Put actual timing into the forecast'}</h2></div>
				{#if editingId}<button type="button" class="text-button" onclick={clearEventForm}>New event</button>{/if}
			</div>
			<form onsubmit={saveEvent}>
				<div class="event-kind" role="group" aria-label="Cash event type">
					<button type="button" class:active={kind === 'outflow'} aria-pressed={kind === 'outflow'} onclick={() => kind = 'outflow'}>Bill / outflow</button>
					<button type="button" class:active={kind === 'income'} aria-pressed={kind === 'income'} onclick={() => kind = 'income'}>Income</button>
				</div>
				<label><span>Label</span><input bind:value={label} maxlength="100" placeholder={kind === 'income' ? 'e.g. weekly pay' : 'e.g. rent'} /></label>
				<div class="field-row">
					<label><span>Amount</span><div class="money-input"><span aria-hidden="true">$</span><input bind:value={amountText} type="text" inputmode="decimal" placeholder="0.00" /></div></label>
					<label><span>First due date</span><input bind:value={dueDate} type="date" /></label>
				</div>
				<div class="field-row">
					<label><span>Recurrence</span><select bind:value={recurrence}><option value="none">One time</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option><option value="yearly">Yearly</option></select></label>
					<label><span>Ends on {recurrence === 'none' ? '(not used)' : '(optional)'}</span><input bind:value={endDate} type="date" disabled={recurrence === 'none'} /></label>
				</div>
				{#if eventError}<p class="form-error" role="alert">{eventError}</p>{/if}
				<button class="primary-action" type="submit" disabled={previewBusy}>{previewBusy ? 'Updating…' : editingId ? 'Update what-if' : 'Preview this event'}</button>
			</form>

			{#if editingId}
				<section class="settlement-editor" aria-labelledby="settlement-title">
					<div class="section-heading"><div><p class="eyebrow">Occurrence lifecycle</p><h2 id="settlement-title">{kind === 'income' ? 'Received or skipped income' : 'Paid or skipped bill'}</h2></div></div>
					<p>Settlement dates preserve the original scheduled occurrence. Paid or received on or after the opening date flows on the actual settlement date; a settlement before that snapshot is already reflected and is not deducted again. Skipped occurrences do not flow.</p>
					<form onsubmit={saveSettlement}>
						<div class="field-row">
							<label><span>Occurrence due date</span><input bind:value={settlementDueDate} type="date" /></label>
							<label><span>Status</span><select bind:value={settlementStatus}><option value="settled">{kind === 'income' ? 'Received' : 'Paid'}</option><option value="skipped">Skipped</option></select></label>
						</div>
						{#if settlementStatus === 'settled'}<label><span>{kind === 'income' ? 'Received on' : 'Paid on'}</span><input bind:value={settledOn} type="date" /></label>{/if}
						{#if settlementError}<p class="form-error" role="alert">{settlementError}</p>{/if}
						<button class="secondary-action" type="submit" disabled={previewBusy}>Preview settlement</button>
					</form>
					{#if currentRule?.settlements.length}
						<ul class="settlement-list">
							{#each currentRule.settlements as settlement (settlement.due_date)}
								<li>
									<span>Due {settlement.due_date}</span>
									<strong>
										{#if settlement.status === 'settled' && settlement.settled_on}
											{kind === 'income' ? `Received ${settlement.settled_on}` : `Paid ${settlement.settled_on}`}
										{:else if settlement.status === 'settled'}
											Settlement date needed
										{:else}
											Skipped
										{/if}
									</strong>
									<div>
										<button type="button" onclick={() => startSettlementEdit(settlement)}>Edit</button>
										<button type="button" onclick={() => void removeSettlement(settlement)}>Remove</button>
									</div>
								</li>
							{/each}
						</ul>
					{/if}
				</section>
			{/if}
		</section>

		<section class="event-list-section" aria-labelledby="event-list-title">
			<div class="section-heading"><div><p class="eyebrow">Saved source · staged preview</p><h2 id="event-list-title">Scheduled cash events</h2></div><span>{events.length} total definitions</span></div>
			{#if events.length > 0}
				<ul class="event-list">
					{#each events as event (event.id)}
						{@const eventRule = schedule ? ruleForEvent(schedule.rules, event.id) : undefined}
						<li class:event-list-item--income={event.kind === 'income'}>
							<div class="event-date"><span>{humanDate(event.due_date) ?? event.due_date}</span><strong>{event.kind === 'income' ? 'Income' : 'Bill'}</strong></div>
							<div class="event-main"><strong>{event.label}</strong><span>{eventRule?.recurrence === 'none' || !eventRule ? 'One time' : `${eventRule.recurrence}${eventRule.end_date ? ` · through ${humanDate(eventRule.end_date) ?? eventRule.end_date}` : ''}`}</span></div>
							<strong class="event-amount numeric">{event.kind === 'income' ? '+' : '−'}{formatCurrency(event.amount_cents / 100)}</strong>
							<div class="event-actions"><button type="button" onclick={() => editEvent(event)}>Edit</button><button type="button" class="danger" onclick={() => void removeEvent(event)} disabled={previewBusy}>Remove</button></div>
						</li>
					{/each}
				</ul>
			{:else}
				<div class="empty-events"><p>No income or bills are scheduled yet.</p><span>Add a bill or income event above. Add historical or assumption inputs in Data when your forecast needs more than a known schedule.</span></div>
			{/if}
			<div class="list-footer"><a href={resolve('/data?section=income')}>Model income and history in Data</a><a href={resolve('/liquidity')}>Review reserve impact</a></div>
		</section>
	</div>

	{#if financialStore.forecastError}<p class="forecast-error" role="alert">{financialStore.forecastError}</p>{/if}
</section>

<style>
	.events-workbench { display:grid; gap:1rem; padding:clamp(.8rem,2vw,1.35rem); background:var(--paper); color:var(--ink); }.event-toolbar { display:flex; align-items:end; justify-content:space-between; gap:1rem; }.event-toolbar > div:first-child { display:grid; gap:.3rem; }.eyebrow,.event-date strong,.preview-status strong { color:var(--ink-soft); font-family:var(--font-mono); font-size:.63rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }.event-toolbar h1 { font-size:clamp(1.3rem,2.6vw,2rem); letter-spacing:-.05em; line-height:1; text-wrap:balance; }.event-toolbar > div:first-child > span { max-width:64ch; color:var(--ink-soft); font-size:.8rem; line-height:1.4; }.preview-status { display:grid; gap:.18rem; flex:none; padding:.55rem .65rem; background:var(--paper-soft); border:1px solid var(--rule); }.preview-status strong { color:var(--cobalt-deep); }.preview-status span { color:var(--ink-soft); font-size:.7rem; }.correction-note { margin:0; padding:.7rem .8rem; background:var(--negative-soft); border-left:3px solid var(--negative); color:var(--negative); font-size:.78rem; line-height:1.45; }.correction-note strong { color:var(--negative); }
	.event-layout { display:grid; grid-template-columns:minmax(20rem,.78fr) minmax(0,1.22fr); gap:1rem; align-items:start; }.event-editor,.event-list-section { display:grid; gap:.85rem; min-width:0; padding:1rem; background:var(--paper-soft); border:1px solid var(--rule); }.section-heading { display:flex; align-items:start; justify-content:space-between; gap:.75rem; }.section-heading > div { display:grid; gap:.2rem; }.section-heading h2 { font-size:1rem; letter-spacing:-.025em; line-height:1.15; }.section-heading > span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.62rem; letter-spacing:.04em; text-transform:uppercase; }.text-button { min-height:2.75rem; padding:0 .55rem; background:var(--paper); border:1px solid var(--control-border); color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.63rem; font-weight:700; cursor:pointer; text-transform:uppercase; }.text-button:hover { background:var(--paper-deep); }
	form { display:grid; gap:.7rem; } label { display:grid; gap:.32rem; color:var(--ink-soft); font-size:.73rem; font-weight:650; } input,select { width:100%; min-height:2.75rem; padding:0 .65rem; background:var(--paper); border:1px solid var(--control-border); color:var(--ink); } input:focus,select:focus { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); outline:0; }.event-kind { display:grid; grid-template-columns:1fr 1fr; border:1px solid var(--control-border); }.event-kind button { min-height:2.75rem; border:0; border-right:1px solid var(--rule); background:var(--paper); color:var(--ink-soft); font-family:var(--font-mono); font-size:.65rem; font-weight:700; cursor:pointer; text-transform:uppercase; }.event-kind button:last-child { border-right:0; }.event-kind button.active { background:var(--cobalt); color:var(--paper); }.field-row { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; }.money-input { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:center; background:var(--paper); border:1px solid var(--control-border); }.money-input > span { padding-left:.65rem; color:var(--cobalt); font-family:var(--font-mono); }.money-input input { border:0; outline:0; background:transparent; }.money-input:focus-within { border-color:var(--cobalt); box-shadow:0 0 0 1px var(--cobalt); }.form-error,.forecast-error { margin:0; color:var(--negative); font-size:.73rem; line-height:1.4; }.primary-action,.secondary-action { min-height:2.75rem; justify-self:start; padding:0 .75rem; border:1px solid var(--cobalt); background:var(--cobalt); color:var(--paper); font-family:var(--font-mono); font-size:.66rem; font-weight:700; letter-spacing:.035em; text-transform:uppercase; cursor:pointer; }.secondary-action { background:var(--paper); border-color:var(--control-border); color:var(--cobalt-deep); }.primary-action:hover:not(:disabled) { background:var(--cobalt-bright); }.secondary-action:hover:not(:disabled) { background:var(--paper-deep); border-color:var(--cobalt); }.primary-action:disabled,.secondary-action:disabled { cursor:wait; opacity:.6; }
	.settlement-editor { display:grid; gap:.7rem; padding-top:.9rem; border-top:1px solid var(--rule); }.settlement-editor > p { margin:0; color:var(--ink-soft); font-size:.73rem; line-height:1.42; }.settlement-list { display:grid; gap:1px; padding:0; margin:0; background:var(--rule); list-style:none; }.settlement-list li { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.2fr) auto; align-items:center; gap:.5rem; padding:.5rem; background:var(--paper); }.settlement-list span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.61rem; }.settlement-list strong { font-size:.7rem; }.settlement-list div { display:flex; gap:.3rem; }.settlement-list button,.event-actions button { min-height:2.4rem; padding:0 .45rem; background:var(--paper); border:1px solid var(--control-border); color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.61rem; font-weight:700; cursor:pointer; text-transform:uppercase; }.settlement-list button:hover,.event-actions button:hover:not(:disabled) { background:var(--paper-deep); border-color:var(--cobalt); }.event-actions button.danger { color:var(--negative); }.event-actions button:disabled { cursor:wait; opacity:.6; }
	.event-list { display:grid; gap:1px; padding:0; margin:0; background:var(--rule); border:1px solid var(--rule); list-style:none; }.event-list li { display:grid; grid-template-columns:5.7rem minmax(0,1fr) auto auto; align-items:center; gap:.7rem; padding:.7rem; background:var(--paper); }.event-list li.event-list-item--income { box-shadow:inset 3px 0 var(--positive); }.event-date { display:grid; gap:.12rem; }.event-date > span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.65rem; }.event-date strong { color:var(--negative); font-size:.56rem; }.event-list-item--income .event-date strong,.event-list-item--income .event-amount { color:var(--positive); }.event-main { display:grid; gap:.16rem; min-width:0; }.event-main strong { overflow:hidden; font-size:.82rem; text-overflow:ellipsis; white-space:nowrap; }.event-main span { color:var(--ink-soft); font-size:.69rem; }.event-amount { color:var(--negative); font-size:.76rem; }.event-actions { display:flex; gap:.3rem; }.empty-events { display:grid; gap:.3rem; min-height:12rem; place-content:center start; padding:.9rem; background:var(--paper); border:1px dashed var(--control-border); }.empty-events p { font-size:.84rem; font-weight:700; }.empty-events span { max-width:46ch; color:var(--ink-soft); font-size:.74rem; line-height:1.45; }.list-footer { display:flex; flex-wrap:wrap; gap:.7rem 1rem; }.list-footer a { min-height:2.5rem; display:inline-flex; align-items:center; color:var(--cobalt-deep); font-size:.73rem; font-weight:700; }.forecast-error { padding:.7rem .8rem; background:var(--negative-soft); border-left:3px solid var(--negative); }
	@media(max-width:60rem){.event-layout{grid-template-columns:1fr}.event-editor{order:0}.event-list-section{order:1}}@media(max-width:42rem){.events-workbench{padding:.75rem}.event-toolbar{display:grid;align-items:start}.field-row{grid-template-columns:1fr}.event-list li{grid-template-columns:1fr auto;gap:.4rem}.event-date{grid-column:1 / -1;grid-template-columns:auto auto;align-items:baseline}.event-main{grid-column:1}.event-actions{grid-column:1 / -1}.settlement-list li{grid-template-columns:1fr}.settlement-list div{justify-content:start}.primary-action,.secondary-action{width:100%;justify-content:center}.preview-status{width:100%}}
	@media(max-width:42rem){.settlement-list button,.event-actions button{min-height:2.75rem}.list-footer a{min-height:2.75rem}}
</style>
