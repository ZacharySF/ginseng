<script lang="ts">
	import '$lib/analysis.css';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { AnalysisStore } from '$lib/analysis.svelte';
	import type { FundingAnalysis } from '$lib/analysis-types';
	import { formatCurrency, formatPercent } from '$lib/format';
	const analysis = new AnalysisStore<FundingAnalysis>('funding');
	const revision = $derived(JSON.stringify(scenarioStore.request));
	let selectedIndex = $state(0);
	$effect(() => { revision; analysis.reset(); selectedIndex = 0; });
	const report = $derived(analysis.data && 'frontier' in analysis.data ? analysis.data : null);
	const solved = $derived(report?.frontier.filter(point => point.plan !== null) ?? []);
	const selected = $derived(solved[selectedIndex]);
	const anchors = $derived(report?.anchors ?? []);
	const maxCost = $derived(Math.max(1, ...solved.map(p => p.plan!.expected_cost), ...anchors.map(p => p.expected_cost)));
	const maxDeficit = $derived(Math.max(1, ...solved.map(p => p.plan!.tail_deficit), ...anchors.map(p => p.tail_deficit)));
	const x = (value: number) => 65 + value / maxCost * 500;
	const y = (value: number) => 215 - value / maxDeficit * 170;
	const marginal = (value: number | null) => value === null ? 'Unavailable' : `$${(Math.abs(value) < .00005 ? 0 : value).toFixed(4)}`;
</script>

