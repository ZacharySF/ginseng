<script lang="ts">
	import { onMount } from 'svelte';
	import { themeStore } from '$lib/theme.svelte';
	import type { FrontierReady, FrontierPoint } from '$lib/frontier-types';
	import type * as PlotlyType from 'plotly.js';

	let { report, selectedId, view, frontierOnly, onSelect }: {
		report: FrontierReady; selectedId: string; view: 'discovery' | 'evaluation';
		frontierOnly: boolean; onSelect: (id: string) => void;
	} = $props();
	let chart: HTMLDivElement;
	let plotly = $state<typeof PlotlyType | null>(null);
	let error = $state('');
	let narrow = $state(false);
	let lastNarrow: boolean | null = null;
	const camera = { eye: { x: 1.6, y: -1.7, z: 1.25 } };
	const mobileCamera = { eye: { x: 2.5, y: -2.6, z: 1.9 } };

	onMount(() => {
		let alive = true;
		narrow = chart.clientWidth < 600;
		import('plotly.js-gl3d-dist-min').then(module => {
			if (alive) plotly = module.default;
		}).catch(() => { if (alive) error = 'The 3D renderer could not load. Use the allocation selector and table below.'; });
		const observer = new ResizeObserver(() => {
			narrow = chart.clientWidth < 600;
			if (plotly) void Promise.resolve(plotly.Plots.resize(chart)).catch(() => {});
		});
		observer.observe(chart);
		return () => { alive = false; observer.disconnect(); if (plotly) plotly.purge(chart); };
	});

	$effect(() => {
		const theme = themeStore.current;
		const p = plotly;
		const data = report;
		const mode = view;
		const selected = data.points.find(point => point.id === selectedId);
		const current = data.points.find(point => point.label.toLowerCase().includes('current'));
		const only = frontierOnly;
		if (!p || !chart) return;
		const css = getComputedStyle(document.documentElement);
		const color = (name: string) => css.getPropertyValue(name).trim();
		const paper = color('--paper'), ink = color('--ink'), rule = color('--rule');
		const trace = (points: FrontierPoint[], name: string, marker: object): PlotlyType.Data => ({
			type: 'scatter3d', mode: 'markers', name,
			x: points.map(point => point[mode].volatility),
			y: points.map(point => point[mode].mean_return),
			z: points.map(point => point[mode].pressure_cvar),
			text: points.map(point => point.label), customdata: points.map(point => point.id), marker,
			hovertemplate: '%{text}<br>Volatility %{x:.2%}<br>Expected return %{y:.2%}<br>Pressure tail loss %{z:.2%}<extra></extra>'
		} as PlotlyType.Data);
		const traces: PlotlyType.Data[] = [];
		if (!only) traces.push(trace(data.points.filter(point => !point.pareto), 'Other explored allocations', { size: 3, color: color('--ink-muted'), opacity: .3 }));
		traces.push(trace(data.points.filter(point => point.pareto), 'Discovery Pareto set', { size: 5, color: color('--cobalt'), opacity: .9 }));
		if (current) traces.push(trace([current], 'Current allocation', { size: 7, symbol: 'diamond', color: color('--negative') }));
		if (selected) {
			traces.push(trace([selected], 'Selected allocation', { size: 9, color: color('--positive'), line: { color: ink, width: 2 } }));
			if (mode === 'evaluation') traces.push({
				type: 'scatter3d', mode: 'lines+markers', name: 'Selected: discovery → check',
				x: [selected.discovery.volatility, selected.evaluation.volatility],
				y: [selected.discovery.mean_return, selected.evaluation.mean_return],
				z: [selected.discovery.pressure_cvar, selected.evaluation.pressure_cvar],
				line: { color: color('--positive'), width: 5 }, marker: { size: 4, color: color('--positive') }, hoverinfo: 'skip'
			} as PlotlyType.Data);
		}
		const axis = { color: ink, gridcolor: rule, zerolinecolor: color('--rule-strong'), showbackground: true, backgroundcolor: paper, tickformat: '.1%', nticks: 4 };
		const resized = lastNarrow !== narrow; lastNarrow = narrow;
		const targetCamera = structuredClone(narrow ? mobileCamera : camera);
		let alive = true;
		void p.react(chart, traces, {
			autosize: true, height: narrow ? 380 : 530, margin: { l: 0, r: 5, t: 0, b: 55 },
			paper_bgcolor: paper, font: { color: ink, family: 'Archivo Narrow, sans-serif', size: narrow ? 10 : 12 },
			showlegend: false, uirevision: 'frontier-' + narrow,
			scene: { camera: targetCamera, aspectmode: 'cube',
				xaxis: { ...axis, title: { text: 'Volatility ↓' } },
				yaxis: { ...axis, title: { text: 'Expected return ↑' } },
				zaxis: { ...axis, title: { text: narrow ? 'Tail loss ↓' : 'Cash-pressure tail loss ↓' } }
			}
		}, { responsive: true, displayModeBar: false, displaylogo: false, scrollZoom: false })
		.then(async graph => {
			if (!alive) return;
			graph.removeAllListeners('plotly_click');
			graph.on('plotly_click', event => {
				const id = event.points[0]?.customdata;
				if (typeof id === 'string') onSelect(id);
			});
			if (resized) await p.relayout(chart, { 'scene.camera': targetCamera } as unknown as Partial<PlotlyType.Layout>);
		}).catch(() => { if (alive) error = '3D is unavailable in this browser. All allocation values remain available below.'; });
		return () => { alive = false; };
	});
</script>

<div class="chart-frame">
	<div class="chart-toolbar">
		<span>Drag to rotate · click a portfolio to inspect its weights</span>
		<button onclick={() => { if (plotly) void plotly.relayout(chart, { 'scene.camera': narrow ? mobileCamera : camera } as unknown as Partial<PlotlyType.Layout>); }}>Reset camera ↗</button>
	</div>
	<div class="frontier-plot" class:narrow bind:this={chart} role="img" aria-label="Three-objective portfolio cloud: volatility, expected return and tail loss when bank cash first falls below its buffer. Select allocations with the keyboard using the selector below."></div>
	{#if !plotly && !error}<p role="status">Loading the 3D allocation space…</p>{/if}
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	<div class="legend"><span class="muted">● Other allocations</span><span class="pareto">● Discovery Pareto set</span><span class="current">◆ Current allocation</span><span class="selected">● Selected</span></div>
</div>
<style>
	.chart-frame { min-width: 0; background: var(--paper); }
	.chart-toolbar { display: flex; justify-content: space-between; align-items: center; gap: .75rem; padding: .7rem 1rem; border-bottom: 1px solid var(--rule); }
	.chart-toolbar span { color: var(--ink-soft); font-size: .85rem; }
	button { min-height: 2.5rem; padding: .4rem .7rem; border: 1px solid var(--control-border); color: var(--ink); background: var(--paper); font: inherit; cursor: pointer; }
	.frontier-plot { width: 100%; height: 530px; overflow: hidden; }
	.frontier-plot.narrow { height: 380px; }
	.legend { display: flex; flex-wrap: wrap; gap: 1rem; padding: .7rem 1rem; font-family: var(--font-mono); font-size: .65rem; border-top: 1px solid var(--rule); }
	.muted { color: var(--ink-muted); } .pareto { color: var(--cobalt); } .current { color: var(--negative); } .selected { color: var(--positive); }
	.error { padding: 1rem; color: var(--negative); }
	@media(max-width: 42rem) { .chart-toolbar { flex-wrap: wrap; } .legend { gap: .7rem; } }
</style>
