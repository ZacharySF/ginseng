<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatCurrency, formatPercent } from '$lib/format';
	import type { BacktestSummary } from '$lib/finance';

	interface Props {
		modelMode: 'scheduled' | 'assumptions' | 'history';
		accuracy: BacktestSummary | null;
		error: string | null;
		loading: boolean;
		onRun: () => void | Promise<void>;
	}

	let { modelMode, accuracy, error, loading, onRun }: Props = $props();
</script>

<section class="accuracy" aria-labelledby="accuracy-title">
	<header>
		<div>
			<p class="eyebrow">Forecast accuracy</p>
			<h2 id="accuracy-title">Check the model against held-out history</h2>
		</div>
		{#if modelMode === 'history'}
			<button type="button" onclick={() => void onRun()} disabled={loading}>{loading ? 'Checking…' : accuracy ? 'Run again' : 'Run accuracy check'}</button>
		{/if}
	</header>

	{#if modelMode !== 'history'}
		<p class="accuracy-copy">These checks evaluate history-based forecasts, not your current {modelMode} forecast. Choose History as the model source to run them.</p>
		<a class="data-link" href={resolve('/data?section=income')}>Choose history mode in Data</a>
	{:else if error}
		<p class="accuracy-error" role="alert">{error}</p>
		<a class="data-link" href={resolve('/data?section=history')}>Review history input</a>
	{:else if accuracy}
		<div class="accuracy-readout">
			<div>
				<span>Windows checked</span>
				<strong class="numeric">{accuracy.periods}</strong>
			</div>
			<div>
				<span>Within 80% range</span>
				<strong class="numeric">{formatPercent(accuracy.covered_80_percent)}</strong>
			</div>
			<div>
				<span>Mean absolute error</span>
				<strong class="numeric">{formatCurrency(accuracy.mean_absolute_error_cents / 100)}</strong>
			</div>
		</div>
		{#if accuracy.warning}
			<p class="accuracy-warning" role="status">{accuracy.warning}</p>
		{/if}
		{#if accuracy.windows.length > 0}
			<details class="window-detail">
				<summary>View held-out windows</summary>
				<div class="window-table-wrap">
					<table>
						<thead>
							<tr><th scope="col">Window</th><th scope="col">Actual change</th><th scope="col">Predicted change</th><th scope="col">Result</th></tr>
						</thead>
						<tbody>
							{#each accuracy.windows as window (`${window.start_date}:${window.end_date}`)}
								<tr>
									<td>{window.start_date}–{window.end_date}</td>
									<td class="numeric">{formatCurrency(window.actual_change_cents / 100)}</td>
									<td class="numeric">{formatCurrency(window.predicted_change_cents / 100)}</td>
									<td>{window.covered ? 'Inside range' : 'Outside range'}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</details>
		{/if}
	{:else}
		<p class="accuracy-copy">Run a rolling, held-out check. It never trains on the window it evaluates.</p>
	{/if}
</section>

<style>
	.accuracy {
		display: grid;
		gap: 0.75rem;
		padding: 1rem;
		background: var(--paper-soft);
		border-top: 1px solid var(--rule);
		color: var(--ink);
	}

	header {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 1rem;
	}

	header > div {
		display: grid;
		gap: 0.18rem;
	}

	.eyebrow,
	.accuracy-readout span,
	.window-detail summary {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.64rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	h2 {
		font-size: 1rem;
		letter-spacing: -0.025em;
	}

	button,
	.data-link {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 2.75rem;
		padding: 0 0.75rem;
		background: var(--cobalt);
		border: 1px solid var(--cobalt);
		color: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.035em;
		text-decoration: none;
		text-transform: uppercase;
		cursor: pointer;
	}

	button:hover:not(:disabled),
	.data-link:hover {
		background: var(--cobalt-bright);
	}

	button:disabled {
		cursor: wait;
		opacity: 0.58;
	}

	.accuracy-copy,
	.accuracy-error,
	.accuracy-warning {
		max-width: 68ch;
		margin: 0;
		color: var(--ink-soft);
		font-size: 0.78rem;
		line-height: 1.45;
	}

	.accuracy-error {
		padding: 0.55rem 0.65rem;
		background: var(--negative-soft);
		border-left: 2px solid var(--negative);
		color: var(--negative);
	}

	.accuracy-warning {
		padding-left: 0.65rem;
		border-left: 2px solid var(--warning);
	}

	.accuracy-readout {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1px;
		background: var(--rule);
		border: 1px solid var(--rule);
	}

	.accuracy-readout div {
		display: grid;
		gap: 0.25rem;
		padding: 0.65rem;
		background: var(--paper);
	}

	.accuracy-readout strong {
		font-size: 0.94rem;
		letter-spacing: -0.035em;
	}

	.window-detail {
		display: grid;
		gap: 0.55rem;
	}

	.window-detail summary {
		min-height: 2.5rem;
		display: inline-flex;
		align-items: center;
		cursor: pointer;
	}

	.window-table-wrap {
		overflow-x: auto;
		border: 1px solid var(--rule);
	}

	table {
		width: 100%;
		min-width: 34rem;
		border-collapse: collapse;
		font-size: 0.74rem;
	}

	th,
	td {
		padding: 0.55rem 0.65rem;
		border-bottom: 1px solid var(--rule);
		text-align: left;
	}

	th {
		background: var(--paper-deep);
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		letter-spacing: 0.035em;
		text-transform: uppercase;
	}

	tr:last-child td {
		border-bottom: 0;
	}

	@media (max-width: 40rem) {
		header {
		display: grid;
		align-items: start;
		}

		header button,
		.data-link {
			width: 100%;
		}

		.accuracy-readout {
			grid-template-columns: 1fr;
		}
	}
</style>
