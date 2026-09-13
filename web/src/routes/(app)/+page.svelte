<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { authStore } from '$lib/auth.svelte';
	import {
		getWorkspace,
		projectWorkspace,
		saveWorkspace,
		parseUsdCents,
		MAX_ABS_BALANCE_CENTS,
		MAX_BILL_CENTS,
		WORKSPACE_SAVED_EVENT,
		type WorkspaceSavedDetail,
		type CashAccount,
		type CashAccountKind,
		type CashBill,
		type CashWorkspace,
		type ProjectionHorizonDays,
		type ScheduledProjection,
		type WorkspaceDraft
	} from '$lib/workspace';

	type WorkspaceLoadState = 'loading' | 'ready' | 'error' | 'unconfigured';
	type RemovalCandidate =
		| { collection: 'account'; id: string; label: string }
		| { collection: 'bill'; id: string; label: string };

	interface AccountDraft {
		id: string;
		name: string;
		kind: CashAccountKind;
		balance: string;
	}

	interface BillDraft {
		id: string;
		label: string;
		amount: string;
		due_date: string;
	}

	const MIN_DATE = '1900-01-01';
	const MAX_DATE = '2100-12-31';
	const HORIZONS: ProjectionHorizonDays[] = [14, 30, 60];

	let isAlive = false;
	let pendingAssistantWorkspace: CashWorkspace | null = null;
	let requestVersion = 0;
	let currentIdentity: string | null = null;
	let workspaceState = $state<WorkspaceLoadState>('loading');
	let savedWorkspace = $state<CashWorkspace | null>(null);
	let draftAsOf = $state(localToday());
	let accountDrafts = $state<AccountDraft[]>([]);
	let billDrafts = $state<BillDraft[]>([]);
	let loadError = $state<string | null>(null);
	let formIssues = $state<string[]>([]);
	let saveMessage = $state<string | null>(null);
	let saveError = $state<string | null>(null);
	let isSaving = $state(false);
	let saveUncertain = $state(false);
	let reloadConfirmation = $state(false);
	let removalCandidate = $state<RemovalCandidate | null>(null);
	let selectedHorizon = $state<ProjectionHorizonDays>(30);
	let projection = $state<ScheduledProjection | null>(null);
	let projectionError = $state<string | null>(null);
	let isProjecting = $state(false);

	const editingLocked = $derived(isSaving || workspaceState !== 'ready');
	const draftIsDirty = $derived(draftSignature() !== savedSignature());
	const savedRevision = $derived(savedWorkspace?.revision ?? 0);
	const canProject = $derived(
		workspaceState === 'ready' &&
		!draftIsDirty &&
		!isSaving &&
		!saveUncertain &&
		!isProjecting &&
		savedWorkspace?.as_of !== null &&
		(savedWorkspace?.accounts.length ?? 0) > 0
	);

	function localToday(): string {
		const today = new Date();
		return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
	}

	function formatCents(cents: number): string {
		const sign = cents < 0 ? '-' : '';
		const digits = Math.abs(cents).toString().padStart(3, '0');
		const whole = digits.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
		return `${sign}$${whole}.${digits.slice(-2)}`;
	}

	function centsInput(cents: number): string {
		const sign = cents < 0 ? '-' : '';
		const digits = Math.abs(cents).toString().padStart(3, '0');
		return `${sign}${digits.slice(0, -2)}.${digits.slice(-2)}`;
	}


	function isCalendarDate(value: string): boolean {
		if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < MIN_DATE || value > MAX_DATE) return false;
		const date = new Date(`${value}T00:00:00Z`);
		return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
	}

	function toAccountDraft(account: CashAccount): AccountDraft {
		return { id: account.id, name: account.name, kind: account.kind, balance: centsInput(account.balance_cents) };
	}

	function toBillDraft(bill: CashBill): BillDraft {
		return { id: bill.id, label: bill.label, amount: centsInput(bill.amount_cents), due_date: bill.due_date };
	}

	function applyWorkspace(workspace: CashWorkspace): void {
		savedWorkspace = workspace;
		draftAsOf = workspace.as_of ?? localToday();
		accountDrafts = workspace.accounts.map(toAccountDraft);
		billDrafts = workspace.bills.map(toBillDraft);
		formIssues = [];
		saveError = null;
		saveMessage = null;
		saveUncertain = false;
		reloadConfirmation = false;
		removalCandidate = null;
		projection = null;
		projectionError = null;
	}

	function receiveAssistantWorkspace(workspace: CashWorkspace): void {
		if (workspace.revision <= (savedWorkspace?.revision ?? -1)) return;
		if (isSaving) {
			if (workspace.revision > (pendingAssistantWorkspace?.revision ?? -1)) {
				pendingAssistantWorkspace = workspace;
			}
			return;
		}
		requestVersion += 1;
		isProjecting = false;
		projection = null;
		projectionError = null;
		if (draftIsDirty || saveUncertain) {
			saveError = 'The assistant saved a newer snapshot. Your unsaved edits are still here; reload only if you want to discard them.';
			reloadConfirmation = true;
			if (savedWorkspace) workspaceState = 'ready';
			return;
		}
		applyWorkspace(workspace);
		workspaceState = 'ready';
		loadError = null;
		saveMessage = `Assistant saved snapshot revision ${workspace.revision}.`;
	}

	function resetWorkspace(): void {
		requestVersion += 1;
		pendingAssistantWorkspace = null;
		currentIdentity = null;
		workspaceState = authStore.status === 'unconfigured' ? 'unconfigured' : 'loading';
		savedWorkspace = null;
		draftAsOf = localToday();
		accountDrafts = [];
		billDrafts = [];
		loadError = null;
		formIssues = [];
		saveMessage = null;
		saveError = null;
		isSaving = false;
		saveUncertain = false;
		reloadConfirmation = false;
		removalCandidate = null;
		projection = null;
		projectionError = null;
		isProjecting = false;
	}

	function snapshotSignature(asOf: string, accounts: AccountDraft[], bills: BillDraft[]): string {
		return JSON.stringify({
			as_of: asOf,
			accounts: [...accounts]
				.map(({ id, name, kind, balance }) => ({ id, name, kind, balance }))
				.sort((left, right) => left.id.localeCompare(right.id)),
			bills: [...bills]
				.map(({ id, label, amount, due_date }) => ({ id, label, amount, due_date }))
				.sort((left, right) => left.due_date.localeCompare(right.due_date) || left.id.localeCompare(right.id))
		});
	}

	function draftSignature(): string {
		return snapshotSignature(draftAsOf, accountDrafts, billDrafts);
	}

	function savedSignature(): string {
		if (!savedWorkspace) return snapshotSignature(localToday(), [], []);
		return snapshotSignature(
			savedWorkspace.as_of ?? localToday(),
			savedWorkspace.accounts.map(toAccountDraft),
			savedWorkspace.bills.map(toBillDraft)
		);
	}

	function belongsToCurrentSession(identity: string, version: number): boolean {
		return isAlive && version === requestVersion && identity === currentIdentity && authStore.user?.id === identity;
	}

	async function loadWorkspace(identity = currentIdentity): Promise<void> {
		if (isSaving || !identity || authStore.status !== 'signed-in') return;
		const version = ++requestVersion;
		workspaceState = 'loading';
		isProjecting = false;
		projection = null;
		projectionError = null;
		loadError = null;
		try {
			const result = await getWorkspace();
			if (!belongsToCurrentSession(identity, version)) return;
			if (result.status === 'ok') {
				applyWorkspace(result.data);
				workspaceState = 'ready';
				return;
			}
			workspaceState = 'error';
			loadError = result.message;
		} catch {
			if (!belongsToCurrentSession(identity, version)) return;
			workspaceState = 'error';
			loadError = 'Your saved workspace could not be loaded. Retry to continue.';
		}
	}

	function validateDraft(): WorkspaceDraft | null {
		const issues: string[] = [];
		if ((savedWorkspace?.revision ?? 0) > Number.MAX_SAFE_INTEGER - 1) {
			issues.push('This workspace has reached its final revision and cannot be saved again.');
		}
		if (!isCalendarDate(draftAsOf)) {
			issues.push(`Opening date must be a real date between ${MIN_DATE} and ${MAX_DATE}.`);
		}
		if (accountDrafts.length > 50) issues.push('A workspace can contain up to 50 cash accounts.');
		if (billDrafts.length > 200) issues.push('A workspace can contain up to 200 one-time bills.');

		const accountIds = new Set<string>();
		const accounts: CashAccount[] = accountDrafts.map((account, index) => {
			const name = account.name.trim();
			const balance = parseUsdCents(account.balance);
			if (accountIds.has(account.id)) issues.push(`Account ${index + 1} has a duplicate identifier.`);
			accountIds.add(account.id);
			if (name.length === 0 || name.length > 100) issues.push(`Account ${index + 1} needs a name of 1–100 characters.`);
			if (balance === null || Math.abs(balance) > MAX_ABS_BALANCE_CENTS) issues.push(`Account ${index + 1} needs a signed USD amount up to $1,000,000,000.00.`);
			return { id: account.id, name, kind: account.kind, balance_cents: balance ?? 0 };
		});

		const billIds = new Set<string>();
		const bills: CashBill[] = billDrafts.map((bill, index) => {
			const label = bill.label.trim();
			const amount = parseUsdCents(bill.amount, false);
			if (billIds.has(bill.id)) issues.push(`Bill ${index + 1} has a duplicate identifier.`);
			billIds.add(bill.id);
			if (label.length === 0 || label.length > 100) issues.push(`Bill ${index + 1} needs a label of 1–100 characters.`);
			if (amount === null || amount < 1 || amount > MAX_BILL_CENTS) issues.push(`Bill ${index + 1} needs a positive USD amount up to $1,000,000,000.00.`);
			if (!isCalendarDate(bill.due_date)) {
				issues.push(`Bill ${index + 1} needs a real due date between ${MIN_DATE} and ${MAX_DATE}.`);
			} else if (isCalendarDate(draftAsOf) && bill.due_date < draftAsOf) {
				issues.push(`Bill ${index + 1} is before the opening date. Resolve overdue bills before saving.`);
			}
			return { id: bill.id, label, amount_cents: amount ?? 0, due_date: bill.due_date };
		});

		formIssues = issues;
		if (issues.length > 0 || !isCalendarDate(draftAsOf)) return null;
		return { expected_revision: savedWorkspace?.revision ?? 0, as_of: draftAsOf, accounts, bills };
	}

	function invalidateProjection(): void {
		projection = null;
		projectionError = null;
	}

	function addAccount(): void {
		if (accountDrafts.length >= 50 || editingLocked) return;
		accountDrafts.push({ id: crypto.randomUUID(), name: '', kind: 'checking', balance: '0.00' });
		invalidateProjection();
	}

	function addBill(): void {
		if (billDrafts.length >= 200 || editingLocked) return;
		billDrafts.push({ id: crypto.randomUUID(), label: '', amount: '', due_date: draftAsOf });
		invalidateProjection();
	}

	function savedItem(collection: RemovalCandidate['collection'], id: string): boolean {
		if (!savedWorkspace) return false;
		return collection === 'account'
			? savedWorkspace.accounts.some((account) => account.id === id)
			: savedWorkspace.bills.some((bill) => bill.id === id);
	}

	function requestRemoval(candidate: RemovalCandidate): void {
		if (editingLocked) return;
		if (savedItem(candidate.collection, candidate.id)) {
			removalCandidate = candidate;
			return;
		}
		removeDraft(candidate);
	}

	function removeDraft(candidate: RemovalCandidate): void {
		if (candidate.collection === 'account') {
			accountDrafts = accountDrafts.filter((account) => account.id !== candidate.id);
		} else {
			billDrafts = billDrafts.filter((bill) => bill.id !== candidate.id);
		}
		removalCandidate = null;
		invalidateProjection();
	}

	async function saveDraft(): Promise<void> {
		if (editingLocked || saveUncertain || !currentIdentity) return;
		const draft = validateDraft();
		if (!draft) {
			saveError = 'Fix the listed fields before saving this snapshot.';
			return;
		}
		isSaving = true;
		isProjecting = false;
		saveError = null;
		saveMessage = null;
		projectionError = null;
		projection = null;
		const identity = currentIdentity;
		const version = ++requestVersion;
		try {
			const result = await saveWorkspace(draft);
			if (!belongsToCurrentSession(identity, version)) return;
			if (result.status === 'ok') {
				applyWorkspace(result.data);
				saveMessage = `Saved snapshot revision ${result.data.revision}.`;
				workspaceState = 'ready';
				return;
			}
			if (result.status === 'engine-error' && result.http_status === 409) {
				saveError = 'This workspace changed elsewhere. Your edits are still here; reload only if you want to discard them.';
				reloadConfirmation = true;
			} else if (result.status === 'engine-unreachable' || result.http_status === undefined || result.http_status >= 500) {
				saveUncertain = true;
				saveError = 'We did not receive a save acknowledgment. Reload and reconcile the saved snapshot before trying again; your local entries are still here.';
			} else {
				saveError = result.message;
			}
		} catch {
			if (!belongsToCurrentSession(identity, version)) return;
			saveUncertain = true;
			saveError = 'We did not receive a save acknowledgment. Reload and reconcile the saved snapshot before trying again; your local entries are still here.';
		} finally {
			if (belongsToCurrentSession(identity, version)) {
				isSaving = false;
				if (pendingAssistantWorkspace) {
					const updated = pendingAssistantWorkspace;
					pendingAssistantWorkspace = null;
					receiveAssistantWorkspace(updated);
				}
			}
		}
	}

	function requestReload(): void {
		if (isSaving) return;
		if (draftIsDirty || saveUncertain) {
			reloadConfirmation = true;
			return;
		}
		void loadWorkspace();
	}

	function confirmReload(): void {
		reloadConfirmation = false;
		void loadWorkspace();
	}

	async function requestProjection(): Promise<void> {
		if (!canProject || !currentIdentity || !savedWorkspace) return;
		const identity = currentIdentity;
		const expectedRevision = savedWorkspace.revision;
		const version = ++requestVersion;
		isProjecting = true;
		projection = null;
		projectionError = null;
		try {
			const result = await projectWorkspace(selectedHorizon);
			if (!belongsToCurrentSession(identity, version)) return;
			if (result.status !== 'ok') {
				projectionError = result.message;
				return;
			}
			if (savedWorkspace?.revision !== expectedRevision || draftIsDirty || result.data.input_revision !== expectedRevision) {
				projectionError = 'The saved snapshot changed while this projection was running. Reload or request a new scheduled projection.';
				return;
			}
			projection = result.data;
		} catch {
			if (!belongsToCurrentSession(identity, version)) return;
			projectionError = 'The scheduled projection could not be loaded. Try again from the saved snapshot.';
		} finally {
			if (belongsToCurrentSession(identity, version)) isProjecting = false;
		}
	}

	function chooseHorizon(horizon: ProjectionHorizonDays): void {
		if (isProjecting || editingLocked) return;
		selectedHorizon = horizon;
		invalidateProjection();
	}

	onMount(() => {
		isAlive = true;
		const assistantSaved = (event: Event) => {
			const detail = (event as CustomEvent<WorkspaceSavedDetail>).detail;
			if (detail?.ownerId !== currentIdentity || detail?.ownerId !== authStore.user?.id) return;
			receiveAssistantWorkspace(detail.workspace);
		};
		window.addEventListener(WORKSPACE_SAVED_EVENT, assistantSaved);
		return () => {
			window.removeEventListener(WORKSPACE_SAVED_EVENT, assistantSaved);
			isAlive = false;
			requestVersion += 1;
		};
	});

	$effect(() => {
		const status = authStore.status;
		const identity = authStore.user?.id ?? null;
		if (status === 'unconfigured') {
			if (workspaceState !== 'unconfigured') resetWorkspace();
			return;
		}
		if (status !== 'signed-in' || !identity) {
			if (currentIdentity !== null || savedWorkspace !== null) resetWorkspace();
			return;
		}
		if (identity !== currentIdentity) {
			resetWorkspace();
			currentIdentity = identity;
			void loadWorkspace(identity);
		}
	});
