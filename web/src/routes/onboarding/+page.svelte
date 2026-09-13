<script lang="ts">
	import { resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/auth.svelte';
	import ThemeToggle from '$lib/components/ThemeToggle.svelte';
	import OnboardingCashStep from '$lib/components/OnboardingCashStep.svelte';
	import OnboardingEventsStep from '$lib/components/OnboardingEventsStep.svelte';
	import {
		getFinanceWorkspace,
		saveFinanceWorkspace,
		type FinanceWorkspace
	} from '$lib/finance';
	import {
		cashStepError,
		localCalendarDate,
		normalizedOnboardingWorkspace,
		scheduleStepError
	} from '$lib/onboarding-finance';
	import { profileStore, type SetupPath } from '$lib/profile.svelte';
	import { getNessieSample, type NessieSampleResult } from '$lib/api';

	type Step = 1 | 2 | 3 | 4 | 5 | 6;
	type FinanceStatus = 'idle' | 'loading' | 'ready' | 'error';

	const MANUAL_STEPS: { id: Step; label: string }[] = [
		{ id: 1, label: 'Welcome' },
		{ id: 2, label: 'Setup path' },
		{ id: 3, label: 'Cash' },
		{ id: 4, label: 'Income' },
		{ id: 5, label: 'Bills' },
		{ id: 6, label: 'Review' }
	];
	const SAMPLE_STEPS: { id: Step; label: string }[] = [
		{ id: 1, label: 'Welcome' },
		{ id: 2, label: 'Setup path' },
		{ id: 6, label: 'Review' }
	];

	interface PathOption {
		id: SetupPath;
		title: string;
		body: string;
		available: boolean;
		badge: string | null;
	}

	const pathOptions: PathOption[] = [
		{
			id: 'sample',
			title: 'Sample workspace',
			body: 'Preview the synthetic demo with a simulated Nessie banking profile. The preview is illustrative and never supplies the synthetic forecast.',
			available: true,
			badge: null
		},
		{
			id: 'manual',
			title: 'Enter manually',
			body: 'Set up cash balances, expected income, and upcoming bills in a short guided flow.',
			available: true,
			badge: null
		},
		{
			id: 'import',
			title: 'Import a bank CSV',
			body: 'Importing bank transactions is not available yet.',
			available: false,
			badge: 'Not available'
		}
	];

	let step = $state<Step>(1);
	let selectedPath = $state<SetupPath | null>(null);
	let sample = $state<NessieSampleResult | null>(null);
	let sampleLoading = $state(false);
	let consented = $state(false);
	let choosingPath = $state(false);
	let navigating = $state(false);
	let finishing = $state(false);
	let financeStatus = $state<FinanceStatus>('idle');
	let financeSaving = $state(false);
	let financeDraft = $state<FinanceWorkspace | null>(null);
	let saveError = $state('');
	let resumed = $state(false);
	let sampleRequest = 0;
	let financeRequest = 0;

	const profileReady = $derived(
		profileStore.status === 'bypassed' ||
			(authStore.user !== null && profileStore.isReadyFor(authStore.user.id))
	);
	const busy = $derived(
		choosingPath ||
			navigating ||
			finishing ||
			financeSaving ||
			financeStatus === 'loading' ||
			profileStore.saving
	);
	const visibleSteps = $derived(selectedPath === 'sample' ? SAMPLE_STEPS : MANUAL_STEPS);
	const currentStepIndex = $derived(
		Math.max(0, visibleSteps.findIndex((candidate) => candidate.id === step))
	);
	const canAdvanceFromWelcome = $derived(profileReady && !busy);
	const canAdvanceFromPath = $derived(
		!busy && (selectedPath === 'manual' || selectedPath === 'sample')
	);
	const manualCashError = $derived(
		financeDraft ? cashStepError(financeDraft.as_of, financeDraft.accounts) : 'Loading your cash workspace.'
	);
	const manualIncomeError = $derived(
		financeDraft ? scheduleStepError('income', financeDraft.inputs.income_events) : 'Loading your income schedule.'
	);
	const manualBillsError = $derived(
		financeDraft ? scheduleStepError('bill', financeDraft.bills) : 'Loading your bill schedule.'
	);
	const canFinish = $derived(
		!busy &&
			selectedPath !== null &&
			(selectedPath === 'sample'
				? sample?.status !== 'ok' || consented
				: financeDraft !== null && !manualCashError && !manualIncomeError && !manualBillsError)
	);
	const totalCashCents = $derived(
		financeDraft?.accounts.reduce((total, account) => total + account.balance_cents, 0) ?? 0
	);

	$effect(() => {
		if (resumed || !profileStore.profile) return;
		resumed = true;
		const path = profileStore.profile.setup_path;
		selectedPath = path === 'import' ? null : path;
		const savedStep = Math.min(6, Math.max(1, profileStore.profile.onboarding_step)) as Step;
		if (selectedPath === null && savedStep > 2) {
			step = 2;
		} else if (selectedPath === 'sample' && savedStep >= 3) {
			step = 6;
		} else {
			step = savedStep;
		}
	});

	$effect(() => {
		if (step === 6 && selectedPath === 'sample' && sample === null && !sampleLoading) {
			void loadSample();
		}
	});

	$effect(() => {
		if (
			profileReady &&
			selectedPath === 'manual' &&
			step >= 3 &&
			financeStatus === 'idle'
		) {
			void ensureFinanceDraft();
		}
	});

	async function ensureFinanceDraft(): Promise<boolean> {
		if (financeDraft && financeStatus === 'ready') return true;
		if (financeStatus === 'loading') return false;
		const ownerId = authStore.user?.id;
		if (!ownerId) {
			saveError = 'Sign in again to load your financial workspace.';
			return false;
		}
		const request = ++financeRequest;
		financeStatus = 'loading';
		saveError = '';
		const result = await getFinanceWorkspace();
		if (request !== financeRequest || authStore.user?.id !== ownerId) return false;
		if (result.status !== 'ok') {
			financeStatus = 'error';
			saveError = result.message;
			return false;
		}
		const next = structuredClone(result.data);
		next.as_of ??= localCalendarDate();
		if (next.accounts.length === 0) {
			next.accounts.push({
				id: crypto.randomUUID(),
				name: '',
				kind: 'checking',
				balance_cents: 0
			});
		}
		financeDraft = next;
		financeStatus = 'ready';
		return true;
	}

	async function saveManualFinance(from: Step): Promise<boolean> {
		if (!financeDraft || from < 3 || from > 5) return false;
		const error =
			from === 3
				? cashStepError(financeDraft.as_of, financeDraft.accounts)
				: from === 4
					? scheduleStepError('income', financeDraft.inputs.income_events)
					: scheduleStepError('bill', financeDraft.bills);
		if (error) {
			saveError = error;
			return false;
		}
		const candidate = normalizedOnboardingWorkspace($state.snapshot(financeDraft));
		if (!candidate.as_of) {
			saveError = 'Choose the opening date for these balances.';
			return false;
		}
		financeSaving = true;
		saveError = '';
		const result = await saveFinanceWorkspace({
			expected_revision: candidate.revision,
			as_of: candidate.as_of,
			accounts: candidate.accounts,
			bills: candidate.bills,
			inputs: candidate.inputs
		});
		financeSaving = false;
		if (result.status !== 'ok') {
			saveError = result.message;
			return false;
		}
		financeDraft = structuredClone(result.data);
		return true;
	}

	async function advance(from: Step) {
		if (busy || (from === 1 && !canAdvanceFromWelcome) || (from === 2 && !canAdvanceFromPath)) {
			return;
		}
		if (from === 2 && selectedPath === 'manual' && !(await ensureFinanceDraft())) return;
		if (selectedPath === 'manual' && from >= 3 && from <= 5 && !(await saveManualFinance(from))) {
			return;
		}

		navigating = true;
		saveError = '';
		const next = from === 2 && selectedPath === 'sample' ? 6 : ((from + 1) as Step);
		const saved = await profileStore.updateStep(next);
		navigating = false;
		if (!saved) {
			saveError = profileStore.loadError ?? 'Could not save your progress.';
			return;
		}
		step = next;
	}

	async function loadSample() {
		if (sample || sampleLoading || selectedPath !== 'sample') return;
		const request = ++sampleRequest;
		sampleLoading = true;
		let result: NessieSampleResult;
		try {
			result = await getNessieSample();
		} catch {
			result = {
				status: 'engine-unreachable',
				message: 'The optional Nessie preview is unavailable.'
			};
		}
		if (request === sampleRequest) {
			sample = result;
			sampleLoading = false;
		}
	}

	async function choosePath(path: SetupPath) {
		if (busy || path === selectedPath || path === 'import') return;
		choosingPath = true;
		saveError = '';
		const saved = await profileStore.setSetupPath(path);
		choosingPath = false;
		if (!saved) {
			saveError = profileStore.loadError ?? 'Could not save your choice.';
			return;
		}
		selectedPath = path;
		consented = false;
		sample = null;
		sampleRequest += 1;
	}

	async function finish() {
		const path = selectedPath;
		if (!canFinish || !path) return;
		finishing = true;
		saveError = '';
		const saved = await profileStore.completeSetup(path);
		if (!saved) {
			saveError = profileStore.loadError ?? 'Could not save your setup.';
			finishing = false;
			return;
		}
		goto(resolve(path === 'sample' ? '/demo' : '/'), { replaceState: true });
	}

	async function back() {
		if (busy || step === 1) return;
		navigating = true;
		saveError = '';
		const previous = selectedPath === 'sample' && step === 6 ? 2 : ((step - 1) as Step);
		const saved = await profileStore.updateStep(previous);
		navigating = false;
		if (!saved) {
			saveError = profileStore.loadError ?? 'Could not save your progress.';
			return;
		}
		step = previous;
	}

	function money(amount: number): string {
		return amount.toLocaleString('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 2
		});
	}

	function cents(amount: number): string {
		return money(amount / 100);
	}
