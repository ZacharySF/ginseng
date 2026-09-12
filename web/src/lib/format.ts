// Shared number formatters. Every dollar and percentage figure rendered by
// the UI passes through exactly these three functions so formatting stays
// in lockstep everywhere a scenario value appears. `maximumFractionDigits`
// caps precision but never forces trailing zeros the engine did not report.

const CURRENCY_FORMATTER = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD',
	minimumFractionDigits: 0,
	maximumFractionDigits: 2
});

const SIGNED_CURRENCY_FORMATTER = new Intl.NumberFormat('en-US', {
	style: 'currency',
	currency: 'USD',
	minimumFractionDigits: 0,
	maximumFractionDigits: 2,
	signDisplay: 'exceptZero'
});

const PERCENT_FORMATTER = new Intl.NumberFormat('en-US', {
	style: 'percent',
	minimumFractionDigits: 0,
	maximumFractionDigits: 1
});

export function formatCurrency(amount: number): string {
	return CURRENCY_FORMATTER.format(amount);
}

export function formatSignedCurrency(amount: number): string {
	return SIGNED_CURRENCY_FORMATTER.format(amount);
}

export function formatPercent(fraction: number): string {
	return PERCENT_FORMATTER.format(fraction);
}
