import type { HistoricalTransaction } from './finance';

export type HistoricalIncomeWindow = 3 | 6 | 12 | 'all';

export type HistoricalIncomeEstimate =
	| {
			status: 'ready';
			monthlyIncomeCents: number;
			variability: number;
			uncappedVariability: number;
			months: number;
			periodStart: string;
			periodEnd: string;
			totalIncomeCents: number;
	  }
	| {
			status: 'unavailable';
			reason: 'coverage' | 'duration' | 'income';
			message: string;
	  };

type CalendarDate = { year: number; month: number; day: number };

function parseCalendarDate(value: string | null): CalendarDate | null {
	if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
	const [year, month, day] = value.split('-').map(Number);
	const date = new Date(Date.UTC(year, month - 1, day));
	if (
		date.getUTCFullYear() !== year ||
		date.getUTCMonth() !== month - 1 ||
		date.getUTCDate() !== day
	) {
		return null;
	}
	return { year, month, day };
}

function daysInMonth(year: number, month: number): number {
	return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function monthIndex(date: CalendarDate): number {
	return date.year * 12 + date.month - 1;
}

function monthKey(index: number): string {
	const year = Math.floor(index / 12);
	const month = (index % 12) + 1;
	return `${year}-${String(month).padStart(2, '0')}`;
}

/**
 * Derive prospective variable-income inputs from fully covered calendar months.
 * Zero-income months remain observations; fixed income and every non-income
 * category are excluded so scheduled pay is not counted twice.
 */
export function deriveHistoricalIncome(
	transactions: readonly HistoricalTransaction[],
	coverageStart: string | null,
	coverageEnd: string | null,
	window: HistoricalIncomeWindow
): HistoricalIncomeEstimate {
	const start = parseCalendarDate(coverageStart);
	const end = parseCalendarDate(coverageEnd);
	if (!start || !end || monthIndex(start) > monthIndex(end)) {
		return {
			status: 'unavailable',
			reason: 'coverage',
			message: 'Set a valid history coverage start and end date first.'
		};
	}

	const firstFullMonth = monthIndex(start) + (start.day === 1 ? 0 : 1);
	const lastFullMonth =
		monthIndex(end) - (end.day === daysInMonth(end.year, end.month) ? 0 : 1);
	if (lastFullMonth - firstFullMonth + 1 < 2) {
		return {
			status: 'unavailable',
			reason: 'duration',
			message: 'At least two complete calendar months are needed to estimate variability.'
		};
	}

	const availableMonths = Array.from(
		{ length: lastFullMonth - firstFullMonth + 1 },
		(_, index) => firstFullMonth + index
	);
	const selectedMonths =
		window === 'all' ? availableMonths : availableMonths.slice(-window);
	const totals = new Map(selectedMonths.map((index) => [index, 0]));

	for (const transaction of transactions) {
		if (transaction.category !== 'income_variable' || transaction.amount_cents <= 0) continue;
		const date = parseCalendarDate(transaction.date);
		if (!date) continue;
		const index = monthIndex(date);
		if (totals.has(index)) totals.set(index, (totals.get(index) ?? 0) + transaction.amount_cents);
	}

	const monthlyTotals = selectedMonths.map((index) => totals.get(index) ?? 0);
	const totalIncomeCents = monthlyTotals.reduce((total, amount) => total + amount, 0);
	if (totalIncomeCents === 0) {
		return {
			status: 'unavailable',
			reason: 'income',
			message: 'No transactions classified as variable income appear in the selected complete months.'
		};
	}

	const mean = totalIncomeCents / monthlyTotals.length;
	const variance =
		monthlyTotals.reduce((total, amount) => total + (amount - mean) ** 2, 0) /
		monthlyTotals.length;
	const uncappedVariability = Math.sqrt(variance) / mean;

	return {
		status: 'ready',
		monthlyIncomeCents: Math.round(mean),
		variability: Math.min(2, uncappedVariability),
		uncappedVariability,
		months: monthlyTotals.length,
		periodStart: `${monthKey(selectedMonths[0])}-01`,
		periodEnd: `${monthKey(selectedMonths.at(-1)!)}-${String(
			daysInMonth(
				Math.floor(selectedMonths.at(-1)! / 12),
				(selectedMonths.at(-1)! % 12) + 1
			)
		).padStart(2, '0')}`,
		totalIncomeCents
	};
}
