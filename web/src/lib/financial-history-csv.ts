import type { TransactionCategory } from './finance';
import { MAX_ABS_BALANCE_CENTS } from './workspace';

export const MAX_IMPORT_ROWS = 20_000;

export const TRANSACTION_CATEGORIES: readonly TransactionCategory[] = [
	'income_fixed',
	'income_variable',
	'expense_fixed',
	'expense_essential_variable',
	'expense_discretionary_variable',
	'expense_irregular',
	'transfer',
	'credit_purchase',
	'credit_payment',
	'investment_buy',
	'investment_sell'
];

export const TRANSACTION_CATEGORY_LABELS: Record<TransactionCategory, string> = {
	income_fixed: 'Fixed income',
	income_variable: 'Variable income',
	expense_fixed: 'Fixed expense',
	expense_essential_variable: 'Essential variable expense',
	expense_discretionary_variable: 'Discretionary variable expense',
	expense_irregular: 'Irregular expense',
	transfer: 'Transfer',
	credit_purchase: 'Credit-card purchase',
	credit_payment: 'Credit-card payment',
	investment_buy: 'Investment purchase',
	investment_sell: 'Investment sale'
};

export type CsvDelimiter = ',' | ';' | '\t';
export type CsvDateOrder = 'year-month-day' | 'month-day-year' | 'day-month-year';
export type AmountInterpretation = 'as-reported' | 'reverse-sign';
export type ReturnInterpretation = 'decimal' | 'percent';

export interface CsvTable {
	rows: string[][];
	delimiter: CsvDelimiter;
	warnings: string[];
}

export interface CsvColumn {
	index: number;
	label: string;
	normalized: string;
}

export interface CsvColumnMapping {
	date: number | null;
	description: number | null;
	amount: number | null;
	debit: number | null;
	credit: number | null;
	category: number | null;
	sourceKey: number | null;
	dateOrder: CsvDateOrder;
	amountInterpretation: AmountInterpretation;
}

export interface ImportCandidate {
	sourceRow: number;
	date: string | null;
	description: string;
	amount_cents: number | null;
	category: TransactionCategory | null;
	source_key: string | null;
	issues: string[];
	raw: string[];
}

export interface PortfolioReturnMapping {
	date: number | null;
	returnValue: number | null;
	dateOrder: CsvDateOrder;
	returnInterpretation: ReturnInterpretation;
}

export interface PortfolioReturnCandidate {
	sourceRow: number;
	date: string | null;
	return_decimal: number | null;
	issues: string[];
	raw: string[];
}

export interface TransactionFingerprintInput {
	date: string;
	description: string;
	amount_cents: number;
	source_key: string | null;
}

function stripBom(value: string): string {
	return value.charCodeAt(0) === 0xfeff ? value.slice(1) : value;
}

function delimiterCount(value: string, delimiter: CsvDelimiter): number {
	let count = 0;
	let quoted = false;
	for (let index = 0; index < value.length; index += 1) {
		const character = value[index];
		if (character === '"') {
			if (quoted && value[index + 1] === '"') {
				index += 1;
				continue;
			}
			quoted = !quoted;
			continue;
		}
		if (!quoted && character === delimiter) count += 1;
		if (!quoted && (character === '\n' || character === '\r')) break;
	}
	return count;
}

function chooseDelimiter(value: string): CsvDelimiter {
	const candidates: CsvDelimiter[] = [',', ';', '\t'];
	return candidates.reduce((best, candidate) =>
		delimiterCount(value, candidate) > delimiterCount(value, best) ? candidate : best
	);
}

/**
 * RFC-4180-style parsing for local, user-selected text. Quoted commas, quoted
 * newlines, escaped quotes, UTF-8 BOMs, and CRLF are kept intact. The caller
 * deliberately decides whether the first row is a header because banks vary.
 */
