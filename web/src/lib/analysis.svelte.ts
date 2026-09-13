import { postAnalysis } from './api';
import type { ScenarioRequest } from './types';

export class AnalysisStore<T> {
	data = $state<T | null>(null);
	loading = $state(false);
	error = $state('');
	#sequence = 0;
	#controller: AbortController | null = null;
	constructor(private kind: 'calibration' | 'funding' | 'portfolio') {}
	reset() {
		this.#sequence++;
		this.#controller?.abort();
		this.data = null; this.loading = false; this.error = '';
	}
	async run(request: ScenarioRequest) {
		this.reset();
		const sequence = this.#sequence;
		this.#controller = new AbortController();
		this.loading = true;
		const result = await postAnalysis<T>(this.kind, JSON.parse(JSON.stringify(request)), this.#controller.signal);
		if (sequence !== this.#sequence) return;
		this.loading = false;
		if (result.status === 'ok') this.data = result.data;
		else this.error = result.message;
	}
}
