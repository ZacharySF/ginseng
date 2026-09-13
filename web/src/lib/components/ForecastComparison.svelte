<script lang="ts">
	import { formatCurrency, formatPercent } from '$lib/format';
	import type { ScenarioResponse } from '$lib/types';

	interface Props {
		current: ScenarioResponse;
		comparison: ScenarioResponse | null;
		comparisonLabel: string;
		deterministic: boolean;
		currentLabel?: string;
	}

	let { current, comparison, comparisonLabel, deterministic, currentLabel = 'Current what-if' }: Props = $props();
</script>

{#if comparison}
	<section class="comparison" aria-labelledby="comparison-title">
		<header>
			<div><p class="eyebrow">Scenario comparison</p><h2 id="comparison-title">{currentLabel} against {comparisonLabel}</h2></div>
			<span>Same saved revision, horizon, and seed. Each scenario uses its selected model.</span>
		</header>
		<div class="comparison-grid">
			<div><span>{deterministic ? 'Ending cash' : 'Median ending cash'}</span><strong class="numeric">{formatCurrency(comparison.cash_paths.p50[comparison.cash_paths.p50.length - 1])} → {formatCurrency(current.cash_paths.p50[current.cash_paths.p50.length - 1])}</strong></div>
			<div><span>Reserve</span><strong class="numeric">{formatCurrency(comparison.required_liquidity_reserve)} → {formatCurrency(current.required_liquidity_reserve)}</strong></div>
			<div><span>{deterministic ? 'Known reserve gap' : 'Shortfall chance'}</span><strong class="numeric">{deterministic ? `${formatCurrency(comparison.funding_gap)} → ${formatCurrency(current.funding_gap)}` : `${formatPercent(comparison.severity.cash_shortfall_probability)} → ${formatPercent(current.severity.cash_shortfall_probability)}`}</strong></div>
		</div>
	</section>
{/if}

<style>
	.comparison { display:grid; gap:.7rem; padding:1rem; background:var(--paper-soft); border-top:1px solid var(--rule); color:var(--ink); } header { display:flex; align-items:end; justify-content:space-between; gap:1rem; } header > div { display:grid; gap:.2rem; }.eyebrow,.comparison-grid span { color:var(--ink-soft); font-family:var(--font-mono); font-size:.63rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; } h2 { font-size:1rem; letter-spacing:-.025em; } header > span { max-width:42ch; color:var(--ink-soft); font-size:.71rem; line-height:1.4; text-align:right; }.comparison-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; background:var(--rule); border:1px solid var(--rule); }.comparison-grid div { display:grid; gap:.25rem; min-width:0; padding:.65rem; background:var(--paper); }.comparison-grid strong { overflow:hidden; font-size:.8rem; letter-spacing:-.025em; text-overflow:ellipsis; white-space:nowrap; } @media(max-width:42rem){header{display:grid;align-items:start}header > span{text-align:left}.comparison-grid{grid-template-columns:1fr}.comparison-grid strong{white-space:normal}}
</style>