</script>

<svelte:head>
	<title>Ginseng — Set up your workspace</title>
	<meta name="description" content="Choose how to set up your Ginseng liquidity workspace." />
</svelte:head>

<div class="onboarding">
	<header class="onboarding-header">
		<div class="header-brand">
			<span class="header-mark" aria-hidden="true"><img src="/brand/ginseng-avatar-reversed.svg" alt="" /></span>
			<p class="header-kicker">Liquidity workspace</p>
		</div>
		<ThemeToggle />
		{#if authStore.status === 'signed-in' && authStore.user}
			<div class="header-account">
				<span class="header-email">{authStore.user.email}</span>
				<button type="button" class="text-button" disabled={busy} onclick={() => void authStore.signOut()}>Sign out</button>
			</div>
		{/if}
	</header>

	{#if authStore.error}
		<p class="signout-error" role="alert">{authStore.error}</p>
	{/if}

	{#if !profileReady}
		<div class="panel" role="status" aria-live="polite">
			<p class="quiet">Loading your workspace…</p>
		</div>
	{:else if profileStore.status === 'bypassed' || authStore.status === 'unconfigured'}
		<div class="panel">
			<h1>Setup needs a configured backend</h1>
			<p class="body-copy">
				Onboarding saves your progress to your Ginseng account. Set
				<code>PUBLIC_SUPABASE_URL</code> and <code>PUBLIC_SUPABASE_PUBLISHABLE_KEY</code> in
				<code>web/.env</code>, then sign in to set up your workspace.
			</p>
			<a class="button" href={resolve('/login')}>Go to sign in</a>
		</div>
	{:else}
		<div class="panel">
			<ol class="steps" aria-label="Setup progress">
				{#each visibleSteps as visibleStep, index (visibleStep.id)}
					<li
						class:current={step === visibleStep.id}
						class:done={index < currentStepIndex}
						aria-current={step === visibleStep.id ? 'step' : undefined}
					>
						<span class="step-badge" aria-hidden="true">{index < currentStepIndex ? '✓' : index + 1}</span>
						<span class="step-label">{visibleStep.label}</span>
						<span class="visually-hidden">
							{index < currentStepIndex ? '(completed)' : step === visibleStep.id ? '(current step)' : '(not started)'}
						</span>
					</li>
				{/each}
			</ol>

			{#if step === 1}
				<h1>Welcome{authStore.displayName ? ', ' + authStore.displayName : ''}.</h1>
				<p class="body-copy">
					Ginseng starts with the cash you have now, expected income, and bills you know are
					coming. A short guided setup turns those records into your first cash projection.
				</p>
				<ul class="needs-list">
					<li><strong>Cash accounts</strong> — checking or savings balances at the opening of the day.</li>
					<li><strong>Expected income</strong> — paychecks or deposits with known dates and cadence.</li>
					<li><strong>Upcoming bills</strong> — one-time or recurring payments you expect.</li>
				</ul>
				<p class="body-copy quiet">
					Income and bills are optional. Ginseng saves only what you enter and never fills
					missing amounts with guesses.
				</p>
			{:else if step === 2}
				<h1>How do you want to set up?</h1>
				<fieldset class="path-field">
					<legend class="visually-hidden">Choose a setup path</legend>
					{#each pathOptions as option (option.id)}
						<label
							class="path-option"
							class:selected={selectedPath === option.id}
							class:unavailable={!option.available}
						>
							<input
								type="radio"
								name="setup-path"
								value={option.id}
								checked={selectedPath === option.id}
								disabled={!option.available || busy}
								onchange={() => choosePath(option.id)}
							/>
							<span class="path-copy">
								<span class="path-title-row">
									<span class="path-title">{option.title}</span>
									{#if option.badge}<span class="path-badge">{option.badge}</span>{/if}
								</span>
								<span class="path-body">{option.body}</span>
							</span>
						</label>
					{/each}
				</fieldset>
			{:else if step >= 3 && step <= 5}
				{#if financeStatus === 'loading' || financeStatus === 'idle'}
					<div class="finance-loading" role="status">
						<strong>Loading your saved financial data…</strong>
						<span>Existing accounts and schedules will appear here.</span>
					</div>
				{:else if financeStatus === 'error' || !financeDraft}
					<div class="notice notice-error" role="alert">
						<p>We could not load your financial data.</p>
						<button type="button" class="button secondary" onclick={() => { financeStatus = 'idle'; void ensureFinanceDraft(); }}>Try again</button>
					</div>
				{:else if step === 3}
					<OnboardingCashStep bind:asOf={financeDraft.as_of} bind:accounts={financeDraft.accounts} disabled={busy} />
				{:else if step === 4}
					<OnboardingEventsStep
						kind="income"
						bind:events={financeDraft.inputs.income_events}
						bind:rules={financeDraft.inputs.event_rules}
						asOf={financeDraft.as_of ?? localCalendarDate()}
						disabled={busy}
					/>
				{:else}
					<OnboardingEventsStep
						kind="bill"
						bind:events={financeDraft.bills}
						bind:rules={financeDraft.inputs.event_rules}
						asOf={financeDraft.as_of ?? localCalendarDate()}
						disabled={busy}
					/>
				{/if}
			{:else}
				{#if selectedPath === 'manual'}
					<div class="review-heading">
						<h1>Review your starting plan</h1>
					</div>
					<p class="body-copy">
						These saved records will create a deterministic scheduled cash projection.
						You can refine every item later in Data or Events.
					</p>
					{#if financeDraft}
						<dl class="review-summary">
							<div><dt>Opening date</dt><dd>{financeDraft.as_of}</dd></div>
							<div><dt>Cash accounts</dt><dd>{financeDraft.accounts.length}</dd></div>
							<div><dt>Opening cash</dt><dd>{cents(totalCashCents)}</dd></div>
							<div><dt>Income schedules</dt><dd>{financeDraft.inputs.income_events.length}</dd></div>
							<div><dt>Bill schedules</dt><dd>{financeDraft.bills.length}</dd></div>
						</dl>
					{/if}
					<p class="body-copy quiet">
						No probabilistic assumptions are added during setup. Historical and variable
						income models remain opt-in.
					</p>
				{:else}
					<div class="review-heading">
						<h1>Review your sample workspace</h1>
						<span class="sample-chip">Simulated</span>
					</div>
					<p class="body-copy">
						This is <strong>simulated banking data</strong> from the Nessie preview, not
						your real accounts. It is illustrative only and does not supply data to the
						synthetic forecast.
					</p>

					{#if sampleLoading}
						<div class="sample-loading" role="status">
							<p>Loading the optional Nessie preview…</p>
						</div>
					{:else if sample?.status === 'engine-unreachable' || sample?.status === 'engine-error'}
						<div class="notice notice-error" role="alert">
							<p>The optional Nessie preview is unavailable.</p>
							<p class="notice-followup">
								You can finish setup without this preview, or try again.
							</p>
							<button type="button" class="button secondary" onclick={() => { sample = null; void loadSample(); }}>
								Try again
							</button>
						</div>
					{:else if sample && sample.status === 'ok'}
						{@const data = sample.data}
						<p class="sample-meta">
							Sample profile: <strong>{[data.customer.first_name, data.customer.last_name].filter(Boolean).join(' ') || 'Unnamed sample customer'}</strong>
						</p>

						<section class="sample-section" aria-labelledby="sample-accounts-heading">
							<div class="section-head">
								<h2 id="sample-accounts-heading">Accounts</h2>
								<span class="section-count">{data.accounts.length}</span>
							</div>
							<table class="sample-table">
								<caption class="visually-hidden">Simulated accounts</caption>
								<thead>
									<tr><th scope="col">Account</th><th scope="col">Type</th><th scope="col" class="num">Balance</th></tr>
								</thead>
								<tbody>
									{#each data.accounts as account (account.external_id)}
										<tr>
											<td>{account.name}</td>
											<td class="capitalize">{account.kind}</td>
											<td class="num">{money(account.balance)}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</section>

						<section class="sample-section" aria-labelledby="sample-activity-heading">
							<div class="section-head">
								<h2 id="sample-activity-heading">Recent activity</h2>
								<span class="section-count">{data.transactions.length}</span>
							</div>
							{#if data.transactions.length === 0}
								<p class="section-empty">
									This simulated profile has no posted transactions.
								</p>
							{:else}
								<table class="sample-table">
									<caption class="visually-hidden">Simulated deposits</caption>
									<thead>
										<tr><th scope="col">Date</th><th scope="col">Description</th><th scope="col" class="num">Amount</th></tr>
									</thead>
									<tbody>
										{#each data.transactions.slice(0, 8) as transaction (transaction.external_id)}
											<tr>
												<td class="num-plain">{transaction.date}</td>
												<td>{transaction.description ?? 'Deposit'}</td>
												<td class="num">{money(transaction.amount)}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							{/if}
						</section>

						{#if data.bills.length > 0}
							<section class="sample-section" aria-labelledby="sample-bills-heading">
								<div class="section-head">
									<h2 id="sample-bills-heading">Scheduled bills</h2>
									<span class="section-count">{data.bills.length}</span>
								</div>
								<table class="sample-table">
									<caption class="visually-hidden">Simulated bills</caption>
									<thead>
										<tr><th scope="col">Payee</th><th scope="col">Due</th><th scope="col" class="num">Amount</th></tr>
									</thead>
									<tbody>
										{#each data.bills.slice(0, 5) as bill (bill.external_id)}
											<tr>
												<td>
													{bill.payee}
													{#if bill.recurring}<span class="row-tag">Recurring</span>{/if}
												</td>
												<td class="num-plain">{bill.payment_date}</td>
												<td class="num">{money(bill.amount)}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</section>
						{/if}

						<label class="consent">
							<input type="checkbox" bind:checked={consented} />
							<span>
								I understand this is a simulated Nessie preview. It will open the synthetic
								demo, not my personal workspace.
							</span>
						</label>
					{/if}
				{/if}
			{/if}

			{#if saveError}
				<p class="notice notice-error" role="alert">{saveError}</p>
			{/if}

			<div class="actions">
				{#if step > 1}
					<button type="button" class="button secondary" disabled={busy} onclick={back}>Back</button>
				{/if}
				{#if step < 6}
					<button
						type="button"
						class="button primary"
						disabled={busy || (step === 1 && !canAdvanceFromWelcome) || (step === 2 && !canAdvanceFromPath)}
						onclick={() => advance(step)}
					>
						{financeSaving ? 'Saving…' : 'Continue'}
					</button>
				{:else}
					<button type="button" class="button primary" disabled={!canFinish} onclick={finish}>
						{finishing ? 'Setting up…' : 'Enter the workspace'}
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.onboarding {
		display: grid;
		gap: 1.5rem;
		justify-items: center;
		min-height: 100dvh;
		padding: 3rem 1.25rem 4rem;
		background: var(--paper);
	}

	.onboarding-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		max-width: 48rem;
	}

	.header-brand {
		display: inline-flex;
		align-items: center;
		gap: 0.6rem;
	}

	.header-account {
		display: inline-flex;
		align-items: center;
		gap: 0.7rem;
		min-width: 0;
	}

	.header-email {
		overflow: hidden;
		color: var(--ink-soft);
		font-size: 0.78rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.text-button {
		flex: none;
		min-height: 2.75rem;
		padding: 0 0.2rem;
		background: none;
		border: 0;
		color: var(--cobalt);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		cursor: pointer;
	}

	.text-button:hover { color: var(--link); }
	.text-button:disabled {
		cursor: not-allowed;
		opacity: 0.5;
	}

	.signout-error {
		width: 100%;
		max-width: 48rem;
		margin: -0.75rem 0 0;
		color: var(--negative);
		font-size: 0.875rem;
		font-weight: 700;
	}

	.header-mark {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2.2rem;
		height: 2.2rem;
		background: var(--cobalt);
	}

	.header-mark img { width: 100%; height: 100%; object-fit: contain; }

	.header-kicker {
		margin: 0;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.panel {
		display: grid;
		gap: 1.2rem;
		width: 100%;
		max-width: 48rem;
		padding: 2rem;
		background: var(--paper);
		border: 1px solid var(--rule);
	}

	h1 {
		margin: 0;
		color: var(--ink);
		font-size: clamp(1.6rem, 3vw, 2.1rem);
		font-weight: 800;
		letter-spacing: -0.02em;
		text-wrap: balance;
	}

	h2 {
		margin: 0 0 0.5rem;
		color: var(--ink);
		font-size: 0.95rem;
		font-weight: 750;
	}

	.body-copy {
		margin: 0;
		color: var(--ink-soft);
		font-size: 0.95rem;
		line-height: 1.55;
		text-wrap: pretty;
	}

	.body-copy code, .panel code {
		font-family: var(--font-mono);
		font-size: 0.85em;
		color: var(--ink);
	}

	.quiet { color: var(--ink-soft); }

	.needs-list {
		display: grid;
		gap: 0.6rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.needs-list li {
		padding-left: 1.1rem;
		color: var(--ink-soft);
		font-size: 0.92rem;
		line-height: 1.5;
	}

	.needs-list li::before {
		content: '';
		display: inline-block;
		width: 0.45rem;
		height: 0.45rem;
		margin-right: 0.55rem;
		margin-left: -1.1rem;
		background: var(--cobalt);
		vertical-align: 0.12em;
	}

	.steps {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(4.5rem, 1fr));
		gap: 0.65rem;
		margin: 0;
		padding: 0 0 0.9rem;
		list-style: none;
		border-bottom: 1px solid var(--rule);
	}

	.steps li {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.steps li span.step-badge {
		display: inline-grid;
		flex: none;
		place-items: center;
		width: 1.4rem;
		height: 1.4rem;
		border: 1px solid var(--rule-strong);
		font-size: 0.62rem;
		transition: background-color 160ms cubic-bezier(0.23, 1, 0.32, 1), border-color 160ms cubic-bezier(0.23, 1, 0.32, 1), color 160ms cubic-bezier(0.23, 1, 0.32, 1);
	}

	.steps li.current { color: var(--ink); }

	.steps li.current span.step-badge {
		background: var(--cobalt);
		border-color: var(--cobalt);
		color: var(--on-accent);
	}

	.steps li.done { color: var(--ink-soft); }

	.steps li.done span.step-badge {
		background: var(--paper-soft);
		border-color: var(--control-border);
		color: var(--ink-soft);
	}

	@media (prefers-reduced-motion: reduce) {
		.steps li span.step-badge { transition: none; }
	}

	.path-field {
		display: grid;
		gap: 0.7rem;
		margin: 0;
		padding: 0;
		border: 0;
	}

	.path-option {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.75rem;
		padding: 0.9rem 1rem;
		background: var(--paper);
		border: 1px solid var(--rule);
		cursor: pointer;
	}

	.path-option:hover:not(.unavailable) { border-color: var(--rule-strong); }
	.path-option.selected { border-color: var(--cobalt); outline: 1px solid var(--cobalt); }

	.path-option.unavailable { opacity: 0.62; cursor: not-allowed; }

	.path-option input { accent-color: var(--cobalt); margin-top: 0.2rem; }

	.path-copy { display: grid; gap: 0.25rem; }

	.path-title-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-wrap: wrap;
	}

	.path-title { color: var(--ink); font-weight: 750; font-size: 0.95rem; }

	.path-badge {
		padding: 0.15rem 0.4rem;
		background: var(--paper-soft);
		border: 1px solid var(--rule);
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.path-body { color: var(--ink-soft); font-size: 0.82rem; line-height: 1.5; }

	.notice {
		margin: 0;
		padding: 0.8rem 0.9rem;
		background: var(--paper-soft);
		border-left: 3px solid var(--warning);
		color: var(--ink-soft);
		font-size: 0.85rem;
		line-height: 1.5;
	}

	.notice-error { border-left-color: var(--negative); color: var(--negative); }

	.notice-error p { margin: 0; }

	.notice-error p.notice-followup {
		margin-top: 0.45rem;
		color: var(--ink-soft);
		font-size: 0.82rem;
	}

	.notice .button { margin-top: 0.6rem; }

	.sample-loading {
		padding: 1.5rem;
		background: var(--paper-soft);
		color: var(--ink-soft);
		font-size: 0.85rem;
		text-align: center;
	}

	.sample-loading p { margin: 0; animation: sample-pulse 1.1s ease-in-out infinite; }

	@keyframes sample-pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.55; }
	}

	@media (prefers-reduced-motion: reduce) {
		.sample-loading p { animation: none; }
	}

	.sample-section { display: grid; gap: 0.25rem; }

	.sample-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	.sample-table th {
		padding: 0.45rem 0.6rem;
		background: var(--paper-soft);
		border-bottom: 1px solid var(--rule);
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		text-align: left;
	}

	.sample-table td {
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--rule);
		color: var(--ink-soft);
	}

	.sample-table .num { text-align: right; font-variant-numeric: tabular-nums; }

	.consent {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.6rem;
		padding: 0.85rem 0.9rem;
		background: var(--paper-soft);
		border-left: 3px solid var(--cobalt);
		color: var(--ink-soft);
		font-size: 0.85rem;
		line-height: 1.5;
		cursor: pointer;
	}

	.consent input { accent-color: var(--cobalt); margin-top: 0.2rem; }

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.7rem;
		margin-top: 0.4rem;
	}

	.button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 2.85rem;
		padding: 0 1.3rem;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		cursor: pointer;
		text-decoration: none;
		border: 1px solid var(--cobalt);
	}

	.button.primary { background: var(--cobalt); color: var(--on-accent); }
	.button.primary:hover:not(:disabled) { background: var(--cobalt-bright); }
	.button.primary:active:not(:disabled) { transform: scale(0.98); }
	.button.primary:disabled { opacity: 0.5; cursor: not-allowed; }

	.button.secondary {
		background: var(--paper);
		color: var(--cobalt);
	}
	.button.secondary:hover { background: var(--paper-deep); }

	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
		border: 0;
	}

	/* One visible focus treatment for every control in the flow. */
	.button:focus-visible,
	.text-button:focus-visible,
	.path-option input:focus-visible,
	.consent input:focus-visible {
		outline: 2px solid var(--cobalt);
		outline-offset: 2px;
	}

	.path-option:has(input:focus-visible) {
		outline: 2px solid var(--cobalt);
		outline-offset: 2px;
	}

	.finance-loading {
		display: grid;
		gap: 0.25rem;
		padding: 1.2rem;
		background: var(--paper-soft);
		border-left: 3px solid var(--cobalt);
	}

	.finance-loading strong { color: var(--ink); font-size: 0.88rem; }
	.finance-loading span { color: var(--ink-soft); font-size: 0.78rem; }

	.review-summary {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1px;
		margin: 0;
		background: var(--rule);
		border: 1px solid var(--rule);
	}

	.review-summary div {
		display: grid;
		gap: 0.25rem;
		padding: 0.8rem;
		background: var(--paper-soft);
	}

	.review-summary dt {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.review-summary dd {
		margin: 0;
		color: var(--ink);
		font-size: 0.9rem;
		font-variant-numeric: tabular-nums;
		font-weight: 750;
	}

	.review-heading {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		flex-wrap: wrap;
	}

	.sample-chip {
		padding: 0.2rem 0.45rem;
		background: var(--warning);
		color: var(--on-accent);
		font-family: var(--font-mono);
		font-size: 0.6rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.sample-meta {
		margin: 0;
		color: var(--ink-soft);
		font-size: 0.82rem;
	}

	.sample-meta strong { color: var(--ink-soft); }

	.section-head {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		margin-bottom: 0.4rem;
	}

	.section-count {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-variant-numeric: tabular-nums;
		font-weight: 700;
	}

	.section-empty {
		margin: 0;
		padding: 0.75rem 0.85rem;
		background: var(--paper-soft);
		color: var(--ink-soft);
		font-size: 0.82rem;
		line-height: 1.5;
	}

	.sample-table .capitalize { text-transform: capitalize; }
	.sample-table .num-plain { font-variant-numeric: tabular-nums; white-space: nowrap; }

	.row-tag {
		display: inline-block;
		margin-left: 0.35rem;
		padding: 0.05rem 0.3rem;
		background: var(--paper-soft);
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.58rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		vertical-align: 0.08em;
	}

	@media (max-width: 40rem) {
		.onboarding-header { max-width: 100%; }
		.header-email { display: none; }
		.actions { flex-direction: column-reverse; }
		.actions .button { width: 100%; }
		.review-summary { grid-template-columns: 1fr 1fr; }
	}

	@media (max-width: 30rem) {
		.onboarding { padding: 2rem 1rem 3rem; }
		.panel { padding: 1.4rem; }
		.steps { gap: 0.7rem; }
		.step-label { display: none; }
		.sample-table { font-size: 0.8rem; }
		.sample-table th, .sample-table td { padding: 0.4rem 0.45rem; }
		.review-summary { grid-template-columns: 1fr; }
	}
</style>
