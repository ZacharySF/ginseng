<script lang="ts">
	import { formatCurrency, formatPercent } from '$lib/format';
	import type { ScenarioResponse } from '$lib/types';

	interface Props {
		response?: ScenarioResponse | null;
		loading?: boolean;
		onRetry: () => void;
		onLoadExample?: () => void;
        deterministic?: boolean;
	}

	let { response = null, loading = false, onRetry, onLoadExample, deterministic = false }: Props = $props();
	const status = $derived(response?.optimizer_status);
	// An older engine cannot supply the risk-limit details required by this panel.
	const plan = $derived(status ? response?.optimal_plan : null);
	const count = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
	const accountNames = { taxable: 'Taxable brokerage', traditional: 'Traditional IRA', roth: 'Roth IRA contributions' };
	function cost(value: number) {
		return formatCurrency(Math.abs(value) < 0.005 ? 0 : value);
	}
</script>

<section class="optimizer-card" aria-label="Optimized funding mix" aria-busy={loading}>
	<header>
		<div>
			<p class="eyebrow">Funding optimizer</p>
			<h2>Optimized funding mix</h2>
		</div>
		{#if !loading && plan}
			<span class="badge">{status?.code === 'optimal_inaccurate' ? 'Approximate solution' : 'Model solution'}</span>
		{/if}
	</header>

	{#if loading}
		<div class="state" role="status" aria-live="polite">
			<strong>Finding a funding mix…</strong>
			<p>Evaluating the scenario and its funding options. Larger runs can take a little longer.</p>
		</div>
	{:else if response?.stress?.status === 'unsupported'}
		<div class="state failure" role="status"><strong>Stress assumption unavailable</strong><p>The selected stress has no supporting scenarios. Remove or adjust it before using a funding mix.</p></div>
	{:else if status?.code === 'not_needed'}
		<div class="state">
			<strong>No additional funding needed</strong>
			<p>{status.message}</p>
			{#if onLoadExample}<button type="button" onclick={onLoadExample}>Load repair example <span aria-hidden="true">↗</span></button>{/if}
		</div>
	{:else if plan && response}
		<p class="intro">Minimizes modeled tail cost under the selected buffer deficit limits below.</p>
		{#if response.stress?.status === 'active' && !response.stress.recommendation_supported}<p class="coverage-note analysis-alert">The stress tail is too concentrated under the support policy. This computed mix is not a recommendation.</p>{/if}
		{#if plan.meets_policy === false}<p class="coverage-note analysis-alert">Outside your policy: {plan.policy_reason ?? 'This mix does not meet every funding limit.'}</p>{:else if plan.meets_policy}<p class="coverage-note">Meets your policy on the evaluated paths. Historical validation is separate.</p>{/if}
        <p class="run-context">{count.format(plan.evaluation_paths)} futures · {plan.evaluation_horizon_days}-day evaluation</p>
		<div class="cost-grid">
			<div>
				<p class="eyebrow">Average cost</p>
				<strong class="cost numeric">{cost(plan.expected_cost)}</strong>
				<span>Average across all modeled futures.</span>
			</div>
			<div class="tail-cost">
				<p class="eyebrow">{plan.cost_coverage_target === 1 ? 'Worst future cost' : 'Tail cost · CVaR'}</p>
				<strong class="cost numeric">{cost(plan.cvar_cost)}</strong>
				<span>{plan.cost_coverage_target === 1 ? 'Cost of the most expensive modeled future.' : `Average cost in the worst ${formatPercent(1 - plan.cost_coverage_target)} of futures.`}</span>
			</div>
		</div>

		<div class="mix-grid" aria-label="Proposed funding amounts">
			<div><span>Use credit</span><strong class="numeric">{formatCurrency(plan.credit_draw)}</strong></div>
			<div><span>Withdraw investments · gross</span><strong class="numeric">{formatCurrency(plan.liquidation_amount)}</strong></div>
			<div><span>Reduce discretionary spending</span><strong>{formatPercent(plan.deferral_fraction)}</strong></div>
		</div>
		{#if plan.withdrawal_accounts?.length}
			<div class="withdrawal-breakdown">
				<h3>Where the spendable cash comes from</h3>
				<div class="withdrawal-table"><table><thead><tr><th>Account</th><th>Gross</th><th>Tax reserve</th><th>Penalty reserve</th><th>Spendable</th></tr></thead>
					<tbody>{#each plan.withdrawal_accounts as account}<tr><td>{accountNames[account.account_type]}</td><td>{formatCurrency(account.gross)}</td><td>{formatCurrency(account.tax_reserve)}</td><td>{formatCurrency(account.penalty_reserve)}</td><td>{formatCurrency(account.net_cash)}</td></tr>{/each}</tbody>
				</table></div>
				<p>Only the spendable amount enters the cash forecast. The tax and penalty reserve stays earmarked. Rates and account limits are listed below.</p>
			</div>
		{/if}

		<div class="risk-section">
			<h3>Risk with this mix</h3>
			{#if !deterministic}<div class="risk-grid">
				<div><span>Runs out of cash</span><strong>{formatPercent(plan.cash_shortfall_probability)}</strong><small>Futures that fall below $0.</small></div>
				<div><span>Breaches the buffer</span><strong>{formatPercent(plan.buffer_breach_probability)}</strong><small>Futures that fall below {formatCurrency(response.operating_buffer)}.</small></div>
			</div>
			{/if}<div class="buffer-limit">
				<div><span>Average buffer deficit</span><strong>{count.format(plan.dollar_days_below_buffer)} dollar-days</strong></div>
				<div><span>Allowed by this optimization</span><strong>{count.format(plan.buffer_tolerance_dollar_days)} dollar-days</strong></div>
			</div>
			<p class="explanation">A $100 buffer deficit lasting 3 days is 300 dollar-days. The limit applies to the average across all futures.</p>
			{#if plan.tail_deficit !== undefined}<p class="explanation">Tail buffer deficit: <strong>{formatCurrency(plan.tail_deficit)}</strong>. {plan.tail_deficit_limit == null ? 'No additional tail-deficit limit is set.' : `Allowed tail deficit: ${formatCurrency(plan.tail_deficit_limit)}.`} This averages each path's largest buffer deficit in the worst {plan.cost_coverage_target === 1 ? 'modeled case' : `${formatPercent(1 - plan.cost_coverage_target)} of deficits`}.</p>{/if}
			<p class="coverage-note">{plan.buffer_coverage_target != null ? `The optimizer conservatively enforces ${formatPercent(plan.buffer_coverage_target)} buffer coverage using the tail average of each future's worst signed buffer margin. This is a scenario-model requirement, not a guarantee about real outcomes.` : `The ${formatPercent(plan.cost_coverage_target)} setting selects the cost tail; this older result has no buffer-coverage constraint.`}</p>
		</div>

		<details>
			<summary>Cost assumptions and buffer sensitivity</summary>
			<p>Cost includes interest, account-specific taxes and early-withdrawal penalties, spending reductions valued dollar for dollar, and overdraft costs. Withdrawal principal is not counted as a cost: a $0 modeled cost can still require selling investments.</p>
			<p>{plan.cost_is_path_dependent ? 'Evaluated costs differ across the modeled futures.' : 'Evaluated costs are effectively the same across the modeled futures.'}</p>
			{#if !plan.buffer_constraint_binding}
				<p><strong>Buffer limit: not binding.</strong> This mix has room within the average deficit limit.</p>
			{:else}
				<p><strong>Buffer limit: at the limit.</strong> This mix uses the allowed average buffer deficit.</p>
			{/if}
			{#if plan.implied_liquidity_price === null}
				<p>The local value of relaxing the buffer deficit limit is unavailable.</p>
			{:else}
				<p>Near this solution, allowing one more dollar-day of average buffer deficit is worth {plan.implied_liquidity_price < 0.005 ? 'less than $0.01' : cost(plan.implied_liquidity_price)} in modeled tail cost. This is a local estimate.</p>
			{/if}
			{#if status?.code === 'optimal_inaccurate'}<p>{status.message}</p>{/if}
		</details>
	{:else}
		<div class="state failure" role="status">
			<strong>{status?.code === 'infeasible' ? 'No mix meets the buffer limit' : status?.code === 'solver_timeout' ? 'Optimization timed out' : 'Optimized mix unavailable'}</strong>
			<p>{status?.message ?? 'The engine did not provide optimizer details. Retry after updating the engine.'}</p>
			<p>Named funding plans remain available below.</p>
			<button type="button" onclick={onRetry}>Retry analysis</button>
		</div>
	{/if}
</section>

<style>
	.optimizer-card { margin-bottom: 1.25rem; border: 1px solid var(--rule); border-top: 3px solid var(--cobalt); background: var(--paper); color: var(--ink); }
	header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem; padding: 1.1rem 1.2rem 0.7rem; }
	h2 { margin: 0.25rem 0 0; font-size: 1.65rem; line-height: 1.15; letter-spacing: -0.035em; }
	h3 { margin: 0 0 0.85rem; font-size: 1.05rem; }
	.eyebrow, .badge, .run-context { font-family: var(--font-mono); font-size: 0.64rem; letter-spacing: 0.04em; text-transform: uppercase; }
	.eyebrow { color: var(--ink-muted); font-weight: 700; }
	.badge { padding: 0.4rem 0.55rem; border: 1px solid var(--cobalt); color: var(--cobalt); }
	.intro, .run-context { padding: 0 1.2rem; color: var(--ink-muted); }
	.intro { margin: 0 0 0.5rem; font-size: 0.88rem; }
	.run-context { margin-bottom: 1rem; }
	.cost-grid, .risk-grid, .buffer-limit { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.cost-grid { border-block: 1px solid var(--rule); }
	.cost-grid > div { display: grid; gap: 0.25rem; padding: 1rem 1.2rem; }
	.cost-grid span { color: var(--ink-muted); font-size: 0.82rem; }
	.cost { font-size: 2.7rem; line-height: 1.2; letter-spacing: -0.055em; }
	.tail-cost { background: var(--paper-soft); border-left: 1px solid var(--rule); }
	.tail-cost .cost { color: var(--cobalt); }
	.mix-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 1px solid var(--rule); }
	.mix-grid > div { display: grid; align-content: start; gap: 0.45rem; padding: 1rem 1.2rem; }
	.mix-grid > div + div { border-left: 1px solid var(--rule); }
	.mix-grid span, .risk-grid span, .buffer-limit span { color: var(--ink-muted); font-size: 0.83rem; }
	.mix-grid strong { font-size: 1.3rem; }
	.risk-section { padding: 1.1rem 1.2rem; }
	.withdrawal-breakdown { padding: 1.1rem 1.2rem; border-bottom: 1px solid var(--rule); }
	.withdrawal-table { max-width: 100%; overflow-x: auto; }
	.withdrawal-table table { width: 100%; border-collapse: collapse; font-size: .82rem; }
	.withdrawal-table th, .withdrawal-table td { text-align: left; padding: .65rem; border: 1px solid var(--rule); }
	.withdrawal-table th { background: var(--paper-soft); }
	.withdrawal-breakdown p { margin-top: .65rem; color: var(--ink-muted); font-size: .8rem; line-height: 1.5; }
	.risk-grid { gap: 1.2rem; margin-bottom: 1rem; }
	.risk-grid > div, .buffer-limit > div { display: grid; gap: 0.3rem; }
	.risk-grid strong { font-size: 1.35rem; }
	small { font-size: 0.77rem; color: var(--ink-muted); }
	.buffer-limit { padding: 0.85rem; gap: 1rem; background: var(--paper-soft); border: 1px solid var(--rule); }
	.buffer-limit strong { font-family: var(--font-mono); font-size: 0.8rem; }
	.explanation, .coverage-note { font-size: 0.8rem; line-height: 1.5; }
	.explanation { margin-top: 0.6rem; color: var(--ink-muted); }
	.coverage-note { margin-top: 0.6rem; }
	details { padding: 0.85rem 1.2rem; border-top: 1px solid var(--rule); font-size: 0.8rem; line-height: 1.5; }
	summary { cursor: pointer; font-weight: 700; }
	details p { margin-top: 0.7rem; color: var(--ink-muted); }
	.state { display: grid; justify-items: start; gap: 0.75rem; padding: 0.7rem 1.2rem 1.2rem; }
	.state strong { font-size: 1.1rem; }
	.state p { font-size: 0.85rem; color: var(--ink-muted); line-height: 1.5; }
	.failure strong { color: var(--negative); }
	button { padding: 0.8rem 1rem; border: 1px solid var(--cobalt); background: var(--cobalt); color: var(--on-accent); font: 700 0.72rem var(--font-mono); cursor: pointer; }
	button:focus-visible, summary:focus-visible { outline: 2px solid var(--cobalt); outline-offset: 4px; }
	@media (max-width: 38rem) {
		.cost-grid, .mix-grid, .risk-grid, .buffer-limit { grid-template-columns: 1fr; }
		.tail-cost, .mix-grid > div + div { border-left: 0; border-top: 1px solid var(--rule); }
	}
</style>
