import { browser } from '$app/environment';
import { authStore } from './auth.svelte';
import { supabase } from './supabase';
import {
	getFinanceWorkspace, saveFinanceWorkspace, forecastFinance, runBacktest,
	type FinanceWorkspace, type ForecastRun, type ScenarioChange,
	type ScenarioOverrides, type PlanningPolicy, type BacktestSummary
} from './finance';
import { WORKSPACE_SAVED_EVENT, type WorkspaceSavedDetail, type ProjectionHorizonDays } from './workspace';

type Status = 'idle' | 'loading' | 'ready' | 'error';

// Canonical snapshots are replaced, never edited in place. Editors own their drafts.
// https://svelte.dev/docs/svelte/$state#$state.raw
export class FinancialStore {
	workspace = $state.raw<FinanceWorkspace | null>(null);
	forecast = $state.raw<ForecastRun | null>(null);
	baseline = $state.raw<ForecastRun | null>(null);
	changes = $state.raw<ScenarioChange[]>([]);
	status = $state<Status>('idle');
	forecastStatus = $state<Status>('idle');
	error = $state<string | null>(null);
	forecastError = $state<string | null>(null);
	horizonDays = $state<ProjectionHorizonDays>(30);
	scenario = $state.raw<ScenarioOverrides | null>(null);
	scenarioName = $state<string | null>(null);
	readonly isPreview = $derived(this.scenario !== null);
	saving = $state(false);
	saveUncertain = $state(false);
	accuracy = $state.raw<BacktestSummary | null>(null);
	accuracyError = $state<string | null>(null);
	accuracyLoading = $state(false);
	comparison = $state.raw<ForecastRun | null>(null);
	comparisonName = $state<string | null>(null);
	comparisonStatus = $state<Status>('idle');
	comparisonError = $state<string | null>(null);
	#comparisonId: string | null = null;
	readonly comparisonForCurrent = $derived(
		(this.isPreview || this.comparisonStatus === 'ready')
			? this.comparison ?? (this.comparisonStatus === 'idle' ? this.baseline : null)
			: null
	);
	#comparisonSequence = 0;
	#comparisonTask: Promise<void> | null = null;
	#owner: string | null = null;
	#epoch = 0;
	#loadSequence = 0;
	#forecastSequence = 0;
	#refreshTask: Promise<void> | null = null;
	#accuracySequence = 0;
	#conflict = $state(false);
	readonly requiresReconciliation = $derived(this.saveUncertain || this.#conflict);

	constructor() {
		if (!browser) return;
		this.#owner = authStore.user?.id ?? null;
		// Synchronous callback only: never await a Supabase API inside auth dispatch.
		// https://supabase.com/docs/reference/javascript/auth-onauthstatechange
		const subscription = supabase?.auth.onAuthStateChange((_event, session) => {
			const owner = session?.user.id ?? null;
			if (owner !== this.#owner) { this.reset(); this.#owner = owner; }
		});
		const onSaved = (event: Event) => {
			const detail = (event as CustomEvent<WorkspaceSavedDetail>).detail;
			if (!detail || detail.ownerId !== this.#owner || !this.#current(this.#owner, this.#epoch)) return;
			if (this.workspace && detail.workspace.revision <= this.workspace.revision) return;
			if (this.scenario || this.saving || this.saveUncertain) {
				this.#markConflict();
			} else {
				void this.#fetchWorkspace(false);
			}
		};
		window.addEventListener(WORKSPACE_SAVED_EVENT, onSaved);
		if (import.meta.hot) import.meta.hot.dispose(() => {
			subscription?.data.subscription.unsubscribe();
			window.removeEventListener(WORKSPACE_SAVED_EVENT, onSaved);
		});
	}

	reset(): void {
		this.#epoch += 1;
		this.#refreshTask = null;
		this.#comparisonTask = null;
		this.#loadSequence += 1;
		this.#forecastSequence += 1;
		this.#accuracySequence += 1;
		this.#comparisonSequence += 1;
		this.#comparisonId = null;
		this.comparison = null;
		this.comparisonName = null;
		this.comparisonStatus = 'idle';
		this.comparisonError = null;
		this.#owner = null;
		this.workspace = null;
		this.forecast = null;
		this.baseline = null;
		this.changes = [];
		this.status = 'idle';
		this.forecastStatus = 'idle';
		this.error = null;
		this.forecastError = null;
		this.scenario = null;
		this.scenarioName = null;
		this.horizonDays = 30;
		this.saving = false;
		this.saveUncertain = false;
		this.#conflict = false;
		this.accuracy = null;
		this.accuracyError = null;
		this.accuracyLoading = false;
	}

	#current(owner: string | null, epoch: number): boolean {
		return owner !== null && owner === this.#owner && owner === authStore.user?.id
			&& authStore.status === 'signed-in' && epoch === this.#epoch;
	}

	#markConflict(): void {
		this.#conflict = true;
		this.#clearAccuracy();
		this.#forecastSequence += 1;
		this.#comparisonSequence += 1;
		this.comparison = null;
		this.comparisonStatus = 'error';
		this.forecastStatus = 'error';
		this.error = 'Saved inputs changed. Your draft is retained. Reload and reconcile before saving.';
		this.forecastError = this.error;
	}

	async load(): Promise<void> {
		if (!browser || authStore.status !== 'signed-in' || !authStore.user) return;
		if (this.#owner !== authStore.user.id) { this.reset(); this.#owner = authStore.user.id; }
		if (this.workspace || this.status === 'loading') return;
		await this.#fetchWorkspace(false);
	}

	async #fetchWorkspace(discard: boolean): Promise<void> {
		const owner = this.#owner;
		const epoch = this.#epoch;
		if (!this.#current(owner, epoch) || this.saving) return;
		const sequence = ++this.#loadSequence;
		this.status = 'loading';
		this.error = null;
		const result = await getFinanceWorkspace();
		if (!this.#current(owner, epoch) || sequence !== this.#loadSequence) return;
		if (result.status !== 'ok') { this.status = 'error'; this.error = result.message; return; }
		this.workspace = result.data;
		this.status = 'ready';
		if (discard) {
			this.scenario = null;
			this.scenarioName = null;
			this.#comparisonId = null;
			this.#conflict = false;
			this.saveUncertain = false;
		}
		this.#clearAccuracy();
		await this.refresh();
	}

	/** Explicit user action: discard/reconcile local scenario and unknown save outcome. */
	async reload(): Promise<void> { await this.#fetchWorkspace(true); }

	async refresh(): Promise<void> {
		if (!this.workspace || this.saving || this.saveUncertain || this.#conflict) return;
		++this.#forecastSequence;
		this.forecastStatus = 'loading';
		this.forecastError = null;
		void this.compareScenario(this.#comparisonId);
		if (!this.#refreshTask) {
			const task = this.#drainForecasts(this.#epoch).finally(() => {
				if (this.#refreshTask === task) this.#refreshTask = null;
			});
			this.#refreshTask = task;
		}
		return this.#refreshTask;
	}

	async #drainForecasts(epoch: number): Promise<void> {
		while (epoch === this.#epoch) {
			const sequence = this.#forecastSequence;
			await this.#refreshOne(sequence);
			if (sequence === this.#forecastSequence) return;
		}
	}

	async #refreshOne(sequence: number): Promise<void> {
		const workspace = this.workspace;
		const owner = this.#owner;
		const epoch = this.#epoch;
		if (!workspace || !this.#current(owner, epoch) || this.saving) return;
		if (this.#conflict || this.saveUncertain) return;
		this.forecastStatus = 'loading';
		this.forecastError = null;
		const result = await forecastFinance({
			expected_revision: workspace.revision,
			horizon_days: this.horizonDays,
			...(this.scenario === null ? {} : { overrides: this.scenario })
		});
		if (!this.#current(owner, epoch) || sequence !== this.#forecastSequence
			|| this.workspace?.revision !== workspace.revision) return;
		if (result.status !== 'ok') {
			this.forecastStatus = 'error';
			this.forecastError = result.message;
			if (result.status === 'engine-error' && result.http_status === 409) this.#markConflict();
			return;
		}
		this.baseline = result.data.baseline;
		this.forecast = result.data.preview ?? result.data.baseline;
		this.changes = result.data.changes;
		this.forecastStatus = 'ready';
	}

	async setHorizonDays(horizon: ProjectionHorizonDays): Promise<void> {
		if (![14, 30, 60].includes(horizon) || horizon === this.horizonDays || this.saving) return;
		this.horizonDays = horizon;
		this.#clearAccuracy();
		await this.refresh();
	}

	#clearAccuracy(): void {
		++this.#accuracySequence;
		this.accuracy = null;
		this.accuracyError = null;
		this.accuracyLoading = false;
	}

	async previewScenario(overrides: ScenarioOverrides): Promise<void> {
		if (!this.workspace || this.saving || this.saveUncertain || this.#conflict) return;
		this.#clearAccuracy();
		this.scenario = structuredClone($state.snapshot(overrides));
		this.scenarioName = null;
		await this.refresh();
	}

	async discardScenario(): Promise<void> {
		if (this.saving) return;
		this.#clearAccuracy();
		this.scenario = null;
		this.scenarioName = null;
		await this.refresh();
	}

	async setPolicy(patch: Partial<PlanningPolicy>): Promise<void> {
		if (!this.workspace) return;
		await this.previewScenario({ ...this.scenario,
			policy: { ...(this.scenario?.policy ?? this.workspace.inputs.policy), ...patch } });
	}

	async loadScenario(id: string): Promise<void> {
		const saved = this.workspace?.inputs.scenarios.find((entry) => entry.id === id);
		if (!saved || this.saving || this.saveUncertain || this.#conflict) return;
		this.#clearAccuracy();
		this.scenario = structuredClone(saved.overrides);
		this.scenarioName = saved.name;
		this.error = saved.base_revision !== this.workspace?.revision
			? 'This scenario was saved against an earlier snapshot. It is now compared with your current saved inputs.' : null;
		await this.refresh();
	}

	async compareScenario(id: string | null): Promise<void> {
		if (!this.workspace || !this.#current(this.#owner, this.#epoch)
			|| this.saving || this.saveUncertain || this.#conflict) return;
		++this.#comparisonSequence;
		this.#comparisonId = id;
		this.comparison = null;
		this.comparisonError = null;
		const saved = this.workspace.inputs.scenarios.find(entry => entry.id === id);
		this.comparisonName = saved?.name ?? null;
		this.comparisonStatus = id === null ? 'idle' : saved ? 'loading' : 'error';
		if (id !== null && !saved) this.comparisonError = 'That saved scenario no longer exists. Choose another comparison.';
		if (!this.#comparisonTask && saved) {
			const task = this.#drainComparisons(this.#epoch).finally(() => {
				if (this.#comparisonTask === task) this.#comparisonTask = null;
			});
			this.#comparisonTask = task;
		}
		return this.#comparisonTask ?? Promise.resolve();
	}

	async #drainComparisons(epoch: number): Promise<void> {
		while (epoch === this.#epoch) {
			const sequence = this.#comparisonSequence;
			await this.#compareOne(sequence);
			if (sequence === this.#comparisonSequence) return;
		}
	}

	async #compareOne(sequence: number): Promise<void> {
		const workspace = this.workspace;
		const owner = this.#owner;
		const epoch = this.#epoch;
		if (!workspace || !this.#current(owner, epoch) || this.saving || this.saveUncertain || this.#conflict) return;
		const saved = workspace.inputs.scenarios.find(entry => entry.id === this.#comparisonId);
		if (!saved) return;
		const result = await forecastFinance({ expected_revision: workspace.revision,
			horizon_days: this.horizonDays, overrides: saved.overrides });
		if (!this.#current(owner, epoch) || sequence !== this.#comparisonSequence
			|| this.workspace?.revision !== workspace.revision) return;
		if (result.status === 'ok') {
			this.comparison = result.data.preview ?? result.data.baseline;
			this.comparisonStatus = 'ready';
		} else {
			this.comparisonStatus = 'error';
			this.comparisonError = result.message;
			if (result.status === 'engine-error' && result.http_status === 409) this.#markConflict();
		}
	}

	async saveScenario(name: string): Promise<boolean> {
		const workspace = this.workspace;
		const trimmed = name.trim();
		if (!workspace || !trimmed || trimmed.length > 100) {
			this.error = 'Enter a scenario name of 1–100 characters.'; return false;
		}
		if (workspace.inputs.scenarios.length >= 20) {
			this.error = 'Remove a saved scenario before adding another (20 maximum).'; return false;
		}
		const draft = structuredClone(workspace);
		const overrides: ScenarioOverrides = {
			bills: workspace.bills,
			income_events: workspace.inputs.income_events,
			event_rules: workspace.inputs.event_rules,
			assumptions: workspace.inputs.assumptions,
			policy: workspace.inputs.policy,
			mode: workspace.inputs.mode,
			...this.scenario
		};
		draft.inputs.scenarios.push({ id: crypto.randomUUID(), name: trimmed,
			base_revision: workspace.revision + 1, overrides: structuredClone(overrides) });
		return this.#persist(draft, true);
	}

	async deleteScenario(id: string): Promise<boolean> {
		const workspace = this.workspace;
		const removed = workspace?.inputs.scenarios.find((entry) => entry.id === id);
		if (!workspace || !removed) return false;
		const draft = structuredClone(workspace);
		draft.inputs.scenarios = draft.inputs.scenarios.filter((entry) => entry.id !== id);
		if (!await this.#persist(draft, true)) return false;
		if (this.#comparisonId === id) await this.compareScenario(null);
		if (this.scenarioName === removed.name) this.scenarioName = null;
		return true;
	}

	async commitScenario(): Promise<boolean> {
		if (!this.workspace || !this.scenario) return false;
		if (this.forecastStatus !== 'ready') return false;
		const draft = structuredClone(this.workspace);
		const { bills, ...supplemental } = this.scenario;
		if (bills !== undefined) draft.bills = structuredClone(bills);
		Object.assign(draft.inputs, structuredClone(supplemental));
		return this.#persist(draft, false);
	}

	async saveWorkspace(draft: FinanceWorkspace): Promise<boolean> { return this.#persist(draft, false); }

	async #persist(draft: FinanceWorkspace, retainScenario: boolean): Promise<boolean> {
		const owner = this.#owner;
		const epoch = this.#epoch;
		if (!this.#current(owner, epoch) || this.saving || this.saveUncertain || this.#conflict) return false;
		if (draft.revision !== this.workspace?.revision) { this.#markConflict(); return false; }
		if (!draft.as_of) { this.error = 'Choose the opening date before saving.'; return false; }
		this.#loadSequence += 1;
		this.#forecastSequence += 1;
		this.#clearAccuracy();
		this.saving = true;
		this.error = null;
		try {
			const result = await saveFinanceWorkspace({ expected_revision: draft.revision,
				as_of: draft.as_of, accounts: draft.accounts, bills: draft.bills, inputs: draft.inputs });
			if (!this.#current(owner, epoch)) return false;
			if (result.status !== 'ok') {
				if (result.status === 'engine-error' && result.http_status === 409) this.#markConflict();
				else {
					this.saveUncertain = result.status === 'engine-unreachable'
						|| result.http_status === undefined || result.http_status >= 500;
					this.error = this.saveUncertain
						? 'The save acknowledgment was not received. Your draft is retained. Reload and reconcile saved inputs before another save.'
						: result.message;
				}
				return false;
			}
			this.workspace = result.data;
			this.status = 'ready';
			this.accuracy = null;
			if (!retainScenario) { this.scenario = null; this.scenarioName = null; }
			return true;
		} catch {
			if (this.#current(owner, epoch)) {
				this.saveUncertain = true;
				this.error = 'The save result is unknown. Reload and reconcile saved inputs before another save.';
			}
			return false;
		} finally {
			if (this.#current(owner, epoch)) { this.saving = false; void this.refresh(); }
		}
	}

	async backtest(): Promise<void> {
		const workspace = this.workspace;
		const owner = this.#owner;
		const epoch = this.#epoch;
		if (!workspace || !this.#current(owner, epoch) || this.saving || this.saveUncertain || this.#conflict) return;
		const sequence = ++this.#accuracySequence;
		this.accuracyLoading = true;
		this.accuracyError = null;
		const result = await runBacktest({ expected_revision: workspace.revision, horizon_days: this.horizonDays,
			policy: this.scenario?.policy ?? workspace.inputs.policy });
		if (!this.#current(owner, epoch) || sequence !== this.#accuracySequence
			|| this.workspace?.revision !== workspace.revision) return;
		this.accuracyLoading = false;
		if (result.status === 'ok') this.accuracy = result.data;
		else {
			this.accuracy = null;
			this.accuracyError = result.message;
			if (result.status === 'engine-error' && result.http_status === 409) this.#markConflict();
		}
	}
}

export const financialStore = new FinancialStore();
