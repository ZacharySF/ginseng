<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatCurrency, formatPercent } from '$lib/format';
	import PlanTable from '$lib/components/PlanTable.svelte';
	import type { ScenarioResponse, ScenarioSummary } from '$lib/types';
	import type { ScenarioChange } from '$lib/finance';

	type ModelMode = 'scheduled' | 'assumptions' | 'history' | 'demo';

	interface Props {
		response: ScenarioResponse;
		baseline?: ScenarioResponse | ScenarioSummary | null;
		comparisonLabel?: string;
		source: 'personal' | 'demo';
		modelMode: ModelMode;
		changes?: ScenarioChange[];
		isPreview?: boolean;
		showComparison?: boolean;
		eventsHref: string;
		dataHref?: string;
		hasCreditAccounts?: boolean;
		hasHoldings?: boolean;
	}

	let {
		response,
		baseline = null,
		comparisonLabel = 'saved inputs',
		source,
		modelMode,
		changes = [],
		isPreview = false,
		eventsHref,
		dataHref = '/data',
		hasCreditAccounts = false,
		showComparison = isPreview,
		hasHoldings = false
	}: Props = $props();

	const deterministic = $derived(modelMode === 'scheduled');
	const availablePlans = $derived(response.plans.filter((plan) => plan.feasible));
	const unavailablePlans = $derived(response.plans.filter((plan) => !plan.feasible));
	const comparisonHeading = $derived(isPreview ? 'What-if comparison' : 'Saved plan comparison');
	const capitalInputMissing = $derived(source === 'personal' && !hasCreditAccounts && !hasHoldings);
	const fundingTitle = $derived(response.funding_gap > 0 ? 'Ways to close the reserve gap' : 'Your modeled reserve is covered');
	function baselineFunding(value: ScenarioResponse | ScenarioSummary): number {
		return 'immediate_funding' in value ? value.immediate_funding : response.immediate_funding;
	}

</script>