<section class="analysis-panel" aria-label="Funding cost and downside analysis">
	<h2>Cost versus downside</h2>
	<p>Compare lower-cost choices with stricter limits on the worst buffer deficits. Named plans stay on the chart as reference points.</p>
	<button class="primary" type="button" disabled={analysis.loading} onclick={() => analysis.run(scenarioStore.request)}>{analysis.loading ? 'Comparing funding limits…' : 'Explore cost and downside'}</button>
	<p class="analysis-note">Also checks the original optimized mix on fresh simulations and measures the value of small changes in credit capacity and buffer allowance. This additional analysis can take up to a minute.</p>
	{#if analysis.error}<p class="analysis-alert" role="alert">{analysis.error}</p>{/if}
	{#if analysis.data && !report}<p class="analysis-alert" role="alert">Analysis unavailable: {analysis.data.reason}</p>{/if}
	{#if report}
		<p>{report.paths.toLocaleString()} shared futures · {report.evaluation_horizon_days} days · identical weights and cost definitions.</p>
		{#if report.status !== 'ready'}<p class="analysis-alert">Analysis unavailable: {report.reason}. Adjust the deficit limit or try again.</p>{/if}
		{#if solved.length}
			<svg class="analysis-plot" viewBox="0 0 640 275" role="img" aria-label="Average cost versus tail buffer deficit, including named funding plans">
				<path d="M65 35V215H565" stroke="var(--rule-strong)" fill="none" />
				{#each anchors as anchor}<rect x={x(anchor.expected_cost)-4} y={y(anchor.tail_deficit)-4} width="8" height="8" fill={anchor.feasible ? 'var(--ink-muted)' : 'var(--negative)'}><title>{anchor.label}: average cost {formatCurrency(anchor.expected_cost)}, tail deficit {formatCurrency(anchor.tail_deficit)}{anchor.feasible ? '' : ' · funding operation unavailable'}</title></rect>{/each}
				{#each solved as point,i}<circle cx={x(point.plan!.expected_cost)} cy={y(point.plan!.tail_deficit)} r={i === selectedIndex ? 7 : 4} fill="var(--cobalt)"><title>Limit {formatCurrency(point.limit)}: cost {formatCurrency(point.plan!.expected_cost)}, tail deficit {formatCurrency(point.plan!.tail_deficit)}</title></circle>{/each}
				<text x="65" y="20">Tail buffer deficit · up to {formatCurrency(maxDeficit)}</text>
				<text x="65" y="239">$0</text><text x="565" y="239" text-anchor="end">{formatCurrency(maxCost)}</text><text x="315" y="264" text-anchor="middle">Average modeled cost →</text>
			</svg>
			<p class="analysis-note">Blue circles: solved limits. Squares: named plans (red means an unavailable funding operation). These are sampled tradeoffs; values between points are not computed.</p>
			<label>Explore the {solved.length} solved limits<input type="range" min="0" max={solved.length-1} step="1" bind:value={selectedIndex} aria-valuetext={selected ? `Tail deficit limit ${formatCurrency(selected.limit)}` : undefined} /></label>
			{#if selected?.plan}
				{@const p = selected.plan}
				<div class="analysis-grid">
					<div><small>Selected tail deficit limit</small><strong class="analysis-value">{formatCurrency(selected.limit)}</strong></div>
					<div><small>Average modeled cost</small><strong class="analysis-value">{formatCurrency(p.expected_cost)}</strong></div>
					<div><small>Actual tail deficit</small><strong class="analysis-value">{formatCurrency(p.tail_deficit)}</strong></div>
				</div>
				<p>Borrow {formatCurrency(p.credit_draw)}, withdraw {formatCurrency(p.liquidation_amount)} gross from investments, reduce discretionary spending by {formatPercent(p.deferral_fraction)}.</p>
				{#if p.withdrawal_net_cash !== undefined}<p>Spendable withdrawal cash: {formatCurrency(p.withdrawal_net_cash)}. {p.withdrawal_accounts?.filter(a => a.gross > .005).map(a => `${a.account_type === 'roth' ? 'Roth contributions' : a.account_type === 'traditional' ? 'Traditional IRA' : 'Taxable brokerage'}: ${formatCurrency(a.gross)} gross → ${formatCurrency(a.net_cash)} spendable`).join('; ')}.</p>{/if}
				<p>Buffer breach frequency: {formatPercent(p.buffer_breach_probability)}. The deficit limit controls severity, not a promise of zero breaches.</p>
				<button type="button" onclick={() => scenarioStore.setTailDeficitLimit(selected.limit)}>Use this deficit limit</button>
			{/if}
		{/if}
		{#if report.frontier.some(p => p.plan === null)}<p class="analysis-note">Unsolved limits: {report.frontier.filter(p => p.plan === null).map(p => `${formatCurrency(p.limit)} (${p.status.replaceAll('_',' ')})`).join(', ')}.</p>{/if}
		{#if report.budget_exhausted}<p class="analysis-alert">The analysis reached its time budget. Completed comparisons are shown; missing results are labeled.</p>{/if}
		{#if report.anchors.length}
			<div class="analysis-table"><table><caption>Named plans measured using the same losses</caption><thead><tr><th>Plan</th><th>Average cost</th><th>Tail cost</th><th>Tail buffer deficit</th></tr></thead><tbody>
				{#each report.anchors as anchor}<tr><td>{anchor.label}{#if !anchor.feasible}<br />Funding operation unavailable{/if}</td><td>{formatCurrency(anchor.expected_cost)}</td><td>{formatCurrency(anchor.cvar_cost)}</td><td>{formatCurrency(anchor.tail_deficit)}</td></tr>{/each}
			</tbody></table></div>
		{/if}
		{#if report.holdout}
			<h3>Original optimized mix on fresh futures</h3>
			{#if report.holdout.status === 'ready'}
				<p>{report.holdout.label}</p>
				<div class="analysis-grid"><div><small>Average cost</small><strong>{formatCurrency(report.holdout.expected_cost)}</strong></div><div><small>Tail cost</small><strong>{formatCurrency(report.holdout.cvar_cost)}</strong></div><div><small>Cash shortfall</small><strong>{formatPercent(report.holdout.cash_shortfall_probability)}</strong></div></div>
				<p>Mean buffer limit: {report.holdout.within_mean_buffer_limit ? 'held in this fresh sample' : 'exceeded in this fresh sample'}.{report.holdout.within_tail_deficit_limit === null ? '' : ` Tail deficit limit: ${report.holdout.within_tail_deficit_limit ? 'held' : 'exceeded'}.`}</p>
			{:else}<p>{report.holdout.message}</p>{/if}
		{/if}
		<details><summary>Marginal values and comparison assumptions</summary>
			<p>{report.loss_definition}</p><p>{report.risk_definition}</p>
			{#each report.shadow_checks as check}
				<h3>{check.resource === 'credit_capacity' ? 'Value of extra credit capacity' : 'Value of extra average buffer dollar-days'}</h3>
				<p>Solver's local value: {marginal(check.solver_dual)} per additional unit.</p>
				<div class="analysis-table"><table><thead><tr><th>Extra capacity</th><th>Cost saved per unit</th></tr></thead><tbody>{#each check.checks as row}<tr><td>{row.bump}</td><td>{row.value_per_unit === null ? row.status.replaceAll('_',' ') : marginal(row.value_per_unit)}</td></tr>{/each}</tbody></table></div>
				{#if check.range}<p>Measured range: {marginal(check.range.low)}–{marginal(check.range.high)}. {check.stable ? 'Similar across the three tested increments.' : 'The marginal value varies or some checks are unavailable.'}</p>{/if}
			{/each}
			<p>These values apply near the current plan. Multiplying them by the entire credit limit would not measure the cost of that limit.</p>
		</details>
	{/if}
</section>