export function parseCsvTable(source: string): { table: CsvTable | null; error: string | null } {
	const text = stripBom(source);
	if (text.trim().length === 0) return { table: null, error: 'Choose a non-empty CSV file.' };

	const delimiter = chooseDelimiter(text);
	const rows: string[][] = [];
	let row: string[] = [];
	let cell = '';
	let quoted = false;

	for (let index = 0; index < text.length; index += 1) {
		const character = text[index];
		if (quoted) {
			if (character === '"') {
				if (text[index + 1] === '"') {
					cell += '"';
					index += 1;
				} else {
					quoted = false;
				}
			} else {
				cell += character;
			}
			continue;
		}

		if (character === '"' && cell.length === 0) {
			quoted = true;
			continue;
		}
		if (character === delimiter) {
			row.push(cell);
			cell = '';
			continue;
		}
		if (character === '\r' || character === '\n') {
			if (character === '\r' && text[index + 1] === '\n') index += 1;
			row.push(cell);
			if (row.some((value) => value.length > 0)) rows.push(row);
			if (rows.length > MAX_IMPORT_ROWS + 1) {
				return {
					table: null,
					error: `This file has more than ${MAX_IMPORT_ROWS.toLocaleString()} rows. Split it before importing.`
				};
			}
			row = [];
			cell = '';
			continue;
		}
		cell += character;
	}

	if (quoted) return { table: null, error: 'The CSV has an unclosed quoted field. Fix the quote and choose the file again.' };
	if (cell.length > 0 || row.length > 0) {
		row.push(cell);
		if (row.some((value) => value.length > 0)) rows.push(row);
		if (rows.length > MAX_IMPORT_ROWS + 1) {
			return {
				table: null,
				error: `This file has more than ${MAX_IMPORT_ROWS.toLocaleString()} rows. Split it before importing.`
			};
		}
	}
	if (rows.length === 0) return { table: null, error: 'The CSV does not contain any rows.' };

	const width = Math.max(...rows.map((candidate) => candidate.length));
	const uneven = rows.some((candidate) => candidate.length !== width);
	return {
		table: {
			rows,
			delimiter,
			warnings: uneven
				? ['Some rows have fewer columns than the widest row. Blank cells will be shown for missing values.']
				: []
		},
		error: null
	};
}

