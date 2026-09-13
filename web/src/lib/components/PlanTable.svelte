<script lang="ts">
	import { formatCurrency, formatPercent, formatSignedCurrency } from '$lib/format';
	import type { Plan, Recommendation } from '$lib/types';

	interface Props {
		plans: Plan[];
		recommendation: Recommendation | null;
		deterministic?: boolean;
		emptyMessage?: string;
	}

	let {
		plans,
		recommendation,
		deterministic = false,
		emptyMessage = 'No funding paths are available for this forecast yet.'
	}: Props = $props();

	const stochasticMetrics = [
		{ label: 'Shortfall', read: (plan: Plan) => formatPercent(plan.cash_shortfall_probability) },
		{ label: 'Avg. deficit', read: (plan: Plan) => formatCurrency(plan.avg_cash_deficit_when_short) }
	];
	const sharedMetrics = [
		{ label: 'New debt', read: (plan: Plan) => formatCurrency(plan.new_debt) },
		{ label: 'Interest', read: (plan: Plan) => formatCurrency(plan.interest_exposure) },
		{ label: 'Assets sold', read: (plan: Plan) => formatCurrency(plan.investment_sold) },
		{ label: 'Taxable gain/loss', read: (plan: Plan) => formatSignedCurrency(plan.realized_gain_loss) },
		{ label: 'Deferred', read: (plan: Plan) => formatCurrency(plan.deferred_spending) }
	];
	const displayedMetrics = $derived(deterministic ? sharedMetrics : [...stochasticMetrics, ...sharedMetrics]);
</script>

{#if plans.length === 0}
	<div class="plans-empty">
		<p>No funding paths yet.</p>
		<span>{emptyMessage}</span>
	</div>
{:else}
	{#if recommendation}
		{@const recommendedPlan = plans.find((plan) => plan.id === recommendation.plan_id)}
		<section class="recommendation-line" aria-label="Model recommendation">
			<div>
				<p>Model recommendation</p>
				<strong>{recommendedPlan?.label ?? recommendation.plan_id}</strong>
			</div>
			<span>{recommendation.explanation}</span>
		</section>
	{/if}

	<div class="plan-list" role="list" aria-label="Funding path comparison">
		{#each plans as plan, index (plan.id)}
			<article class:recommended={plan.recommended} class:dominated={plan.dominated} class:infeasible={!plan.feasible} class="plan-row" role="listitem">
				<header>
					<span class="plan-index">0{index + 1}</span>
					<div class="plan-title">
						<h3>{plan.label}</h3>
						<p>{plan.explanation}</p>
					</div>
					<div class="plan-states">
						{#if plan.recommended}<span class="plan-state selected">Selected</span>{/if}
						{#if !plan.feasible}<span class="plan-state limited">Unavailable</span>{/if}
						{#if plan.dominated}<span class="plan-state dominated-state">Dominated</span>{/if}
					</div>
				</header>

				{#if !plan.feasible && plan.infeasible_reason}
					<p class="constraint"><strong>Limit:</strong> {plan.infeasible_reason}</p>
				{/if}
				{#if plan.dominated && plan.dominated_by}
					<p class="dominance-note">Dominated by {plan.dominated_by}; it has no better modeled tradeoff under the same inputs.</p>
				{/if}

				<div class="plan-metrics">
					{#each displayedMetrics as metric (metric.label)}
						<div>
							<span>{metric.label}</span>
							<strong class="numeric">{metric.read(plan)}</strong>
						</div>
					{/each}
				</div>
			</article>
		{/each}
	</div>
{/if}

<style>
	.plans-empty,
	.recommendation-line,
	.plan-list {
		border: 1px solid var(--rule);
	}

	.plans-empty {
		display: grid;
		gap: 0.35rem;
		padding: 1rem;
		background: var(--paper-soft);
		color: var(--ink);
	}

	.plans-empty span,
	.recommendation-line > span,
	.plan-title p,
	.constraint,
	.dominance-note {
		color: var(--ink-soft);
		font-size: 0.75rem;
		line-height: 1.42;
	}

	.recommendation-line {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr);
		gap: 1rem;
		margin-bottom: 0.75rem;
		padding: 0.85rem 1rem;
		background: var(--paper-deep);
	}

	.recommendation-line div {
		display: grid;
		gap: 0.2rem;
	}

	.recommendation-line p,
	.plan-metrics span,
	.plan-index,
	.plan-state {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.recommendation-line strong,
	.plan-index {
		color: var(--cobalt);
	}

	.recommendation-line strong {
		font-size: 1.05rem;
		letter-spacing: -0.025em;
	}

	.plan-list {
		display: grid;
		gap: 1px;
		background: var(--rule);
	}

	.plan-row {
		display: grid;
		gap: 0.7rem;
		padding: 0.9rem 1rem;
		background: var(--paper);
	}

	.plan-row.recommended {
		background: var(--paper-soft);
		box-shadow: inset 3px 0 var(--cobalt);
	}

	.plan-row.dominated {
		opacity: 0.74;
	}

	.plan-row.infeasible {
		background: var(--negative-soft);
	}

	.plan-row header {
		display: grid;
		grid-template-columns: 2rem minmax(0, 1fr) auto;
		gap: 0.6rem;
		align-items: start;
	}

	.plan-index {
		padding-top: 0.18rem;
	}

	.plan-title {
		display: grid;
		gap: 0.3rem;
	}

	.plan-row h3 {
		font-size: 0.95rem;
		letter-spacing: -0.025em;
		line-height: 1.1;
	}

	.plan-title p,
	.constraint,
	.dominance-note {
		margin: 0;
	}

	.plan-states {
		display: flex;
		flex-wrap: wrap;
		justify-content: end;
		gap: 0.3rem;
	}

	.plan-state {
		padding: 0.25rem 0.35rem;
		background: var(--paper-deep);
	}

	.plan-state.selected {
		background: var(--cobalt);
		color: var(--paper);
	}

	.plan-state.limited {
		background: var(--negative);
		color: var(--paper);
	}

	.plan-state.dominated-state {
		background: var(--warning);
		color: var(--paper);
	}

	.constraint {
		padding: 0.5rem 0.6rem;
		background: rgb(255 255 255 / 48%);
		border-left: 2px solid var(--negative);
	}

	.constraint strong {
		color: var(--negative);
	}

	.dominance-note {
		padding-left: 0.6rem;
		border-left: 2px solid var(--warning);
	}

	.plan-metrics {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(6.7rem, 1fr));
		gap: 1px;
		background: var(--rule);
		border: 1px solid var(--rule);
	}

	.plan-metrics div {
		display: grid;
		align-content: start;
		gap: 0.22rem;
		min-width: 0;
		padding: 0.45rem 0.5rem;
		background: var(--paper);
	}

	.plan-metrics strong {
		overflow: hidden;
		color: var(--ink);
		font-size: 0.77rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	@media (max-width: 48rem) {
		.recommendation-line {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 32rem) {
		.plan-row header {
			grid-template-columns: 1.7rem minmax(0, 1fr);
		}

		.plan-states {
			grid-column: 1 / -1;
			justify-content: start;
		}
	}
</style>
