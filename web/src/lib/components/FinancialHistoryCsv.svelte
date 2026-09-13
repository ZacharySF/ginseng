<script lang="ts">
	import type { HistoricalTransaction, TransactionCategory } from '$lib/finance';
	import { MAX_ABS_BALANCE_CENTS } from '$lib/workspace';
	import {
		buildImportCandidates,
		csvColumns,
		duplicateTransactionKeys,
		inferTransactionMapping,
		parseCsvCents,
		parseCsvDate,
		parseCsvTable,
		TRANSACTION_CATEGORIES,
		TRANSACTION_CATEGORY_LABELS,
		transactionCategorySignIssue,
		type CsvColumnMapping,
		type CsvTable,
		type ImportCandidate
	} from '$lib/financial-history-csv';

	interface Props {
		transactions: readonly HistoricalTransaction[];
		disabled?: boolean;
		maximumRecords?: number;
		onApply: (transactions: HistoricalTransaction[]) => void;
		onImportStateChange?: (hasPendingReview: boolean) => void;
	}

	interface RowEdit {
		date?: string;
		description?: string;
		amount?: string;
		category?: TransactionCategory;
		sourceKey?: string;
	}

	interface ReviewRow {
		sourceRow: number;
		date: string | null;
		description: string;
		amount_cents: number | null;
		category: TransactionCategory | null;
		source_key: string | null;
		issues: string[];
		duplicateKeys: string[];
		raw: string[];
	}

	let {
		transactions,
		disabled = false,
		maximumRecords = 20_000,
		onApply,
		onImportStateChange
	}: Props = $props();

	let table = $state<CsvTable | null>(null);
	let mapping = $state<CsvColumnMapping | null>(null);
	let hasHeader = $state(true);
	let fileName = $state<string | null>(null);
	let importError = $state<string | null>(null);
	let rowEdits = $state<Record<number, RowEdit>>({});
	let excludedRows = $state<number[]>([]);
	let page = $state(0);
	let fileRequest = 0;

	const PAGE_SIZE = 40;
	const columns = $derived(table ? csvColumns(table, hasHeader) : []);
	const baseCandidates = $derived(table && mapping ? buildImportCandidates(table, hasHeader, mapping) : []);
	const availableSlots = $derived(Math.max(0, maximumRecords - transactions.length));
	const reviewRows = $derived.by(() => {
		const earlier: Array<Pick<ReviewRow, 'date' | 'description' | 'amount_cents' | 'source_key'>> = [
			...transactions
		];
		return baseCandidates.map((candidate) => {
			const review = reviewedCandidate(candidate);
			const duplicateKeys = review.date !== null && review.amount_cents !== null
				? duplicateTransactionKeys(
					{
						date: review.date,
						description: review.description,
						amount_cents: review.amount_cents,
						source_key: review.source_key
					},
					earlier.filter((value): value is { date: string; description: string; amount_cents: number; source_key: string | null } =>
						value.date !== null && value.amount_cents !== null
					)
				)
				: [];
			if (review.date !== null && review.amount_cents !== null && review.issues.length === 0 && duplicateKeys.length === 0) earlier.push(review);
			return { ...review, duplicateKeys };
		});
	});
	const selectedRows = $derived(reviewRows.filter((row) => !excludedRows.includes(row.sourceRow)));
	const validRows = $derived(selectedRows.filter((row) => row.issues.length === 0 && row.duplicateKeys.length === 0));
	const acceptedRows = $derived(validRows.slice(0, availableSlots));
	const capacityExceededRows = $derived(new Set(validRows.slice(availableSlots).map((row) => row.sourceRow)));
	const pageCount = $derived(Math.max(1, Math.ceil(reviewRows.length / PAGE_SIZE)));
	const visibleRows = $derived(reviewRows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE));
	const acceptedCount = $derived(acceptedRows.length);

	function formattedCents(cents: number | null): string {
		if (cents === null) return '';
		const sign = cents < 0 ? '-' : '';
		const digits = Math.abs(cents).toString().padStart(3, '0');
		return `${sign}${digits.slice(0, -2)}.${digits.slice(-2)}`;
	}

	function reviewedCandidate(candidate: ImportCandidate): Omit<ReviewRow, 'duplicateKeys'> {
		const edit = rowEdits[candidate.sourceRow];
		const dateText = edit?.date ?? candidate.date ?? '';
		const amountText = edit?.amount ?? formattedCents(candidate.amount_cents);
		const date = parseCsvDate(dateText, 'year-month-day');
		const amount = parseCsvCents(amountText);
		const description = (edit?.description ?? candidate.description).trim();
		const category = edit?.category ?? candidate.category;
		const sourceKey = (edit?.sourceKey ?? candidate.source_key ?? '').trim() || null;
		const issues: string[] = [];
		if (!date) issues.push('Use a real ISO date from 1900 through 2100.');
		if (description.length === 0 || description.length > 500) issues.push('Add a description of up to 500 characters.');
		if (sourceKey !== null && sourceKey.length > 200) issues.push('Source IDs can be up to 200 characters.');
		if (amount === null) issues.push('Use a signed USD amount with at most two decimal places.');
		if (amount !== null && Math.abs(amount) > MAX_ABS_BALANCE_CENTS) issues.push('This amount is outside the supported range.');
		if (category === null) issues.push('Choose a classification before applying this row.');
		if (amount !== null && category !== null) {
			const signIssue = transactionCategorySignIssue(category, amount);
			if (signIssue) issues.push(signIssue);
		}
		return {
			sourceRow: candidate.sourceRow,
			date,
			description,
			amount_cents: amount,
			category,
			source_key: sourceKey,
			issues,
			raw: candidate.raw
		};
	}

	function resetReview(): void {
		rowEdits = {};
		excludedRows = [];
		page = 0;
	}

	function clearImport(): void {
		fileRequest += 1;
		table = null;
		mapping = null;
		fileName = null;
		importError = null;
		resetReview();
	}

	async function chooseFile(event: Event): Promise<void> {
		if (disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLInputElement)) return;
		const file = target.files?.[0];
		if (!file) return;
		const request = ++fileRequest;
		importError = null;
		try {
			const parsed = parseCsvTable(await file.text());
			if (request !== fileRequest) return;
			if (!parsed.table) {
				clearImport();
				importError = parsed.error;
				return;
			}
			table = parsed.table;
			hasHeader = true;
			mapping = inferTransactionMapping(parsed.table, true);
			fileName = file.name;
			resetReview();
		} catch {
			if (request !== fileRequest) return;
			clearImport();
			importError = 'The file could not be read. Choose a text CSV exported from your financial institution.';
		} finally {
			target.value = '';
		}
	}

	function changeHeader(event: Event): void {
		if (!table || disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLInputElement)) return;
		hasHeader = target.checked;
		mapping = inferTransactionMapping(table, hasHeader);
		resetReview();
	}

	function changeColumn(field: keyof Pick<CsvColumnMapping, 'date' | 'description' | 'amount' | 'debit' | 'credit' | 'category' | 'sourceKey'>, event: Event): void {
		if (!mapping || disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLSelectElement)) return;
		const nextValue = target.value === '' ? null : Number(target.value);
		if (nextValue !== null && (!Number.isInteger(nextValue) || nextValue < 0)) return;
		mapping[field] = nextValue;
		if (field === 'amount' && nextValue !== null) {
			mapping.debit = null;
			mapping.credit = null;
		}
		if ((field === 'debit' || field === 'credit') && nextValue !== null) mapping.amount = null;
		resetReview();
	}

	function changeDateOrder(event: Event): void {
		if (!mapping || disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLSelectElement)) return;
		if (!['year-month-day', 'month-day-year', 'day-month-year'].includes(target.value)) return;
		mapping.dateOrder = target.value as CsvColumnMapping['dateOrder'];
		resetReview();
	}

	function changeAmountInterpretation(event: Event): void {
		if (!mapping || disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLSelectElement)) return;
		if (target.value !== 'as-reported' && target.value !== 'reverse-sign') return;
		mapping.amountInterpretation = target.value;
		resetReview();
	}

	function updateEdit(sourceRow: number, field: keyof RowEdit, event: Event): void {
		if (disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
		const current = rowEdits[sourceRow] ?? {};
		if (field === 'category') {
			if (!TRANSACTION_CATEGORIES.includes(target.value as TransactionCategory)) return;
			rowEdits[sourceRow] = { ...current, category: target.value as TransactionCategory };
		} else if (field === 'date') {
			rowEdits[sourceRow] = { ...current, date: target.value };
		} else if (field === 'description') {
			rowEdits[sourceRow] = { ...current, description: target.value };
		} else if (field === 'amount') {
			rowEdits[sourceRow] = { ...current, amount: target.value };
		} else {
			rowEdits[sourceRow] = { ...current, sourceKey: target.value };
		}
	}

	function toggleRow(sourceRow: number, event: Event): void {
		if (disabled) return;
		const target = event.currentTarget;
		if (!(target instanceof HTMLInputElement)) return;
		if (target.checked) {
			excludedRows = excludedRows.filter((row) => row !== sourceRow);
		} else if (!excludedRows.includes(sourceRow)) {
			excludedRows = [...excludedRows, sourceRow];
		}
	}

	function selectValidRows(): void {
		if (disabled) return;
		excludedRows = reviewRows
			.filter((row) => row.issues.length > 0 || row.duplicateKeys.length > 0)
			.map((row) => row.sourceRow);
	}

	function applyRows(): void {
		if (disabled || acceptedCount === 0) return;
		const toApply = acceptedRows.flatMap((row) => {
			if (row.date === null || row.amount_cents === null || row.category === null) return [];
			return [
				{
					id: crypto.randomUUID(),
					date: row.date,
					description: row.description,
					amount_cents: row.amount_cents,
					category: row.category,
					source_key: row.source_key
				} satisfies HistoricalTransaction
			];
		});
		if (toApply.length === 0) return;
		onApply(toApply);
		clearImport();
	}

	function previousPage(): void {
		if (page > 0) page -= 1;
	}

	function nextPage(): void {
		if (page < pageCount - 1) page += 1;
	}

	$effect(() => {
		onImportStateChange?.(table !== null);
		return () => {
			onImportStateChange?.(false);
		};
	});
</script>

<section class="csv-import" aria-labelledby="csv-import-title">
	<header class="import-heading">
		<div>
			<p class="eyebrow">Manual review required</p>
			<h3 id="csv-import-title">Import transaction history from CSV</h3>
			<p>Files stay in this browser until you apply reviewed rows to the unsaved draft. Nothing is sent to Ginseng until you save the full workspace.</p>
		</div>
		<label class="file-button" class:file-button--disabled={disabled}>
			<span>{fileName ? 'Choose another CSV' : 'Choose CSV'}</span>
			<input type="file" accept=".csv,text/csv,text/plain" onchange={chooseFile} disabled={disabled} />
		</label>
	</header>

	{#if importError}
		<p class="import-alert import-alert--error" role="alert">{importError}</p>
	{/if}

	{#if table && mapping}
		<div class="review-toolbar">
			<p><strong>{fileName}</strong> · {table.rows.length.toLocaleString()} parsed rows · {table.delimiter === '\t' ? 'tab-delimited' : `${table.delimiter === ';' ? 'semicolon' : 'comma'}-delimited`}</p>
			<button type="button" class="text-button" onclick={clearImport} disabled={disabled}>Clear import</button>
		</div>

		{#if table.warnings.length > 0}
			<div class="import-alert" role="status">
				{#each table.warnings as warning (warning)}<p>{warning}</p>{/each}
			</div>
		{/if}

		<fieldset class="mapping-grid" disabled={disabled}>
			<legend>Map this export</legend>
			<label class="check-field">
				<input type="checkbox" checked={hasHeader} onchange={changeHeader} />
				<span>First row contains column names</span>
			</label>
			<label class="field"><span>Date</span><select value={mapping.date ?? ''} onchange={(event) => changeColumn('date', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Description</span><select value={mapping.description ?? ''} onchange={(event) => changeColumn('description', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Amount</span><select value={mapping.amount ?? ''} onchange={(event) => changeColumn('amount', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Debit (optional)</span><select value={mapping.debit ?? ''} onchange={(event) => changeColumn('debit', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Credit (optional)</span><select value={mapping.credit ?? ''} onchange={(event) => changeColumn('credit', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Category (optional)</span><select value={mapping.category ?? ''} onchange={(event) => changeColumn('category', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Source ID (optional)</span><select value={mapping.sourceKey ?? ''} onchange={(event) => changeColumn('sourceKey', event)}><option value="">No column</option>{#each columns as column (column.index)}<option value={column.index}>{column.label}</option>{/each}</select></label>
			<label class="field"><span>Date order</span><select value={mapping.dateOrder} onchange={changeDateOrder}><option value="year-month-day">YYYY-MM-DD</option><option value="month-day-year">MM/DD/YYYY</option><option value="day-month-year">DD/MM/YYYY</option></select></label>
			<label class="field"><span>Amount sign</span><select value={mapping.amountInterpretation} onchange={changeAmountInterpretation} disabled={mapping.debit !== null || mapping.credit !== null}><option value="as-reported">Use the sign in the file</option><option value="reverse-sign">Reverse every amount sign</option></select></label>
		</fieldset>
		<p class="mapping-help">Use one signed Amount column, or Debit and Credit columns. A debit becomes negative and a credit becomes positive. Review every category and sign below before applying.</p>

		<div class="review-summary" aria-live="polite">
			<div><strong>{reviewRows.length.toLocaleString()}</strong><span>rows read</span></div>
			<div><strong>{acceptedRows.length.toLocaleString()}</strong><span>ready to apply</span></div>
			<div><strong>{reviewRows.filter((row) => row.duplicateKeys.length > 0).length.toLocaleString()}</strong><span>duplicate warnings</span></div>
			<div><strong>{capacityExceededRows.size.toLocaleString()}</strong><span>over remaining capacity</span></div>
			<div><strong>{availableSlots.toLocaleString()}</strong><span>history slots left</span></div>
		</div>

		<div class="review-actions">
			<p>{acceptedCount > 0 ? `Applying will add ${acceptedCount.toLocaleString()} reviewed row${acceptedCount === 1 ? '' : 's'} to the unsaved History draft.` : 'Correct or uncheck rows before applying them to the draft.'}</p>
			<div>
				<button type="button" class="button button--quiet" onclick={selectValidRows} disabled={disabled}>Select valid rows</button>
				<button type="button" class="button button--primary" onclick={applyRows} disabled={disabled || acceptedCount === 0}>Apply reviewed rows</button>
			</div>
		</div>

		<div class="preview-wrap" aria-label="CSV import review">
			<table class="review-table">
				<thead><tr><th scope="col">Keep</th><th scope="col">Date</th><th scope="col">Description</th><th scope="col">Amount (USD)</th><th scope="col">Classification</th><th scope="col">Source ID</th><th scope="col">Review</th></tr></thead>
				<tbody>
					{#each visibleRows as row (row.sourceRow)}
						<tr class:row--problem={row.issues.length > 0 || row.duplicateKeys.length > 0 || capacityExceededRows.has(row.sourceRow)}>
							<td data-label="Keep"><label class="row-check"><input type="checkbox" checked={!excludedRows.includes(row.sourceRow)} onchange={(event) => toggleRow(row.sourceRow, event)} disabled={disabled} /><span class="sr-only">Keep CSV row {row.sourceRow}</span></label></td>
							<td data-label="Date"><input aria-label={`Date, CSV row ${row.sourceRow}`} type="date" min="1900-01-01" max="2100-12-31" value={rowEdits[row.sourceRow]?.date ?? row.date ?? ''} onchange={(event) => updateEdit(row.sourceRow, 'date', event)} disabled={disabled} /></td>
							<td data-label="Description"><input aria-label={`Description, CSV row ${row.sourceRow}`} value={rowEdits[row.sourceRow]?.description ?? row.description} maxlength="500" onchange={(event) => updateEdit(row.sourceRow, 'description', event)} disabled={disabled} /></td>
							<td data-label="Amount (USD)"><input aria-label={`Amount in US dollars, CSV row ${row.sourceRow}`} class="numeric" inputmode="decimal" value={rowEdits[row.sourceRow]?.amount ?? formattedCents(row.amount_cents)} placeholder="-12.34" onchange={(event) => updateEdit(row.sourceRow, 'amount', event)} disabled={disabled} /></td>
							<td data-label="Classification"><select aria-label={`Classification, CSV row ${row.sourceRow}`} value={rowEdits[row.sourceRow]?.category ?? row.category ?? ''} onchange={(event) => updateEdit(row.sourceRow, 'category', event)} disabled={disabled}><option value="" disabled>Choose classification</option>{#each TRANSACTION_CATEGORIES as category (category)}<option value={category}>{TRANSACTION_CATEGORY_LABELS[category]}</option>{/each}</select></td>
							<td data-label="Source ID"><input aria-label={`Source ID, CSV row ${row.sourceRow}`} value={rowEdits[row.sourceRow]?.sourceKey ?? row.source_key ?? ''} maxlength="200" onchange={(event) => updateEdit(row.sourceRow, 'sourceKey', event)} disabled={disabled} /></td>
							<td data-label="Review">
								{#if row.issues.length > 0}<ul class="issues">{#each row.issues as issue (issue)}<li>{issue}</li>{/each}</ul>{/if}
								{#if row.duplicateKeys.length > 0}<p class="duplicate">Possible duplicate of saved or earlier imported row. It will not apply unless you uncheck or correct it.</p>{/if}
								{#if capacityExceededRows.has(row.sourceRow)}<p class="duplicate">This otherwise valid row exceeds the remaining history capacity. Uncheck it or remove saved history before applying it.</p>{/if}
								<details class="raw-row"><summary>Source row {row.sourceRow}</summary><p>{row.raw.join(' · ')}</p></details>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		{#if reviewRows.length > PAGE_SIZE}
			<nav class="pagination" aria-label="CSV review pages">
				<button type="button" class="button button--quiet" onclick={previousPage} disabled={disabled || page === 0}>Previous</button>
				<span>Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, reviewRows.length)} of {reviewRows.length.toLocaleString()}</span>
				<button type="button" class="button button--quiet" onclick={nextPage} disabled={disabled || page >= pageCount - 1}>Next</button>
			</nav>
		{/if}
	{/if}
</section>

<style>
	.csv-import { display: grid; gap: 0.9rem; padding: 1rem; border: 1px solid var(--rule); background: var(--paper-soft); }
	.import-heading { display: flex; align-items: start; justify-content: space-between; gap: 1rem; }
	.import-heading > div { display: grid; gap: 0.28rem; max-width: 60ch; }
	.eyebrow { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.63rem; font-weight: 750; letter-spacing: 0.07em; text-transform: uppercase; }
	h3 { color: var(--ink); font-size: 1.08rem; letter-spacing: -0.035em; }
	.import-heading p:last-child, .mapping-help, .review-actions p { color: var(--ink-soft); font-size: 0.8rem; line-height: 1.45; }
	.file-button, .button, .text-button { display: inline-flex; align-items: center; justify-content: center; min-height: 2.75rem; padding: 0 0.75rem; border: 1px solid var(--control-border); border-radius: 0; background: var(--paper); color: var(--ink); font-family: var(--font-mono); font-size: 0.67rem; font-weight: 750; letter-spacing: 0.035em; text-transform: uppercase; cursor: pointer; }
	.file-button { position: relative; flex: none; overflow: hidden; }
	.file-button:focus-within { outline: 2px solid var(--cobalt-bright); outline-offset: 3px; }
	.file-button input { position: absolute; inset: 0; width: 100%; cursor: pointer; opacity: 0; }
	.file-button--disabled, .button:disabled, .text-button:disabled { cursor: not-allowed; opacity: 0.55; }
	.file-button:not(.file-button--disabled):hover, .button:hover:not(:disabled), .text-button:hover:not(:disabled) { border-color: var(--ink-soft); background: var(--paper-deep); }
	.button:active:not(:disabled), .text-button:active:not(:disabled) { transform: scale(0.98); }
	.button--primary { border-color: var(--cobalt); background: var(--cobalt); color: var(--paper); }
	.button--primary:hover:not(:disabled) { border-color: var(--cobalt-deep); background: var(--cobalt-deep); }
	.button--quiet, .text-button { background: transparent; }
	.import-alert { padding: 0.7rem 0.8rem; border: 1px solid var(--rule-strong); background: var(--paper); color: var(--ink-soft); font-size: 0.78rem; }
	.import-alert--error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
	.import-alert p + p { margin-top: 0.3rem; }
	.review-toolbar, .review-actions, .pagination { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; }
	.review-toolbar p, .pagination span { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.68rem; line-height: 1.4; }
	.mapping-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.65rem; min-width: 0; margin: 0; padding: 0.85rem; border: 1px solid var(--rule); }
	.mapping-grid legend { padding: 0 0.3rem; color: var(--ink); font-family: var(--font-mono); font-size: 0.67rem; font-weight: 750; letter-spacing: 0.045em; text-transform: uppercase; }
	.check-field { grid-column: 1 / -1; display: inline-flex; align-items: center; gap: 0.55rem; min-height: 2.75rem; color: var(--ink); font-size: 0.8rem; font-weight: 700; }
	.check-field input, .row-check input { inline-size: 1.1rem; block-size: 1.1rem; accent-color: var(--cobalt); }
	.field { display: grid; gap: 0.3rem; min-width: 0; color: var(--ink-soft); font-size: 0.72rem; font-weight: 700; }
	select, input { width: 100%; min-width: 0; min-height: 2.75rem; padding: 0 0.6rem; border: 1px solid var(--control-border); border-radius: 0; background: var(--paper); color: var(--ink); font: inherit; font-size: 0.8rem; }
	select { cursor: pointer; }
	select:disabled, input:disabled { cursor: not-allowed; opacity: 0.62; }
	.mapping-help { margin: -0.2rem 0 0; }
	.review-summary { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1px; border: 1px solid var(--rule); background: var(--rule); }
	.review-summary div { display: grid; gap: 0.16rem; padding: 0.65rem 0.7rem; background: var(--paper); }
	.review-summary strong { color: var(--ink); font-size: 1.05rem; font-variant-numeric: tabular-nums; letter-spacing: -0.04em; }
	.review-summary span { color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.6rem; font-weight: 700; letter-spacing: 0.045em; text-transform: uppercase; }
	.review-actions { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.75rem; border: 1px solid var(--rule); background: var(--paper-deep); }
	.review-actions > div { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.preview-wrap { position: relative; max-width: 100%; overflow-x: auto; border: 1px solid var(--rule); background: var(--rule); }
	.review-table { width: 100%; min-width: 75rem; border-collapse: collapse; background: var(--paper); }
	.review-table th { padding: 0.5rem 0.55rem; background: var(--paper-deep); color: var(--ink-soft); font-family: var(--font-mono); font-size: 0.6rem; font-weight: 750; letter-spacing: 0.045em; text-align: left; text-transform: uppercase; }
	.review-table td { min-width: 8rem; padding: 0.45rem; border-top: 1px solid var(--rule); vertical-align: top; }
	.review-table td:first-child { min-width: 3.4rem; width: 3.4rem; text-align: center; }
	.review-table td:nth-child(3) { min-width: 14rem; }
	.review-table td:last-child { min-width: 17rem; }
	.row--problem { background: var(--negative-soft); }
	.issues { display: grid; gap: 0.18rem; padding: 0; margin: 0; color: var(--negative); font-size: 0.69rem; line-height: 1.3; list-style: none; }
	.duplicate { margin: 0.35rem 0 0; color: var(--warning); font-size: 0.69rem; line-height: 1.35; }
	.raw-row { margin-top: 0.4rem; color: var(--ink-soft); font-size: 0.67rem; }
	.raw-row summary { cursor: pointer; }
	.raw-row p { margin-top: 0.28rem; overflow-wrap: anywhere; }
	.pagination { padding-top: 0.05rem; }
	@media (max-width: 52rem) {
		.import-heading, .review-toolbar, .review-actions, .pagination { align-items: stretch; flex-direction: column; }
		.file-button { align-self: start; min-width: 10rem; }
		.mapping-grid { grid-template-columns: 1fr 1fr; }
		.review-summary { grid-template-columns: 1fr 1fr; }
		.review-actions > div { width: 100%; }
		.review-actions .button { flex: 1 1 12rem; }
	}
	@media (max-width: 32rem) { .mapping-grid { grid-template-columns: 1fr; }.review-summary { grid-template-columns: 1fr; } }
	@media (prefers-reduced-motion: reduce) { .button, .text-button { transition: none; } }
</style>