function normalize(value: string): string {
	return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

export function csvColumns(table: CsvTable, hasHeader: boolean): CsvColumn[] {
	const width = Math.max(...table.rows.map((row) => row.length));
	const header = hasHeader ? table.rows[0] ?? [] : [];
	return Array.from({ length: width }, (_, index) => {
		const source = header[index]?.trim();
		const label = source && source.length > 0 ? source : `Column ${index + 1}`;
		return { index, label, normalized: normalize(label) };
	});
}

function matchingColumn(columns: readonly CsvColumn[], patterns: readonly string[]): number | null {
	for (const pattern of patterns) {
		const exact = columns.find((column) => column.normalized === pattern);
		if (exact) return exact.index;
	}
	for (const pattern of patterns) {
		const partial = columns.find((column) => column.normalized.includes(pattern));
		if (partial) return partial.index;
	}
	return null;
}

function inferredDateOrder(table: CsvTable, dateColumn: number | null, hasHeader: boolean): CsvDateOrder {
	if (dateColumn === null) return 'month-day-year';
	const values = table.rows.slice(hasHeader ? 1 : 0, hasHeader ? 13 : 12).map((row) => row[dateColumn] ?? '');
	if (values.some((value) => /^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$/.test(value.trim()))) return 'year-month-day';
	const dayFirstSignal = values.some((value) => {
		const match = value.trim().match(/^(\d{1,2})[/-](\d{1,2})[/-]\d{2,4}$/);
		return match !== null && Number(match[1]) > 12;
	});
	return dayFirstSignal ? 'day-month-year' : 'month-day-year';
}

export function inferTransactionMapping(table: CsvTable, hasHeader: boolean): CsvColumnMapping {
	const columns = csvColumns(table, hasHeader);
	const date = matchingColumn(columns, ['date', 'transaction date', 'posted date', 'posting date', 'value date']);
	const debit = matchingColumn(columns, ['debit', 'withdrawal', 'withdrawals', 'outflow', 'money out']);
	const credit = matchingColumn(columns, ['credit', 'deposit', 'deposits', 'inflow', 'money in']);
	return {
		date,
		description: matchingColumn(columns, ['description', 'memo', 'details', 'payee', 'merchant', 'name']),
		amount: matchingColumn(columns, ['amount', 'transaction amount', 'value', 'net amount']),
		debit,
		credit,
		category: matchingColumn(columns, ['category', 'type', 'transaction type']),
		sourceKey: matchingColumn(columns, ['transaction id', 'reference', 'fitid', 'id']),
		dateOrder: inferredDateOrder(table, date, hasHeader),
		amountInterpretation: 'as-reported'
	};
}

export function inferPortfolioReturnMapping(table: CsvTable, hasHeader: boolean): PortfolioReturnMapping {
	const columns = csvColumns(table, hasHeader);
	const returnValue = matchingColumn(columns, ['return', 'daily return', 'portfolio return', 'return percent', 'return pct']);
	const selected = returnValue === null ? null : columns.find((column) => column.index === returnValue);
	return {
		date: matchingColumn(columns, ['date', 'trading date', 'as of date']),
		returnValue,
		dateOrder: inferredDateOrder(table, matchingColumn(columns, ['date', 'trading date', 'as of date']), hasHeader),
		returnInterpretation: selected?.normalized.includes('percent') || selected?.normalized.includes('pct') ? 'percent' : 'decimal'
	};
}

function validDate(year: number, month: number, day: number): string | null {
	if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day) || year < 1900 || year > 2100) return null;
	const candidate = new Date(Date.UTC(year, month - 1, day));
	if (
		candidate.getUTCFullYear() !== year ||
		candidate.getUTCMonth() !== month - 1 ||
		candidate.getUTCDate() !== day
	) return null;
	return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/** Parse common bank dates without ever letting local time move a calendar date. */
export function parseCsvDate(value: string, order: CsvDateOrder): string | null {
	const trimmed = value.trim();
	const ymd = trimmed.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/);
	if (ymd) return validDate(Number(ymd[1]), Number(ymd[2]), Number(ymd[3]));
	const compact = trimmed.match(/^(\d{4})(\d{2})(\d{2})$/);
	if (compact) return validDate(Number(compact[1]), Number(compact[2]), Number(compact[3]));
	const parts = trimmed.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})$/);
	if (!parts) return null;
	const year = parts[3].length === 2 ? 2000 + Number(parts[3]) : Number(parts[3]);
	if (order === 'month-day-year') return validDate(year, Number(parts[1]), Number(parts[2]));
	return validDate(year, Number(parts[2]), Number(parts[1]));
}

/**
 * Parse a decimal monetary representation to exact cents. Parentheses and a
 * leading minus both mean negative. Three-plus decimal places are rejected,
 * rather than rounded, because importing a ledger must not silently change it.
 */
export function parseCsvCents(value: string): number | null {
	let text = value.trim().replace(/\u00a0/g, '');
	if (text.length === 0) return null;
	const parenthesized = /^\(.*\)$/.test(text);
	if (parenthesized) text = text.slice(1, -1);
	text = text.replace(/[\s$£€¥]/g, '');
	if (text.includes(',') && !/^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?$/.test(text)) return null;
	text = text.replace(/,/g, '');
	const match = text.match(/^([+-]?)(\d+)(?:\.(\d{1,2}))?$/);
	if (!match) return null;
	const whole = BigInt(match[2]);
	const fraction = BigInt((match[3] ?? '').padEnd(2, '0') || '0');
	const absolute = whole * 100n + fraction;
	if (absolute > BigInt(Number.MAX_SAFE_INTEGER)) return null;
	const negative = parenthesized || match[1] === '-';
	return Number(negative ? -absolute : absolute);
}

