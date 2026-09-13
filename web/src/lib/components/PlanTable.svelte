<script lang="ts">
	import { formatCurrency, formatPercent, formatSignedCurrency } from '$lib/format';
	import type { Plan, Recommendation } from '$lib/types';

	interface Props {
		plans: Plan[];
		recommendation: Recommendation | null;
	}

	let { plans, recommendation }: Props = $props();

	interface Metric {
		label: string;
		read: (plan: Plan) => string;
	}

	const METRICS: Metric[] = [
		{ label: 'Shortfall', read: (plan) => formatPercent(plan.cash_shortfall_probability) },
		{ label: 'Avg. deficit', read: (plan) => formatCurrency(plan.avg_cash_deficit_when_short) },
		{ label: 'New debt', read: (plan) => formatCurrency(plan.new_debt) },
		{ label: 'Interest', read: (plan) => formatCurrency(plan.interest_exposure) },
		{ label: 'Sold · gross', read: (plan) => formatCurrency(plan.investment_sold) },
		{ label: 'Spendable proceeds', read: (plan) => plan.withdrawal_net_cash === undefined ? 'Unavailable' : formatCurrency(plan.withdrawal_net_cash) },
		{ label: 'Tax reserve', read: (plan) => plan.withdrawal_tax_reserve === undefined ? 'Unavailable' : formatCurrency(plan.withdrawal_tax_reserve) },
		{ label: 'Sale gain/loss', read: (plan) => formatSignedCurrency(plan.realized_gain_loss) },
		{ label: 'Deferred', read: (plan) => formatCurrency(plan.deferred_spending) }
	];
</script>

{#if plans.length === 0}
	<div class="plans-empty">
		<p>No funding paths yet.</p>
		<span>Add a future cost in Events when you want to compare ways to close a reserve gap.</span>
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
			<article class:recommended={plan.recommended} class:dominated={plan.dominated} class="plan-row" role="listitem">
				<header>
					<span class="plan-index">0{index + 1}</span>
					<div>
						<h3>{plan.label}</h3>
						<p>{plan.explanation}</p>
					</div>
					{#if plan.recommended}<span class="plan-state">Selected</span>{/if}
				</header>
				<div class="plan-metrics">
					{#each METRICS as metric (metric.label)}
						<div>
							<span>{metric.label}</span>
							<strong class="numeric">{metric.read(plan)}</strong>
						</div>
					{/each}
				</div>
			</article>
		{/each}
	</div>
	<p class="sale-assumptions">Named sale plans use taxable accounts at today’s prices. Spendable proceeds exclude the assumed lot-specific tax reserve and arrive after settlement and transfer. Sale gain/loss compares proceeds with purchase cost; losses create no cash rebate. The optimizer above also considers traditional and Roth accounts.</p>
{/if}

<style>
	.sale-assumptions {
		margin-top: 0.75rem;
		color: var(--ink-muted);
		font-size: 0.75rem;
		line-height: 1.5;
	}

	.plans-empty,
	.recommendation-line,
	.plan-list {
		border: 1px solid #29292d;
	}

	.plans-empty {
		display: grid;
		gap: 0.35rem;
		padding: 1rem;
		background: #0b0b0c;
		color: #c8c8cc;
	}

	.plans-empty span {
		color: #85858a;
		font-size: 0.75rem;
	}

	.recommendation-line {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr);
		gap: 1rem;
		margin-bottom: 0.75rem;
		padding: 0.85rem 1rem;
		background: #101011;
	}

	.recommendation-line div {
		display: grid;
		gap: 0.2rem;
	}

	.recommendation-line p,
	.plan-metrics span,
	.plan-index,
	.plan-state {
		color: #8e8e94;
		font-family: var(--font-mono);
		font-size: 0.62rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.recommendation-line strong {
		color: #42d3ba;
		font-size: 1.05rem;
		letter-spacing: -0.025em;
	}

	.recommendation-line > span {
		align-self: center;
		color: #babac0;
		font-size: 0.78rem;
		line-height: 1.4;
	}

	.plan-list {
		display: grid;
		gap: 1px;
		background: #29292d;
	}

	.plan-row {
		display: grid;
		grid-template-columns: minmax(12rem, 0.75fr) minmax(0, 1.25fr);
		gap: 1rem;
		padding: 0.9rem 1rem;
		background: #0d0d0e;
	}

	.plan-row.recommended {
		background: #101617;
		box-shadow: inset 3px 0 #42d3ba;
	}

	.plan-row.dominated {
		opacity: 0.65;
	}

	.plan-row header {
		display: grid;
		grid-template-columns: 2rem minmax(0, 1fr) auto;
		gap: 0.6rem;
		align-items: start;
	}

	.plan-index {
		padding-top: 0.22rem;
		color: #42d3ba;
	}

	.plan-row h3 {
		margin: 0;
		color: #eeeeef;
		font-size: 0.92rem;
		letter-spacing: -0.02em;
		line-height: 1.1;
	}

	.plan-row header p {
		margin: 0.3rem 0 0;
		color: #85858a;
		font-size: 0.68rem;
		line-height: 1.35;
	}

	.plan-state {
		padding: 0.25rem 0.35rem;
		background: #1a5650;
		color: #b9fff2;
	}

	.plan-metrics {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 0.5rem;
	}

	.plan-metrics div {
		display: grid;
		align-content: start;
		gap: 0.22rem;
		min-width: 0;
	}

	.plan-metrics strong {
		overflow: hidden;
		color: #e2e2e5;
		font-size: 0.76rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	@media (max-width: 64rem) {
		.plan-row {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 42rem) {
		.recommendation-line {
			grid-template-columns: 1fr;
		}

		.plan-metrics {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	/* Cobalt ledger skin */
	.plans-empty, .recommendation-line, .plan-list { border-color: var(--rule); }
	.plans-empty { background: var(--paper-soft); color: var(--ink); }
	.plans-empty span, .recommendation-line > span, .plan-row header p { color: var(--ink-muted); }
	.recommendation-line { background: var(--paper-deep); }
	.recommendation-line p, .plan-metrics span, .plan-index, .plan-state { color: var(--ink-muted); }
	.recommendation-line strong, .plan-index { color: var(--cobalt); }
	.plan-list { background: var(--rule); }
	.plan-row { background: var(--paper); }
	.plan-row.recommended { background: var(--paper-soft); box-shadow: inset 3px 0 var(--cobalt); }
	.plan-row h3, .plan-metrics strong { color: var(--ink); }
	.plan-state { background: var(--cobalt); color: var(--on-accent); }
</style>
