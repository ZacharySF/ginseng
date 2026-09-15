<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { resolve } from '$app/paths';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { AnalysisStore } from '$lib/analysis.svelte';
	import type { FrontierReport } from '$lib/frontier-types';
	import PortfolioFrontier from '$lib/components/PortfolioFrontier.svelte';
	const analysis = new AnalysisStore<FrontierReport>('frontier');
	const revision = $derived(JSON.stringify(scenarioStore.request));
	$effect(() => { revision; analysis.reset(); });
	onMount(() => { scenarioStore.ensureLoaded(); });
	onDestroy(() => analysis.reset());
	const supported = $derived(!scenarioStore.request.drought_view && scenarioStore.request.horizon_days <= 60);
</script>
<svelte:head><title>Ginseng — Liquidity-aware portfolio research</title><meta name="description" content="Explore portfolio tradeoffs in expected return, volatility and tail loss at the first cash-buffer breach, with an independent numerical holdout."/></svelte:head>

<div class="research-page">
	<header>
		<div><p class="eyebrow">Ginseng research / synthetic market histories</p><h1>When the portfolio<br/>has to be the backstop.</h1></div>
		<p class="lead">Explore the tradeoff that a two-axis frontier leaves out: how investments behave at the moment bank cash first falls below its buffer.</p>
	</header>
	<div class="research-question"><span>01 / EXPECTED RETURN ↑</span><span>02 / VOLATILITY ↓</span><span>03 / CASH-PRESSURE TAIL LOSS ↓</span></div>
	<section class="launch" aria-label="Research experiment controls">
		<div><h2>Liquidity-aware Pareto lab</h2><p>{scenarioStore.request.horizon_days}-day horizon · {scenarioStore.request.obligations.length} active commitments · 2,048 futures per sample. ETF-labeled returns are generated synthetic data, not actual market observations. All allocations are hypothetical.</p></div>
		<div class="actions"><button class="secondary" disabled={scenarioStore.loadState === 'loading' || analysis.loading} onclick={() => scenarioStore.loadRepairExample()}>Load repair case</button><button class="primary" disabled={scenarioStore.loadState !== 'ready' || !supported || analysis.loading} onclick={() => analysis.run(scenarioStore.request)}>{analysis.loading ? 'Solving allocation tradeoffs…' : 'Build portfolio frontier'}</button></div>
		<p class="start">For a useful first experiment, load the two-stage repair, then build the frontier. <a href={resolve('/demo/future')}>Edit its cash events ↗</a></p>
	</section>
	{#if !supported}<p class="notice">Disable stress weighting and choose a horizon of 60 days or less to use this research model.</p>{/if}
	{#if scenarioStore.loadState === 'error' || scenarioStore.loadState === 'unreachable'}<p class="notice" role="alert">{scenarioStore.errorMessage} <button onclick={() => scenarioStore.refresh()}>Retry model</button></p>{/if}
	{#if analysis.loading}<div class="progress" role="status"><span class="pulse"></span><div><strong>Searching for three-objective tradeoffs</strong><p>Solving long-only allocations, identifying candidate dominance, then checking frozen weights on fresh simulations.</p></div></div>{/if}
	{#if analysis.error}<p class="notice" role="alert">{analysis.error}</p>{/if}
	{#if analysis.data}
		{#if analysis.data.status === 'ready'}{#key revision}<PortfolioFrontier report={analysis.data}/>{/key}
		{:else}<div class="notice" role="status"><h2>This experiment is unavailable</h2><p>{analysis.data.message ?? analysis.data.reason ?? 'This scenario does not support a conditional tail estimate.'}</p><p>For a supported example, load the repair case and try again.</p></div>{/if}
	{:else if !analysis.loading}
		<div class="empty"><div><p class="eyebrow">Why a third dimension belongs here</p><h2>Good average behavior.<br/>Different behavior under pressure.</h2></div><p>Each dot will be an allocation across the two synthetic investment assets and a zero-yield portfolio cash sleeve. Inspect its weights, compare three objectives, and see how its position changes on an independent sample.</p></div>
	{/if}
</div>
<style>
	.research-page { padding: clamp(1rem, 3vw, 2.5rem); background: var(--paper); color: var(--ink); min-height: calc(100dvh - 3rem); }
	header { display: flex; align-items: end; justify-content: space-between; gap: 2rem; padding-bottom: 1.8rem; }.eyebrow { font: .65rem var(--font-mono); letter-spacing: .07em; text-transform: uppercase; color: var(--ink-soft); margin-bottom: .8rem; }h1 { font-size: clamp(2.4rem, 5vw, 4.7rem); letter-spacing: -.04em; line-height: .98; }.lead { max-width: 38ch; font-size: 1.15rem; color: var(--ink-soft); line-height: 1.4; }
	.research-question { display: flex; flex-wrap: wrap; gap: 1.5rem; padding: 1rem 0; border-block: 1px solid var(--rule); color: var(--cobalt); font: .65rem var(--font-mono); }
	.launch { padding: 1.3rem; background: var(--paper-soft); border: 1px solid var(--rule); margin: 1.5rem 0; display: grid; grid-template-columns: 1fr auto; gap: 1rem; }.launch h2 { font-size: 1.3rem; }.launch p { max-width: 75ch; color: var(--ink-soft); font-size: .9rem; line-height: 1.4; margin-top: .4rem; }.actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }.start { grid-column: 1/-1; }a { color: var(--link); }
	button { padding: .6rem .9rem; min-height: 2.8rem; font: inherit; border: 1px solid var(--control-border); cursor: pointer; }.primary { background: var(--cobalt); border-color: var(--cobalt); color: var(--on-accent); }.secondary { background: var(--paper); color: var(--ink); }button:disabled { cursor: wait; opacity: .7; }
	.notice { padding: 1.2rem; border: 1px solid var(--rule); background: var(--paper-soft); margin: 1rem 0; }.notice p { margin-top: .6rem; color: var(--ink-soft); }.notice h2 { font-size: 1.25rem; }.empty { display: grid; grid-template-columns: 1fr 1fr; gap: 3rem; padding: clamp(1.3rem,4vw,3rem); border: 1px dashed var(--rule-strong); }.empty h2 { font-size: 2rem; line-height: 1.1; letter-spacing: -.03em; }.empty > p { color: var(--ink-soft); font-size: 1.05rem; line-height: 1.5; align-self: center; }
	.progress { display: flex; align-items: center; gap: 1rem; padding: 2rem; border: 1px solid var(--rule); }.progress p { color: var(--ink-soft); margin-top: .3rem; }.pulse { width: .75rem; height: .75rem; background: var(--cobalt); border-radius: 50%; animation: breathe 1.2s ease-in-out infinite; }@keyframes breathe { 50% { opacity: .25; } }@media(prefers-reduced-motion:reduce) { .pulse { animation: none; } }
	@media(max-width:65rem) { .launch { grid-template-columns: 1fr; }header { align-items: start; flex-direction: column; }.lead { max-width: 60ch; } }
	@media(max-width:42rem) { .empty { grid-template-columns: 1fr; gap: 1rem; }.research-question { gap: .75rem; }.actions { flex-direction: column; align-items: stretch; }.actions button { width: 100%; } }
</style>