export function parsePortfolioReturn(value: string, interpretation: ReturnInterpretation): number | null {
	let text = value.trim().replace(/\u00a0/g, '');
	if (text.length === 0) return null;
	const explicitPercent = text.endsWith('%');
	text = text.replace(/[%\s]/g, '');
	if (text.includes(',') && !/^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$/.test(text)) return null;
	text = text.replace(/,/g, '');
	const numeric = Number(text);
	if (!Number.isFinite(numeric)) return null;
	return explicitPercent || interpretation === 'percent' ? numeric / 100 : numeric;
}

const CATEGORY_BY_NAME: Partial<Record<string, TransactionCategory>> = Object.create(null);
for (const category of TRANSACTION_CATEGORIES) {
	CATEGORY_BY_NAME[normalize(category)] = category;
	CATEGORY_BY_NAME[normalize(TRANSACTION_CATEGORY_LABELS[category])] = category;
}

export function inferTransactionCategory(value: string): TransactionCategory | null {
	const text = normalize(value);
	const explicit = CATEGORY_BY_NAME[text];
	if (explicit) return explicit;
	if (/\b(internal transfer|transfer)\b/.test(text)) return 'transfer';
	if (/\b(credit card payment|card payment|cc payment)\b/.test(text)) return 'credit_payment';
	if (/\b(card purchase|credit purchase)\b/.test(text)) return 'credit_purchase';
	if (/\b(investment sale|sell|sold)\b/.test(text)) return 'investment_sell';
	if (/\b(investment purchase|buy|bought)\b/.test(text)) return 'investment_buy';
	if (/\b(payroll|salary|wage|employer|paycheck)\b/.test(text)) return 'income_fixed';
	if (/\b(freelance|contract|gig|tips|commission|side income)\b/.test(text)) return 'income_variable';
	if (/\b(rent|mortgage|insurance|subscription|utility|utilities|loan)\b/.test(text)) return 'expense_fixed';
	if (/\b(grocery|groceries|food|gas|fuel|pharmacy|medical|doctor|transit)\b/.test(text)) return 'expense_essential_variable';
	if (/\b(restaurant|dining|coffee|entertainment|travel|shopping|retail)\b/.test(text)) return 'expense_discretionary_variable';
	if (/\b(tax|repair|maintenance|gift|fee|charge)\b/.test(text)) return 'expense_irregular';
	return null;
}

export function transactionCategorySignIssue(category: TransactionCategory, amount: number): string | null {
	if (amount === 0) return 'Transactions need a non-zero amount.';
	if (['income_fixed', 'income_variable', 'investment_sell'].includes(category) && amount < 0) {
		return 'This category needs a positive amount.';
	}
	if (
		[
			'expense_fixed',
			'expense_essential_variable',
			'expense_discretionary_variable',
			'expense_irregular',
			'credit_purchase',
			'credit_payment',
			'investment_buy'
		].includes(category) &&
		amount > 0
	) {
		return 'This category needs a negative amount.';
	}
	return null;
}

function cell(row: readonly string[], index: number | null): string {
	return index === null ? '' : row[index] ?? '';
}

function parsedAmount(row: readonly string[], mapping: CsvColumnMapping): number | null {
	if (mapping.debit !== null || mapping.credit !== null) {
		const debitRaw = cell(row, mapping.debit).trim();
		const creditRaw = cell(row, mapping.credit).trim();
		const debit = debitRaw.length === 0 ? 0 : parseCsvCents(debitRaw);
		const credit = creditRaw.length === 0 ? 0 : parseCsvCents(creditRaw);
		if (debit === null || credit === null) return null;
		return Math.abs(credit) - Math.abs(debit);
	}
	const amount = parseCsvCents(cell(row, mapping.amount));
	if (amount === null) return null;
	return mapping.amountInterpretation === 'reverse-sign' ? -amount : amount;
}

