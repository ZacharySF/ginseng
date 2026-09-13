import type { EventRule, FinanceWorkspace } from '$lib/finance';
import type { CashAccount, CashBill } from '$lib/workspace';

export function localCalendarDate(now = new Date()): string {
	const offset = now.getTimezoneOffset() * 60_000;
	return new Date(now.valueOf() - offset).toISOString().slice(0, 10);
}

export function isCalendarDate(value: string): boolean {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
	const date = new Date(`${value}T00:00:00Z`);
	return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

export function cashStepError(asOf: string | null, accounts: CashAccount[]): string | null {
	if (!asOf || !isCalendarDate(asOf)) return 'Choose the opening date for these balances.';
	if (accounts.length === 0) return 'Add at least one checking or savings account.';
	for (const account of accounts) {
		if (!account.name.trim()) return 'Name every cash account.';
		if (account.name.trim().length > 100) return 'Keep account names to 100 characters or fewer.';
		if (!Number.isSafeInteger(account.balance_cents)) return 'Enter a valid balance for every account.';
	}
	return null;
}

export function scheduleStepError(kind: 'income' | 'bill', events: CashBill[]): string | null {
	for (const event of events) {
		if (!event.label.trim()) return `Name every ${kind}.`;
		if (event.label.trim().length > 100) return `Keep ${kind} names to 100 characters or fewer.`;
		if (!Number.isSafeInteger(event.amount_cents) || event.amount_cents < 1) {
			return `Enter an amount greater than zero for every ${kind}.`;
		}
		if (!isCalendarDate(event.due_date)) return `Choose a valid first date for every ${kind}.`;
	}
	return null;
}

export function ruleForEvent(rules: EventRule[], eventId: string): EventRule | undefined {
	return rules.find((rule) => rule.event_id === eventId);
}

export function normalizedOnboardingWorkspace(workspace: FinanceWorkspace): FinanceWorkspace {
	const normalized = structuredClone(workspace);
	normalized.accounts.forEach((account) => { account.name = account.name.trim(); });
	normalized.bills.forEach((bill) => { bill.label = bill.label.trim(); });
	normalized.inputs.income_events.forEach((income) => { income.label = income.label.trim(); });
	return normalized;
}
