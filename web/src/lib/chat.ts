import { requestEngineStream, describeNetworkError, type EngineResult } from './api';
import {
	MAX_ABS_BALANCE_CENTS,
	MAX_BILL_CENTS,
	type CashAccount,
	type CashBill,
	type ProjectionHorizonDays,
	type WorkspaceDraft
} from './workspace';

export const CHAT_MAX_MESSAGE_LENGTH = 2000;
export const CHAT_MAX_HISTORY_TURNS = 12;
const CHAT_TIMEOUT_MS = 45_000;
const CHAT_MAX_REPLY_LENGTH = 8000;
// A single NDJSON line must stay bounded, but a personal `done` frame can carry
// a full proposed workspace draft: up to 50 accounts plus 200 bills with
// 100-character names, UUID ids, the added-id lists, and a deterministic
// preview. With every string worst-case \uXXXX-escaped that stays under ~190k
// characters, so the bound is 200k.
const CHAT_MAX_LINE_LENGTH = 200_000;
const PROPOSAL_MAX_ACCOUNTS = 50;
const PROPOSAL_MAX_BILLS = 200;
const PROPOSAL_MAX_TEXT_LENGTH = 100;
const PROJECTION_MAX_MESSAGE_LENGTH = 1000;

export interface ChatTurn {
	role: 'user' | 'model';
	text: string;
}

export interface DemoChatContext {
	horizon_days: 14 | 30 | 60;
	coverage_target: number;
	operating_buffer: number;
	funding_gap: number;
	required_liquidity_reserve: number;
	coverage_at_current_funding: number;
	obligations: Array<{ label: string; amount: number; due_in_days: number }>;
}

// Personal financial context is loaded by the server using the caller's JWT.
// The browser may supply only a horizon, never another owner's records.
export type ChatContext =
	| { source: 'personal'; horizon_days: 14 | 30 | 60 }
	| { source: 'demo'; scenario: DemoChatContext };

export interface AdditionsProjectionPreview {
	opening_balance_cents: number;
	scheduled_bills_cents: number;
	ending_balance_cents: number;
	lowest_balance_cents: number;
	additional_cash_needed_cents: number;
}

// Client copy of the shared propose_workspace_additions contract. The draft is
// a complete next snapshot (existing records preserved) that the user must
// explicitly approve before it is ever sent to PUT /workspace.
export interface WorkspaceAdditionsProposal {
	draft: WorkspaceDraft;
	added_account_ids: string[];
	added_bill_ids: string[];
	horizon_days: ProjectionHorizonDays;
	projection: AdditionsProjectionPreview | null;
	projection_error: string | null;
}

export interface ChatResponse {
	reply: string;
	source: 'personal' | 'demo';
	input_revision: number | null;
	// Present only for personal responses whose validated `done` frame carried
	// a proposal; never populated for the demo context.
	proposal?: WorkspaceAdditionsProposal;
}

type StreamFrame =
	| { type: 'delta'; text: string }
	| {
			type: 'done';
			source: 'personal' | 'demo';
			input_revision: number | null;
			proposal?: WorkspaceAdditionsProposal;
		}
	| { type: 'error'; message: string; status: number };

function isDeltaFrame(value: Record<string, unknown>): value is { type: 'delta'; text: string } {
	return typeof value.text === 'string';
}

function isDoneFrame(
	value: Record<string, unknown>,
	source: ChatContext['source']
): value is {
	type: 'done';
	source: 'personal' | 'demo';
	input_revision: number | null;
	proposal?: unknown;
} {
	return (
		value.source === source &&
		(source === 'demo'
			? value.input_revision === null
			: typeof value.input_revision === 'number' &&
				Number.isSafeInteger(value.input_revision) &&
				value.input_revision >= 0)
	);
}

function isErrorFrame(value: Record<string, unknown>): value is { type: 'error'; message: string; status: number } {
	return (
		typeof value.message === 'string' &&
		value.message.length > 0 &&
		value.message.length <= 1000 &&
		typeof value.status === 'number' &&
		Number.isSafeInteger(value.status) &&
		value.status >= 400 &&
		value.status <= 599
	);
}

