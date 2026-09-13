<script lang="ts">
	import { beforeNavigate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/auth.svelte';
	import FinancialHistoryCsv from '$lib/components/FinancialHistoryCsv.svelte';
	import CurrencyInput from '$lib/components/CurrencyInput.svelte';
	import { financialStore } from '$lib/finance.svelte';
	import { MAX_ABS_BALANCE_CENTS, MAX_BILL_CENTS } from '$lib/workspace';
	import {
		exportFinanceWorkspace,
		type FinanceWorkspace,
		type HistoricalTransaction
	} from '$lib/finance';
	import {
		buildPortfolioReturnCandidates,
		csvColumns,
		duplicateTransactionIndexes,
		inferPortfolioReturnMapping,
		isTransactionCategory,
		parseCsvTable,
		TRANSACTION_CATEGORIES,
		TRANSACTION_CATEGORY_LABELS,
		transactionCategorySignIssue,
		type CsvTable,
		type PortfolioReturnMapping
	} from '$lib/financial-history-csv';

	type FinanceSection = 'cash' | 'income' | 'history' | 'assumptions' | 'credit' | 'investments' | 'policy';
	type RemovalPrompt = { message: string; action: () => void };

	interface Props {
		section?: FinanceSection;
	}

	let { section = 'cash' }: Props = $props();

	const SECTIONS: Array<{ id: FinanceSection; label: string; note: string }> = [
		{ id: 'cash', label: 'Cash', note: 'Opening cash' },
		{ id: 'income', label: 'Income', note: 'Model source' },
		{ id: 'history', label: 'History', note: 'CSV & review' },
		{ id: 'assumptions', label: 'Assumptions', note: 'Variability' },
		{ id: 'credit', label: 'Credit', note: 'Actual accounts' },
		{ id: 'investments', label: 'Investments', note: 'Lots & returns' },
		{ id: 'policy', label: 'Policy', note: 'Funding rules' }
	];
	const PRIORITIES = [
		'avoid_interest_bearing_debt',
		'minimize_taxable_sales',
		'minimize_deferred_spending'
	] as const;
	const PRIORITY_LABELS: Record<(typeof PRIORITIES)[number], string> = {
		avoid_interest_bearing_debt: 'Avoid interest-bearing debt',
		minimize_taxable_sales: 'Minimize taxable sales',
		minimize_deferred_spending: 'Minimize deferred spending'
	};

	let draft = $state<FinanceWorkspace | null>(null);
	let baseSnapshot = $state<FinanceWorkspace | null>(null);
	let editorOwner = $state<string | null>(null);
	let requestOwner = $state<string | null>(null);
	let remoteWorkspace = $state<FinanceWorkspace | null>(null);
	let formElement = $state<HTMLFormElement | null>(null);
	let formIssues = $state<string[]>([]);
	let saveMessage = $state<string | null>(null);
	let reloadConfirmation = $state(false);
	let reconciliationLock = $state(false);
	let removalPrompt = $state<RemovalPrompt | null>(null);
	let historyImportPending = $state(false);
	let historyImportKey = $state(0);
	let historyPage = $state(0);
	let returnPage = $state(0);
	let returnTable = $state<CsvTable | null>(null);
	let returnMapping = $state<PortfolioReturnMapping | null>(null);
	let returnFileName = $state<string | null>(null);
	let returnImportError = $state<string | null>(null);
	let returnHasHeader = $state(true);
	let returnFileRequest = 0;
	let exportState = $state<'idle' | 'working' | 'error' | 'done'>('idle');
	let exportMessage = $state<string | null>(null);

	const HISTORY_PAGE_SIZE = 50;
	const PORTFOLIO_RETURN_PAGE_SIZE = 50;
	const MAX_HISTORY_RECORDS = 20_000;
	const MAX_CREDIT_ACCOUNTS = 100;
	const MAX_HOLDINGS = 500;
	const MAX_TAX_LOTS_PER_HOLDING = 1_000;
	const MAX_PORTFOLIO_RETURNS = 20_000;
	const MAX_TRANSACTION_DESCRIPTION_LENGTH = 500;
	const MAX_HOLDING_SYMBOL_LENGTH = 32;
	const MAX_BUFFER_TOLERANCE_DOLLAR_DAYS = 1_000_000_000_000_000;
	const draftIsDirty = $derived(
		draft !== null &&
		baseSnapshot !== null &&
		JSON.stringify($state.snapshot(draft)) !== JSON.stringify(baseSnapshot)
	);
	const pendingImport = $derived(historyImportPending || returnTable !== null);
	const editingLocked = $derived(financialStore.saving || financialStore.saveUncertain || reconciliationLock);
	const totalCashCents = $derived(
		(draft?.accounts ?? []).reduce((total, account) => total + account.balance_cents, 0)
	);
	const historyRows = $derived(draft?.inputs.transactions ?? []);
	const duplicateHistoryIndexes = $derived(duplicateTransactionIndexes(historyRows));
	const historyPageCount = $derived(Math.max(1, Math.ceil(historyRows.length / HISTORY_PAGE_SIZE)));
	const displayedHistoryRows = $derived(
		historyRows.slice(historyPage * HISTORY_PAGE_SIZE, historyPage * HISTORY_PAGE_SIZE + HISTORY_PAGE_SIZE)
	);
	const portfolioReturnPageCount = $derived(
		Math.max(1, Math.ceil((draft?.inputs.portfolio_returns.length ?? 0) / PORTFOLIO_RETURN_PAGE_SIZE))
	);
	const displayedPortfolioReturns = $derived(
		(draft?.inputs.portfolio_returns ?? []).slice(
			returnPage * PORTFOLIO_RETURN_PAGE_SIZE,
			returnPage * PORTFOLIO_RETURN_PAGE_SIZE + PORTFOLIO_RETURN_PAGE_SIZE
		)
	);
	const returnColumns = $derived(returnTable ? csvColumns(returnTable, returnHasHeader) : []);
	const returnCandidates = $derived(
		returnTable && returnMapping
			? buildPortfolioReturnCandidates(returnTable, returnHasHeader, returnMapping)
			: []
	);
	const existingReturnDates = $derived(new Set(draft?.inputs.portfolio_returns.map((entry) => entry.date) ?? []));
	const availableReturnSlots = $derived(
		Math.max(0, MAX_PORTFOLIO_RETURNS - (draft?.inputs.portfolio_returns.length ?? 0))
	);
	const reviewReturnCandidates = $derived.by(() => {
		const seenDates = new Set(existingReturnDates);
		let acceptedCount = 0;
		return returnCandidates.map((candidate) => {
			const validData = candidate.date !== null && candidate.return_decimal !== null && candidate.issues.length === 0;
			const duplicate = validData && candidate.date !== null && seenDates.has(candidate.date);
			if (validData && candidate.date !== null) seenDates.add(candidate.date);
			const valid = validData && !duplicate;
			const capacityExceeded = valid && acceptedCount >= availableReturnSlots;
			if (valid && !capacityExceeded) acceptedCount += 1;
			return { ...candidate, duplicate, capacityExceeded };
		});
	});
	const acceptedReturnCandidates = $derived(
		reviewReturnCandidates.filter(
			(candidate) =>
				candidate.date !== null &&
				candidate.return_decimal !== null &&
				candidate.issues.length === 0 &&
				!candidate.duplicate &&
				!candidate.capacityExceeded
		)
	);

	function validCalendarDate(value: string | null): value is string {
		if (value === null || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < '1900-01-01' || value > '2100-12-31') return false;
		const parsed = new Date(`${value}T00:00:00Z`);
		return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
	}

	function localCalendarDate(): string {
		const today = new Date();
		return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
	}


	function readableCents(cents: number): string {
		if (!Number.isFinite(cents)) return 'Not set';
		const sign = cents < 0 ? '−' : '';
		const digits = Math.abs(Math.trunc(cents)).toString().padStart(3, '0');
		const whole = digits.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
		return `${sign}$${whole}.${digits.slice(-2)}`;
	}

	function displayPercent(value: number): string {
		if (!Number.isFinite(value)) return '';
		const percent = Math.round(value * 100 * 10_000) / 10_000;
		return String(percent);
	}


	function applyIncomingWorkspace(workspace: FinanceWorkspace): void {
		const next = structuredClone(workspace);
		draft = structuredClone(next);
		baseSnapshot = structuredClone(next);
		remoteWorkspace = null;
		formIssues = [];
		saveMessage = null;
		reloadConfirmation = false;
		removalPrompt = null;
		reconciliationLock = false;
		historyImportPending = false;
		historyImportKey += 1;
		clearReturnImport();
		historyPage = 0;
		returnPage = 0;
	}

	function resetEditorForOwner(owner: string | null): void {
		editorOwner = owner;
		draft = null;
		baseSnapshot = null;
		remoteWorkspace = null;
		formIssues = [];
		saveMessage = null;
		reloadConfirmation = false;
		reconciliationLock = false;
		removalPrompt = null;
		historyImportPending = false;
		clearReturnImport();
		historyPage = 0;
		returnPage = 0;
	}


	function clearReturnImport(): void {
		returnFileRequest += 1;
		returnTable = null;
		returnMapping = null;
		returnFileName = null;
		returnImportError = null;
		returnHasHeader = true;
	}
	function setHistoryImportPending(pending: boolean): void {
		historyImportPending = pending;
	}


	function protectedDraft(): boolean {
		return (
			editorOwner !== null &&
			authStore.status === 'signed-in' &&
			authStore.user?.id === editorOwner &&
			(draftIsDirty || pendingImport || financialStore.saving || financialStore.saveUncertain || reconciliationLock)
		);
	}

	function navigationWarning(): string {
		if (financialStore.saving) return 'Your financial workspace is still saving. Leave this page anyway?';
		if (financialStore.saveUncertain || reconciliationLock) return 'The saved workspace needs reconciliation. Leave before reconciling it?';
		if (pendingImport) return 'A CSV review is still open. Leave and discard the unsaved import review?';
		return 'You have unsaved financial changes. Leave this page without saving them?';
	}

	function beforeUnload(event: BeforeUnloadEvent): void {
		if (!protectedDraft()) return;
		event.preventDefault();
		event.returnValue = '';
	}


	function updatePercent<T extends object>(target: T, field: keyof T, event: Event): void {
		if (editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		if (input.value.trim().length === 0) return;
		const percent = Number(input.value);
		if (!Number.isFinite(percent)) return;
		Object.assign(target, { [field]: percent / 100 });
		formIssues = [];
	}

	function updateInteger<T extends object>(target: T, field: keyof T, event: Event): void {
		if (editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		if (input.value.trim().length === 0) return;
		const value = Number(input.value);
		if (!Number.isSafeInteger(value)) return;
		Object.assign(target, { [field]: value });
		formIssues = [];
	}

	function updateNumber<T extends object>(target: T, field: keyof T, event: Event): void {
		if (editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		if (input.value.trim().length === 0) return;
		const value = Number(input.value);
		if (!Number.isFinite(value)) return;
		Object.assign(target, { [field]: value });
		formIssues = [];
	}

	function updateOptionalDate(event: Event, field: 'history_start' | 'history_end'): void {
		if (!draft || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		draft.inputs[field] = input.value.length === 0 ? null : input.value;
		formIssues = [];
	}

	function updateTolerance(event: Event): void {
		if (!draft || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		if (input.value.length === 0) {
			draft.inputs.policy.buffer_tolerance_dollar_days = null;
			formIssues = [];
			return;
		}
		const value = Number(input.value);
		if (!Number.isFinite(value)) return;
		draft.inputs.policy.buffer_tolerance_dollar_days = value;
		formIssues = [];
	}

	function addCashAccount(): void {
		if (!draft || editingLocked || draft.accounts.length >= 50) return;
		draft.accounts.push({ id: crypto.randomUUID(), name: '', kind: 'checking', balance_cents: 0 });
		formIssues = [];
	}

	function addManualTransaction(): void {
		if (!draft || editingLocked || draft.inputs.transactions.length >= MAX_HISTORY_RECORDS) return;
		draft.inputs.transactions.push({
			id: crypto.randomUUID(),
			date: draft.as_of ?? localCalendarDate(),
			description: '',
			amount_cents: Number.NaN,
			category: 'expense_essential_variable',
			source_key: null
		});
		historyPage = Math.max(0, Math.ceil(draft.inputs.transactions.length / HISTORY_PAGE_SIZE) - 1);
		formIssues = [];
	}

	function appendImportedTransactions(transactions: HistoricalTransaction[]): void {
		if (!draft || editingLocked || transactions.length === 0) return;
		const space = Math.max(0, MAX_HISTORY_RECORDS - draft.inputs.transactions.length);
		if (space === 0) {
			formIssues = ['The saved history limit is 20,000 transactions. Remove entries before applying more.'];
			return;
		}
		draft.inputs.transactions.push(...transactions.slice(0, space));
		historyPage = Math.max(0, Math.ceil(draft.inputs.transactions.length / HISTORY_PAGE_SIZE) - 1);
		formIssues = [];
	}

	function addCreditAccount(): void {
		if (!draft || editingLocked || draft.inputs.credit_accounts.length >= MAX_CREDIT_ACCOUNTS) return;
		draft.inputs.credit_accounts.push({
			id: crypto.randomUUID(),
			name: '',
			credit_limit_cents: 0,
			current_balance_cents: 0,
			purchase_apr: 0,
			statement_close_day: 1,
			payment_due_day: 1,
			grace_period_eligible: false,
			minimum_payment_cents: 0
		});
		formIssues = [];
	}

	function addHolding(): void {
		if (!draft || editingLocked || draft.inputs.holdings.length >= MAX_HOLDINGS) return;
		draft.inputs.holdings.push({
			id: crypto.randomUUID(),
			symbol: '',
			account: 'taxable',
			current_price_cents: 0,
			tax_lots: []
		});
		formIssues = [];
	}

	function addTaxLot(holdingId: string): void {
		if (!draft || editingLocked) return;
		const holding = draft.inputs.holdings.find((candidate) => candidate.id === holdingId);
		if (!holding || holding.tax_lots.length >= MAX_TAX_LOTS_PER_HOLDING) return;
		holding.tax_lots.push({
			id: crypto.randomUUID(),
			quantity: Number.NaN,
			cost_basis_per_share_cents: Number.NaN,
			purchase_date: ''
		});
		formIssues = [];
	}

	function addPortfolioReturn(): void {
		if (!draft || editingLocked || draft.inputs.portfolio_returns.length >= MAX_PORTFOLIO_RETURNS) return;
		draft.inputs.portfolio_returns.push({
			date: draft.as_of ?? localCalendarDate(),
			return_decimal: Number.NaN
		});
		returnPage = Math.max(0, Math.ceil(draft.inputs.portfolio_returns.length / PORTFOLIO_RETURN_PAGE_SIZE) - 1);
		formIssues = [];
	}

	function movePriority(index: number, direction: -1 | 1): void {
		if (!draft || editingLocked) return;
		const nextIndex = index + direction;
		if (nextIndex < 0 || nextIndex >= draft.inputs.policy.priorities.length) return;
		const priorities = [...draft.inputs.policy.priorities];
		const current = priorities[index];
		const next = priorities[nextIndex];
		if (!current || !next) return;
		priorities[index] = next;
		priorities[nextIndex] = current;
		draft.inputs.policy.priorities = priorities;
		formIssues = [];
	}

	function addPriority(): void {
		if (!draft || editingLocked || draft.inputs.policy.priorities.length >= PRIORITIES.length) return;
		const priorities = draft.inputs.policy.priorities;
		const priority = PRIORITIES.find((candidate) => !priorities.includes(candidate));
		if (!priority) return;
		draft.inputs.policy.priorities = [...draft.inputs.policy.priorities, priority];
		formIssues = [];
	}

	function removePriority(index: number): void {
		if (!draft || editingLocked || draft.inputs.policy.priorities.length <= 1) return;
		draft.inputs.policy.priorities = draft.inputs.policy.priorities.filter((_, candidateIndex) => candidateIndex !== index);
		formIssues = [];
	}

	function askRemoval(message: string, action: () => void): void {
		if (editingLocked) return;
		removalPrompt = { message, action };
	}

	function confirmRemoval(): void {
		if (!removalPrompt || editingLocked) return;
		removalPrompt.action();
		removalPrompt = null;
		formIssues = [];
	}

	function changeReturnHeader(event: Event): void {
		if (!returnTable || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		returnHasHeader = input.checked;
		returnMapping = inferPortfolioReturnMapping(returnTable, returnHasHeader);
	}

	function changeReturnColumn(field: 'date' | 'returnValue', event: Event): void {
		if (!returnMapping || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLSelectElement)) return;
		const index = input.value === '' ? null : Number(input.value);
		if (index !== null && (!Number.isInteger(index) || index < 0)) return;
		returnMapping[field] = index;
	}

	function changeReturnDateOrder(event: Event): void {
		if (!returnMapping || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLSelectElement)) return;
		if (!['year-month-day', 'month-day-year', 'day-month-year'].includes(input.value)) return;
		returnMapping.dateOrder = input.value as PortfolioReturnMapping['dateOrder'];
	}

	function changeReturnInterpretation(event: Event): void {
		if (!returnMapping || editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLSelectElement)) return;
		if (input.value !== 'decimal' && input.value !== 'percent') return;
		returnMapping.returnInterpretation = input.value;
	}

	async function chooseReturnFile(event: Event): Promise<void> {
		if (editingLocked) return;
		const input = event.currentTarget;
		if (!(input instanceof HTMLInputElement)) return;
		const file = input.files?.[0];
		if (!file) return;
		const request = ++returnFileRequest;
		returnImportError = null;
		try {
			const parsed = parseCsvTable(await file.text());
			if (request !== returnFileRequest) return;
			if (!parsed.table) {
				clearReturnImport();
				returnImportError = parsed.error;
				return;
			}
			returnTable = parsed.table;
			returnHasHeader = true;
			returnMapping = inferPortfolioReturnMapping(parsed.table, true);
			returnFileName = file.name;
		} catch {
			if (request !== returnFileRequest) return;
			clearReturnImport();
			returnImportError = 'The return CSV could not be read. Choose a text CSV with a date and one daily-return column.';
		} finally {
			input.value = '';
		}
	}

	function applyPortfolioReturns(): void {
		if (!draft || editingLocked || acceptedReturnCandidates.length === 0) return;
		draft.inputs.portfolio_returns.push(
			...acceptedReturnCandidates.flatMap((candidate) =>
				candidate.date === null || candidate.return_decimal === null
					? []
					: [{ date: candidate.date, return_decimal: candidate.return_decimal }]
			)
		);
		returnPage = Math.max(0, Math.ceil(draft.inputs.portfolio_returns.length / PORTFOLIO_RETURN_PAGE_SIZE) - 1);
		clearReturnImport();
		formIssues = [];
	}

	function validateWorkspace(): FinanceWorkspace | null {
		if (!draft) return null;
		const candidate = structuredClone($state.snapshot(draft));
		const issues: string[] = [];
		if (!validCalendarDate(candidate.as_of)) issues.push('Cash needs an opening-of-day date from 1900 through 2100 before you can save.');
		if (candidate.accounts.length > 50) issues.push('Cash supports up to 50 accounts.');
		const accountIds = new Set<string>();
		candidate.accounts.forEach((account, index) => {
			if (accountIds.has(account.id)) issues.push(`Cash account ${index + 1} has a duplicate identifier.`);
			accountIds.add(account.id);
			if (account.name.trim().length === 0 || account.name.length > 100 || account.name !== account.name.trim()) {
				issues.push(`Cash account ${index + 1} needs a trimmed name of up to 100 characters.`);
			}
			if (account.kind !== 'checking' && account.kind !== 'savings') issues.push(`Cash account ${index + 1} needs a valid account kind.`);
			if (!Number.isSafeInteger(account.balance_cents) || Math.abs(account.balance_cents) > MAX_ABS_BALANCE_CENTS) {
				issues.push(`Cash account ${index + 1} needs an exact USD balance within the supported range.`);
			}
		});

		const inputs = candidate.inputs;
		if (!['scheduled', 'assumptions', 'history'].includes(inputs.mode)) issues.push('Choose a valid model source.');
		if (inputs.transactions.length > MAX_HISTORY_RECORDS) issues.push('History supports up to 20,000 transactions.');
		const transactionIds = new Set<string>();
		inputs.transactions.forEach((transaction, index) => {
			if (transactionIds.has(transaction.id)) issues.push(`History row ${index + 1} has a duplicate identifier.`);
			transactionIds.add(transaction.id);
			if (!validCalendarDate(transaction.date)) issues.push(`History row ${index + 1} needs a calendar date from 1900 through 2100.`);
			if (
				transaction.description.trim().length === 0 ||
				transaction.description.length > MAX_TRANSACTION_DESCRIPTION_LENGTH ||
				transaction.description !== transaction.description.trim()
			) {
				issues.push(`History row ${index + 1} needs a trimmed description of up to ${MAX_TRANSACTION_DESCRIPTION_LENGTH} characters.`);
			}
			if (
				transaction.source_key !== null &&
				(transaction.source_key.trim().length === 0 || transaction.source_key.length > 200 || transaction.source_key !== transaction.source_key.trim())
			) {
				issues.push(`History row ${index + 1} has an invalid source key.`);
			}
			if (!Number.isSafeInteger(transaction.amount_cents) || Math.abs(transaction.amount_cents) > MAX_ABS_BALANCE_CENTS) {
				issues.push(`History row ${index + 1} needs an exact signed USD amount within the supported range.`);
			}
			if (!isTransactionCategory(transaction.category)) issues.push(`History row ${index + 1} needs a valid classification.`);
			if (isTransactionCategory(transaction.category) && Number.isSafeInteger(transaction.amount_cents)) {
				const signIssue = transactionCategorySignIssue(transaction.category, transaction.amount_cents);
				if (signIssue) issues.push(`History row ${index + 1}: ${signIssue}`);
			}
		});
		if (inputs.history_start !== null && !validCalendarDate(inputs.history_start)) issues.push('History coverage start must be a calendar date from 1900 through 2100.');
		if (inputs.history_end !== null && !validCalendarDate(inputs.history_end)) issues.push('History coverage end must be a calendar date from 1900 through 2100.');
		if (inputs.history_start && inputs.history_end && inputs.history_start > inputs.history_end) {
			issues.push('History coverage start cannot be after its end.');
		}
		if (inputs.mode === 'history') {
			if (!inputs.history_start || !inputs.history_end) issues.push('History mode needs a stated coverage start and end date.');
			if (!inputs.history_complete) issues.push('Confirm that the stated history coverage is complete before choosing history mode.');
			if (inputs.transactions.length === 0) issues.push('History mode needs classified transactions.');
		}

		const assumptions = inputs.assumptions;
		const monthlyMoneyInputs: Array<[string, number]> = [
			['Variable income', assumptions.monthly_variable_income_cents],
			['Essential spending', assumptions.monthly_essential_spending_cents],
			['Discretionary spending', assumptions.monthly_discretionary_spending_cents]
		];
		monthlyMoneyInputs.forEach(([label, value]) => {
			if (!Number.isSafeInteger(value) || value < 0 || value > MAX_BILL_CENTS) {
				issues.push(`${label} must be a nonnegative exact USD amount within the supported range.`);
			}
		});
		if (assumptions.income_variability_pct < 0 || assumptions.income_variability_pct > 2 || !Number.isFinite(assumptions.income_variability_pct)) issues.push('Income variability must be between 0% and 200%.');
		if (assumptions.spending_variability_pct < 0 || assumptions.spending_variability_pct > 2 || !Number.isFinite(assumptions.spending_variability_pct)) issues.push('Spending variability must be between 0% and 200%.');
		if (!Number.isSafeInteger(assumptions.persistence_days) || assumptions.persistence_days < 1 || assumptions.persistence_days > 30) issues.push('Persistence must be an integer from 1 to 30 days.');
		const modelCorrelations: Array<[string, number]> = [
			['Income/spending correlation', assumptions.income_spending_correlation],
			['Income/market correlation', assumptions.income_market_correlation]
		];
		modelCorrelations.forEach(([label, value]) => {
			if (!Number.isFinite(value) || value < -0.95 || value > 0.95) issues.push(`${label} must be between −0.95 and 0.95.`);
		});
		if (!Number.isFinite(assumptions.expected_annual_return_pct) || assumptions.expected_annual_return_pct < -0.99 || assumptions.expected_annual_return_pct > 2) issues.push('Expected annual return must be between −99% and 200%.');
		if (!Number.isFinite(assumptions.annual_return_volatility_pct) || assumptions.annual_return_volatility_pct < 0 || assumptions.annual_return_volatility_pct > 2) issues.push('Annual return volatility must be between 0% and 200%.');

		if (inputs.credit_accounts.length > MAX_CREDIT_ACCOUNTS) issues.push('Credit supports up to 100 accounts.');
		const creditIds = new Set<string>();
		inputs.credit_accounts.forEach((account, index) => {
			if (creditIds.has(account.id)) issues.push(`Credit account ${index + 1} has a duplicate identifier.`);
			creditIds.add(account.id);
			if (account.name.trim().length === 0 || account.name.length > 100 || account.name !== account.name.trim()) {
				issues.push(`Credit account ${index + 1} needs a trimmed name of up to 100 characters.`);
			}
			if (!Number.isSafeInteger(account.credit_limit_cents) || account.credit_limit_cents < 0 || account.credit_limit_cents > MAX_ABS_BALANCE_CENTS) {
				issues.push(`Credit account ${index + 1} needs a nonnegative credit limit within the supported range.`);
			}
			if (!Number.isSafeInteger(account.current_balance_cents) || account.current_balance_cents < 0 || account.current_balance_cents > MAX_ABS_BALANCE_CENTS) {
				issues.push(`Credit account ${index + 1} needs a nonnegative current balance within the supported range.`);
			}
			if (!Number.isFinite(account.purchase_apr) || account.purchase_apr < 0 || account.purchase_apr > 1) issues.push(`Credit account ${index + 1} needs an APR from 0% to 100%.`);
			if (!Number.isSafeInteger(account.statement_close_day) || account.statement_close_day < 1 || account.statement_close_day > 28) issues.push(`Credit account ${index + 1} needs a statement close day from 1 to 28.`);
			if (!Number.isSafeInteger(account.payment_due_day) || account.payment_due_day < 1 || account.payment_due_day > 28) issues.push(`Credit account ${index + 1} needs a payment due day from 1 to 28.`);
			if (!Number.isSafeInteger(account.minimum_payment_cents) || account.minimum_payment_cents < 0 || account.minimum_payment_cents > MAX_ABS_BALANCE_CENTS) {
				issues.push(`Credit account ${index + 1} needs a nonnegative minimum payment within the supported range.`);
			}
		});

		if (inputs.holdings.length > MAX_HOLDINGS) issues.push('Investments support up to 500 holdings.');
		const holdingIds = new Set<string>();
		const lotIds = new Set<string>();
		let aggregateHoldingValueCents = 0;
		let aggregateCostBasisCents = 0;
		inputs.holdings.forEach((holding, holdingIndex) => {
			if (holdingIds.has(holding.id)) issues.push(`Holding ${holdingIndex + 1} has a duplicate identifier.`);
			holdingIds.add(holding.id);
			if (holding.symbol.trim().length === 0 || holding.symbol.length > MAX_HOLDING_SYMBOL_LENGTH || holding.symbol !== holding.symbol.trim()) {
				issues.push(`Holding ${holdingIndex + 1} needs a trimmed symbol of up to ${MAX_HOLDING_SYMBOL_LENGTH} characters.`);
			}
			if (holding.account !== 'taxable' && holding.account !== 'retirement') issues.push(`Holding ${holdingIndex + 1} needs an account type.`);
			if (!Number.isSafeInteger(holding.current_price_cents) || holding.current_price_cents <= 0 || holding.current_price_cents > MAX_BILL_CENTS) {
				issues.push(`Holding ${holdingIndex + 1} needs a positive current price within the supported range.`);
			}
			if (holding.tax_lots.length > MAX_TAX_LOTS_PER_HOLDING) issues.push(`Holding ${holdingIndex + 1} supports up to 1,000 tax lots.`);
			holding.tax_lots.forEach((lot, lotIndex) => {
				if (lotIds.has(lot.id)) issues.push(`Tax lot ${holdingIndex + 1}.${lotIndex + 1} has a duplicate identifier.`);
				lotIds.add(lot.id);
				if (!Number.isFinite(lot.quantity) || lot.quantity <= 0 || lot.quantity > 1_000_000_000_000) issues.push(`Tax lot ${holdingIndex + 1}.${lotIndex + 1} needs a positive quantity within the supported range.`);
				if (!Number.isSafeInteger(lot.cost_basis_per_share_cents) || lot.cost_basis_per_share_cents < 0 || lot.cost_basis_per_share_cents > MAX_BILL_CENTS) {
					issues.push(`Tax lot ${holdingIndex + 1}.${lotIndex + 1} needs a nonnegative per-share cost basis within the supported range.`);
				}
				if (!validCalendarDate(lot.purchase_date)) issues.push(`Tax lot ${holdingIndex + 1}.${lotIndex + 1} needs a calendar purchase date from 1900 through 2100.`);
				const marketValueCents = holding.current_price_cents * lot.quantity;
				const costBasisCents = lot.cost_basis_per_share_cents * lot.quantity;
				if (Number.isFinite(marketValueCents)) aggregateHoldingValueCents += marketValueCents;
				if (Number.isFinite(costBasisCents)) aggregateCostBasisCents += costBasisCents;
			});
		});
		if (aggregateHoldingValueCents > MAX_ABS_BALANCE_CENTS || aggregateCostBasisCents > MAX_ABS_BALANCE_CENTS) {
			issues.push('Aggregate holding market value and tax-lot cost basis must each stay at or below $1,000,000,000.');
		}

		if (inputs.portfolio_returns.length > MAX_PORTFOLIO_RETURNS) issues.push('Portfolio return history supports up to 20,000 dates.');
		const returnDates = new Set<string>();
		inputs.portfolio_returns.forEach((entry, index) => {
			if (!validCalendarDate(entry.date)) issues.push(`Portfolio return ${index + 1} needs a calendar date from 1900 through 2100.`);
			if (returnDates.has(entry.date)) issues.push(`Portfolio return ${index + 1} duplicates a date.`);
			returnDates.add(entry.date);
			if (!Number.isFinite(entry.return_decimal) || entry.return_decimal < -1 || entry.return_decimal > 100) {
				issues.push(`Portfolio return ${index + 1} must be between −100% and 10,000%.`);
			}
		});

		const policy = inputs.policy;
		if (!Number.isSafeInteger(policy.operating_buffer_cents) || policy.operating_buffer_cents < 0 || policy.operating_buffer_cents > MAX_ABS_BALANCE_CENTS) {
			issues.push('Operating buffer must be a nonnegative exact USD amount within the supported range.');
		}
		if (!Number.isFinite(policy.coverage_target) || policy.coverage_target <= 0 || policy.coverage_target > 1) {
			issues.push('Coverage target must be greater than 0% and no more than 100%.');
		}
		const percentagePolicyInputs: Array<[string, number]> = [
			['Maximum credit utilization', policy.max_credit_utilization],
			['Capital-gains rate', policy.capital_gains_rate],
			['Overdraft APR', policy.overdraft_apr],
			['Shortfall probability', inputs.alerts.shortfall_probability]
		];
		percentagePolicyInputs.forEach(([label, value]) => {
			if (!Number.isFinite(value) || value < 0 || value > 1) issues.push(`${label} must be between 0% and 100%.`);
		});
		if (!Number.isSafeInteger(policy.settlement_days) || policy.settlement_days < 0 || policy.settlement_days > 30) issues.push('Settlement days must be a whole number from 0 to 30.');
		if (!Number.isSafeInteger(policy.external_transfer_days) || policy.external_transfer_days < 0 || policy.external_transfer_days > 30) issues.push('External transfer days must be a whole number from 0 to 30.');
		if (
			policy.buffer_tolerance_dollar_days !== null &&
			(!Number.isFinite(policy.buffer_tolerance_dollar_days) ||
				policy.buffer_tolerance_dollar_days < 0 ||
				policy.buffer_tolerance_dollar_days > MAX_BUFFER_TOLERANCE_DOLLAR_DAYS)
		) {
			issues.push('Buffer tolerance must be blank or a nonnegative dollar-day amount within the supported range.');
		}
		if (policy.lot_selection !== 'fifo' && policy.lot_selection !== 'hifo') issues.push('Choose FIFO or HIFO for lot selection.');
		if (
			policy.priorities.length < 1 ||
			policy.priorities.length > PRIORITIES.length ||
			new Set(policy.priorities).size !== policy.priorities.length ||
			!policy.priorities.every((priority) => PRIORITIES.includes(priority))
		) {
			issues.push('Add one to three unique funding priorities.');
		}
		if (!Number.isSafeInteger(inputs.alerts.stale_after_days) || inputs.alerts.stale_after_days < 1 || inputs.alerts.stale_after_days > 3_650) {
			issues.push('Alert freshness must be a whole number from 1 to 3,650 days.');
		}
		if (new TextEncoder().encode(JSON.stringify(inputs)).byteLength > 4_000_000) {
			issues.push('Supplemental financial inputs exceed the 4 MB saved-workspace limit. Remove or shorten history before saving.');
		}

		formIssues = issues;
		return issues.length === 0 ? candidate : null;
	}

	async function saveWorkspace(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!draft || editingLocked) return;
		if (pendingImport) {
			formIssues = ['Apply or clear each open CSV review before saving. CSV files are intentionally never saved automatically.'];
			return;
		}
		if (formElement && !formElement.reportValidity()) return;
		const candidate = validateWorkspace();
		if (!candidate) return;
		saveMessage = null;
		const saved = await financialStore.saveWorkspace(candidate);
		if (saved && financialStore.workspace) {
			applyIncomingWorkspace(financialStore.workspace);
			saveMessage = 'Saved your complete financial workspace.';
			return;
		}
		if (financialStore.requiresReconciliation) reconciliationLock = true;
		formIssues = financialStore.error ? [financialStore.error] : ['The workspace was not saved. Your local draft is still here.'];
	}

	function requestReload(): void {
		if (financialStore.saving) return;
		if (protectedDraft()) {
			reloadConfirmation = true;
			return;
		}
		void reloadSavedWorkspace();
	}

	async function reloadSavedWorkspace(): Promise<void> {
		if (financialStore.saving) return;
		reloadConfirmation = false;
		await financialStore.reload();
		if (financialStore.status === 'ready' && financialStore.workspace) {
			applyIncomingWorkspace(financialStore.workspace);
			return;
		}
		if (financialStore.error) formIssues = [financialStore.error];
	}

	async function exportCurrentWorkspace(): Promise<void> {
		if (exportState === 'working') return;
		exportState = 'working';
		exportMessage = null;
		try {
			const result = await exportFinanceWorkspace();
			if (result.status !== 'ok') {
				exportState = 'error';
				exportMessage = result.message;
				return;
			}
			const payload = JSON.stringify(result.data, null, 2);
			const blob = new Blob([payload], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `ginseng-financial-workspace-${result.data.as_of ?? 'export'}.json`;
			document.body.append(link);
			link.click();
			link.remove();
			window.setTimeout(() => URL.revokeObjectURL(url), 0);
			exportState = 'done';
			exportMessage = 'Downloaded the current saved workspace.';
		} catch {
			exportState = 'error';
			exportMessage = 'The saved workspace could not be exported. Check the connection and try again.';
		}
	}

	beforeNavigate((navigation) => {
		if (!protectedDraft()) return;
		const staysOnDataPage = navigation.to?.url.pathname === navigation.from?.url.pathname;
		if (staysOnDataPage && !pendingImport) return;
		if (!window.confirm(navigationWarning())) navigation.cancel();
	});

	$effect(() => {
		const owner = authStore.user?.id ?? null;
		if (authStore.status !== 'signed-in' || !owner) {
			if (editorOwner !== null || draft !== null) resetEditorForOwner(null);
			requestOwner = null;
			return;
		}
		if (owner !== requestOwner) {
			requestOwner = owner;
			void financialStore.load();
		}
		if (owner !== editorOwner) {
			resetEditorForOwner(owner);
			return;
		}
		const workspace = financialStore.workspace;
		if (!workspace) return;
		if (!draft || !baseSnapshot) {
			applyIncomingWorkspace(workspace);
			return;
		}
		if (workspace.revision !== baseSnapshot.revision) {
			if (draftIsDirty || pendingImport || financialStore.saving || financialStore.saveUncertain || reconciliationLock) {
				remoteWorkspace = structuredClone(workspace);
				reconciliationLock = true;
				return;
			}
			applyIncomingWorkspace(workspace);
		}
	});

	$effect(() => {
		if (financialStore.requiresReconciliation) reconciliationLock = true;
	});
</script>

<svelte:window onbeforeunload={beforeUnload} />

{#if authStore.status === 'unconfigured'}
	<section class="state-screen" aria-labelledby="data-unavailable-title">
		<p class="eyebrow">Personal data</p>
		<h1 id="data-unavailable-title">Personal data is not available in this build.</h1>
		<p>Sign-in and the finance service must be configured before Ginseng can load or save your workspace. No balance or forecast is shown as a fallback.</p>
	</section>
{:else if authStore.status !== 'signed-in'}
	<section class="state-screen" aria-labelledby="data-signin-title">
		<p class="eyebrow">Personal data</p>
		<h1 id="data-signin-title">Sign in to work with your financial data.</h1>
		<p>Your cash, history, credit, investments, and policy stay in your own authenticated workspace.</p>
		<a class="button button--primary" href={resolve('/login')}>Sign in</a>
	</section>
{:else if financialStore.status === 'loading' && !draft}
	<section class="state-screen" role="status" aria-live="polite">
		<p class="eyebrow">Personal data</p>
		<h1>Loading your financial workspace</h1>
		<p>Loading your saved opening cash and supplemental planning inputs.</p>
	</section>
{:else if financialStore.status === 'error' && !draft}
	<section class="state-screen state-screen--error" role="alert" aria-labelledby="data-error-title">
		<p class="eyebrow">Personal data</p>
		<h1 id="data-error-title">Saved financial data is unavailable</h1>
		<p>{financialStore.error ?? 'The workspace could not be loaded.'}</p>
		<button type="button" class="button button--primary" onclick={requestReload}>Retry loading</button>
	</section>
{:else if draft}
	{#key draft}
	<div class="data-workbench">
		<header class="data-toolbar">
			<div class="toolbar-identity">
				<p class="terminal-name">Financial data</p>
				<span>one saved workspace · USD</span>
			</div>
			<div class="toolbar-summary" aria-label="Current data summary">
				<span>{readableCents(totalCashCents)} opening cash</span>
				<span>{historyRows.length.toLocaleString()} history rows</span>
				<span>{draft.inputs.mode} model source</span>
			</div>
			<p class:toolbar-state--dirty={draftIsDirty || pendingImport} class="toolbar-state" role="status" aria-live="polite">
				{financialStore.saving ? 'Saving workspace' : financialStore.saveUncertain ? 'Save not acknowledged' : reconciliationLock ? 'Reconcile saved workspace' : pendingImport ? 'CSV review open' : draftIsDirty ? 'Unsaved changes' : 'Saved workspace'}
			</p>
		</header>

		{#if financialStore.status === 'loading'}
			<p class="notice" role="status" aria-live="polite">Refreshing the saved workspace. Your local draft remains on screen until you explicitly reconcile it.</p>
		{/if}
		{#if financialStore.error}
			<div class="notice notice--error" role="alert"><span>{financialStore.error}</span>{#if !financialStore.saving}<button type="button" class="text-button" onclick={requestReload}>Reload saved workspace</button>{/if}</div>
		{/if}
		{#if saveMessage && !draftIsDirty && !pendingImport}<p class="notice notice--success" role="status" aria-live="polite">{saveMessage}</p>{/if}
		{#if remoteWorkspace}
			<div class="notice notice--error" role="alert"><span>A newer saved revision is available. This form still holds your local draft; reload only when you are ready to discard and reconcile it.</span><button type="button" class="text-button" onclick={requestReload}>Reconcile</button></div>
		{/if}
		{#if reloadConfirmation}
			<section class="confirmation" role="alert" aria-labelledby="reload-title">
				<h2 id="reload-title">Discard this local draft and reconcile?</h2>
				<p>Reloading replaces every unsaved entry and CSV review with the current saved workspace. It is the only safe action after a conflict or unknown save acknowledgement.</p>
				<div><button type="button" class="button button--danger" onclick={reloadSavedWorkspace}>Discard draft and reload</button><button type="button" class="button button--quiet" onclick={() => (reloadConfirmation = false)}>Keep this draft</button></div>
			</section>
		{/if}
		{#if removalPrompt}
			<section class="confirmation confirmation--remove" role="alert">
				<p>{removalPrompt.message} It remains saved until you save this workspace.</p>
				<div><button type="button" class="button button--danger" onclick={confirmRemoval}>Remove from draft</button><button type="button" class="button button--quiet" onclick={() => (removalPrompt = null)}>Cancel</button></div>
			</section>
		{/if}
		{#if formIssues.length > 0}
			<section class="validation-summary" role="alert" aria-labelledby="validation-title">
				<strong id="validation-title">Check these fields before saving</strong>
				<ul>{#each formIssues as issue (issue)}<li>{issue}</li>{/each}</ul>
			</section>
		{/if}

		<div class="editor-layout">
			<nav class="section-index" aria-label="Financial data sections">
				<p>Data ledger</p>
				{#each SECTIONS as item (item.id)}
					<a class:active={section === item.id} href={`${resolve('/data')}?section=${item.id}#${item.id}`} aria-current={section === item.id ? 'page' : undefined}>
						<strong>{item.label}</strong><span>{item.note}</span>
					</a>
				{/each}
				<div class="index-note"><strong>Manual only</strong><span>CSV and direct entry are supported. Ginseng never connects to your bank.</span></div>
			</nav>

			<form class="financial-form" bind:this={formElement} onsubmit={saveWorkspace} oninput={() => { formIssues = []; }}>
				<fieldset disabled={editingLocked}>
					{#if section === 'cash'}
						<section id="cash" class="form-section" aria-labelledby="cash-title">
							<header class="section-heading">
								<div><p class="eyebrow">Opening-of-day reconciliation</p><h1 id="cash-title">Opening cash balances</h1><p>Set the settled cash that belongs to one opening calendar day. Importing history never changes this number.</p></div>
								<dl class="section-stats"><div><dt>Opening cash</dt><dd>{readableCents(totalCashCents)}</dd></div><div><dt>Scheduled bills</dt><dd>{draft.bills.length}</dd></div></dl>
							</header>
							<div class="callout"><strong>Manual, not connected.</strong><span>There is no bank connection in personal workspaces. The Nessie provider remains a separate synthetic example, never a source for your saved finances.</span><a href={resolve('/demo')}>Open the synthetic example</a></div>
							<div class="field-grid field-grid--opening">
								<label class="field"><span>Balances reflect the opening of</span><input type="date" min="1900-01-01" max="2100-12-31" bind:value={draft.as_of} required /><small>All accounts share this opening-of-day date.</small></label>
								<div class="reconciliation-note"><strong>History does not rewrite cash</strong><p>Use a clearly classified <em>Transfer</em> if your records explain the bridge to this opening balance. We never treat imported transactions as extra income or silently adjust accounts.</p></div>
							</div>
							<div class="ledger-block">
								<div class="ledger-head"><span>Cash account</span><span>Kind</span><span>Settled balance (USD)</span><span></span></div>
								{#each draft.accounts as account, index (account.id)}
									<div class="ledger-row">
										<label class="field" data-label="Cash account"><span class="sr-only">Cash account {index + 1} name</span><input maxlength="100" placeholder="e.g. Main checking" bind:value={account.name} required /></label>
										<label class="field" data-label="Kind"><span class="sr-only">Cash account {index + 1} kind</span><select bind:value={account.kind}><option value="checking">Checking</option><option value="savings">Savings</option></select></label>
										<label class="field" data-label="Settled balance (USD)"><span class="sr-only">Cash account {index + 1} settled balance in US dollars</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`-?[0-9]+(?:\.[0-9]{1,2})?`} bind:value={account.balance_cents} placeholder="0.00" required /></label>
										<button type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove ${account.name.trim() || `cash account ${index + 1}`} from this draft?`, () => { if (draft) draft.accounts = draft.accounts.filter((candidate) => candidate.id !== account.id); })}>Remove</button>
									</div>
								{/each}
							</div>
							{#if draft.accounts.length === 0}<p class="empty-copy">No cash account has been entered. Add a settled checking or savings account before running a personal forecast.</p>{/if}
							<button type="button" class="button button--quiet" onclick={addCashAccount} disabled={draft.accounts.length >= 50}>Add cash account</button>

							<section class="linked-data" aria-labelledby="cash-events-title">
								<div><p class="eyebrow">One authoritative event editor</p><h2 id="cash-events-title">Scheduled bills live on Events.</h2><p>These outflows are preserved in the same workspace but stay read-only here, so one-time schedules, recurrence, and settlement history have one place to edit.</p></div>
								<a class="button button--primary" href={resolve('/future')}>Manage cash events</a>
							</section>
							{#if draft.bills.length > 0}
								<ul class="event-strip" aria-label="Saved scheduled cash bills">{#each draft.bills as bill (bill.id)}<li><span>{bill.due_date}</span><strong>{bill.label}</strong><em>{readableCents(bill.amount_cents)}</em></li>{/each}</ul>
							{:else}<p class="empty-copy">No scheduled bills are saved yet. Add actual obligations on Events; no bill is assumed here.</p>{/if}
						</section>
					{:else if section === 'income'}
						<section id="income" class="form-section" aria-labelledby="income-title">
							<header class="section-heading"><div><p class="eyebrow">Choose the model source deliberately</p><h1 id="income-title">Choose the forecast source</h1><p>Scheduled is the conservative default. It stays in effect until you explicitly select assumptions or history.</p></div></header>
							<div class="mode-grid" role="radiogroup" aria-label="Forecast model source">
								<label class:mode-card--selected={draft.inputs.mode === 'scheduled'} class="mode-card"><input type="radio" name="mode" value="scheduled" bind:group={draft.inputs.mode} /><strong>Scheduled</strong><span>Use known income and bills only. Forecasts are deterministic, not a probability claim.</span></label>
								<label class:mode-card--selected={draft.inputs.mode === 'assumptions'} class="mode-card"><input type="radio" name="mode" value="assumptions" bind:group={draft.inputs.mode} /><strong>Assumptions</strong><span>Use explicitly reviewed monthly income, spending, and variability.</span></label>
								<label class:mode-card--selected={draft.inputs.mode === 'history'} class="mode-card"><input type="radio" name="mode" value="history" bind:group={draft.inputs.mode} /><strong>History</strong><span>Use actual classified daily history with a declared complete coverage window.</span></label>
							</div>
							<div class="linked-data">
								<div><p class="eyebrow">Scheduled income events</p><h2>Income schedules live on Events.</h2><p>Enter actual income labels, positive amounts, dates, recurrence, and received/skip states in one authoritative event editor. This page preserves them but does not create a competing list.</p></div>
								<a class="button button--primary" href={resolve('/future')}>Manage income events</a>
							</div>
							<details class="explanation"><summary>Why the source matters</summary><div><p><strong>Scheduled</strong> uses only settled opening cash plus known events. <strong>Assumptions</strong> does not invent past transactions. <strong>History</strong> never fills sparse records with synthetic assumptions; it asks for the missing coverage instead.</p></div></details>
						</section>
					{:else if section === 'history'}
						<section id="history" class="form-section" aria-labelledby="history-title">
							<header class="section-heading"><div><p class="eyebrow">Actual historical records</p><h1 id="history-title">Transaction history</h1><p>Classify every imported row, declare what period is covered, and make completeness a conscious confirmation.</p></div><dl class="section-stats"><div><dt>Stored rows</dt><dd>{historyRows.length.toLocaleString()}</dd></div><div><dt>Capacity</dt><dd>{Math.max(0, MAX_HISTORY_RECORDS - historyRows.length).toLocaleString()} left</dd></div></dl></header>
							<div class="reconciliation-note reconciliation-note--wide"><strong>Cash/history reconciliation is explicit</strong><p>Your saved opening cash is <b>{readableCents(totalCashCents)}</b> as of <b>{draft.as_of ?? 'an unset date'}</b>. Historical import never mutates it. A user-classified transfer can document reconciliation, but it is neither extra income nor a variable-spending observation.</p></div>
							<div class="field-grid field-grid--three">
								<label class="field"><span>History coverage starts</span><input type="date" min="1900-01-01" max="2100-12-31" value={draft.inputs.history_start ?? ''} onchange={(event) => updateOptionalDate(event, 'history_start')} /><small>Leave blank until you can state the period.</small></label>
								<label class="field"><span>History coverage ends</span><input type="date" min="1900-01-01" max="2100-12-31" value={draft.inputs.history_end ?? ''} onchange={(event) => updateOptionalDate(event, 'history_end')} /></label>
								<label class="check-card"><input type="checkbox" bind:checked={draft.inputs.history_complete} /><span><strong>This coverage is complete.</strong><small>I have not selectively omitted accounts or spending during this stated window.</small></span></label>
							</div>
							<details class="explanation" open><summary>How classifications affect learning</summary><div><p><strong>Transfers</strong> are excluded. <strong>Fixed income and fixed expenses</strong> are not repeated as variable noise, avoiding double counting against scheduled events. Only the appropriate variable cash-flow categories train history mode. Credit purchases are not settled cash until the credit payment is recorded.</p><p>For a useful history model, aim for at least 90 contiguous days. A shorter or incomplete window remains honest and will surface a data requirement instead of a made-up forecast.</p></div></details>
							{#key historyImportKey}
								<FinancialHistoryCsv transactions={historyRows} disabled={editingLocked} maximumRecords={MAX_HISTORY_RECORDS} onApply={appendImportedTransactions} onImportStateChange={setHistoryImportPending} />
							{/key}
							<div class="list-heading"><div><p class="eyebrow">Manual entries and imported rows</p><h2>Classified transaction ledger</h2></div><button type="button" class="button button--quiet" onclick={addManualTransaction} disabled={historyRows.length >= MAX_HISTORY_RECORDS}>Add manual row</button></div>
							{#if historyRows.length === 0}
								<p class="empty-copy">No transactions are saved in this draft. Import a CSV above or add an actual transaction manually. Nothing is assumed.</p>
							{:else}
								<div class="table-scroll">
									<table class="data-table history-table">
										<thead><tr><th scope="col">Date</th><th scope="col">Description</th><th scope="col">Amount (USD)</th><th scope="col">Classification</th><th scope="col">Source key</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
										<tbody>
											{#each displayedHistoryRows as transaction, offset (transaction.id)}
												{@const index = historyPage * HISTORY_PAGE_SIZE + offset}
												<tr class:row--duplicate={duplicateHistoryIndexes.has(index)}>
													<td data-label="Date"><input aria-label={`Date, history row ${index + 1}`} type="date" min="1900-01-01" max="2100-12-31" bind:value={transaction.date} required /></td>
													<td data-label="Description"><input aria-label={`Description, history row ${index + 1}`} maxlength={MAX_TRANSACTION_DESCRIPTION_LENGTH} bind:value={transaction.description} required /></td>
													<td data-label="Amount (USD)"><CurrencyInput aria-label={`Amount in US dollars, history row ${index + 1}`} class="numeric" inputmode="decimal" pattern={String.raw`-?[0-9]+(?:\.[0-9]{1,2})?`} bind:value={transaction.amount_cents} required /></td>
													<td data-label="Classification">
														<select aria-label={`Classification, history row ${index + 1}`} bind:value={transaction.category}>
															{#each TRANSACTION_CATEGORIES as category (category)}
																<option value={category}>{TRANSACTION_CATEGORY_LABELS[category]}</option>
															{/each}
														</select>
													</td>
													<td data-label="Source key"><input aria-label={`Source key, history row ${index + 1}`} maxlength="200" value={transaction.source_key ?? ''} oninput={(event) => { const input = event.currentTarget; if (input instanceof HTMLInputElement) transaction.source_key = input.value === '' ? null : input.value; }} /></td>
													<td data-label="">
														<button aria-label={`Remove history row ${index + 1}`} type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove history row ${index + 1} from this draft?`, () => { if (draft) { const remaining = draft.inputs.transactions.filter((candidate) => candidate.id !== transaction.id); draft.inputs.transactions = remaining; historyPage = Math.max(0, Math.min(historyPage, Math.ceil(remaining.length / HISTORY_PAGE_SIZE) - 1)); } })}>Remove</button>
														{#if duplicateHistoryIndexes.has(index)}<small class="duplicate-tag">Possible duplicate</small>{/if}
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
								{#if historyRows.length > HISTORY_PAGE_SIZE}<nav class="pager" aria-label="History pages"><button type="button" class="button button--quiet" onclick={() => { if (historyPage > 0) historyPage -= 1; }} disabled={historyPage === 0}>Previous</button><span>Rows {historyPage * HISTORY_PAGE_SIZE + 1}–{Math.min((historyPage + 1) * HISTORY_PAGE_SIZE, historyRows.length)} of {historyRows.length.toLocaleString()}</span><button type="button" class="button button--quiet" onclick={() => { if (historyPage < historyPageCount - 1) historyPage += 1; }} disabled={historyPage >= historyPageCount - 1}>Next</button></nav>{/if}
							{/if}
						</section>
					{:else if section === 'assumptions'}
						<section id="assumptions" class="form-section" aria-labelledby="assumptions-title">
							<header class="section-heading"><div><p class="eyebrow">Explicit prospective assumptions</p><h1 id="assumptions-title">Income, spending, and variability</h1><p>These inputs are stored as decimal rates and shown here as percentages. They are used only after you choose Assumptions on Income.</p></div><a class="button button--quiet" href={`${resolve('/data')}?section=income#income`}>Choose model source</a></header>
							<div class="assumption-band"><p><strong>Current source: {draft.inputs.mode}</strong> {draft.inputs.mode === 'assumptions' ? 'These values will drive the personal forecast after you save.' : 'These values are retained but not selected as the active model source.'}</p></div>
							<section class="input-group" aria-labelledby="monthly-inputs-title"><header><p class="eyebrow">Monthly cash flow</p><h2 id="monthly-inputs-title">Variable income and spending</h2><p>Known recurring events stay on Events. Monthly assumptions are rates spread across forecast days at an average 30.44 days per month, not scheduled deposits or bills.</p></header><div class="field-grid field-grid--three"><label class="field"><span>Variable income (USD/month)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={draft.inputs.assumptions.monthly_variable_income_cents} required /><small>Nonnegative</small></label><label class="field"><span>Essential variable spending (USD/month)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={draft.inputs.assumptions.monthly_essential_spending_cents} required /><small>Nonnegative</small></label><label class="field"><span>Discretionary spending (USD/month)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={draft.inputs.assumptions.monthly_discretionary_spending_cents} required /><small>Nonnegative</small></label></div></section>
							<section class="input-group" aria-labelledby="variability-title"><header><p class="eyebrow">Variability and persistence</p><h2 id="variability-title">How cash-flow changes cluster</h2><p>Correlations link underlying daily shocks, not the resulting dollar amounts or returns. Variability is a percentage from 0% to 200%; persistence controls how long favorable or unfavorable shocks last.</p></header><div class="field-grid field-grid--four"><label class="field"><span>Income variability (%)</span><input type="number" min="0" max="200" step="0.1" value={displayPercent(draft.inputs.assumptions.income_variability_pct)} required oninput={(event) => draft && updatePercent(draft.inputs.assumptions, 'income_variability_pct', event)} /></label><label class="field"><span>Spending variability (%)</span><input type="number" min="0" max="200" step="0.1" value={displayPercent(draft.inputs.assumptions.spending_variability_pct)} required oninput={(event) => draft && updatePercent(draft.inputs.assumptions, 'spending_variability_pct', event)} /></label><label class="field"><span>Persistence (days)</span><input type="number" min="1" max="30" step="1" value={draft.inputs.assumptions.persistence_days} required oninput={(event) => draft && updateInteger(draft.inputs.assumptions, 'persistence_days', event)} /></label><label class="field"><span>Income / spending shock correlation</span><input type="number" min="-0.95" max="0.95" step="0.01" value={draft.inputs.assumptions.income_spending_correlation} required oninput={(event) => draft && updateNumber(draft.inputs.assumptions, 'income_spending_correlation', event)} /></label></div></section>
							<section class="input-group input-group--market" aria-labelledby="market-title"><header><p class="eyebrow">Market link</p><h2 id="market-title">Optional market assumptions</h2><p>Enable only when a market-sensitive income or spending relationship is meaningful for your plan. These prospective paths preserve your annual return and volatility inputs over a 365-day horizon; they are not observed returns. Holdings and actual returns stay under Investments.</p></header><label class="check-card"><input type="checkbox" bind:checked={draft.inputs.assumptions.market_assumptions_enabled} /><span><strong>Include market assumptions in the model</strong><small>Disabled values are retained but not used.</small></span></label><div class="field-grid field-grid--three"><label class="field"><span>Expected annual return (%)</span><input type="number" min="-99" max="200" step="0.1" value={displayPercent(draft.inputs.assumptions.expected_annual_return_pct)} required oninput={(event) => draft && updatePercent(draft.inputs.assumptions, 'expected_annual_return_pct', event)} /></label><label class="field"><span>Annual return volatility (%)</span><input type="number" min="0" max="200" step="0.1" value={displayPercent(draft.inputs.assumptions.annual_return_volatility_pct)} required oninput={(event) => draft && updatePercent(draft.inputs.assumptions, 'annual_return_volatility_pct', event)} /></label><label class="field"><span>Income / market shock correlation</span><input type="number" min="-0.95" max="0.95" step="0.01" value={draft.inputs.assumptions.income_market_correlation} required oninput={(event) => draft && updateNumber(draft.inputs.assumptions, 'income_market_correlation', event)} /></label></div></section>
						</section>
					{:else if section === 'credit'}
						<section id="credit" class="form-section" aria-labelledby="credit-title">
							<header class="section-heading">
								<div><p class="eyebrow">Actual available credit</p><h1 id="credit-title">Credit accounts and terms</h1><p>Ginseng never creates a synthetic card. Funding comparisons use only the limits, balances, timing, and APR you explicitly save.</p></div>
								<button type="button" class="button button--quiet" onclick={addCreditAccount} disabled={draft.inputs.credit_accounts.length >= MAX_CREDIT_ACCOUNTS}>Add credit account</button>
							</header>
							{#if draft.inputs.credit_accounts.length === 0}
								<p class="empty-copy">No credit account is saved. That means credit is unavailable to the funding planner, rather than guessed.</p>
							{/if}
							<div class="record-stack">
								{#each draft.inputs.credit_accounts as account, index (account.id)}
									<section class="record" aria-labelledby={`credit-${account.id}`}>
										<header>
											<div><p class="eyebrow">Credit account {index + 1}</p><h2 id={`credit-${account.id}`}>{account.name.trim() || 'Unnamed account'}</h2></div>
											<button type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove ${account.name.trim() || `credit account ${index + 1}`} from this draft?`, () => { if (draft) draft.inputs.credit_accounts = draft.inputs.credit_accounts.filter((candidate) => candidate.id !== account.id); })}>Remove</button>
										</header>
										<div class="field-grid field-grid--four">
											<label class="field"><span>Name</span><input maxlength="100" bind:value={account.name} required /></label>
											<label class="field"><span>Credit limit (USD)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={account.credit_limit_cents} required /></label>
											<label class="field"><span>Current balance (USD)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={account.current_balance_cents} required /></label>
											<label class="field"><span>Purchase APR (%)</span><input type="number" min="0" max="100" step="0.01" value={displayPercent(account.purchase_apr)} required oninput={(event) => updatePercent(account, 'purchase_apr', event)} /></label>
											<label class="field"><span>Statement closes (day)</span><input type="number" min="1" max="28" step="1" value={account.statement_close_day} required oninput={(event) => updateInteger(account, 'statement_close_day', event)} /></label>
											<label class="field"><span>Payment due (day)</span><input type="number" min="1" max="28" step="1" value={account.payment_due_day} required oninput={(event) => updateInteger(account, 'payment_due_day', event)} /></label>
											<label class="field"><span>Minimum payment (USD)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={account.minimum_payment_cents} required /></label>
											<label class="check-card"><input type="checkbox" bind:checked={account.grace_period_eligible} /><span><strong>Grace period eligible</strong><small>Use the current account’s actual eligibility.</small></span></label>
										</div>
									</section>
								{/each}
							</div>
						</section>
					{:else if section === 'investments'}
						<section id="investments" class="form-section" aria-labelledby="investments-title">
							<header class="section-heading">
								<div><p class="eyebrow">Marketable holdings and historical returns</p><h1 id="investments-title">Investments and tax lots</h1><p>Current prices and tax lots support actual funding trade-offs. Retirement and taxable holdings stay distinct.</p></div>
								<button type="button" class="button button--quiet" onclick={addHolding} disabled={draft.inputs.holdings.length >= MAX_HOLDINGS}>Add holding</button>
							</header>
							{#if draft.inputs.holdings.length === 0}
								<p class="empty-copy">No holdings are saved. Funding plans will not imply an investment sale.</p>
							{/if}
							<div class="record-stack">
								{#each draft.inputs.holdings as holding, holdingIndex (holding.id)}
									<section class="record holding-record" aria-labelledby={`holding-${holding.id}`}>
										<header>
											<div><p class="eyebrow">Holding {holdingIndex + 1}</p><h2 id={`holding-${holding.id}`}>{holding.symbol.trim() || 'Unnamed holding'}</h2></div>
											<button type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove ${holding.symbol.trim() || `holding ${holdingIndex + 1}`} and its tax lots from this draft?`, () => { if (draft) draft.inputs.holdings = draft.inputs.holdings.filter((candidate) => candidate.id !== holding.id); })}>Remove holding</button>
										</header>
										<div class="field-grid field-grid--three">
											<label class="field"><span>Symbol</span><input maxlength={MAX_HOLDING_SYMBOL_LENGTH} placeholder="e.g. VTI" bind:value={holding.symbol} required /></label>
											<label class="field"><span>Account</span><select bind:value={holding.account}><option value="taxable">Taxable</option><option value="retirement">Retirement</option></select></label>
											<label class="field"><span>Current price (USD/share)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={holding.current_price_cents} required /></label>
										</div>
										<div class="lot-heading">
											<div><p class="eyebrow">Actual tax lots</p><p>Lot selection can only use the quantity, basis, and purchase date you enter.</p></div>
											<button type="button" class="button button--quiet" onclick={() => addTaxLot(holding.id)} disabled={holding.tax_lots.length >= MAX_TAX_LOTS_PER_HOLDING}>Add tax lot</button>
										</div>
										{#if holding.tax_lots.length === 0}
											<p class="empty-copy">No tax lots are saved for this holding yet. Add only actual lots when you need tax-aware sale detail.</p>
										{/if}
										<div class="table-scroll">
											<table class="data-table lots-table">
												<thead><tr><th scope="col">Quantity</th><th scope="col">Cost basis (USD/share)</th><th scope="col">Purchase date</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
												<tbody>
													{#each holding.tax_lots as lot, lotIndex (lot.id)}
														<tr>
															<td data-label="Quantity"><input aria-label={`Quantity, ${holding.symbol || "holding"} tax lot ${lotIndex + 1}`} type="number" min="0" max="1000000000000" step="any" value={Number.isFinite(lot.quantity) ? lot.quantity : ''} required oninput={(event) => updateNumber(lot, 'quantity', event)} /></td>
															<td data-label="Cost basis (USD/share)"><CurrencyInput aria-label={`Cost basis in US dollars per share, ${holding.symbol || "holding"} tax lot ${lotIndex + 1}`} class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={lot.cost_basis_per_share_cents} required /></td>
															<td data-label="Purchase date"><input aria-label={`Purchase date, ${holding.symbol || "holding"} tax lot ${lotIndex + 1}`} type="date" min="1900-01-01" max="2100-12-31" bind:value={lot.purchase_date} required /></td>
															<td data-label=""><button aria-label={`Remove ${holding.symbol || "holding"} tax lot ${lotIndex + 1}`} type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove tax lot ${lotIndex + 1} from ${holding.symbol.trim() || 'this holding'}?`, () => { if (draft) { const current = draft.inputs.holdings.find((candidate) => candidate.id === holding.id); if (current) current.tax_lots = current.tax_lots.filter((candidate) => candidate.id !== lot.id); } })}>Remove</button></td>
														</tr>
													{/each}
												</tbody>
											</table>
										</div>
									</section>
								{/each}
							</div>

							<section class="return-import" aria-labelledby="returns-title">
								<header class="subsection-heading">
									<div><p class="eyebrow">Portfolio return history</p><h2 id="returns-title">Manual rows or a return CSV</h2><p>Provide actual dated portfolio returns if you want them considered. A return column can be decimal (0.0125) or percentage (1.25%).</p></div>
									<label class="file-button" class:file-button--disabled={editingLocked}>
										<span>{returnFileName ? 'Choose another CSV' : 'Choose return CSV'}</span>
										<input type="file" accept=".csv,text/csv,text/plain" onchange={chooseReturnFile} disabled={editingLocked} />
									</label>
								</header>
								{#if returnImportError}
									<p class="import-alert import-alert--error" role="alert">{returnImportError}</p>
								{/if}
								{#if returnTable && returnMapping}
									<div class="return-map">
										<label class="check-field"><input type="checkbox" checked={returnHasHeader} onchange={changeReturnHeader} /><span>First row contains column names</span></label>
										<label class="field">
											<span>Date</span>
											<select value={returnMapping.date ?? ''} onchange={(event) => changeReturnColumn('date', event)}>
												<option value="">No column</option>
												{#each returnColumns as column (column.index)}
													<option value={column.index}>{column.label}</option>
												{/each}
											</select>
										</label>
										<label class="field">
											<span>Return</span>
											<select value={returnMapping.returnValue ?? ''} onchange={(event) => changeReturnColumn('returnValue', event)}>
												<option value="">No column</option>
												{#each returnColumns as column (column.index)}
													<option value={column.index}>{column.label}</option>
												{/each}
											</select>
										</label>
										<label class="field">
											<span>Date order</span>
											<select value={returnMapping.dateOrder} onchange={changeReturnDateOrder}>
												<option value="year-month-day">YYYY-MM-DD</option>
												<option value="month-day-year">MM/DD/YYYY</option>
												<option value="day-month-year">DD/MM/YYYY</option>
											</select>
										</label>
										<label class="field">
											<span>Return format</span>
											<select value={returnMapping.returnInterpretation} onchange={changeReturnInterpretation}>
												<option value="decimal">Decimal (0.0125)</option>
												<option value="percent">Percent (1.25)</option>
											</select>
										</label>
									</div>
									<div class="return-review">
										<p>
											<strong>{acceptedReturnCandidates.length.toLocaleString()}</strong> valid rows ready to apply ·
											{availableReturnSlots.toLocaleString()} portfolio-return slot{availableReturnSlots === 1 ? '' : 's'} left ·
											{reviewReturnCandidates.filter((candidate) => candidate.duplicate).length.toLocaleString()} duplicate-date warning(s)
											{#if reviewReturnCandidates.some((candidate) => candidate.capacityExceeded)}
												· {reviewReturnCandidates.filter((candidate) => candidate.capacityExceeded).length.toLocaleString()} row(s) exceed the remaining capacity
											{/if}
										</p>
										<div><button type="button" class="button button--quiet" onclick={clearReturnImport}>Clear import</button><button type="button" class="button button--primary" onclick={applyPortfolioReturns} disabled={acceptedReturnCandidates.length === 0}>Apply return rows</button></div>
									</div>
									<div class="table-scroll">
										<table class="data-table return-preview">
											<thead><tr><th scope="col">Source row</th><th scope="col">Date</th><th scope="col">Return</th><th scope="col">Review</th></tr></thead>
											<tbody>
												{#each reviewReturnCandidates.slice(0, 20) as candidate (candidate.sourceRow)}
													<tr class:row--duplicate={candidate.duplicate || candidate.capacityExceeded}>
														<td>{candidate.sourceRow}</td>
														<td>{candidate.date ?? 'Invalid'}</td>
														<td>{candidate.return_decimal === null ? 'Invalid' : displayPercent(candidate.return_decimal) + '%'}</td>
														<td>
															{#if candidate.issues.length > 0}
																{candidate.issues.join(' ')}
															{:else if candidate.duplicate}
																Duplicate date — correct manually or omit.
															{:else if candidate.capacityExceeded}
																No remaining portfolio-return slot — omit this row or remove a saved return.
															{:else}
																Ready
															{/if}
														</td>
													</tr>
												{/each}
											</tbody>
										</table>
									</div>
									{#if reviewReturnCandidates.length > 20}
										<p class="empty-copy">Previewing the first 20 rows. Apply uses every valid, non-duplicate row that fits the remaining capacity.</p>
									{/if}
								{/if}
							</section>
							<div class="list-heading">
								<div><p class="eyebrow">Saved return ledger</p><h2>Manual portfolio returns</h2></div>
								<button type="button" class="button button--quiet" onclick={addPortfolioReturn} disabled={draft.inputs.portfolio_returns.length >= MAX_PORTFOLIO_RETURNS}>Add manual return</button>
							</div>
							{#if draft.inputs.portfolio_returns.length === 0}
								<p class="empty-copy">No portfolio returns are saved. The model will not invent them.</p>
							{:else}
								<div class="table-scroll">
									<table class="data-table">
										<thead><tr><th scope="col">Date</th><th scope="col">Daily return (%)</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
										<tbody>
											{#each displayedPortfolioReturns as entry, offset (entry)}
												{@const index = returnPage * PORTFOLIO_RETURN_PAGE_SIZE + offset}
												<tr>
													<td data-label="Date"><input aria-label={`Date, portfolio return ${index + 1}`} type="date" min="1900-01-01" max="2100-12-31" bind:value={entry.date} required /></td>
													<td data-label="Daily return (%)"><input aria-label={`Daily return percentage, portfolio return ${index + 1}`} type="number" min="-100" max="10000" step="0.0001" value={displayPercent(entry.return_decimal)} required oninput={(event) => updatePercent(entry, 'return_decimal', event)} /></td>
													<td data-label=""><button aria-label={`Remove portfolio return ${index + 1}`} type="button" class="text-button text-button--danger" onclick={() => askRemoval(`Remove portfolio return ${index + 1} from this draft?`, () => { if (draft) { const remaining = draft.inputs.portfolio_returns.filter((_, candidateIndex) => candidateIndex !== index); draft.inputs.portfolio_returns = remaining; returnPage = Math.max(0, Math.min(returnPage, Math.ceil(remaining.length / PORTFOLIO_RETURN_PAGE_SIZE) - 1)); } })}>Remove</button></td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
								{#if draft.inputs.portfolio_returns.length > PORTFOLIO_RETURN_PAGE_SIZE}
									<nav class="pager" aria-label="Portfolio return pages">
										<button type="button" class="button button--quiet" onclick={() => { if (returnPage > 0) returnPage -= 1; }} disabled={returnPage === 0}>Previous</button>
										<span>Rows {returnPage * PORTFOLIO_RETURN_PAGE_SIZE + 1}–{Math.min((returnPage + 1) * PORTFOLIO_RETURN_PAGE_SIZE, draft.inputs.portfolio_returns.length)} of {draft.inputs.portfolio_returns.length.toLocaleString()}</span>
										<button type="button" class="button button--quiet" onclick={() => { if (returnPage < portfolioReturnPageCount - 1) returnPage += 1; }} disabled={returnPage >= portfolioReturnPageCount - 1}>Next</button>
									</nav>
								{/if}
							{/if}
						</section>
					{:else}
						<section id="policy" class="form-section" aria-labelledby="policy-title">
							<header class="section-heading">
								<div><p class="eyebrow">Funding and alert rules</p><h1 id="policy-title">Reserve and funding policy</h1><p>These are your policy choices, not recommendations. They affect cash buffering, timing, tax-aware lot selection, and in-app alerts.</p></div>
							</header>
							<section class="input-group" aria-labelledby="liquidity-policy-title">
								<header><p class="eyebrow">Liquidity policy</p><h2 id="liquidity-policy-title">Cash coverage and timing</h2></header>
								<div class="field-grid field-grid--four">
									<label class="field"><span>Operating buffer (USD)</span><CurrencyInput class="numeric" inputmode="decimal" pattern={String.raw`[0-9]+(?:\.[0-9]{1,2})?`} bind:value={draft.inputs.policy.operating_buffer_cents} required /></label>
									<label class="field"><span>Coverage target (%)</span><input type="number" min="0" max="100" step="0.1" value={displayPercent(draft.inputs.policy.coverage_target)} required oninput={(event) => draft && updatePercent(draft.inputs.policy, 'coverage_target', event)} /><small>Greater than 0%</small></label>
									<label class="field"><span>Settlement days</span><input type="number" min="0" max="30" step="1" value={draft.inputs.policy.settlement_days} required oninput={(event) => draft && updateInteger(draft.inputs.policy, 'settlement_days', event)} /></label>
									<label class="field"><span>External transfer days</span><input type="number" min="0" max="30" step="1" value={draft.inputs.policy.external_transfer_days} required oninput={(event) => draft && updateInteger(draft.inputs.policy, 'external_transfer_days', event)} /></label>
									<label class="field"><span>Buffer tolerance (dollar-days)</span><input type="number" min="0" max={MAX_BUFFER_TOLERANCE_DOLLAR_DAYS} step="any" value={draft.inputs.policy.buffer_tolerance_dollar_days ?? ''} oninput={updateTolerance} /><small>Blank means no tolerance is set.</small></label>
								</div>
							</section>
							<section class="input-group" aria-labelledby="funding-policy-title">
								<header><p class="eyebrow">Credit and taxable-sale policy</p><h2 id="funding-policy-title">Cost limits and lot selection</h2></header>
								<div class="field-grid field-grid--four">
									<label class="field"><span>Maximum credit utilization (%)</span><input type="number" min="0" max="100" step="0.1" value={displayPercent(draft.inputs.policy.max_credit_utilization)} required oninput={(event) => draft && updatePercent(draft.inputs.policy, 'max_credit_utilization', event)} /></label>
									<label class="field"><span>Capital-gains rate (%)</span><input type="number" min="0" max="100" step="0.1" value={displayPercent(draft.inputs.policy.capital_gains_rate)} required oninput={(event) => draft && updatePercent(draft.inputs.policy, 'capital_gains_rate', event)} /></label>
									<label class="field"><span>Overdraft APR (%)</span><input type="number" min="0" max="100" step="0.1" value={displayPercent(draft.inputs.policy.overdraft_apr)} required oninput={(event) => draft && updatePercent(draft.inputs.policy, 'overdraft_apr', event)} /></label>
									<label class="field"><span>Tax-lot selection</span><select bind:value={draft.inputs.policy.lot_selection}><option value="fifo">FIFO — oldest shares first</option><option value="hifo">HIFO — highest basis first</option></select></label>
								</div>
								<div class="priority-list">
									<div>
										<p class="eyebrow">Funding priority order</p>
										<p>Add one to three distinct rules, then move them into your order.</p>
										<button type="button" class="button button--quiet" onclick={addPriority} disabled={draft.inputs.policy.priorities.length >= PRIORITIES.length}>Add priority</button>
									</div>
									<ol>
										{#each draft.inputs.policy.priorities as priority, index (priority)}
											<li>
												<strong>{PRIORITY_LABELS[priority]}</strong>
												<span>
													<button type="button" class="text-button" onclick={() => movePriority(index, -1)} disabled={index === 0}>Up</button>
													<button type="button" class="text-button" onclick={() => movePriority(index, 1)} disabled={index === draft.inputs.policy.priorities.length - 1}>Down</button>
													<button type="button" class="text-button text-button--danger" onclick={() => removePriority(index)} disabled={draft.inputs.policy.priorities.length <= 1}>Remove</button>
												</span>
											</li>
										{/each}
									</ol>
								</div>
							</section>
							<section class="input-group" aria-labelledby="alerts-title">
								<header><p class="eyebrow">In-app alerts only</p><h2 id="alerts-title">Tell Ginseng when to surface a warning.</h2><p>Alerts appear in this app. They do not imply email, push notifications, account monitoring, or bank access.</p></header>
								<div class="field-grid field-grid--three">
									<label class="check-card"><input type="checkbox" bind:checked={draft.inputs.alerts.enabled} /><span><strong>Show in-app alerts</strong><small>Enable threshold and freshness alerts in the personal workspace.</small></span></label>
									<label class="field"><span>Shortfall probability threshold (%)</span><input type="number" min="0" max="100" step="0.1" value={displayPercent(draft.inputs.alerts.shortfall_probability)} required oninput={(event) => draft && updatePercent(draft.inputs.alerts, 'shortfall_probability', event)} /></label>
									<label class="field"><span>Data stale after (days)</span><input type="number" min="1" max="3650" step="1" value={draft.inputs.alerts.stale_after_days} required oninput={(event) => draft && updateInteger(draft.inputs.alerts, 'stale_after_days', event)} /></label>
								</div>
							</section>
							<section class="export-panel" aria-labelledby="export-title">
								<div>
									<p class="eyebrow">Portable backup</p>
									<h2 id="export-title">Export the current saved workspace</h2>
									<p>This explicit download contains sensitive financial data: balances, events, history, credit, holdings, assumptions, and policy. Save it only where you trust the storage.</p>
									{#if exportMessage}<p class:export-message--error={exportState === 'error'} class="export-message" role={exportState === 'error' ? 'alert' : 'status'}>{exportMessage}</p>{/if}
								</div>
								<button type="button" class="button button--primary" onclick={exportCurrentWorkspace} disabled={exportState === 'working'}>{exportState === 'working' ? 'Preparing export…' : 'Download JSON export'}</button>
							</section>
						</section>
					{/if}
				</fieldset>

				<footer class="save-bar"><div><strong>{draftIsDirty ? 'Unsaved financial changes' : 'Saved financial workspace'}</strong><span>{pendingImport ? 'Apply or clear the local CSV review before saving.' : reconciliationLock ? 'Reload and reconcile the saved workspace before another save.' : draftIsDirty ? 'Save writes cash and supplemental inputs together in one revisioned snapshot.' : 'Your saved values remain the source for personal forecasts.'}</span></div><div class="save-actions"><button type="button" class="button button--quiet" onclick={requestReload} disabled={financialStore.saving}>Discard and reload</button><button type="submit" class="button button--primary" disabled={!draftIsDirty || editingLocked || pendingImport}>{financialStore.saving ? 'Saving workspace…' : 'Save workspace'}</button></div></footer>
			</form>
		</div>
	</div>
	{/key}
{:else}
	<section class="state-screen" role="status" aria-live="polite">
		<p class="eyebrow">Personal data</p>
		<h1>Preparing your financial workspace</h1>
		<p>Waiting for your authenticated workspace to become available. No estimates are shown until it loads.</p>
	</section>
{/if}

<style>
	.data-workbench, .state-screen { min-height: calc(100dvh - 3.25rem); background: var(--paper); color: var(--ink); }
	.state-screen { display: grid; align-content: center; justify-items: start; gap: 0.8rem; padding: clamp(1.5rem, 8vw, 7rem); }
	.state-screen h1, .section-heading h1 { max-width: 20ch; color: var(--ink); font-size: clamp(2rem, 4vw, 3.4rem); letter-spacing: -0.055em; line-height: 0.92; text-wrap: balance; }
	.state-screen p { max-width: 60ch; color: var(--ink-soft); }
	.eyebrow, .section-stats dt, .toolbar-identity span, .toolbar-summary, .toolbar-state, .section-index > p, .index-note strong { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.63rem; font-weight: 750; letter-spacing: 0.065em; text-transform: uppercase; }
	.data-toolbar { display: flex; align-items: center; gap: 1rem; min-height: 3.25rem; padding: 0.55rem 1rem; border-bottom: 1px solid var(--rule); background: var(--paper); }
	.toolbar-identity { display: flex; align-items: baseline; gap: 0.55rem; white-space: nowrap; }
	.terminal-name { color: var(--ink); font-size: 1rem; font-weight: 800; letter-spacing: -0.04em; }
	.toolbar-summary { display: flex; flex: 1 1 auto; flex-wrap: wrap; gap: 0.4rem 1rem; min-width: 0; }
	.toolbar-state { flex: none; padding: 0.35rem 0.48rem; border: 1px solid var(--rule-strong); background: var(--paper-soft); }
	.toolbar-state--dirty { border-color: var(--cobalt); background: var(--cobalt); color: var(--paper); }
	.notice, .confirmation, .validation-summary { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0; padding: 0.7rem 1rem; border-bottom: 1px solid var(--rule); background: var(--paper-soft); color: var(--ink-soft); font-size: 0.8rem; }
	.notice--error, .validation-summary { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
	.notice--success { border-color: var(--positive); color: var(--ink); }
	.confirmation { display: grid; border-color: var(--negative); background: var(--negative-soft); color: var(--ink); }
	.confirmation h2 { margin: 0; font-size: 1.08rem; letter-spacing: -0.035em; }
	.confirmation > div, .save-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.validation-summary { display: block; }
	.validation-summary strong { color: var(--negative); }
	.validation-summary ul { margin: 0.4rem 0 0; padding-left: 1.1rem; }
	.editor-layout { display: grid; grid-template-columns: 13rem minmax(0, 1fr); min-height: calc(100dvh - 6.5rem); }
	.section-index { display: grid; align-content: start; gap: 1px; padding: 1rem 0.75rem; border-right: 1px solid var(--rule); background: var(--paper-soft); }
	.section-index > p { margin: 0.15rem 0.35rem 0.45rem; }
	.section-index a { display: grid; gap: 0.08rem; min-height: 3.25rem; padding: 0.55rem 0.6rem; border: 1px solid transparent; color: var(--ink); text-decoration: none; }
	.section-index a strong { font-size: 0.88rem; letter-spacing: -0.02em; }
	.section-index a span, .index-note span { color: var(--ink-soft); font-size: 0.68rem; line-height: 1.3; }
	.section-index a:hover { border-color: var(--control-border); background: var(--paper); }
	.section-index a.active { border-color: var(--cobalt); background: var(--cobalt); color: var(--paper); }
	.section-index a.active span { color: var(--paper); }
	.index-note { display: grid; gap: 0.25rem; margin-top: 0.8rem; padding: 0.75rem 0.6rem; border-top: 1px solid var(--rule); }
	.financial-form { min-width: 0; }
	.financial-form fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
	.form-section { min-height: calc(100dvh - 10.5rem); padding: clamp(1rem, 2.5vw, 2.4rem); }
	.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 2rem; padding-bottom: 1.15rem; border-bottom: 1px solid var(--rule); }
	.section-heading > div { display: grid; gap: 0.32rem; max-width: 65ch; }
	.section-heading > div > p:last-child { color: var(--ink-soft); font-size: 0.9rem; line-height: 1.45; }
	.section-heading .button { flex: none; }
	.section-stats { display: grid; grid-template-columns: repeat(2, minmax(7rem, 1fr)); gap: 1px; flex: none; margin: 0; border: 1px solid var(--rule); background: var(--rule); }
	.section-stats div { display: grid; gap: 0.18rem; padding: 0.65rem 0.75rem; background: var(--paper-soft); }
	.section-stats dd { margin: 0; color: var(--ink); font-size: 1rem; font-weight: 800; font-variant-numeric: tabular-nums; letter-spacing: -0.04em; }
	.callout, .reconciliation-note, .assumption-band { display: flex; align-items: start; gap: 0.65rem; margin-top: 1rem; padding: 0.75rem 0.85rem; border-left: 3px solid var(--cobalt); background: var(--paper-soft); color: var(--ink-soft); font-size: 0.79rem; line-height: 1.45; }
	.callout strong, .reconciliation-note strong, .assumption-band strong { flex: none; color: var(--ink); }
	.callout a { color: var(--cobalt-deep); font-weight: 750; }
	.reconciliation-note { display: grid; gap: 0.15rem; border-left-color: var(--warning); }
	.reconciliation-note p { margin: 0; }
	.reconciliation-note em { color: var(--ink); font-style: normal; font-weight: 750; }
	.reconciliation-note--wide { max-width: 76rem; }
	.field-grid { display: grid; gap: 0.8rem; min-width: 0; margin-top: 1rem; }
	.field-grid--opening { grid-template-columns: minmax(15rem, 0.7fr) minmax(0, 1fr); max-width: 74rem; }
	.field-grid--three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
	.field-grid--four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
	.field { display: grid; gap: 0.3rem; min-width: 0; color: var(--ink-soft); font-size: 0.73rem; font-weight: 750; }
	.field small, .check-card small { color: var(--ink-soft); font-size: 0.68rem; font-weight: 500; line-height: 1.3; }
	.financial-form :global(input), select { width: 100%; min-width: 0; min-height: 2.75rem; padding: 0 0.62rem; border: 1px solid var(--control-border); border-radius: 0; background: var(--paper); color: var(--ink); font: inherit; font-size: 0.88rem; }
	.financial-form :global(input)::placeholder { color: var(--ink-soft); opacity: 1; }
	select { cursor: pointer; }
	.financial-form :global(input):disabled, select:disabled { cursor: not-allowed; opacity: 0.6; }
	.button, .text-button, .file-button { display: inline-flex; align-items: center; justify-content: center; min-height: 2.75rem; padding: 0 0.75rem; border: 1px solid var(--control-border); border-radius: 0; background: var(--paper); color: var(--ink); font-family: var(--font-mono); font-size: 0.67rem; font-weight: 750; letter-spacing: 0.035em; text-decoration: none; text-transform: uppercase; cursor: pointer; transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease, transform 150ms ease; }
	.button:hover:not(:disabled), .text-button:hover:not(:disabled), .file-button:not(.file-button--disabled):hover { border-color: var(--ink-soft); background: var(--paper-deep); }
	.button:active:not(:disabled), .text-button:active:not(:disabled) { transform: scale(0.98); }
	.button:disabled, .text-button:disabled { cursor: not-allowed; opacity: 0.55; }
	.button--primary { border-color: var(--cobalt); background: var(--cobalt); color: var(--paper); }
	.button--primary:hover:not(:disabled) { border-color: var(--cobalt-deep); background: var(--cobalt-deep); }
	.button--quiet, .text-button { background: transparent; }
	.button--danger { border-color: var(--negative); background: var(--negative); color: var(--paper); }
	.text-button--danger { color: var(--negative); }
	.ledger-block { display: grid; gap: 1px; margin-top: 1rem; border: 1px solid var(--rule); background: var(--rule); }
	.ledger-head, .ledger-row { display: grid; grid-template-columns: minmax(11rem, 1fr) minmax(7rem, 0.55fr) minmax(10rem, 0.8fr) auto; gap: 0.55rem; align-items: end; min-width: 0; }
	.ledger-head { padding: 0.45rem 0.6rem; background: var(--paper-deep); color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.6rem; font-weight: 750; letter-spacing: 0.045em; text-transform: uppercase; }
	.ledger-row { padding: 0.65rem; background: var(--paper); }
	.empty-copy { max-width: 70ch; margin: 0.8rem 0 0; color: var(--ink-soft); font-size: 0.8rem; line-height: 1.45; }
	.linked-data { display: flex; align-items: center; justify-content: space-between; gap: 1rem; max-width: 76rem; margin-top: 1.5rem; padding: 1rem 0; border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); }
	.linked-data > div { display: grid; gap: 0.25rem; max-width: 57ch; }
	.linked-data h2, .input-group h2, .list-heading h2, .subsection-heading h2, .export-panel h2 { color: var(--ink); font-size: 1.18rem; letter-spacing: -0.04em; }
	.linked-data p:last-child, .input-group header > p:last-child, .subsection-heading p:last-child, .export-panel p { color: var(--ink-soft); font-size: 0.8rem; line-height: 1.45; }
	.event-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 1px; max-width: 76rem; padding: 0; margin: 1rem 0 0; border: 1px solid var(--rule); background: var(--rule); list-style: none; }
	.event-strip li { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.18rem 0.5rem; padding: 0.65rem; background: var(--paper); }
	.event-strip span { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.62rem; }
	.event-strip strong { min-width: 0; overflow: hidden; color: var(--ink); font-size: 0.78rem; text-overflow: ellipsis; white-space: nowrap; }
	.event-strip em { grid-column: 2; color: var(--negative); font-size: 0.72rem; font-style: normal; font-weight: 750; }
	.mode-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1px; margin-top: 1.2rem; border: 1px solid var(--rule); background: var(--rule); }
	.mode-card { display: grid; gap: 0.35rem; min-height: 10rem; padding: 1rem; background: var(--paper); color: var(--ink); cursor: pointer; }
	.mode-card input { width: 1.1rem; min-height: auto; accent-color: var(--cobalt); }
	.mode-card strong { font-size: 1.1rem; letter-spacing: -0.04em; }
	.mode-card span { color: var(--ink-soft); font-size: 0.8rem; line-height: 1.4; }
	.mode-card--selected { background: var(--cobalt); color: var(--paper); }
	.mode-card--selected span { color: var(--paper); }
	.explanation { max-width: 76rem; margin-top: 1rem; border: 1px solid var(--rule); background: var(--paper-soft); }
	.explanation summary { min-height: 2.75rem; padding: 0.7rem 0.8rem; color: var(--ink); font-family: var(--font-mono); font-size: 0.67rem; font-weight: 750; letter-spacing: 0.04em; text-transform: uppercase; cursor: pointer; }
	.explanation > div { display: grid; gap: 0.5rem; padding: 0 0.8rem 0.8rem; color: var(--ink-soft); font-size: 0.79rem; line-height: 1.45; }
	.explanation strong { color: var(--ink); }
	.check-card { display: flex; align-items: start; gap: 0.6rem; min-width: 0; min-height: 2.75rem; padding: 0.65rem; border: 1px solid var(--control-border); background: var(--paper); color: var(--ink); cursor: pointer; }
	.check-card input { flex: none; width: 1.1rem; min-height: auto; margin-top: 0.1rem; accent-color: var(--cobalt); }
	.check-card > span { display: grid; gap: 0.12rem; }
	.check-card strong { font-size: 0.77rem; }
	.input-group { max-width: 82rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--rule); }
	.input-group header { display: grid; gap: 0.25rem; max-width: 64ch; }
	.input-group--market { padding-bottom: 0.2rem; }
	.record-stack { display: grid; gap: 1px; max-width: 84rem; margin-top: 1rem; border: 1px solid var(--rule); background: var(--rule); }
	.record { display: grid; gap: 0.8rem; padding: 1rem; background: var(--paper); }
	.record > header, .list-heading, .subsection-heading, .export-panel { display: flex; align-items: start; justify-content: space-between; gap: 1rem; }
	.record > header > div, .list-heading > div, .subsection-heading > div, .export-panel > div { display: grid; gap: 0.2rem; }
	.record h2 { color: var(--ink); font-size: 1.15rem; letter-spacing: -0.04em; }
	.lot-heading { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-top: 0.25rem; padding-top: 0.8rem; border-top: 1px solid var(--rule); }
	.lot-heading > div { display: grid; gap: 0.18rem; }
	.lot-heading p:last-child { color: var(--ink-soft); font-size: 0.76rem; }
	.list-heading { align-items: center; max-width: 84rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--rule); }
	.table-scroll { position: relative; max-width: 100%; overflow-x: auto; margin-top: 0.75rem; border: 1px solid var(--rule); }
	.data-table { width: 100%; min-width: 58rem; border-collapse: collapse; background: var(--paper); }
	.data-table th { padding: 0.48rem 0.58rem; background: var(--paper-deep); color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.6rem; font-weight: 750; letter-spacing: 0.045em; text-align: left; text-transform: uppercase; }
	.data-table td { padding: 0.45rem; border-top: 1px solid var(--rule); vertical-align: top; }
	.data-table td:last-child { width: 1%; white-space: nowrap; }
	.data-table input, .data-table select { min-width: 8rem; }
	.history-table { min-width: 68rem; }
	.lots-table { min-width: 42rem; }
	.row--duplicate { background: var(--negative-soft); }
	.duplicate-tag { display: block; margin-top: 0.3rem; color: var(--warning); font-size: 0.64rem; line-height: 1.2; }
	.pager { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; max-width: 84rem; margin-top: 0.75rem; }
	.pager span { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.67rem; }
	.return-import { display: grid; gap: 0.8rem; max-width: 84rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--rule); }
	.file-button { position: relative; flex: none; overflow: hidden; }
	.file-button:focus-within { outline: 2px solid var(--cobalt-bright); outline-offset: 3px; }
	.file-button input { position: absolute; inset: 0; width: 100%; cursor: pointer; opacity: 0; }
	.file-button--disabled { cursor: not-allowed; opacity: 0.55; }
	.return-map { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.65rem; padding: 0.8rem; border: 1px solid var(--rule); background: var(--paper-soft); }
	.return-map .check-field { grid-column: 1 / -1; }
	.return-review { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.75rem; border: 1px solid var(--rule); background: var(--paper-deep); color: var(--ink-soft); font-size: 0.78rem; }
	.return-review strong { color: var(--ink); }
	.return-review > div { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.import-alert { margin: 0; padding: 0.7rem 0.8rem; border: 1px solid var(--rule-strong); background: var(--paper-soft); color: var(--ink-soft); font-size: 0.78rem; }
	.import-alert--error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
	.priority-list { display: grid; grid-template-columns: minmax(13rem, 0.75fr) minmax(0, 1.25fr); gap: 1rem; margin-top: 1rem; padding: 0.8rem; border: 1px solid var(--rule); background: var(--paper-soft); }
	.priority-list > div { display: grid; gap: 0.18rem; }
	.priority-list > div > p:last-child { color: var(--ink-soft); font-size: 0.76rem; line-height: 1.35; }
	.priority-list ol { display: grid; gap: 1px; padding: 0; margin: 0; background: var(--rule); list-style: none; }
	.priority-list li { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.5rem 0.65rem; background: var(--paper); }
	.priority-list li strong { font-size: 0.8rem; }
	.priority-list li span { display: flex; gap: 0.3rem; }
	.priority-list .text-button { min-height: 2.75rem; }
	.export-panel { align-items: center; max-width: 84rem; margin-top: 1.5rem; padding: 1rem; border: 1px solid var(--cobalt); background: var(--paper-soft); }
	.export-panel > div { max-width: 63ch; }
	.export-message { color: var(--positive) !important; font-weight: 750; }
	.export-message--error { color: var(--negative) !important; }
	.save-bar { position: sticky; bottom: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem 1rem; border-top: 1px solid var(--rule-strong); background: var(--paper-deep); }
	.save-bar > div:first-child { display: grid; gap: 0.1rem; }
	.save-bar strong { color: var(--ink); font-size: 0.9rem; }
	.save-bar span { color: var(--ink-soft); font-size: 0.75rem; }
	@media (max-width: 72rem) { .field-grid--four { grid-template-columns: repeat(2, minmax(0, 1fr)); }.return-map { grid-template-columns: repeat(2, minmax(0, 1fr)); }.section-heading { align-items: start; flex-direction: column; }.section-stats { width: 100%; max-width: 30rem; }.field-grid--opening { grid-template-columns: 1fr; }.priority-list { grid-template-columns: 1fr; } }
	@media (max-width: 64rem) {
		.ledger-head { display: none; }
		.ledger-row { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; }
		.ledger-row .field:first-child, .ledger-row > button { grid-column: 1 / -1; }
		.ledger-row > button { justify-self: start; }
		.ledger-row .field::before { content: attr(data-label); color: var(--ink-soft); font-size: 0.72rem; font-weight: 700; }
	}
	@media (max-width: 56rem) { .editor-layout { grid-template-columns: 1fr; }.section-index { grid-template-columns: repeat(4, minmax(0, 1fr)); padding: 0.55rem; border-right: 0; border-bottom: 1px solid var(--rule); }.section-index > p, .index-note { display: none; }.section-index a { min-height: 2.75rem; padding: 0.4rem; }.section-index a span { display: none; }.section-index a strong { font-size: 0.75rem; }.form-section { min-height: auto; padding: 1rem 0.75rem 6.5rem; }.mode-grid, .field-grid--three { grid-template-columns: 1fr; }.linked-data, .return-review, .export-panel, .save-bar { align-items: stretch; flex-direction: column; }.toolbar-summary { display: none; }.data-toolbar { flex-wrap: wrap; }.toolbar-identity { flex: 1 1 auto; }.toolbar-state { margin-left: auto; }.save-actions { width: 100%; }.save-actions .button { flex: 1 1 12rem; }.record > header, .subsection-heading, .list-heading { align-items: stretch; flex-direction: column; } }
	@media (max-width: 34rem) { .section-index { grid-template-columns: repeat(3, minmax(0, 1fr)); }.field-grid--four, .return-map { grid-template-columns: 1fr; }.section-stats { grid-template-columns: 1fr; }.event-strip { grid-template-columns: 1fr; }.toolbar-identity span { display: none; }.mode-card { min-height: 8rem; }.data-toolbar { padding: 0.55rem 0.7rem; }.notice, .confirmation { align-items: stretch; flex-direction: column; } }
	@media (prefers-reduced-motion: reduce) { .button, .text-button, .file-button { transition: none; } }
</style>
