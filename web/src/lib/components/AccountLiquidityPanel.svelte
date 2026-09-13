<script lang="ts">
	import '$lib/analysis.css';
	import { formatCurrency } from '$lib/format';
	import type { AccountLiquidity } from '$lib/types';
	let { data }: { data: AccountLiquidity } = $props();
	const labels = { taxable: 'Taxable brokerage', traditional: 'Traditional IRA', roth: 'Roth IRA' };
</script>

<section class="analysis-panel" aria-label="Account access and withdrawal assumptions">
	<p class="eyebrow">Account access</p>
	<h2>What each account can fund</h2>
	<p>Withdrawals reach your cash balance after the availability delay, with an estimated tax and penalty reserve set aside. The optimizer chooses among these account types.</p>
	<div class="account-grid">
		{#each data.accounts as account}
			<article>
				<h3>{labels[account.account_type]}</h3>
				<p class="balance">{formatCurrency(account.balance)} account value</p>
				<strong class="analysis-value">{formatCurrency(account.net_cash)}</strong>
				<span>Maximum modeled spendable cash</span>
				{#if account.account_type === 'roth'}
					<p>{formatCurrency(data.roth_contribution_basis)} remaining regular contributions recorded. Access is capped by those contributions and the account value.</p>
				{:else if account.account_type === 'traditional'}
					<p>Ordinary income tax and the early-withdrawal penalty apply to the entire pretax withdrawal.</p>
				{:else}
					<p>Positive gains are priced lot by lot, using each lot's holding period. Realized losses create no cash rebate.</p>
				{/if}
				{#if account.account_type === 'roth' && account.excluded_balance >= 0.005}<p>{formatCurrency(account.excluded_balance)} excluded from modeled access. Roth earnings and conversion eligibility are not recorded.</p>{/if}
			</article>
		{/each}
	</div>
	<div class="analysis-table"><table>
		<caption>If the maximum accessible amount were withdrawn</caption>
		<thead><tr><th>Account</th><th>Gross withdrawal</th><th>Tax reserve</th><th>Penalty reserve</th><th>Spendable cash</th></tr></thead>
		<tbody>{#each data.accounts as account}<tr><td>{labels[account.account_type]}</td><td>{formatCurrency(account.gross)}</td><td>{formatCurrency(account.tax_reserve)}</td><td>{formatCurrency(account.penalty_reserve)}</td><td><strong>{formatCurrency(account.net_cash)}</strong></td></tr>{/each}</tbody>
	</table></div>
	<p class="analysis-note">Available after an assumed {data.availability_delay_days} calendar days. These amounts are account capacities; the proposed funding mix above may withdraw less.</p>
	{#if data.unclassified_retirement_balance > 0}<p class="analysis-alert">{formatCurrency(data.unclassified_retirement_balance)} in unclassified retirement accounts remains unavailable until the account type is known.</p>{/if}
	<h3>Visible assumptions</h3>
	<p>{data.scope}</p>
	<div class="analysis-table"><table>
		<thead><tr><th>Assumption</th><th>Value</th><th>Basis and source</th></tr></thead>
		<tbody>{#each data.assumptions as row}<tr><td>{row.label}</td><td>{row.value}</td><td>{row.source}{#if row.url}{' '}<a href={row.url} target="_blank" rel="noreferrer">IRS reference ↗</a>{/if}</td></tr>{/each}</tbody>
	</table></div>
	<p class="analysis-note">{data.tie_break} Future tax-sheltered growth is not priced. Assumptions version: {data.assumptions_version}.</p>
</section>

<style>
	.eyebrow { color: var(--ink-muted); font: 700 .65rem var(--font-mono); text-transform: uppercase; letter-spacing: .06em; }
	.account-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--rule); margin: 1rem 0; }
	article { padding: 1rem; background: var(--paper-soft); }
	article + article { border-left: 1px solid var(--rule); }
	article h3 { margin: 0 0 .45rem; }
	article p, article span { font-size: .82rem; line-height: 1.5; color: var(--ink-soft); }
	article .balance { margin: 0 0 .6rem; }
	article .analysis-value { display: block; margin-bottom: .2rem; }
	td { vertical-align: top; }
	td:nth-child(2) { white-space: nowrap; }
	a { color: var(--cobalt); }
	@media (max-width: 48rem) { .account-grid { grid-template-columns: 1fr; } article + article { border-left: 0; border-top: 1px solid var(--rule); } }
</style>
