<script lang="ts">
	import '$lib/analysis.css';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { AnalysisStore } from '$lib/analysis.svelte';
	import type { PortfolioReport } from '$lib/analysis-types';
	import { formatCurrency, formatPercent } from '$lib/format';
	const analysis = new AnalysisStore<PortfolioReport>('portfolio');
	const revision = $derived(JSON.stringify(scenarioStore.request));
	$effect(() => { revision; analysis.reset(); });
	const pct = (value: number | null) => value === null ? 'No cash-pressure sample' : formatPercent(value);
</script>

<section class="analysis-panel" aria-label="Investment backstop analysis">
	<h2>Which investments back up your cash?</h2>
	<p>Inspect each holding when cash is tight, then compare fractional-share sales that raise the same amount.</p>
	<button class="primary" type="button" disabled={analysis.loading} onclick={() => analysis.run(scenarioStore.request)}>{analysis.loading ? 'Analyzing holdings…' : 'Compare investment sales'}</button>
	{#if analysis.error}<p class="analysis-alert" role="alert">{analysis.error}</p>{/if}
	{#if analysis.data}
		{@const report = analysis.data}
		{#if report.status !== 'ready'}<p class="analysis-alert">{report.message}</p>{:else}
			<p>{report.source} · {report.history_days} aligned days. The model estimates relationships between holdings using Ledoit–Wolf shrinkage ({formatPercent(report.shrinkage)} toward a scaled identity matrix).</p>
			<p>Cash falls below the buffer in {formatPercent(report.cash_pressure_probability)} of these futures. Conditional returns below refer to that subset.</p>
			<div class="analysis-table"><table><thead><tr><th>Holding</th><th>Current value</th><th>Variance contribution</th><th>Average return</th><th>Return when cash is tight</th></tr></thead><tbody>
				{#each report.assets as asset}<tr><td>{asset.symbol}</td><td>{formatCurrency(asset.value)}</td><td>{formatPercent(asset.risk_contribution)}</td><td>{pct(asset.return_all_paths)}</td><td>{pct(asset.return_under_cash_pressure)}</td></tr>{/each}
			</tbody></table></div>
			{#if report.variants.length}
				<h3>Raise {formatCurrency(report.target_proceeds)}</h3>
				<p>Before selling, modeled daily volatility is {formatPercent(report.before.daily_volatility)}. Each comparison recalculates the portfolio remaining after the sale.</p>
				<div class="analysis-table"><table><thead><tr><th>Sale method</th><th>Gain / loss</th><th>Assumed gain tax</th><th>Remaining daily volatility</th><th>Conditional underperformance</th></tr></thead><tbody>
					{#each report.variants as variant}<tr><td>{variant.label}</td><td>{formatCurrency(variant.realized_gain_loss)}</td><td>{formatCurrency(variant.estimated_positive_gain_tax)}</td><td>{formatPercent(variant.after.daily_volatility)}</td><td>{pct(variant.after.conditional_underperformance)}</td></tr>{/each}
				</tbody></table></div>
				<p class="analysis-note">Conditional underperformance is average return minus return when cash is tight. Lower values mean a smaller shortfall as a backstop. The conditional method recomputes the remaining portfolio after each slice; it is a heuristic and may increase concentration or volatility.</p>
				{#each report.variants as variant}<details><summary>{variant.label} · lots sold</summary><div class="analysis-table"><table><thead><tr><th>Lot</th><th>Shares</th><th>Proceeds</th><th>Gain / loss</th></tr></thead><tbody>{#each variant.lots as lot}<tr><td>{lot.symbol} · {lot.lot_id}</td><td>{lot.shares.toFixed(4)}</td><td>{formatCurrency(lot.dollars)}</td><td>{formatCurrency(lot.realized_gain_loss)}</td></tr>{/each}</tbody></table></div></details>{/each}
			{:else}<p>No reserve gap currently requires an investment sale.</p>{/if}
			<p>{report.tax_assumptions.label} Assumed rates: {formatPercent(report.tax_assumptions.long_term_rate)} for longer-held lots and {formatPercent(report.tax_assumptions.short_term_rate)} for shorter-held lots.</p>
			<p class="analysis-note">The tax-conscious method solves a sell-only linear program with fractional shares. Proceeds become available after the model's settlement and transfer delay. None of these controls execute a trade.</p>
		{/if}
	{/if}
</section>
