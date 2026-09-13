<script lang="ts">
	import { resolve } from '$app/paths';
	import { formatCurrency, formatPercent } from '$lib/format';
	import CashPathChart from '$lib/components/CashPathChart.svelte';
	import { humanDate } from '$lib/forecast-presentation';
	import type { ScenarioResponse } from '$lib/types';

	type ModelMode = 'scheduled' | 'assumptions' | 'history' | 'demo';
	type WorkbenchHref =
		| '/future'
		| '/liquidity'
		| '/plans'
		| '/data'
		| '/demo/future'
		| '/demo/liquidity'
		| '/demo/plans';

	interface ChartEvent {
		id: string;
		label: string;
		amount: number;
		day: number;
		kind: 'income' | 'outflow';
		date?: string;
	}

	interface Props {
		response: ScenarioResponse;
		events?: ChartEvent[];
		source: 'personal' | 'demo';
		horizonDays: number;
		modelMode: ModelMode;
		onHorizonChange?: ((horizon: 14 | 30 | 60) => void | Promise<void>) | undefined;
		eventsHref: WorkbenchHref;
		reserveHref: WorkbenchHref;
		fundingHref: WorkbenchHref;
		dataHref?: WorkbenchHref;
		paths?: number | null;
		isPreview?: boolean;
		updating?: boolean;
		comparison?: ScenarioResponse | null;
		comparisonLabel?: string;
	}

	let {
		response,
		events = [],
		source,
		horizonDays,
		modelMode,
		onHorizonChange = undefined,
		eventsHref,
		reserveHref,
		fundingHref,
		dataHref = '/data',
		paths = null,
		isPreview = false,
		updating = false,
		comparison = null,
		comparisonLabel = 'Saved inputs',
	}: Props = $props();

	const horizonOptions: Array<14 | 30 | 60> = [14, 30, 60];
	const deterministic = $derived(modelMode === 'scheduled');
	const sourceName = $derived(source === 'personal' ? 'Personal cash' : 'Synthetic cash');
	const sourceDescriptor = $derived(
		source === 'personal'
			? deterministic
				? 'Known income and bills'
				: `${modelMode} forecast`
			: 'Synthetic example'
	);
	const scheduledEvents = $derived([...events].sort((left, right) => left.day - right.day || left.label.localeCompare(right.label)));
</script>