export function buildImportCandidates(
	table: CsvTable,
	hasHeader: boolean,
	mapping: CsvColumnMapping
): ImportCandidate[] {
	const rows = table.rows.slice(hasHeader ? 1 : 0);
	return rows.map((row, index) => {
		const issues: string[] = [];
		const date = parseCsvDate(cell(row, mapping.date), mapping.dateOrder);
		const description = cell(row, mapping.description).trim();
		const amount = parsedAmount(row, mapping);
		const mappedCategory = cell(row, mapping.category);
		const category = inferTransactionCategory(mappedCategory || description);
		const sourceKey = cell(row, mapping.sourceKey).trim() || null;
		if (!date) issues.push('Choose a date column and date order that produces a real calendar date.');
		if (description.length === 0) issues.push('Choose a description column or add a description before applying this row.');
		if (amount === null) issues.push('Choose an amount column (or debit and credit columns) with cents to two decimal places.');
		if (amount !== null && Math.abs(amount) > MAX_ABS_BALANCE_CENTS) issues.push('This amount is outside the supported range.');
		if (category === null) issues.push('Choose a classification before applying this row.');
		if (amount !== null && category !== null) {
			const signIssue = transactionCategorySignIssue(category, amount);
			if (signIssue) issues.push(signIssue);
		}
		return {
			sourceRow: index + (hasHeader ? 2 : 1),
			date,
			description,
			amount_cents: amount,
			category,
			source_key: sourceKey,
			issues,
			raw: row
		};
	});
}

export function buildPortfolioReturnCandidates(
	table: CsvTable,
	hasHeader: boolean,
	mapping: PortfolioReturnMapping
): PortfolioReturnCandidate[] {
	return table.rows.slice(hasHeader ? 1 : 0).map((row, index) => {
		const date = parseCsvDate(cell(row, mapping.date), mapping.dateOrder);
		const returnDecimal = parsePortfolioReturn(cell(row, mapping.returnValue), mapping.returnInterpretation);
		const issues: string[] = [];
		if (!date) issues.push('Choose a date column and date order that produces a real calendar date.');
		if (returnDecimal === null) issues.push('Choose a return column with a numeric daily return.');
		if (returnDecimal !== null && (returnDecimal < -1 || returnDecimal > 100)) issues.push('Daily returns must be between −100% and 10,000%.');
		return {
			sourceRow: index + (hasHeader ? 2 : 1),
			date,
			return_decimal: returnDecimal,
			issues,
			raw: row
		};
	});
}

export function transactionFingerprintKeys(value: TransactionFingerprintInput): string[] {
	const keys: string[] = [];
	const source = normalize(value.source_key ?? '');
	if (source.length > 0) keys.push(`source:${source}`);
	const description = normalize(value.description);
	if (value.date && description.length > 0 && Number.isSafeInteger(value.amount_cents)) {
		keys.push(`content:${value.date}|${value.amount_cents}|${description}`);
	}
	return keys;
}

export function duplicateTransactionKeys(
	candidate: TransactionFingerprintInput,
	existing: readonly TransactionFingerprintInput[]
): string[] {
	const candidateKeys = transactionFingerprintKeys(candidate);
	if (candidateKeys.length === 0) return [];
	const seen = new Set(existing.flatMap(transactionFingerprintKeys));
	return candidateKeys.filter((key) => seen.has(key));
}

export function duplicateTransactionIndexes(records: readonly TransactionFingerprintInput[]): Set<number> {
	const seen = new Map<string, number>();
	const duplicates = new Set<number>();
	records.forEach((record, index) => {
		for (const key of transactionFingerprintKeys(record)) {
			const prior = seen.get(key);
			if (prior !== undefined) {
				duplicates.add(prior);
				duplicates.add(index);
			} else {
				seen.set(key, index);
			}
		}
	});
	return duplicates;
}

export function isTransactionCategory(value: string): value is TransactionCategory {
	return (TRANSACTION_CATEGORIES as readonly string[]).includes(value);
}