function isIsoDate(value: unknown): value is string {
	if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '1900-01-01' || value > '2100-12-31') return false;
	const date = new Date(`${value}T00:00:00Z`);
	return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

function parseProposalAccount(value: unknown): CashAccount | null {
	if (typeof value !== 'object' || value === null) return null;
	const { id, name, kind, balance_cents } = value as Record<string, unknown>;
	if (typeof id !== 'string' || id.length === 0 || id.length > PROPOSAL_MAX_TEXT_LENGTH) return null;
	if (typeof name !== 'string' || name.length === 0 || name !== name.trim() || name.length > PROPOSAL_MAX_TEXT_LENGTH) {
		return null;
	}
	if (kind !== 'checking' && kind !== 'savings') return null;
	if (
		typeof balance_cents !== 'number' ||
		!Number.isSafeInteger(balance_cents) ||
		Math.abs(balance_cents) > MAX_ABS_BALANCE_CENTS
	) {
		return null;
	}
	return { id, name, kind, balance_cents };
}

function parseProposalBill(value: unknown): CashBill | null {
	if (typeof value !== 'object' || value === null) return null;
	const { id, label, amount_cents, due_date } = value as Record<string, unknown>;
	if (typeof id !== 'string' || id.length === 0 || id.length > PROPOSAL_MAX_TEXT_LENGTH) return null;
	if (typeof label !== 'string' || label.length === 0 || label !== label.trim() || label.length > PROPOSAL_MAX_TEXT_LENGTH) {
		return null;
	}
	if (
		typeof amount_cents !== 'number' ||
		!Number.isSafeInteger(amount_cents) ||
		amount_cents < 1 ||
		amount_cents > MAX_BILL_CENTS
	) {
		return null;
	}
	if (!isIsoDate(due_date)) return null;
	return { id, label, amount_cents, due_date };
}

function parseAddedIdList(value: unknown, knownIds: Set<string>): string[] | null {
	if (!Array.isArray(value) || value.length > knownIds.size) return null;
	const ids: string[] = [];
	const seen = new Set<string>();
	for (const item of value) {
		if (typeof item !== 'string' || item.length === 0 || seen.has(item) || !knownIds.has(item)) return null;
		seen.add(item);
		ids.push(item);
	}
	return ids;
}

function parseProjectionPreview(value: unknown): AdditionsProjectionPreview | null {
	if (typeof value !== 'object' || value === null) return null;
	const {
		opening_balance_cents,
		scheduled_bills_cents,
		ending_balance_cents,
		lowest_balance_cents,
		additional_cash_needed_cents
	} = value as Record<string, unknown>;
	// Aggregates can exceed a single record's cap (up to 200 bills), so each
	// field only has to be a safe integer; the two that are sums must also be
	// non-negative.
	if (
		typeof opening_balance_cents !== 'number' ||
		!Number.isSafeInteger(opening_balance_cents) ||
		typeof scheduled_bills_cents !== 'number' ||
		!Number.isSafeInteger(scheduled_bills_cents) ||
		scheduled_bills_cents < 0 ||
		typeof ending_balance_cents !== 'number' ||
		!Number.isSafeInteger(ending_balance_cents) ||
		typeof lowest_balance_cents !== 'number' ||
		!Number.isSafeInteger(lowest_balance_cents) ||
		typeof additional_cash_needed_cents !== 'number' ||
		!Number.isSafeInteger(additional_cash_needed_cents) ||
		additional_cash_needed_cents < 0
	) {
		return null;
	}
	return {
		opening_balance_cents,
		scheduled_bills_cents,
		ending_balance_cents,
		lowest_balance_cents,
		additional_cash_needed_cents
	};
}

