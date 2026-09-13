import { requestEngine, type EngineResult } from './api';

export const MAX_ABS_BALANCE_CENTS = 100_000_000_000;
export const MAX_BILL_CENTS = 100_000_000_000;

export type CashAccountKind = 'checking' | 'savings';

export interface CashAccount {
	id: string;
	name: string;
	kind: CashAccountKind;
	// Exact USD cents; guaranteed to be a safe JavaScript integer by the API contract.
	balance_cents: number;
}

export interface CashBill {
	id: string;
	label: string;
	// Exact positive USD cents; guaranteed to be a safe JavaScript integer by the API contract.
	amount_cents: number;
	due_date: string;
}

export interface CashWorkspace {
	revision: number;
	as_of: string | null;
	currency: 'USD';
	accounts: CashAccount[];
	bills: CashBill[];
}

// PUT /workspace is a full replacement. `as_of` is the opening calendar day
// represented by every account balance in the snapshot.
export interface WorkspaceDraft {
	expected_revision: number;
	as_of: string;
	accounts: CashAccount[];
	bills: CashBill[];
}

export type ProjectionHorizonDays = 14 | 30 | 60;


/**
 * Convert a plain USD decimal field to integer cents without float arithmetic.
 * It accepts an optional leading minus sign for cash balances; callers can
 * reject negative bills with the `allowNegative` argument.
 */
export function parseUsdCents(input: string, allowNegative = true): number | null {
	const match = input.trim().match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
	if (!match) return null;
	if (!allowNegative && match[1] === '-') return null;

	const whole = BigInt(match[2]);
	const fractional = BigInt((match[3] ?? '').padEnd(2, '0') || '0');
	const cents = whole * 100n + fractional;
	if (cents > BigInt(MAX_ABS_BALANCE_CENTS)) return null;
	return Number(match[1] === '-' ? -cents : cents);
}

export function saveWorkspace(draft: WorkspaceDraft): Promise<EngineResult<CashWorkspace>> {
	return requestEngine<CashWorkspace>(
		'/workspace',
		{
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(draft)
		},
		{ requiresAuth: true }
	);
}


// Dispatched on `window` after an assistant-proposed addition is approved and
// the engine returns the new canonical snapshot, so the workspace page can
// refresh without polling. The page must still verify the owner before use.
export const WORKSPACE_SAVED_EVENT = 'ginseng:workspace-saved';

export interface WorkspaceSavedDetail {
	ownerId: string;
	workspace: CashWorkspace;
}
