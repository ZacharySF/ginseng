// Shared runes-based scenario store used by every decision surface.
//
// Every mutation re-requests the engine through `$lib/api`; this module only
// validates scenario inputs and coordinates request state. The active request
// begins at a healthy baseline and can hold user-authored future obligations,
// the staged repair preset, and policy settings.
import { postScenario } from './api';
import type { Obligation, ScenarioRequest, ScenarioResponse } from './types';

export type LoadState = 'loading' | 'ready' | 'unreachable' | 'error';
export interface ObligationDraft {
	label: string;
	amount: number;
	due_in_days: number;
}

export const COVERAGE_TARGET_OPTIONS = [0.8, 0.9, 0.95] as const;
export const HORIZON_OPTIONS = [14, 30, 60] as const;

// The canonical HackRice shock (spec section 37): a future obligation, not
// an already-completed debit. Cash today, the portfolio, and the market are
// unchanged by inserting it — only future obligations change.
export const CANONICAL_SHOCKS: Obligation[] = [
	{
		id: 'repair-deposit',
		label: 'Emergency vehicle repair deposit',
		amount: 1500.0,
		due_in_days: 3
	},
	{
		id: 'repair-balance',
		label: 'Emergency vehicle repair balance',
		amount: 3000.0,
		due_in_days: 17
	}
];

const DEFAULT_SEED = 20260911;
const DEFAULT_HORIZON_DAYS = 30;
const DEFAULT_COVERAGE_TARGET = 0.95;
const DEFAULT_OPERATING_BUFFER = 1000.0;
const DEFAULT_PATHS = 2000;

function baselineRequest(): ScenarioRequest {
	return {
		seed: DEFAULT_SEED,
		horizon_days: DEFAULT_HORIZON_DAYS,
		coverage_target: DEFAULT_COVERAGE_TARGET,
		operating_buffer: DEFAULT_OPERATING_BUFFER,
		paths: DEFAULT_PATHS,
		mean_block_length: null,
		obligations: []
	};
}

class ScenarioStore {
	request = $state<ScenarioRequest>(baselineRequest());
	response = $state<ScenarioResponse | null>(null);
	// Same seed/horizon/paths/mean_block_length as `request`, obligations
	// forced empty. `draw_bundle` is a pure function of those shared fields,
	// so this reuses the identical bundle as `response` (spec 20's common
	// random numbers) — it exists only to show the frozen-portfolio contrast
	// (spec 35) honestly, from two real engine responses, never by
	// subtracting or fabricating a number client-side.
	baselineResponse = $state<ScenarioResponse | null>(null);
	loadState = $state<LoadState>('loading');
	errorMessage = $state('');

	#requestSeq = 0;
	#initialized = false;
	#customObligationSequence = 0;

	readonly hasShock = $derived(
		CANONICAL_SHOCKS.every((shock) =>
			this.request.obligations.some((obligation) => obligation.id === shock.id)
		)
	);

	readonly isBaseline = $derived(this.request.obligations.length === 0);

	#normalizeObligation(obligation: Obligation): Obligation | null {
		const label = obligation.label.trim();
		const amount = Number(obligation.amount);
		const dueInDays = Number(obligation.due_in_days);
		if (
			!label ||
			!Number.isFinite(amount) ||
			amount <= 0 ||
			!Number.isInteger(dueInDays) ||
			dueInDays < 1 ||
			dueInDays > this.request.horizon_days
		) {
			return null;
		}
		return { id: obligation.id, label, amount, due_in_days: dueInDays };
	}

	async #refresh(): Promise<void> {
		const seq = ++this.#requestSeq;
		this.loadState = 'loading';
		this.errorMessage = '';

		const baselineRequestForCompare: ScenarioRequest = { ...this.request, obligations: [] };
		const [mainResult, baselineResult] = await Promise.all([
			postScenario(this.request),
			postScenario(baselineRequestForCompare)
		]);
		if (seq !== this.#requestSeq) return; // superseded by a newer mutation

		if (mainResult.status === 'ok') {
			this.response = mainResult.data;
			this.baselineResponse = baselineResult.status === 'ok' ? baselineResult.data : null;
			this.loadState = 'ready';
		} else {
			this.response = null;
			this.baselineResponse = null;
			this.errorMessage = mainResult.message;
			this.loadState = mainResult.status === 'engine-unreachable' ? 'unreachable' : 'error';
		}
	}

	/** Fetch once on first use; safe to call from every consuming screen's `onMount`. */
	ensureLoaded(): void {
		if (this.#initialized) return;
		this.#initialized = true;
		void this.#refresh();
	}

	/** Re-request the current scenario unchanged (e.g. a Retry button). */
	refresh(): void {
		void this.#refresh();
	}

	/**
	 * Add a user-authored future obligation and immediately re-run the engine.
	 * Inputs are validated here so every surface shares the same scenario invariant.
	 */
	addObligation(draft: ObligationDraft): void {
		const obligation = this.#normalizeObligation({
			id: `custom-obligation-${++this.#customObligationSequence}`,
			...draft
		});
		if (!obligation) return;

		this.request = {
			...this.request,
			obligations: [...this.request.obligations, obligation]
		};
		void this.#refresh();
	}

	/** Update one existing obligation; invalid edits leave the active model untouched. */
	updateObligation(id: string, draft: ObligationDraft): void {
		const current = this.request.obligations.find((obligation) => obligation.id === id);
		if (!current) return;

		const next = this.#normalizeObligation({ id, ...draft });
		if (!next) return;

		this.request = {
			...this.request,
			obligations: this.request.obligations.map((obligation) =>
				obligation.id === id ? next : obligation
			)
		};
		void this.#refresh();
	}

	/** Remove one future obligation from the active model. */
	removeObligation(id: string): void {
		if (!this.request.obligations.some((obligation) => obligation.id === id)) return;
		this.request = {
			...this.request,
			obligations: this.request.obligations.filter((obligation) => obligation.id !== id)
		};
		void this.#refresh();
	}

	/** Clear only added events; policy settings remain intact. */
	clearObligations(): void {
		if (this.request.obligations.length === 0) return;
		this.request = { ...this.request, obligations: [] };
		void this.#refresh();
	}

	applyShock(): void {
		if (this.hasShock) return;
		this.request = {
			...this.request,
			obligations: [...this.request.obligations, ...CANONICAL_SHOCKS]
		};
		void this.#refresh();
	}

	reset(): void {
		this.request = baselineRequest();
		void this.#refresh();
	}

	setCoverageTarget(value: number): void {
		if (value === this.request.coverage_target) return;
		this.request = { ...this.request, coverage_target: value };
		void this.#refresh();
	}

	setHorizonDays(value: number): void {
		if (!Number.isInteger(value) || value < 1 || value === this.request.horizon_days) return;
		this.request = {
			...this.request,
			horizon_days: value,
			obligations: this.request.obligations.map((obligation) => ({
				...obligation,
				due_in_days: Math.min(obligation.due_in_days, value)
			}))
		};
		void this.#refresh();
	}

	setOperatingBuffer(value: number): void {
		if (!Number.isFinite(value) || value < 0) return;
		if (value === this.request.operating_buffer) return;
		this.request = { ...this.request, operating_buffer: value };
		void this.#refresh();
	}
}

export const scenarioStore = new ScenarioStore();
