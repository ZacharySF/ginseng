import type { CashBill, EventRule, ScenarioOverrides } from './finance';

export type ForecastEventKind = 'income' | 'outflow';

export interface ForecastEvent {
	id: string;
	label: string;
	amount_cents: number;
	due_date: string;
	kind: ForecastEventKind;
}

export interface ChartEvent {
	id: string;
	label: string;
	amount: number;
	day: number;
	kind: ForecastEventKind;
	date: string;
}

export interface EffectiveSchedule {
	bills: CashBill[];
	incomeEvents: CashBill[];
	rules: EventRule[];
}

function parseDate(value: string): Date | null {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
	const date = new Date(`${value}T00:00:00Z`);
	return Number.isNaN(date.valueOf()) || date.toISOString().slice(0, 10) !== value ? null : date;
}

function formatDate(date: Date): string {
	return date.toISOString().slice(0, 10);
}

function addDays(date: Date, amount: number): Date {
	const next = new Date(date.valueOf());
	next.setUTCDate(next.getUTCDate() + amount);
	return next;
}

function daysInMonth(year: number, month: number): number {
	return new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
}

function addMonthsClipped(date: Date, months: number, anchorDay: number): Date {
	const year = date.getUTCFullYear();
	const month = date.getUTCMonth() + months;
	const targetYear = year + Math.floor(month / 12);
	const targetMonth = ((month % 12) + 12) % 12;
	return new Date(
		Date.UTC(targetYear, targetMonth, Math.min(anchorDay, daysInMonth(targetYear, targetMonth)))
	);
}

function nextOccurrence(
	date: Date,
	recurrence: EventRule['recurrence'],
	anchorDay: number
): Date | null {
	switch (recurrence) {
		case 'weekly':
			return addDays(date, 7);
		case 'biweekly':
			return addDays(date, 14);
		case 'monthly':
			return addMonthsClipped(date, 1, anchorDay);
		case 'yearly':
			return addMonthsClipped(date, 12, anchorDay);
		case 'none':
			return null;
	}
}

function numberOfDaysBetween(start: Date, end: Date): number {
	return Math.round((end.valueOf() - start.valueOf()) / 86_400_000);
}

export function effectiveSchedule(
	workspace: { bills: CashBill[]; inputs: { income_events: CashBill[]; event_rules: EventRule[] } },
	overrides: ScenarioOverrides | null
): EffectiveSchedule {
	return {
		bills: overrides?.bills ?? workspace.bills,
		incomeEvents: overrides?.income_events ?? workspace.inputs.income_events,
		rules: overrides?.event_rules ?? workspace.inputs.event_rules
	};
}

export function mergeScheduleOverrides(
	current: ScenarioOverrides | null,
	schedule: EffectiveSchedule
): ScenarioOverrides {
	return {
		...(current ?? {}),
		bills: schedule.bills,
		income_events: schedule.incomeEvents,
		event_rules: schedule.rules
	};
}

export function scheduleEvents(schedule: EffectiveSchedule): ForecastEvent[] {
	return [
		...schedule.bills.map((event) => ({ ...event, kind: 'outflow' as const })),
		...schedule.incomeEvents.map((event) => ({ ...event, kind: 'income' as const }))
	].sort((left, right) => left.due_date.localeCompare(right.due_date) || left.label.localeCompare(right.label));
}

export function ruleForEvent(rules: EventRule[], eventId: string): EventRule | undefined {
	return rules.find((rule) => rule.event_id === eventId);
}

/**
 * Turns saved schedule definitions into the occurrence markers shown in a forecast window.
 * Source records remain untouched: extending or shortening the visible horizon never rewrites
 * their original dates, recurrence, or settled occurrence ids.
 */
export function chartEventsForSchedule(
	schedule: EffectiveSchedule,
	asOf: string | null,
	horizonDays: number
): ChartEvent[] {
	const opening = asOf ? parseDate(asOf) : null;
	if (!opening || horizonDays < 1) return [];

	const lastDay = addDays(opening, horizonDays - 1);
	const markers: ChartEvent[] = [];

	for (const event of scheduleEvents(schedule)) {
		const firstDue = parseDate(event.due_date);
		if (!firstDue) continue;
		const anchorDay = firstDue.getUTCDate();
		const rule = ruleForEvent(schedule.rules, event.id);
		const endDate = rule?.end_date ? parseDate(rule.end_date) : null;
		let occurrence = firstDue;
		let iterations = 0;

		while (occurrence <= lastDay && iterations < 10_000) {
			if (endDate && occurrence > endDate) break;
			const dueDate = formatDate(occurrence);
			const settlement = rule?.settlements.find((entry) => entry.due_date === dueDate);
			let cashDate = occurrence;

			if (settlement?.status === 'skipped') {
				const next = nextOccurrence(occurrence, rule?.recurrence ?? 'none', anchorDay);
				if (!next) break;
				occurrence = next;
				iterations += 1;
				continue;
			}

			if (settlement?.status === 'settled') {
				const settledOn = settlement.settled_on ? parseDate(settlement.settled_on) : null;
				if (!settledOn) {
					const next = nextOccurrence(occurrence, rule?.recurrence ?? 'none', anchorDay);
					if (!next) break;
					occurrence = next;
					iterations += 1;
					continue;
				}
				cashDate = settledOn;
			}

			const day = numberOfDaysBetween(opening, cashDate) + 1;
			if (day >= 1 && day <= horizonDays) {
				markers.push({
					id: `${event.id}:${dueDate}`,
					label: event.label,
					amount: event.amount_cents / 100,
					day,
					kind: event.kind,
					date: formatDate(cashDate)
				});
			}

			const next = nextOccurrence(occurrence, rule?.recurrence ?? 'none', anchorDay);
			if (!next) break;
			occurrence = next;
			iterations += 1;
		}
	}

	return markers.sort((left, right) => left.day - right.day || left.label.localeCompare(right.label));
}

export function hasUnresolvedHistoricalBill(schedule: EffectiveSchedule, asOf: string | null): boolean {
	if (!asOf) return false;
	return schedule.bills.some((bill) => {
		if (bill.due_date >= asOf) return false;
		const rule = ruleForEvent(schedule.rules, bill.id);
		if (rule?.recurrence && rule.recurrence !== 'none') return false;
		const settlement = rule?.settlements.find((entry) => entry.due_date === bill.due_date);
		return settlement?.status !== 'settled' && settlement?.status !== 'skipped';
	});
}

export function isScheduledOccurrence(
	event: ForecastEvent,
	rule: EventRule | undefined,
	date: string
): boolean {
	const firstDue = parseDate(event.due_date);
	const target = parseDate(date);
	if (!firstDue || !target || target < firstDue) return false;
	const endDate = rule?.end_date ? parseDate(rule.end_date) : null;
	if (endDate && target > endDate) return false;
	const recurrence = rule?.recurrence ?? 'none';
	const anchorDay = firstDue.getUTCDate();
	let occurrence = firstDue;

	for (let iterations = 0; iterations < 10_000; iterations += 1) {
		if (occurrence.valueOf() === target.valueOf()) return true;
		if (occurrence > target) return false;
		const next = nextOccurrence(occurrence, recurrence, anchorDay);
		if (!next) return false;
		occurrence = next;
	}

	return false;
}

export function humanDate(value: string | null): string | null {
	if (!value) return null;
	const date = parseDate(value);
	if (!date) return value;
	return new Intl.DateTimeFormat('en-US', {
		month: 'short',
		day: 'numeric',
		year: 'numeric',
		timeZone: 'UTC'
	}).format(date);
}