</script>

<svelte:head>
	<title>Ginseng — Personal cash workspace</title>
	<meta
		name="description"
		content="Record settled cash and one-time bills, save an opening-of-day snapshot, and inspect a deterministic scheduled cash projection."
	/>
</svelte:head>

{#if workspaceState === 'unconfigured'}
	<section class="configuration-state" aria-labelledby="setup-title">
		<p class="eyebrow">Personal workspace</p>
		<h1 id="setup-title">Workspace setup is unavailable</h1>
		<p>Personal cash snapshots require the configured sign-in service and workspace engine. No account or bill has been saved here.</p>
		<a href={resolve('/demo')}>Open the simulated demo instead</a>
	</section>
{:else if workspaceState === 'loading' && !savedWorkspace}
	<section class="configuration-state" role="status" aria-live="polite">
		<p class="eyebrow">Personal workspace</p>
		<h1>Loading your saved snapshot</h1>
		<p>Loading the cash accounts and bills saved to your Ginseng account.</p>
	</section>
{:else if workspaceState === 'error' && !savedWorkspace}
	<section class="configuration-state configuration-state--error" role="alert" aria-labelledby="load-error-title">
		<p class="eyebrow">Personal workspace</p>
		<h1 id="load-error-title">Saved workspace unavailable</h1>
		<p>{loadError}</p>
		<button type="button" onclick={requestReload}>Retry loading</button>
	</section>
{:else}
	<div class="workspace">
		<header class="workspace-header">
			<div class="workspace-intro">
				<p class="eyebrow">Personal cash ledger · USD</p>
				<h1>Cash accounts and upcoming bills</h1>
				<p>Save one manually entered opening-of-day snapshot, then inspect the balance after only the bills you record below. Ginseng is not connected to a bank.</p>
			</div>
			<dl class="snapshot-status" aria-label="Saved snapshot status">
				<div><dt>Source</dt><dd>{savedWorkspace?.as_of ? 'Manual entry' : 'Not saved'}</dd></div>
				<div><dt>Opening date</dt><dd>{savedWorkspace?.as_of ?? 'Not set'}</dd></div>
				<div><dt>Revision</dt><dd class="numeric">{savedRevision}</dd></div>
			</dl>
		</header>

		{#if workspaceState === 'loading'}
			<p class="notice" role="status" aria-live="polite">Refreshing the saved snapshot. Your current draft remains visible until the response arrives.</p>
		{/if}
		{#if loadError && savedWorkspace}
			<div class="notice notice--error" role="alert"><span>{loadError}</span><button type="button" onclick={requestReload}>Retry reload</button></div>
		{/if}
		{#if saveMessage}
			<p class="notice notice--success" role="status" aria-live="polite">{saveMessage}</p>
		{/if}
		{#if saveError}
			<div class="notice notice--error" role="alert"><span>{saveError}</span>{#if !reloadConfirmation && !isSaving}<button type="button" onclick={requestReload}>Reload saved snapshot</button>{/if}</div>
		{/if}
		{#if reloadConfirmation}
			<div class="confirmation" role="alert">
				<p>Reloading will discard every unsaved account, bill, and opening date currently on this page.</p>
				<div><button type="button" class="button button--danger" onclick={confirmReload}>Discard drafts and reload</button><button type="button" class="button button--quiet" onclick={() => (reloadConfirmation = false)}>Keep editing</button></div>
			</div>
		{/if}
		{#if removalCandidate}
			<div class="confirmation" role="alert">
				<p>Remove saved {removalCandidate.collection === 'account' ? 'account' : 'bill'} “{removalCandidate.label || 'unnamed entry'}” from this draft? It will remain saved until you save the changed snapshot.</p>
				<div><button type="button" class="button button--danger" onclick={() => removeDraft(removalCandidate!)}>Remove from draft</button><button type="button" class="button button--quiet" onclick={() => (removalCandidate = null)}>Cancel</button></div>
			</div>
		{/if}
		{#if formIssues.length > 0}
			<div class="validation-summary" role="alert" aria-labelledby="validation-title">
				<strong id="validation-title">Check this snapshot before saving</strong>
				<ul>{#each formIssues as issue (issue)}<li>{issue}</li>{/each}</ul>
			</div>
		{/if}

		<div class="ledger-layout">
			<section class="entry-panel" aria-labelledby="snapshot-title">
				<div class="section-heading">
					<div><p class="eyebrow">1 · Opening of day</p><h2 id="snapshot-title">Settled cash accounts</h2></div>
					<p>Use balances that are settled at the start of one shared date.</p>
				</div>
				<label class="field field--date"><span>Balances reflect the opening of</span><input aria-describedby="date-help" type="date" min={MIN_DATE} max={MAX_DATE} bind:value={draftAsOf} oninput={invalidateProjection} disabled={editingLocked} /></label>
				<p id="date-help" class="field-help">All account balances share this date. Each bill has its own due date.</p>

				<div class="ledger" aria-label="Cash accounts">
					<div class="ledger-head ledger-head--accounts" aria-hidden="true"><span>Account</span><span>Kind</span><span>Settled balance (USD)</span><span></span></div>
					{#each accountDrafts as account, index (account.id)}
						<div class="ledger-row ledger-row--accounts">
							<label class="field" data-label="Account"><span class="sr-only">Account {index + 1} name</span><input maxlength="100" placeholder="e.g. Main checking" bind:value={account.name} oninput={invalidateProjection} disabled={editingLocked} /></label>
							<label class="field" data-label="Kind"><span class="sr-only">Account {index + 1} kind</span><select bind:value={account.kind} onchange={invalidateProjection} disabled={editingLocked}><option value="checking">Checking</option><option value="savings">Savings</option></select></label>
							<label class="field" data-label="Settled balance (USD)"><span class="sr-only">Account {index + 1} settled balance in US dollars</span><input class="numeric" inputmode="decimal" autocomplete="off" placeholder="0.00" bind:value={account.balance} oninput={invalidateProjection} disabled={editingLocked} /></label>
							<button class="icon-button" type="button" aria-label={`Remove ${account.name || `account ${index + 1}`}`} title="Remove account" onclick={() => requestRemoval({ collection: 'account', id: account.id, label: account.name })} disabled={editingLocked}>Remove</button>
						</div>
					{/each}
				</div>
				{#if accountDrafts.length === 0}<p class="empty-ledger">Add at least one checking or savings account before requesting a scheduled projection.</p>{/if}
				<button type="button" class="button button--add" onclick={addAccount} disabled={editingLocked || accountDrafts.length >= 50}>Add account</button>
			</section>

			<section class="entry-panel" aria-labelledby="bills-title">
				<div class="section-heading"><div><p class="eyebrow">2 · Known outflows</p><h2 id="bills-title">One-time bills</h2></div><p>Only upcoming bills are included. Resolve bills before the opening date first.</p></div>
				<div class="ledger" aria-label="One-time bills">
					<div class="ledger-head ledger-head--bills" aria-hidden="true"><span>Bill</span><span>Amount (USD)</span><span>Due date</span><span></span></div>
					{#each billDrafts as bill, index (bill.id)}
						<div class="ledger-row ledger-row--bills">
							<label class="field" data-label="Bill"><span class="sr-only">Bill {index + 1} label</span><input maxlength="100" placeholder="e.g. Rent" bind:value={bill.label} oninput={invalidateProjection} disabled={editingLocked} /></label>
							<label class="field" data-label="Amount (USD)"><span class="sr-only">Bill {index + 1} amount in US dollars</span><input class="numeric" inputmode="decimal" autocomplete="off" placeholder="0.00" bind:value={bill.amount} oninput={invalidateProjection} disabled={editingLocked} /></label>
							<label class="field" data-label="Due date"><span class="sr-only">Bill {index + 1} due date</span><input type="date" min={isCalendarDate(draftAsOf) ? draftAsOf : MIN_DATE} max={MAX_DATE} bind:value={bill.due_date} oninput={invalidateProjection} disabled={editingLocked} /></label>
							<button class="icon-button" type="button" aria-label={`Remove ${bill.label || `bill ${index + 1}`}`} title="Remove bill" onclick={() => requestRemoval({ collection: 'bill', id: bill.id, label: bill.label })} disabled={editingLocked}>Remove</button>
						</div>
					{/each}
				</div>
				{#if billDrafts.length === 0}<p class="empty-ledger">No bills are scheduled. Add a one-time known outflow if it belongs in this snapshot.</p>{/if}
				<button type="button" class="button button--add" onclick={addBill} disabled={editingLocked || billDrafts.length >= 200}>Add bill</button>
			</section>
		</div>

		<footer class="save-bar">
			<div><strong>{draftIsDirty ? 'Unsaved changes' : savedWorkspace?.as_of ? 'No unsaved changes' : 'Snapshot not saved'}</strong><span>{draftIsDirty ? 'Projection results are hidden until these edits are saved.' : 'A scheduled projection always refers to the saved snapshot only.'}</span></div>
			<div class="save-actions"><button type="button" class="button button--quiet" onclick={requestReload} disabled={isSaving || workspaceState === 'loading'}>{reloadConfirmation ? 'Reload confirmation open' : 'Reload saved'}</button><button type="button" class="button button--primary" onclick={saveDraft} disabled={editingLocked || saveUncertain}>{isSaving ? 'Saving snapshot…' : 'Save snapshot'}</button></div>
		</footer>

		<section class="projection-panel" aria-labelledby="projection-title">
			<div class="projection-head">
				<div><p class="eyebrow">3 · Saved snapshot only</p><h2 id="projection-title">Scheduled balance timeline</h2><p>Deterministic bill timing, not a forecast: it excludes unscheduled spending, income, transaction history, and probability estimates.</p></div>
				<div class="horizon-picker" aria-label="Projection horizon">
					{#each HORIZONS as horizon (horizon)}<button type="button" class:active={selectedHorizon === horizon} aria-pressed={selectedHorizon === horizon} onclick={() => chooseHorizon(horizon)} disabled={isProjecting}>{horizon} days</button>{/each}
				</div>
			</div>
			<div class="projection-actions"><button type="button" class="button button--primary" onclick={requestProjection} disabled={!canProject}>{isProjecting ? 'Calculating scheduled balance…' : `View ${selectedHorizon}-day schedule`}</button>{#if !canProject}<p>{draftIsDirty ? 'Save or discard edits before requesting a projection.' : saveUncertain ? 'Reload and reconcile the prior save before requesting a projection.' : isProjecting ? 'Calculating from the saved snapshot.' : isSaving ? 'Saving your snapshot.' : !savedWorkspace?.as_of ? 'Save an opening date and account first.' : 'A saved account is required.'}</p>{/if}</div>
			{#if projectionError}<p class="projection-error" role="alert">{projectionError}</p>{/if}

			{#if projection}
				<div class="projection-results" aria-live="polite">
					<div class="result-meta"><span>Saved revision {projection.input_revision}</span><span>Opening date {projection.as_of}</span><span>{projection.model_version}</span></div>
					<div class="result-summary">
						<div><span>Opening cash</span><strong class="numeric">{formatCents(projection.opening_balance_cents)}</strong></div>
						<div><span>Scheduled bills</span><strong class="numeric">−{formatCents(projection.scheduled_bills_cents)}</strong></div>
						<div class:negative={projection.ending_balance_cents < 0}><span>Ending cash</span><strong class="numeric">{formatCents(projection.ending_balance_cents)}</strong></div>
						<div class:negative={projection.lowest_balance_cents < 0}><span>Lowest cash</span><strong class="numeric">{formatCents(projection.lowest_balance_cents)}</strong><small>{projection.first_shortfall_date ? `First below zero: ${projection.first_shortfall_date}` : 'No scheduled shortfall'}</small></div>
					</div>
					<div class="timeline-table-wrap">
						<table class="timeline-table"><caption>Daily scheduled balances for the saved opening date and selected horizon.</caption><thead><tr><th scope="col">Date</th><th scope="col">Billed outflow</th><th scope="col">End-of-day balance</th></tr></thead><tbody>{#each projection.days as day (day.date)}<tr class:negative={day.balance_cents < 0}><th scope="row" data-label="Date">{day.date}</th><td data-label="Billed outflow" class="numeric">{day.bills_cents === 0 ? '—' : `−${formatCents(day.bills_cents)}`}</td><td data-label="End-of-day balance" class="numeric">{formatCents(day.balance_cents)}</td></tr>{/each}</tbody></table>
					</div>
				</div>
			{/if}
		</section>
	</div>
{/if}

<style>
	.workspace, .configuration-state { min-height: calc(100dvh - 3.25rem); background: var(--paper); color: var(--ink); }
	.workspace { padding: clamp(1rem, 2.5vw, 2.5rem); }
	.configuration-state { display: grid; align-content: center; justify-items: start; gap: .8rem; padding: clamp(1.5rem, 8vw, 7rem); }
	.configuration-state h1, .workspace h1, .workspace h2 { color: var(--ink); letter-spacing: -.045em; text-wrap: balance; }
	.configuration-state h1 { max-width: 16ch; font-size: clamp(2rem, 5vw, 3.4rem); line-height: .94; }
	.configuration-state p { max-width: 54ch; color: var(--ink-soft); }
	.configuration-state a { min-height: 2.75rem; display: inline-flex; align-items: center; padding: 0 .9rem; background: var(--cobalt); color: var(--on-accent); font-weight: 700; text-decoration: none; }
	.configuration-state--error h1 { color: var(--negative); }
	.eyebrow, .snapshot-status dt, .result-meta, .timeline-table caption { color: var(--ink-soft); font-family: var(--font-mono); font-size: .65rem; font-weight: 700; letter-spacing: .055em; text-transform: uppercase; }
	.workspace-header { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2rem; align-items: end; padding: 0 0 1.4rem; border-bottom: 1px solid var(--rule); }
	.workspace-intro { display: grid; gap: .45rem; max-width: 52rem; }
	.workspace-intro h1 { font-size: clamp(2rem, 3vw, 2.75rem); line-height: 1.05; }
	.workspace-intro > p:last-child { max-width: 58ch; color: var(--ink-soft); font-size: 1rem; }
	.snapshot-status { display: grid; grid-template-columns: repeat(3, minmax(6.6rem, 1fr)); gap: 1px; margin: 0; background: var(--rule); border: 1px solid var(--rule); }
	.snapshot-status div { display: grid; gap: .25rem; min-width: 0; padding: .7rem .8rem; background: var(--paper-soft); }
	.snapshot-status dd { overflow: hidden; margin: 0; color: var(--ink); font-size: .85rem; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
	.notice, .confirmation, .validation-summary, .projection-error { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 1rem 0 0; padding: .75rem .9rem; border: 1px solid var(--rule-strong); background: var(--paper-soft); color: var(--ink-soft); font-size: .85rem; }
	.notice--error, .projection-error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
	.notice--success { border-color: var(--positive); color: var(--ink); }
	.confirmation { display: grid; justify-content: stretch; border-color: var(--negative); background: var(--negative-soft); color: var(--ink); }
	.confirmation > div, .save-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
	.validation-summary { display: block; border-color: var(--negative); background: var(--negative-soft); color: var(--ink); }
	.validation-summary strong { color: var(--negative); }
	.validation-summary ul { margin: .45rem 0 0; padding-left: 1.2rem; }
	.ledger-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1px; margin-top: 1.25rem; background: var(--rule); border: 1px solid var(--rule); }
	.entry-panel { min-width: 0; padding: 1rem; background: var(--paper); }
	.section-heading { display: grid; grid-template-columns: minmax(0, 1fr) minmax(10rem, .8fr); gap: 1rem; margin-bottom: 1rem; }
	.section-heading > div { display: grid; gap: .2rem; }
	.section-heading h2, .projection-head h2 { font-size: 1.45rem; line-height: .95; }
	.section-heading > p, .field-help { color: var(--ink-soft); font-size: .8rem; line-height: 1.4; }
	.field { display: grid; gap: .28rem; min-width: 0; color: var(--ink-soft); font-size: .75rem; font-weight: 700; }
	.field--date { width: fit-content; max-width: 100%; margin-bottom: .25rem; }
	input, select { width: 100%; min-width: 0; min-height: 2.75rem; padding: 0 .65rem; background: var(--paper-soft); border: 1px solid var(--control-border); border-radius: 0; color: var(--ink); font: inherit; font-size: .9rem; }
	select { cursor: pointer; }
	input::placeholder { color: var(--ink-soft); opacity: 1; }
	input:disabled, select:disabled { cursor: not-allowed; opacity: .62; }
	.field-help { margin: .25rem 0 .75rem; }
	.ledger { display: grid; gap: 1px; background: var(--rule); border: 1px solid var(--rule); }
	.ledger-head, .ledger-row { display: grid; align-items: center; gap: .5rem; min-width: 0; }
	.ledger-head { padding: .45rem .6rem; background: var(--paper-deep); color: var(--ink-soft); font-family: var(--font-mono); font-size: .61rem; font-weight: 700; letter-spacing: .045em; text-transform: uppercase; }
	.ledger-row { padding: .55rem .6rem; background: var(--paper); }
	.ledger-head--accounts, .ledger-row--accounts { grid-template-columns: minmax(8rem, 1fr) minmax(6.4rem, .62fr) minmax(8rem, .8fr) auto; }
	.ledger-head--bills, .ledger-row--bills { grid-template-columns: minmax(8rem, 1fr) minmax(7rem, .72fr) minmax(8.7rem, .8fr) auto; }
	.icon-button, .button { min-height: 2.75rem; padding: 0 .75rem; border: 1px solid var(--control-border); border-radius: 0; background: var(--paper); color: var(--ink); font-family: var(--font-mono); font-size: .68rem; font-weight: 700; letter-spacing: .025em; text-transform: uppercase; cursor: pointer; transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, transform 150ms ease; }
	.icon-button { color: var(--negative); }
	.button:hover, .icon-button:hover { background: var(--paper-deep); border-color: var(--ink-soft); }
	.button:active, .icon-button:active { transform: scale(.98); }
	.button:disabled, .icon-button:disabled { cursor: not-allowed; opacity: .55; }
	.button--add { margin-top: .75rem; }
	.button--primary { background: var(--cobalt); border-color: var(--cobalt); color: var(--on-accent); }
	.button--primary:hover { background: var(--cobalt-deep); border-color: var(--link); }
	.button--danger { border-color: var(--negative); background: var(--negative); color: var(--on-accent); }
	.button--quiet { background: transparent; }
	.empty-ledger { margin: .75rem 0 0; color: var(--ink-soft); font-size: .82rem; }
	.save-bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 1px; padding: .9rem 1rem; background: var(--paper-deep); border: 1px solid var(--rule); }
	.save-bar > div:first-child { display: grid; gap: .12rem; }
	.save-bar strong { color: var(--ink); font-size: .95rem; }
	.save-bar span { color: var(--ink-soft); font-size: .78rem; }
	.projection-panel { margin-top: 2rem; padding-top: 1.25rem; border-top: 2px solid var(--cobalt); }
	.projection-head { display: flex; align-items: end; justify-content: space-between; gap: 1rem; }
	.projection-head > div:first-child { display: grid; gap: .35rem; max-width: 52rem; }
	.projection-head > div:first-child > p:last-child { color: var(--ink-soft); font-size: .86rem; }
	.horizon-picker { display: flex; flex-wrap: wrap; border: 1px solid var(--control-border); }
	.horizon-picker button { min-height: 2.75rem; padding: 0 .7rem; background: var(--paper); border: 0; border-right: 1px solid var(--control-border); color: var(--ink-soft); font-family: var(--font-mono); font-size: .68rem; font-weight: 700; cursor: pointer; }
	.horizon-picker button:last-child { border-right: 0; }
	.horizon-picker button.active { background: var(--cobalt); color: var(--on-accent); }
	.horizon-picker button:disabled { cursor: not-allowed; opacity: .6; }
	.projection-actions { display: flex; align-items: center; flex-wrap: wrap; gap: .75rem; margin-top: 1rem; }
	.projection-actions p { color: var(--ink-soft); font-size: .8rem; }
	.projection-results { margin-top: 1rem; border: 1px solid var(--rule); }
	.result-meta { display: flex; flex-wrap: wrap; gap: 1rem; padding: .65rem .8rem; background: var(--paper-soft); border-bottom: 1px solid var(--rule); }
	.result-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1px; background: var(--rule); }
	.result-summary > div { display: grid; gap: .3rem; min-width: 0; padding: .9rem; background: var(--paper); }
	.result-summary span, .result-summary small { color: var(--ink-soft); font-family: var(--font-mono); font-size: .62rem; font-weight: 700; letter-spacing: .045em; text-transform: uppercase; }
	.result-summary strong { overflow: hidden; color: var(--ink); font-size: clamp(1rem, 2.2vw, 1.45rem); letter-spacing: -.045em; text-overflow: ellipsis; }
	.result-summary .negative strong, .timeline-table tr.negative td:last-child, .timeline-table tr.negative th { color: var(--negative); }
	.result-summary small { letter-spacing: 0; text-transform: none; }
	.timeline-table-wrap { max-height: 28rem; overflow: auto; }
	.timeline-table { width: 100%; border-collapse: collapse; font-size: .85rem; }
	.timeline-table caption { padding: .65rem .8rem; text-align: left; }
	.timeline-table th, .timeline-table td { padding: .65rem .8rem; border-top: 1px solid var(--rule); text-align: left; }
	.timeline-table thead { position: sticky; z-index: 1; top: 0; background: var(--paper-deep); color: var(--ink-soft); font-family: var(--font-mono); font-size: .62rem; letter-spacing: .045em; text-transform: uppercase; }
	.timeline-table td { text-align: right; }
	.timeline-table tbody th { color: var(--ink); font-weight: 700; }
	@media (max-width: 74rem) { .workspace-header { grid-template-columns: 1fr; }.snapshot-status { justify-self: start; }.ledger-layout { grid-template-columns: 1fr; }.section-heading { grid-template-columns: 1fr; gap: .45rem; } }
	@media (max-width: 48rem) { .workspace { padding: 1rem .75rem 5.6rem; }.workspace-header { gap: 1rem; padding-bottom: 1rem; }.workspace-intro h1 { font-size: clamp(1.8rem, 7vw, 2.3rem); }.snapshot-status { width: 100%; grid-template-columns: repeat(3, minmax(0, 1fr)); }.snapshot-status div { padding: .6rem; }.notice, .confirmation, .save-bar, .projection-head { align-items: stretch; flex-direction: column; }.notice { display: grid; }.notice button { justify-self: start; }.ledger-head { display: none; }.ledger-row, .ledger-head--accounts, .ledger-row--accounts, .ledger-head--bills, .ledger-row--bills { grid-template-columns: 1fr; gap: .55rem; }.ledger-row { padding: .75rem; }.ledger-row .field::before { color: var(--ink-soft); content: attr(data-label); font-family: var(--font-mono); font-size: .62rem; text-transform: uppercase; }.icon-button { width: 100%; }.save-actions { display: grid; grid-template-columns: 1fr; }.save-actions .button { width: 100%; }.horizon-picker { width: 100%; }.horizon-picker button { flex: 1; }.result-summary { grid-template-columns: 1fr 1fr; }.timeline-table-wrap { max-height: none; overflow: visible; }.timeline-table, .timeline-table tbody, .timeline-table tr, .timeline-table th, .timeline-table td { display: block; }.timeline-table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }.timeline-table tr { padding: .55rem .75rem; border-top: 1px solid var(--rule); }.timeline-table th, .timeline-table td { display: flex; justify-content: space-between; gap: 1rem; padding: .25rem 0; border: 0; text-align: right; }.timeline-table td::before { color: var(--ink-soft); content: attr(data-label); font-family: var(--font-mono); font-size: .62rem; font-weight: 700; letter-spacing: .045em; text-transform: uppercase; }.timeline-table th::before { color: var(--ink-soft); content: 'Date'; font-family: var(--font-mono); font-size: .62rem; letter-spacing: .045em; text-transform: uppercase; } }
	@media (prefers-reduced-motion: reduce) { .button, .icon-button { transition: none; } }
</style>
