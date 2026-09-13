// Shared runes-based scenario store used by every decision surface.
//
// Every mutation re-requests the engine through `$lib/api`; this module only
// validates scenario inputs and coordinates request state. The active request
// begins at a healthy baseline and can hold user-authored future obligations,
// the staged repair preset, and policy settings.
import { postScenario } from './api';
import type { Obligation, ScenarioRequest, ScenarioResponse, ScenarioSummary } from './types';

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

export class ScenarioStore {
	request = $state<ScenarioRequest>(baselineRequest());
	response = $state<ScenarioResponse | null>(null);
	// The engine returns the no-event baseline in the same response, using
	// the same draws and weights. No second request or client-side estimate
	// is needed to show the effect of the user's future events.
	baselineResponse = $state<ScenarioSummary | null>(null);
	loadState = $state<LoadState>('loading');
	errorMessage = $state('');

	#requestSeq = 0;
	#initialized = false;
	#customObligationSequence = 0;
	#running = false;
	#queued: { sequence: number; request: ScenarioRequest } | null = null;

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
			!label || label.length > 100 ||
			!Number.isFinite(amount) ||
			amount <= 0 || amount > 1_000_000 ||
			!Number.isInteger(dueInDays) ||
			dueInDays < 1 ||
			dueInDays > 365
		) {
			return null;
		}
		return { id: obligation.id, label, amount, due_in_days: dueInDays };
	}

	async #refresh(): Promise<void> {
		const seq = ++this.#requestSeq;
		this.loadState = 'loading';
		this.errorMessage = '';
		this.response = null;
		this.baselineResponse = null;
		this.#queued = { sequence: seq, request: JSON.parse(JSON.stringify(this.request)) };
		if (this.#running) return;
		this.#running = true;
		try {
			// One request at a time. Rapid edits replace the pending request;
			// they do not leave multiple expensive server solves running.
			while (this.#queued) {
				const current = this.#queued;
				this.#queued = null;
				const mainResult = await postScenario(current.request);
				if (current.sequence !== this.#requestSeq) continue;
				if (mainResult.status === 'ok') {
					this.response = mainResult.data;
					this.baselineResponse = mainResult.data.baseline_summary;
					this.loadState = 'ready';
				} else {
					this.errorMessage = mainResult.message;
					this.loadState = mainResult.status === 'engine-unreachable' ? 'unreachable' : 'error';
				}
			}
		} finally {
			this.#running = false;
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
		if (this.request.obligations.length >= 200) return;
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
			obligations: [...this.request.obligations, ...CANONICAL_SHOCKS.filter(shock => !this.request.obligations.some(item => item.id === shock.id))]
		};
		void this.#refresh();
	}

	reset(): void {
		this.request = baselineRequest();
		void this.#refresh();
	}

	/** Load the complete 30-day example so both repair payments are included. */
	loadRepairExample(): void {
		this.request = { ...baselineRequest(), obligations: [...CANONICAL_SHOCKS] };
		void this.#refresh();
	}

	setCoverageTarget(value: number): void {
		if (!Number.isFinite(value) || value <= 0 || value > 1) return;
		if (value === this.request.coverage_target) return;
		this.request = { ...this.request, coverage_target: value };
		void this.#refresh();
	}

	setHorizonDays(value: number): void {
		if (!Number.isInteger(value) || value < 1 || value > 365 || value === this.request.horizon_days) return;
		this.request = {
			...this.request,
			horizon_days: value
		};
		void this.#refresh();
	}

	setOperatingBuffer(value: number): void {
		if (!Number.isFinite(value) || value < 0 || value > 1_000_000) return;
		if (value === this.request.operating_buffer) return;
		this.request = { ...this.request, operating_buffer: value };
		void this.#refresh();
	}

	setTailDeficitLimit(value: number | null): void {
		if (value !== null && (!Number.isFinite(value) || value < 0 || value > 1_000_000)) return;
		if (value === this.request.tail_deficit_limit) return;
		this.request = { ...this.request, tail_deficit_limit: value };
		void this.#refresh();
	}

	setRiskLimits(tail: number | null, mean: number | null): void {
		if ([tail, mean].some(value => value !== null && (!Number.isFinite(value) || value < 0 || value > 1_000_000))) return;
		this.request = { ...this.request, tail_deficit_limit: tail, buffer_tolerance_dollar_days: mean };
		void this.#refresh();
	}

	setStressProbability(value: number | null): void {
		if (value !== null && (!Number.isFinite(value) || value < 0 || value > 1)) return;
		this.request = { ...this.request, drought_view: value === null ? null : { probability: value, window_days: 14, income_fraction: 0.5 } };
		void this.#refresh();
	}
}

export const scenarioStore = new ScenarioStore();
