// Shared runes-based scenario store (Future/Liquidity/Plans screens).
//
// Every mutation here re-requests the engine through `$lib/api`; nothing in
// this module computes a financial value locally. The Today screen
// (`routes/+page.svelte`) owns its own independent request/response pair —
// this store starts at the healthy baseline (no obligations) and is mutated
// only through `applyShock()`, `reset()`, and the policy setters below.
import { postScenario } from './api';
import type { Obligation, ScenarioRequest, ScenarioResponse } from './types';

export type LoadState = 'loading' | 'ready' | 'unreachable' | 'error';

// Coverage is capped at 95% for P0 (spec section 25) — two years of history
// makes deeper tail estimates too uncertain to present as if solid.
export const COVERAGE_TARGET_OPTIONS = [0.8, 0.9, 0.95] as const;

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

	readonly hasShock = $derived(
		CANONICAL_SHOCKS.every((shock) =>
			this.request.obligations.some((obligation) => obligation.id === shock.id)
		)
	);

	readonly isBaseline = $derived(this.request.obligations.length === 0);

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

	setOperatingBuffer(value: number): void {
		if (!Number.isFinite(value) || value < 0) return;
		if (value === this.request.operating_buffer) return;
		this.request = { ...this.request, operating_buffer: value };
		void this.#refresh();
	}
}

export const scenarioStore = new ScenarioStore();