<div class:funding-workbench--preview={isPreview} class="funding-workbench">
	<header class="view-toolbar">
		<div><strong>{source === 'personal' ? 'Funding routes' : 'Synthetic funding routes'}</strong><span>matched-horizon paths under the active reserve policy</span></div>
		<div class="toolbar-actions"><a href={eventsHref}>Edit events</a><p>{formatCurrency(response.funding_gap)} gap</p></div>
	</header>

	<div class="funding-layout">
		<main class="plan-console">
			<section class="plan-header" aria-labelledby="funding-title">
				<div>
					<p class="label">Funding decision</p>
					<h1 id="funding-title">{fundingTitle}</h1>
					<p>{response.funding_gap <= 0 ? 'Available cash covers the active reserve target. No additional borrowing, sale, or spending deferral is indicated by this forecast.' : deterministic ? 'The schedule is deterministic, so options are ranked by actual cost, feasibility, debt, sale, tax, and deferral fields without a shortfall probability claim.' : 'Each option uses the same modeled draw bundle. Differences reflect funding tradeoffs, not a different market draw.'}</p>
				</div>
				{#if response.funding_gap > 0}
				<div class="plan-counts" aria-label="Plan availability">
					<span><strong>{availablePlans.length}</strong> feasible</span>
					<span><strong>{unavailablePlans.length}</strong> limited</span>
				</div>
				{/if}
			</section>

			<PlanTable
				plans={response.plans}
				recommendation={response.recommendation}
				deterministic={deterministic}
				emptyMessage={response.funding_gap <= 0 ? 'No reserve gap to fund. Change events or policy to compare a different cash need.' : source === 'personal' ? 'Add credit accounts or priced holdings in Data, or schedule a future cash event, to compare practical funding routes.' : 'Adjust the synthetic events or reserve policy to compare funding routes.'}
			/>

			{#if response.plans.length > 0}
			<section class="plan-status-list" aria-labelledby="plan-status-title">
				<p class="label" id="plan-status-title">Feasibility and limits</p>
					<ul>
						{#each response.plans as plan (plan.id)}
							<li class:limited={!plan.feasible}>
								<span>{plan.label}</span>
								<strong>{plan.feasible ? 'Feasible' : 'Unavailable'}</strong>
								<p>{plan.feasible ? 'Within the modeled available-capital and settlement constraints.' : (plan.infeasible_reason ?? 'The forecast did not return the limiting constraint.')}</p>
							</li>
						{/each}
					</ul>
			</section>
			{/if}

			<section class="advanced-grid" aria-label="Advanced funding diagnostics">
				<article>
					<p class="label">Wrong-way risk</p>
					{#if response.wrong_way_risk}
						<strong>{response.wrong_way_risk.wrong_way_risk_present ? 'Market-linked sale risk present' : 'No market-linked sale risk flagged'}</strong>
						<dl>
							<div><dt>Forced-sale paths</dt><dd class="numeric">{formatPercent(response.wrong_way_risk.fraction_forced_to_sell)}</dd></div>
							<div><dt>All-path return</dt><dd class="numeric">{formatPercent(response.wrong_way_risk.portfolio_return_all_paths)}</dd></div>
							<div><dt>Forced-sale return</dt><dd class="numeric">{response.wrong_way_risk.portfolio_return_when_forced === null ? 'No forced-sale subset' : formatPercent(response.wrong_way_risk.portfolio_return_when_forced)}</dd></div>
						</dl>
					{:else}
						<p class="unavailable">{capitalInputMissing ? 'No personal credit accounts or priced holdings are saved, so a market-linked liquidation analysis cannot run.' : 'The current forecast did not return a market-linked liquidation analysis.'}</p>
						{#if source === 'personal'}<a href={resolve('/data?section=investments')}>Review investments in Data</a>{/if}
					{/if}
				</article>
				<article>
					<p class="label">Cost-aware optimum</p>
					{#if response.optimal_plan}
						<strong>{response.optimal_plan.solver_status}</strong>
						<dl>
							<div><dt>Credit draw</dt><dd class="numeric">{formatCurrency(response.optimal_plan.credit_draw)}</dd></div>
							<div><dt>Liquidation</dt><dd class="numeric">{formatCurrency(response.optimal_plan.liquidation_amount)}</dd></div>
							<div><dt>Deferral</dt><dd class="numeric">{formatPercent(response.optimal_plan.deferral_fraction)}</dd></div>
							<div><dt>CVaR cost</dt><dd class="numeric">{formatCurrency(response.optimal_plan.cvar_cost)}</dd></div>
							<div><dt>VaR cost</dt><dd class="numeric">{formatCurrency(response.optimal_plan.var_cost)}</dd></div>
							<div><dt>Expected cost</dt><dd class="numeric">{formatCurrency(response.optimal_plan.expected_cost)}</dd></div>
							{#if !deterministic}<div><dt>Cash shortfall chance</dt><dd class="numeric">{formatPercent(response.optimal_plan.cash_shortfall_probability)}</dd></div>{/if}
						</dl>
						<p class="solver-note">Uses an average buffer-erosion limit, not a hard cap on shortfall probability. A cost minimum is not necessarily the safest plan.</p>
						{#if response.optimal_plan.implied_liquidity_price !== null}<p class="solver-note">Implied liquidity price {formatCurrency(response.optimal_plan.implied_liquidity_price)}{response.optimal_plan.cost_is_path_dependent ? ' · path-dependent' : ''}.</p>{/if}
					{:else if response.funding_gap <= 0}
						<p class="solver-note">No reserve gap to fund, so no borrowing or sale is optimized.</p>
					{:else}
						<p class="unavailable">{capitalInputMissing ? 'There is no saved credit account or priced holding for the optimizer to allocate.' : 'The solver did not return an optimized plan for this forecast.'}</p>
						{#if source === 'personal'}<a href={resolve('/data?section=credit')}>Review funding inputs in Data</a>{/if}
					{/if}
				</article>
			</section>
		</main>

		<aside class="funding-inspector" aria-label="Funding inspector">
			<section>
				<p class="label">Actual capital classes</p>
				<div class="capital-fact"><span>Available cash</span><strong class="numeric">{formatCurrency(response.immediate_funding)}</strong></div>
				<div class="capital-fact"><span>Marketable backup</span><strong class="numeric">{formatCurrency(response.marketable_backup_capital)}</strong></div>
				<div class="capital-fact"><span>Restricted capital</span><strong class="numeric">{formatCurrency(response.restricted_capital)}</strong></div>
				<p>Restricted capital is not silently counted as spendable cash.</p>
			</section>
			<section>
				<p class="label">Reserve constraint</p>
				<strong class:attention={response.funding_gap > 0} class="inspector-value numeric">{formatCurrency(response.funding_gap)}</strong>
				<span>{response.funding_gap > 0 ? 'Gap to the active reserve guardrail.' : 'Current available funding covers the guardrail.'}</span>
			</section>
			{#if showComparison && baseline}
				<section>
					<p class="label">{comparisonHeading} · {comparisonLabel}</p>
					<div class="comparison"><span>Available cash</span><strong class="numeric">{formatCurrency(baselineFunding(baseline))} → {formatCurrency(response.immediate_funding)}</strong></div>
					<div class="comparison"><span>Reserve</span><strong class="numeric">{formatCurrency(baseline.required_liquidity_reserve)} → {formatCurrency(response.required_liquidity_reserve)}</strong></div>
					<div class="comparison"><span>{deterministic ? 'Known gap' : 'Shortfall chance'}</span><strong>{deterministic ? `${formatCurrency(baseline.funding_gap)} → ${formatCurrency(response.funding_gap)}` : `${formatPercent(baseline.severity.cash_shortfall_probability)} → ${formatPercent(response.severity.cash_shortfall_probability)}`}</strong></div>
				</section>
			{/if}
			{#if isPreview && changes.length > 0}
				<section>
					<p class="label">Changed inputs</p>
					<ul class="change-list">
						{#each changes as change (`${change.label}:${change.before}:${change.after}`)}
							<li><span>{change.label}</span><strong>{change.before} → {change.after}</strong></li>
						{/each}
					</ul>
				</section>
			{/if}
			{#if source === 'personal'}<a class="data-link" href={dataHref}>Edit capital inputs in Data</a>{/if}
		</aside>
	</div>
</div>

<style>
	.funding-workbench { min-height:calc(100dvh - 3.25rem); background:var(--paper); color:var(--ink); }.funding-workbench--preview { box-shadow:inset 3px 0 var(--cobalt); }.view-toolbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; min-height:3.35rem; padding:.3rem 1rem; border-bottom:1px solid var(--rule); }.view-toolbar > div:first-child { display:flex; align-items:baseline; gap:.6rem; min-width:0; }.view-toolbar strong { font-size:.9rem; letter-spacing:-.02em; }.view-toolbar span,.view-toolbar p,.label { color:var(--ink-soft); font-family:var(--font-mono); font-size:.63rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }.view-toolbar p { margin:0; }.toolbar-actions { display:flex; align-items:center; gap:.65rem; }.toolbar-actions a { display:inline-flex; align-items:center; min-height:2.75rem; padding:0 .65rem; border:1px solid var(--control-border); color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.65rem; font-weight:700; letter-spacing:.035em; text-decoration:none; text-transform:uppercase; }.toolbar-actions a:hover { background:var(--cobalt); border-color:var(--cobalt); color:var(--paper); }
	.funding-layout { display:grid; grid-template-columns:minmax(0,1fr) 18rem; min-height:calc(100dvh - 6.6rem); }.plan-console { display:grid; align-content:start; gap:1rem; min-width:0; padding:1rem; border-right:1px solid var(--rule); }.plan-header { display:flex; align-items:end; justify-content:space-between; gap:1rem; }.plan-header > div:first-child { display:grid; gap:.3rem; max-width:64ch; }.plan-header h1 { font-size:clamp(1.25rem,2.4vw,1.8rem); letter-spacing:-.045em; line-height:1; }.plan-header > div:first-child > p:last-child { color:var(--ink-soft); font-size:.78rem; line-height:1.45; }.plan-counts { display:grid; grid-template-columns:repeat(2,auto); gap:1px; flex:none; background:var(--rule); border:1px solid var(--rule); }.plan-counts span { display:grid; gap:.1rem; padding:.4rem .55rem; background:var(--paper-soft); color:var(--ink-soft); font-family:var(--font-mono); font-size:.6rem; font-weight:700; letter-spacing:.04em; text-align:center; text-transform:uppercase; }.plan-counts strong { color:var(--ink); font-size:.85rem; }
	.plan-status-list { display:grid; gap:.55rem; }.plan-status-list ul { display:grid; grid-template-columns:repeat(auto-fit,minmax(13rem,1fr)); gap:1px; padding:0; margin:0; background:var(--rule); border:1px solid var(--rule); list-style:none; }.plan-status-list li { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.25rem .6rem; padding:.65rem; background:var(--paper-soft); }.plan-status-list li.limited { background:var(--negative-soft); box-shadow:inset 2px 0 var(--negative); }.plan-status-list li > span { font-size:.77rem; font-weight:700; }.plan-status-list li > strong { color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.62rem; letter-spacing:.04em; text-transform:uppercase; }.plan-status-list li.limited > strong { color:var(--negative); }.plan-status-list li p { grid-column:1 / -1; margin:0; color:var(--ink-soft); font-size:.7rem; line-height:1.4; }
	.advanced-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1px; background:var(--rule); border:1px solid var(--rule); }.advanced-grid article { display:grid; align-content:start; gap:.55rem; min-width:0; padding:.85rem; background:var(--paper-deep); }.advanced-grid article > strong { font-size:.85rem; }.advanced-grid dl { display:grid; gap:1px; margin:0; background:var(--rule); }.advanced-grid dl div { display:flex; align-items:baseline; justify-content:space-between; gap:.55rem; padding:.42rem .5rem; background:var(--paper); }.advanced-grid dt { color:var(--ink-soft); font-size:.69rem; }.advanced-grid dd { margin:0; color:var(--ink); font-size:.72rem; text-align:right; }.unavailable,.solver-note { margin:0; color:var(--ink-soft); font-size:.73rem; line-height:1.45; }.advanced-grid a { min-height:2.5rem; display:inline-flex; align-items:center; justify-self:start; padding:0 .5rem; border:1px solid var(--control-border); color:var(--cobalt-deep); font-family:var(--font-mono); font-size:.62rem; font-weight:700; letter-spacing:.035em; text-decoration:none; text-transform:uppercase; }.advanced-grid a:hover { background:var(--cobalt); color:var(--paper); }
	.funding-inspector { display:grid; align-content:start; background:var(--paper-soft); }.funding-inspector section { display:grid; gap:.65rem; padding:1rem; border-bottom:1px solid var(--rule); }.capital-fact { display:flex; align-items:baseline; justify-content:space-between; gap:.65rem; color:var(--ink-soft); font-size:.73rem; }.capital-fact strong { color:var(--ink); font-size:.78rem; }.funding-inspector section > p:last-child,.funding-inspector section > span { color:var(--ink-soft); font-size:.73rem; line-height:1.42; }.inspector-value { color:var(--cobalt); font-size:1.7rem; font-weight:800; letter-spacing:-.065em; }.inspector-value.attention { color:var(--negative); }.comparison { display:grid; gap:.18rem; }.comparison span { color:var(--ink-soft); font-size:.68rem; }.comparison strong { color:var(--ink); font-size:.75rem; }.change-list { display:grid; gap:1px; padding:0; margin:0; background:var(--rule); list-style:none; }.change-list li { display:grid; gap:.15rem; padding:.45rem .5rem; background:var(--paper); }.change-list span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.57rem; font-weight:700; letter-spacing:.035em; text-transform:uppercase; }.change-list strong { font-size:.69rem; }.data-link { min-height:2.75rem; display:inline-flex; align-items:center; padding:.8rem 1rem; border-top:1px solid var(--rule); color:var(--cobalt-deep); font-size:.72rem; font-weight:700; text-decoration:none; }.data-link:hover { background:var(--cobalt); color:var(--paper); }
	@media(max-width:60rem){.funding-workbench{min-height:0}.funding-layout{grid-template-columns:1fr;min-height:0}.plan-console{border-right:0}.funding-inspector{grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--rule)}.funding-inspector section{border-right:1px solid var(--rule);border-bottom:0}.data-link{grid-column:1 / -1}}
	@media(max-width:42rem){.view-toolbar{display:grid;gap:.25rem;padding:.6rem .75rem}.view-toolbar > div:first-child{display:grid;gap:.2rem}.toolbar-actions{justify-content:space-between}.plan-console{padding:.75rem}.plan-header{display:grid;align-items:start}.plan-counts{justify-self:start}.advanced-grid{grid-template-columns:1fr}.funding-inspector{grid-template-columns:1fr}.funding-inspector section{border-right:0;border-bottom:1px solid var(--rule)}.data-link{grid-column:auto}}
	@media(max-width:42rem){.advanced-grid a,.data-link{min-height:2.75rem}}
</style>