// Strict validation of the shared proposal contract: a full next-snapshot
// draft within workspace capacity, unique server-generated ids, at least one
// added record, a valid horizon, and a projection XOR projection_error shape.
// Anything else is treated as a malformed frame, never guessed at.
export function parseWorkspaceAdditionsProposal(value: unknown): WorkspaceAdditionsProposal | null {
	if (typeof value !== 'object' || value === null) return null;
	const record = value as Record<string, unknown>;
	if (typeof record.draft !== 'object' || record.draft === null) return null;
	const { expected_revision, as_of, accounts, bills } = record.draft as Record<string, unknown>;
	if (
		typeof expected_revision !== 'number' ||
		!Number.isSafeInteger(expected_revision) ||
		expected_revision < 0 || expected_revision >= Number.MAX_SAFE_INTEGER
	) {
		return null;
	}
	if (!isIsoDate(as_of)) return null;
	if (!Array.isArray(accounts) || accounts.length > PROPOSAL_MAX_ACCOUNTS) return null;
	if (!Array.isArray(bills) || bills.length > PROPOSAL_MAX_BILLS) return null;

	const parsedAccounts: CashAccount[] = [];
	const accountIds = new Set<string>();
	for (const account of accounts) {
		const parsed = parseProposalAccount(account);
		if (!parsed || accountIds.has(parsed.id)) return null;
		accountIds.add(parsed.id);
		parsedAccounts.push(parsed);
	}
	const parsedBills: CashBill[] = [];
	const billIds = new Set<string>();
	for (const bill of bills) {
		const parsed = parseProposalBill(bill);
		if (!parsed || billIds.has(parsed.id)) return null;
		billIds.add(parsed.id);
		parsedBills.push(parsed);
	}

	const added_account_ids = parseAddedIdList(record.added_account_ids, accountIds);
	if (!added_account_ids) return null;
	const added_bill_ids = parseAddedIdList(record.added_bill_ids, billIds);
	if (!added_bill_ids) return null;
	if (added_account_ids.length + added_bill_ids.length === 0) return null;

	const horizon_days = record.horizon_days;
	if (horizon_days !== 14 && horizon_days !== 30 && horizon_days !== 60) return null;

	const projection = record.projection;
	const projection_error = record.projection_error;
	if ((projection === null) === (projection_error === null)) return null;
	let parsedProjection: AdditionsProjectionPreview | null = null;
	if (projection !== null) {
		parsedProjection = parseProjectionPreview(projection);
		if (!parsedProjection) return null;
	}
	if (
		projection_error !== null &&
		(typeof projection_error !== 'string' ||
			projection_error.length === 0 ||
			projection_error.length > PROJECTION_MAX_MESSAGE_LENGTH)
	) {
		return null;
	}

	return {
		draft: { expected_revision, as_of, accounts: parsedAccounts, bills: parsedBills },
		added_account_ids,
		added_bill_ids,
		horizon_days,
		projection: parsedProjection,
		projection_error
	};
}

// The engine emits one JSON object per NDJSON line: zero or more `delta`
// frames, then exactly one terminal `done` frame, or an `error` frame in
// place of `done`. Anything else (bad JSON, unknown type, wrong shape) is
// rejected rather than guessed at. A `done` frame may carry at most one
// strictly validated proposal, personal source only.
function parseFrame(line: string, source: ChatContext['source']): StreamFrame | null {
	let value: unknown;
	try {
		value = JSON.parse(line);
	} catch {
		return null;
	}
	if (typeof value !== 'object' || value === null) return null;
	const record = value as Record<string, unknown>;
	if (record.type === 'delta') return isDeltaFrame(record) ? record : null;
	if (record.type === 'done') {
		if (!isDoneFrame(record, source)) return null;
		const base = { type: 'done' as const, source: record.source, input_revision: record.input_revision };
		if (!('proposal' in record) || record.proposal === undefined) return base;
		if (source !== 'personal') return null;
		const proposal = parseWorkspaceAdditionsProposal(record.proposal);
		if (!proposal || proposal.draft.expected_revision !== record.input_revision) return null;
		return { ...base, proposal };
	}
	if (record.type === 'error') return isErrorFrame(record) ? record : null;
	return null;
}

