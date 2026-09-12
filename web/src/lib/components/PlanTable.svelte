<script lang="ts">
	// Plans-screen comparison table (spec section 60): one row per
	// objective, one column per plan, dominated plans visibly marked, the
	// recommended plan highlighted, and the recommendation's explanation
	// rendered as prose beneath. Every cell is a value read straight off
	// the `Plan`/`Recommendation` props — nothing here is computed.
	import { formatCurrency, formatPercent, formatSignedCurrency } from '$lib/format';
	import type { Plan, Recommendation } from '$lib/types';

	interface Props {
		plans: Plan[];
		recommendation: Recommendation | null;
	}

	let { plans, recommendation }: Props = $props();

	interface ObjectiveRow {
		label: string;
		read: (plan: Plan) => string;
	}

	const OBJECTIVE_ROWS: ObjectiveRow[] = [
		{ label: 'Cash-shortfall probability', read: (p) => formatPercent(p.cash_shortfall_probability) },
		{ label: 'Average deficit when short', read: (p) => formatCurrency(p.avg_cash_deficit_when_short) },
		{ label: 'New debt', read: (p) => formatCurrency(p.new_debt) },
		{ label: 'Interest exposure', read: (p) => formatCurrency(p.interest_exposure) },
		{ label: 'Investment sold', read: (p) => formatCurrency(p.investment_sold) },
		{ label: 'Realized gain/loss', read: (p) => formatSignedCurrency(p.realized_gain_loss) },
		{ label: 'Deferred spending', read: (p) => formatCurrency(p.deferred_spending) }
	];

	function dominatedByLabel(plan: Plan): string | null {
		if (!plan.dominated_by) return null;
		return plans.find((p) => p.id === plan.dominated_by)?.label ?? plan.dominated_by;
	}
</script>

{#if plans.length === 0}
	<p class="empty-state">Plans not yet computed for this scenario.</p>
{:else}
	<div class="plan-table-wrap">
		<table class="plan-table">
			<thead>
				<tr>
					<th scope="col" class="row-header-col">Objective</th>
					{#each plans as plan (plan.id)}
						<th
							scope="col"
							class="plan-col"
							class:plan-col--recommended={plan.recommended}
							class:plan-col--dominated={plan.dominated}
						>
							<span class="plan-name">{plan.label}</span>
							{#if plan.recommended}
								<span class="badge badge--recommended">Recommended</span>
							{/if}
							{#if plan.dominated}
								<span class="badge badge--dominated">
									Dominated{dominatedByLabel(plan) ? ` by ${dominatedByLabel(plan)}` : ''}
								</span>
							{/if}
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each OBJECTIVE_ROWS as row (row.label)}
					<tr>
						<th scope="row" class="row-header-col">{row.label}</th>
						{#each plans as plan (plan.id)}
							<td
								class="plan-col"
								class:plan-col--recommended={plan.recommended}
								class:plan-col--dominated={plan.dominated}
							>
								{row.read(plan)}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<div class="recommendation">
		{#if recommendation}
			{@const recommendedPlan = plans.find((p) => p.id === recommendation.plan_id)}
			<p class="recommendation-title">
				Recommended under your funding policy: {recommendedPlan?.label ?? recommendation.plan_id}
			</p>
			<p class="recommendation-explanation">{recommendation.explanation}</p>
		{:else}
			<p class="recommendation-explanation muted">No recommendation available for this scenario.</p>
		{/if}
	</div>
{/if}

<style>
	.empty-state {
		padding: var(--space-6);
		color: var(--color-text-faint);
		font-size: var(--font-size-md);
	}

	.plan-table-wrap {
		overflow-x: auto;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	.plan-table {
		width: 100%;
		border-collapse: collapse;
		font-size: var(--font-size-sm);
	}

	.plan-table th,
	.plan-table td {
		padding: var(--space-3) var(--space-4);
		text-align: right;
		border-bottom: 1px solid var(--color-border);
		white-space: nowrap;
	}

	.plan-table thead th {
		border-bottom: 1px solid var(--color-border-strong);
		vertical-align: bottom;
	}

	.plan-table tbody tr:last-child th,
	.plan-table tbody tr:last-child td {
		border-bottom: none;
	}

	.row-header-col {
		text-align: left;
		color: var(--color-text-dim);
		font-weight: 500;
		background: var(--color-bg-card);
		position: sticky;
		left: 0;
	}

	.plan-col {
		color: var(--color-text);
		font-variant-numeric: tabular-nums;
	}

	.plan-name {
		display: block;
		font-size: var(--font-size-md);
		font-weight: 700;
	}

	th.plan-col--recommended {
		background: color-mix(in srgb, var(--color-accent) 12%, transparent);
	}

	td.plan-col--recommended {
		background: color-mix(in srgb, var(--color-accent) 8%, transparent);
	}

	.plan-col--dominated .plan-name {
		color: var(--color-text-faint);
	}

	td.plan-col--dominated {
		color: var(--color-text-faint);
	}

	.badge {
		display: inline-block;
		margin-top: var(--space-1);
		padding: 2px var(--space-2);
		border-radius: var(--radius-sm);
		font-size: var(--font-size-xs);
		font-weight: 600;
		letter-spacing: 0.03em;
		white-space: normal;
	}

	.badge--recommended {
		background: var(--color-accent);
		color: var(--color-bg);
	}

	.badge--dominated {
		background: var(--color-bg-raised);
		border: 1px solid var(--color-border-strong);
		color: var(--color-text-faint);
	}

	.recommendation {
		margin-top: var(--space-5);
		padding: var(--space-5) var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	.recommendation-title {
		font-size: var(--font-size-sm);
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		color: var(--color-accent-strong);
		margin-bottom: var(--space-2);
	}

	.recommendation-explanation {
		font-size: var(--font-size-md);
		color: var(--color-text-dim);
		max-width: 62ch;
	}

	.recommendation-explanation.muted {
		color: var(--color-text-faint);
	}
</style>