<div class:cash-workbench--preview={isPreview} class="cash-workbench">
	<header class="workbench-toolbar">
		<div class="workbench-identity">
			<p>{sourceName}</p>
			<span>{sourceDescriptor}</span>
		</div>
		<div class="toolbar-divider" aria-hidden="true"></div>
		<div class="horizon-switcher" role="group" aria-label="Forecast horizon">
			{#each horizonOptions as option (option)}
				<button
					type="button"
					class:active={horizonDays === option}
					aria-pressed={horizonDays === option}
					disabled={!onHorizonChange || updating}
					onclick={() => void onHorizonChange?.(option)}
				>
					{option}D
				</button>
			{/each}
		</div>
		<p class:model-state--updating={updating} class="model-state">
			<i aria-hidden="true"></i>
			{#if updating}
				Recomputing forecast…
			{:else if deterministic}
				Deterministic schedule
			{:else if paths}
				{paths.toLocaleString()} matched paths
			{:else}
				Forecast model
			{/if}
		</p>
		<div class="toolbar-actions">
			<a href={resolve(eventsHref)}>Events</a>
			<a href={resolve(reserveHref)}>Reserve</a>
		</div>
	</header>

	<div class="workbench-grid">
		<main class="chart-workspace">
			<header class="chart-header">
				<div class="decision-lead">
					<p class="chart-instrument">{deterministic ? 'Known schedule reserve' : 'Required liquid reserve'} · {horizonDays}-day view</p>
					<p class:decision-value--risk={response.funding_gap > 0} class="decision-value numeric">{formatCurrency(response.required_liquidity_reserve)}</p>
					<p class="decision-context">
						{deterministic
							? `to cover scheduled flows and keep ${formatCurrency(response.operating_buffer)} available`
							: `to keep the ${formatCurrency(response.operating_buffer)} operating buffer`}
						{#if !deterministic}<span>in {formatPercent(response.coverage_target)} of modeled paths</span>{/if}
					</p>
					{#if !deterministic && response.estimate_band}
						<p class="estimate-readout">Model estimate range <strong class="numeric">{formatCurrency(response.estimate_band.low)}–{formatCurrency(response.estimate_band.high)}</strong></p>
					{/if}
					{#if response.optimal_plan && response.stress?.status !== 'unsupported'}
						<p class="estimate-readout">Optimized funding cost · average <strong>{formatCurrency(response.optimal_plan.expected_cost)}</strong> / worst-tail average <strong>{formatCurrency(response.optimal_plan.cvar_cost)}</strong> · <a href={resolve('/plans')}>View funding mix</a></p>
					{/if}
					{#if response.stress?.status === 'active'}<p class="estimate-readout">Stress assumption active — not an estimated probability. <a href={resolve('/liquidity')}>Inspect weights</a></p>{/if}
					{#if response.stress?.status === 'unsupported'}<p class="estimate-readout">Stress not applied: this view has no supporting futures. These figures use baseline weights.</p>{/if}
					{#if response.excluded_obligations?.length}<p class="estimate-readout">{response.excluded_obligations.length} scheduled events fall after this chart window. Their dates have been preserved.</p>{/if}
				</div>
				<div class="chart-side">
					<p class="source-note">{source === 'personal' ? 'Based on your saved inputs' : 'Separate from personal data'}</p>
					{#if isPreview}<p class="preview-note">What-if preview</p>{/if}
				</div>
			</header>

			<CashPathChart
				cashPaths={response.cash_paths}
				operatingBuffer={response.operating_buffer}
				events={scheduledEvents}
				asOf={response.as_of}
				deterministic={deterministic}
				comparisonPaths={comparison?.cash_paths ?? null}
				{comparisonLabel}
			/>
		</main>

		<aside class="workbench-inspector" aria-label="Forecast inspector">
			<section class="inspector-block">
				<div class="inspector-heading">
					<p class="inspector-label">Scheduled cash events</p>
					<a href={resolve(eventsHref)}>Edit</a>
				</div>
				{#if scheduledEvents.length > 0}
					<ul class="event-watchlist">
						{#each scheduledEvents.slice(0, 7) as event (event.id)}
							<li>
								<span>{humanDate(event.date ?? null) ?? `D${String(event.day).padStart(2, '0')}`}</span>
								<p>{event.label}</p>
								<strong class="numeric" class:income={event.kind === 'income'}>{event.kind === 'income' ? '+' : '−'}{formatCurrency(event.amount)}</strong>
							</li>
						{/each}
					</ul>
					{#if scheduledEvents.length > 7}<p class="more-events">+{scheduledEvents.length - 7} more within this view</p>{/if}
				{:else}
					<p class="empty-inspector">No scheduled events fall inside this forecast window.</p>
				{/if}
			</section>

			<section class="inspector-block policy-readout">
				<div class="inspector-heading">
					<p class="inspector-label">Active guardrails</p>
					<a href={resolve(reserveHref)}>Adjust</a>
				</div>
				<div><span>Operating buffer</span><strong class="numeric">{formatCurrency(response.operating_buffer)}</strong></div>
				<div><span>Coverage target</span><strong>{deterministic ? 'Stored policy' : formatPercent(response.coverage_target)}</strong></div>
				<div><span>{deterministic ? 'Known schedule reserve' : 'Required reserve'}</span><strong class="numeric">{formatCurrency(response.required_liquidity_reserve)}</strong></div>
			</section>

			<section class="inspector-block capital-readout">
				<p class="inspector-label">Capital position</p>
				<div><span>Available cash</span><strong class="numeric">{formatCurrency(response.immediate_funding)}</strong></div>
				{#if response.immediate_cash_coverage_ratio != null}<div><span>Cash / required reserve</span><strong>{formatPercent(response.immediate_cash_coverage_ratio)}</strong></div>{/if}
				<div><span>Marketable capital</span><strong class="numeric">{formatCurrency(response.marketable_backup_capital)}</strong></div>
				<div><span>Restricted capital</span><strong class="numeric">{formatCurrency(response.restricted_capital)}</strong></div>
				{#if response.account_liquidity}<div><span>Net investment access</span><strong class="numeric">{formatCurrency(response.account_liquidity.total_net_accessible)}</strong></div>{/if}
				<p>Only available cash funds the reserve. Other capital requires a funding decision. {#if response.account_liquidity}<a href={resolve('/plans')}>See account assumptions</a>.{/if}</p>
			</section>

			<section class:funding-readout--risk={response.funding_gap > 0} class="inspector-block funding-readout">
				<p class="inspector-label">Gap to reserve</p>
				<p class="numeric">{formatCurrency(response.funding_gap)}</p>
				<a href={resolve(fundingHref)}>{response.funding_gap > 0 ? 'Review funding routes' : 'Review funding position'}</a>
			</section>

			{#if source === 'personal'}
				<a class="data-link" href={resolve(dataHref)}>Review source data</a>
			{/if}

			<details class="source-detail">
				<summary>Source and model</summary>
				<p>
					{source === 'personal' ? 'Saved personal inputs' : 'Synthetic example inputs'} ·
					{deterministic ? 'known schedule' : `${modelMode} model`} ·
					as of {response.as_of}
				</p>
			</details>
		</aside>
	</div>
</div>

<style>
	.cash-workbench {
		min-height: calc(100dvh - 3.25rem);
		background: var(--paper);
		color: var(--ink);
		font-size: 0.8125rem;
	}

	.cash-workbench--preview {
		box-shadow: inset 3px 0 var(--cobalt);
	}

	.workbench-toolbar {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		min-height: 3.35rem;
		padding: 0.3rem 0.9rem;
		border-bottom: 1px solid var(--rule);
	}

	.workbench-identity {
		display: flex;
		align-items: baseline;
		gap: 0.55rem;
		min-width: 0;
	}

	.workbench-identity p {
		font-size: 1rem;
		font-weight: 800;
		letter-spacing: -0.035em;
		white-space: nowrap;
	}

	.workbench-identity span,
	.model-state,
	.chart-instrument,
	.estimate-readout,
	.source-note,
	.preview-note {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.63rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
	}

	.toolbar-divider {
		width: 1px;
		height: 1.45rem;
		background: var(--rule);
	}

	.horizon-switcher {
		display: flex;
		border: 1px solid var(--control-border);
	}

	.horizon-switcher button {
		min-width: 2.75rem;
		min-height: 2.75rem;
		padding: 0 0.55rem;
		background: var(--paper);
		border: 0;
		border-right: 1px solid var(--rule);
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.66rem;
		font-weight: 700;
		cursor: pointer;
	}

	.horizon-switcher button:last-child {
		border-right: 0;
	}

	.horizon-switcher button:hover:not(:disabled) {
		background: var(--paper-deep);
		color: var(--ink);
	}

	.horizon-switcher button.active {
		background: var(--cobalt);
		color: var(--paper);
	}

	.horizon-switcher button:disabled {
		cursor: default;
	}

	.model-state {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin: 0;
	}

	.model-state i {
		width: 0.42rem;
		height: 0.42rem;
		background: var(--cobalt-bright);
		border-radius: 50%;
	}

	.toolbar-actions {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin-left: auto;
	}

	.toolbar-actions a,
	.inspector-heading a,
	.funding-readout a,
	.data-link {
		color: var(--cobalt-deep);
		font-weight: 750;
		text-decoration: none;
	}

	.toolbar-actions a {
		display: inline-flex;
		align-items: center;
		min-height: 2.75rem;
		padding: 0 0.65rem;
		border: 1px solid var(--control-border);
		font-family: var(--font-mono);
		font-size: 0.65rem;
		letter-spacing: 0.03em;
		text-transform: uppercase;
	}

	.toolbar-actions a:hover,
	.inspector-heading a:hover,
	.funding-readout a:hover,
	.data-link:hover {
		background: var(--cobalt);
		border-color: var(--cobalt);
		color: var(--paper);
	}

	.workbench-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 19rem;
		min-height: calc(100dvh - 6.6rem);
	}

	.chart-workspace {
		min-width: 0;
		padding: 1.35rem 1.15rem 1rem;
		border-right: 1px solid var(--rule);
	}

	.chart-header {
		display: flex;
		align-items: start;
		justify-content: space-between;
		gap: 1.5rem;
		padding: 0 0.25rem 0.85rem;
	}

	.decision-lead {
		display: grid;
		gap: 0.3rem;
		min-width: 0;
	}

	.decision-value {
		margin: 0;
		color: var(--cobalt);
		font-size: clamp(2.35rem, 4.5vw, 3.9rem);
		font-weight: 800;
		letter-spacing: -0.08em;
		line-height: 0.9;
	}

	.decision-value--risk {
		color: var(--negative);
	}

	.decision-context {
		max-width: 52ch;
		color: var(--ink-soft);
		font-size: 0.8rem;
		line-height: 1.42;
	}

	.decision-context span {
		display: block;
		color: var(--ink-soft);
	}

	.estimate-readout {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.2rem;
	}

	.estimate-readout strong {
		color: var(--warning);
		font-size: 0.68rem;
		letter-spacing: 0;
	}

	.chart-side {
		display: grid;
		justify-items: end;
		gap: 0.3rem;
		min-width: 10rem;
		padding-top: 0.12rem;
	}

	.source-note {
		max-width: 21ch;
		margin: 0;
		line-height: 1.35;
		text-align: right;
	}

	.preview-note {
		padding: 0.25rem 0.35rem;
		background: var(--cobalt);
		color: var(--paper);
	}

	.workbench-inspector {
		display: grid;
		align-content: start;
		background: var(--paper-soft);
	}

	.inspector-block {
		display: grid;
		gap: 0.68rem;
		padding: 1rem;
		border-bottom: 1px solid var(--rule);
	}

	.inspector-label {
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.63rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.inspector-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.inspector-heading a {
		min-width: 2.75rem;
		min-height: 2.75rem;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0 0.35rem;
		font-size: 0.68rem;
	}

	.event-watchlist {
		display: grid;
		gap: 1px;
		padding: 0;
		margin: 0;
		background: var(--rule);
		list-style: none;
	}

	.event-watchlist li {
		display: grid;
		grid-template-columns: 3.8rem minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.45rem;
		padding: 0.5rem;
		background: var(--paper);
	}

	.event-watchlist li > span {
		color: var(--negative);
		font-family: var(--font-mono);
		font-size: 0.57rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}

	.event-watchlist p {
		overflow: hidden;
		color: var(--ink);
		font-size: 0.71rem;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.event-watchlist strong {
		color: var(--negative);
		font-size: 0.68rem;
	}

	.event-watchlist strong.income {
		color: var(--positive);
	}

	.more-events,
	.empty-inspector {
		color: var(--ink-soft);
		font-size: 0.71rem;
		line-height: 1.45;
	}

	.policy-readout > div,
	.capital-readout > div {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.75rem;
		color: var(--ink-soft);
		font-size: 0.72rem;
	}

	.policy-readout strong,
	.capital-readout strong {
		color: var(--ink);
		font-size: 0.79rem;
	}

	.capital-readout {
		background: var(--paper-deep);
	}

	.capital-readout > p:last-child {
		color: var(--ink-soft);
		font-size: 0.68rem;
		line-height: 1.4;
	}

	.funding-readout {
		background: var(--cobalt);
		color: var(--paper);
	}

	.funding-readout--risk {
		background: var(--negative-soft);
	}

	.funding-readout .inspector-label,
	.funding-readout > p:nth-child(2),
	.funding-readout a {
		color: var(--paper);
	}

	.funding-readout--risk .inspector-label,
	.funding-readout--risk > p:nth-child(2),
	.funding-readout--risk a {
		color: var(--negative);
	}

	.funding-readout > p:nth-child(2) {
		font-size: 1.5rem;
		font-weight: 800;
		letter-spacing: -0.055em;
	}

	.funding-readout a,
	.data-link {
		min-height: 2.75rem;
		display: inline-flex;
		align-items: center;
		padding: 0 0.4rem;
		font-size: 0.72rem;
	}

	.data-link {
		padding: 0.8rem 1rem;
		border-top: 1px solid var(--rule);
	}

	.source-detail {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--rule);
	}

	.source-detail summary {
		min-height: 2.75rem;
		display: flex;
		align-items: center;
		color: var(--cobalt-deep);
		font-family: var(--font-mono);
		font-size: 0.64rem;
		font-weight: 700;
		letter-spacing: 0.045em;
		text-transform: uppercase;
		cursor: pointer;
	}

	.source-detail p {
		margin: 0.3rem 0 0;
		color: var(--ink-soft);
		font-size: 0.7rem;
		line-height: 1.4;
	}

	@media (max-width: 68rem) {
		.workbench-grid {
			grid-template-columns: minmax(0, 1fr) 16.5rem;
		}
	}

	@media (max-width: 54rem) {
		.cash-workbench {
			min-height: 0;
		}

		.workbench-grid {
			grid-template-columns: 1fr;
			min-height: 0;
		}

		.chart-workspace {
			border-right: 0;
		}

		.workbench-inspector {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			border-top: 1px solid var(--rule);
		}

		.funding-readout,
		.data-link,
		.source-detail {
			grid-column: 1 / -1;
		}
	}

	@media (max-width: 42rem) {
		.workbench-toolbar {
			flex-wrap: wrap;
			padding: 0.55rem 0.75rem;
		}

		.workbench-identity {
			width: 100%;
		}

		.toolbar-divider,
		.model-state:not(.model-state--updating) {
			display: none;
		}

		.model-state--updating {
			display: inline-flex;
		}

		.toolbar-actions {
			margin-left: auto;
		}

		.chart-workspace {
			padding: 0.9rem 0.65rem;
		}

		.chart-header {
			display: grid;
			gap: 0.6rem;
		}

		.chart-side {
			justify-items: start;
			min-width: 0;
		}

		.source-note {
			max-width: none;
			text-align: left;
		}
	}

	@media (max-width: 29rem) {
		.workbench-inspector {
			grid-template-columns: 1fr;
		}

		.funding-readout,
		.data-link,
		.source-detail {
			grid-column: auto;
		}
	}
</style>