export async function postChat(
	message: string,
	context: ChatContext,
	history: ChatTurn[],
	onDelta: (text: string) => void,
	signal?: AbortSignal
): Promise<EngineResult<ChatResponse>> {
	const streamResult = await requestEngineStream(
		'/chat',
		{
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ ...context, message, history }),
			signal
		},
		{ requiresAuth: true, timeoutMs: CHAT_TIMEOUT_MS }
	);
	if (streamResult.status !== 'ok') return streamResult;
	const { response, isOwnerCurrent } = streamResult.data;
	if (!response.body) {
		return { status: 'engine-error', message: 'Engine response was not a valid stream.' };
	}

	let reply = '';

	// A single NDJSON line, once fully buffered, decides the outcome of the
	// whole request: keep reading (null) or stop with a final result.
	function handleLine(line: string): EngineResult<ChatResponse> | null {
		if (signal?.aborted) {
			return { status: 'engine-unreachable', message: 'The request was cancelled.' };
		}
		if (line.length > CHAT_MAX_LINE_LENGTH) {
			return { status: 'engine-error', message: 'The assistant stream sent an oversized frame.' };
		}
		if (line.trim().length === 0) return null;
		if (!isOwnerCurrent()) {
			return { status: 'engine-error', message: 'Your account changed. Try again.', http_status: 401 };
		}
		const frame = parseFrame(line, context.source);
		if (!frame) {
			return { status: 'engine-error', message: 'The assistant stream sent a malformed message.' };
		}
		if (frame.type === 'error') {
			return { status: 'engine-error', message: frame.message, http_status: frame.status };
		}
		if (frame.type === 'delta') {
			if (reply.length + frame.text.length > CHAT_MAX_REPLY_LENGTH) {
				return { status: 'engine-error', message: 'The assistant response was too long.' };
			}
			if (frame.text.length > 0) {
				reply += frame.text;
				onDelta(frame.text);
			}
			return null;
		}
		if (reply.trim().length === 0) {
			return { status: 'engine-error', message: 'The assistant returned an empty response.' };
		}
		return {
			status: 'ok',
			data: { reply, source: frame.source, input_revision: frame.input_revision, proposal: frame.proposal }
		};
	}

	// Streams are read incrementally with a ReadableStreamDefaultReader and
	// decoded with TextDecoder's `stream: true` mode so a multi-byte UTF-8
	// character split across two chunks is buffered rather than mangled.
	// https://developer.mozilla.org/en-US/docs/Web/API/ReadableStreamDefaultReader
	// https://developer.mozilla.org/en-US/docs/Web/API/TextDecoder/decode
	const reader = response.body.getReader();
	const decoder = new TextDecoder('utf-8', { fatal: true });
	let buffer = '';
	try {
		while (true) {
			const { value, done } = await reader.read();
			try {
				buffer += decoder.decode(value, { stream: !done });
			} catch {
				return { status: 'engine-error', message: 'The assistant stream contained invalid data.' };
			}
			if (value) {
				let newlineIndex = buffer.indexOf('\n');
				while (newlineIndex !== -1) {
					const rawLine = buffer.slice(0, newlineIndex);
					buffer = buffer.slice(newlineIndex + 1);
					const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
					const outcome = handleLine(line);
					if (outcome) return outcome;
					newlineIndex = buffer.indexOf('\n');
				}
				if (buffer.length > CHAT_MAX_LINE_LENGTH) {
					return { status: 'engine-error', message: 'The assistant stream sent an oversized frame.' };
				}
			}
			if (done) {
				const trailing = buffer.trim();
				if (trailing.length > 0) {
					const outcome = handleLine(trailing);
					if (outcome) return outcome;
				}
				return { status: 'engine-error', message: 'The assistant stream ended before completing.' };
			}
		}
	} catch (error) {
		return { status: 'engine-unreachable', message: describeNetworkError(error, CHAT_TIMEOUT_MS) };
	} finally {
		// Every exit path — success, validation failure, or transport error —
		// releases the underlying connection instead of leaving it open.
		await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
}
