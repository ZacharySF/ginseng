<script lang="ts">
	import { onMount } from 'svelte';
	import { themeStore } from '$lib/theme.svelte';
	import '$lib/chart-lab.css';
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
	let angle = $state<'space' | 'returns' | 'tail'>('space');
	let lastCameraKey = '';
	let pointerOrigin: { x: number; y: number } | null = null;
	let pointerMoved = false;
	let pendingPoint: string | null = null;
	let ignoreClicksUntil = 0;
	function selectPoint(id: string) {
		if (performance.now() < ignoreClicksUntil) return;
		if (pointerOrigin) pendingPoint = id;
		else onSelect(id);
	}
	function cameraForView(): Partial<PlotlyType.Camera> & { projection: { type: 'orthographic' | 'perspective' } } {
		if (angle === 'returns') return { eye: { x: 0, y: 0, z: narrow ? 1.95 : 1.75 }, up: { x: 0, y: 1, z: 0 }, projection: { type: 'orthographic' } };
		if (angle === 'tail') return { eye: { x: narrow ? 1.95 : 1.75, y: 0, z: 0 }, up: { x: 0, y: 0, z: 1 }, projection: { type: 'orthographic' } };
		return { eye: narrow ? { x: 1.45, y: -1.65, z: 1.25 } : { x: 1.3, y: -1.5, z: 1.15 }, up: { x: 0, y: 0, z: 1 }, projection: { type: 'perspective' } };
	}
	function resetCamera() {
		if (plotly) void plotly.relayout(chart, { 'scene.camera': cameraForView() } as unknown as Partial<PlotlyType.Layout>);
	}
	onMount(() => {
		let alive = true;
		// WebGL point clicks can fire on pointer-down. Defer selection until
		// pointer-up so a camera drag across a point cannot trigger a redraw.
		const down = (event: PointerEvent) => { pointerOrigin = { x: event.clientX, y: event.clientY }; pointerMoved = false; pendingPoint = null; };
		const move = (event: PointerEvent) => {
			if (pointerOrigin && Math.hypot(event.clientX - pointerOrigin.x, event.clientY - pointerOrigin.y) > 5) pointerMoved = true;
		};
		const up = (event: PointerEvent) => {
			if (!pointerOrigin) return;
			move(event);
			if (pointerMoved || event.type === 'pointercancel') ignoreClicksUntil = performance.now() + 150;
			else if (pendingPoint) onSelect(pendingPoint);
			pointerOrigin = null; pendingPoint = null;
		};
		chart.addEventListener('pointerdown', down, true);
		window.addEventListener('pointermove', move);
		window.addEventListener('pointerup', up);
		window.addEventListener('pointercancel', up);
		narrow = chart.clientWidth < 600;
		import('plotly.js-gl3d-dist-min').then(module => {
			if (alive) plotly = module.default;
		}).catch(() => { if (alive) error = 'The 3D renderer could not load. Use the allocation selector and table below.'; });
		const observer = new ResizeObserver(() => {
			narrow = chart.clientWidth < 600;
			if (plotly) void Promise.resolve(plotly.Plots.resize(chart)).catch(() => {});
		});
		observer.observe(chart);
		return () => {
			alive = false; observer.disconnect();
			chart.removeEventListener('pointerdown', down, true);
			window.removeEventListener('pointermove', move);
			window.removeEventListener('pointerup', up);
			window.removeEventListener('pointercancel', up);
			if (plotly) plotly.purge(chart);
		};
	});

	$effect(() => {
		themeStore.current;
		const p = plotly;
		const data = report;
		const mode = view;
		const selected = data.points.find(point => point.id === selectedId);
		const current = data.points.find(point => point.id === 'current');
		const only = frontierOnly;
		const cameraKey = `${data.metadata.input_hash}:${narrow}:${angle}`;
		const targetCamera = cameraForView();
		if (!p || !chart) return;
		const css = getComputedStyle(document.documentElement);
		const color = (name: string) => css.getPropertyValue(name).trim();
		const paper = color('--lab-scene'), ink = color('--ink'), grid = color('--lab-grid');
		const trace = (points: FrontierPoint[], name: string, marker: object): PlotlyType.Data => ({
			type: 'scatter3d', mode: 'markers', name,
			x: points.map(point => point[mode].volatility),
			y: points.map(point => point[mode].mean_return),
			z: points.map(point => point[mode].pressure_cvar),
			text: points.map(point => point.label), customdata: points.map(point => point.id), marker,
			hovertemplate: '<b>%{text}</b><br>X · Volatility %{x:.2%}<br>Y · Return %{y:.2%}<br>Z · Pressure tail %{z:.2%}<extra></extra>'
		} as PlotlyType.Data);
		const traces: PlotlyType.Data[] = [];
		if (!only) traces.push(trace(data.points.filter(point => !point.pareto), 'Other explored allocations', { size: 3.5, color: color('--lab-point'), opacity: .5 }));
		traces.push(trace(data.points.filter(point => point.pareto), 'Discovery Pareto set', { size: 5, color: color('--cobalt'), opacity: 1 }));
		if (current) traces.push(trace([current], 'Current allocation', { size: 7, symbol: 'diamond', color: color('--ink-soft') }));
		if (selected) {
			traces.push(trace([selected], 'Selected allocation', { size: 11, symbol: 'circle-open', color: color('--lab-selection'), line: { color: color('--lab-selection'), width: 3 } }));
			if (mode === 'evaluation') traces.push({
				type: 'scatter3d', mode: 'lines+markers', name: 'Selected: discovery → check',
				x: [selected.discovery.volatility, selected.evaluation.volatility],
				y: [selected.discovery.mean_return, selected.evaluation.mean_return],
				z: [selected.discovery.pressure_cvar, selected.evaluation.pressure_cvar],
				line: { color: color('--lab-selection'), width: 4 }, marker: { size: 3, color: color('--lab-selection') }, hoverinfo: 'skip'
			} as PlotlyType.Data);
		}
		const axis = { color: color('--ink-soft'), gridcolor: grid, gridwidth: 1, zeroline: false, showbackground: false, showspikes: false, tickformat: '.1%', nticks: 4, tickfont: { size: narrow ? 10 : 11 } };
		const reset = lastCameraKey !== cameraKey; lastCameraKey = cameraKey;
		let alive = true;
		void p.react(chart, traces, {
			autosize: true, height: narrow ? 370 : 470, margin: { l: 10, r: 10, t: 8, b: narrow ? 38 : 35 },
			paper_bgcolor: paper, font: { color: ink, family: 'SFMono-Regular, Consolas, monospace', size: 11 },
			hoverlabel: { bgcolor: color('--paper'), bordercolor: color('--rule-strong'), font: { color: ink, size: 12 } },
			showlegend: false, uirevision: cameraKey,
			scene: { camera: targetCamera, aspectmode: angle === 'space' ? 'cube' : 'manual',
				aspectratio: angle === 'returns' ? { x: narrow ? 1.15 : 1.9, y: 1.15, z: 1 } : { x: 1, y: narrow ? 1.15 : 1.9, z: 1.15 },
				dragmode: angle === 'space' ? 'orbit' : 'pan',
				xaxis: { ...axis, tickangle: angle === 'returns' ? 0 : 'auto', showticklabels: angle !== 'tail', showgrid: angle !== 'tail', title: { text: angle === 'tail' ? '' : 'X', font: { size: 13, color: ink } } },
				yaxis: { ...axis, tickangle: angle === 'tail' ? 0 : 'auto', title: { text: 'Y', font: { size: 13, color: ink } } },
				zaxis: { ...axis, showticklabels: angle !== 'returns', showgrid: angle !== 'returns', showbackground: angle === 'space', backgroundcolor: paper, title: { text: angle === 'returns' ? '' : 'Z', font: { size: 13, color: ink } } }
			}
		}, { responsive: true, displayModeBar: false, displaylogo: false, scrollZoom: false })
		.then(async graph => {
			if (!alive) return;
			graph.removeAllListeners('plotly_click');
			graph.on('plotly_click', event => {
				const id = event.points[0]?.customdata;
				if (typeof id === 'string') selectPoint(id);
			});
			if (reset) await p.relayout(chart, { 'scene.camera': targetCamera } as unknown as Partial<PlotlyType.Layout>);
		}).catch(() => { if (alive) error = '3D is unavailable in this browser. All allocation values remain available below.'; });
		return () => { alive = false; };
	});
</script>

<div class="chart-frame">
	<div class="lab-axis-key" aria-label="How to read the portfolio axes">
		<div><span class="axis-letter">X</span><div><strong>Volatility</strong><small>Return variability · lower ↓</small></div></div>
		<div><span class="axis-letter">Y</span><div><strong>Expected return</strong><small>Horizon average · higher ↑</small></div></div>
		<div><span class="axis-letter">Z</span><div><strong>Pressure tail loss</strong><small>Worst 5% at breach · lower ↓</small></div></div>
	</div>
	<div class="lab-toolbar">
		<div class="lab-switch lab-switch--camera" aria-label="Portfolio camera view">
			<button aria-pressed={angle === 'space'} onclick={() => angle = 'space'}>3D</button>
			<button aria-pressed={angle === 'returns'} onclick={() => angle = 'returns'}>Risk / return</button>
			<button aria-pressed={angle === 'tail'} onclick={() => angle = 'tail'}>Tail / return</button>
		</div>
		<button class="reset" aria-label="Reset camera" onclick={resetCamera}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 7a6 6 0 1 1-.3 5M4 3v4h4"/></svg>Reset</button>
	</div>
	<div class="scene-area">
		<div class="frontier-plot" class:narrow bind:this={chart} role="img" aria-label="Portfolio allocations by volatility, return and tail loss at the first cash-buffer breach. Use the portfolio selector for keyboard access to every point."></div>
		{#if !plotly && !error}<p role="status">Loading allocation space…</p>{/if}
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	</div>
	<p class="camera-help">{angle === 'space' ? 'Drag to rotate. Select a point to inspect its portfolio.' : angle === 'returns' ? 'Flat view of volatility and return. Switch to 3D to include tail loss.' : 'Flat view of return and tail loss. Switch to 3D to include volatility.'}</p>
	<div class="legend" aria-label="Portfolio point legend"><span class="other"><i></i>Explored</span><span class="pareto"><i></i>Pareto</span><span class="current"><i></i>Current</span><span class="selected"><i></i>Selected</span></div>
</div>
<style>
	.chart-frame { min-width: 0; background: var(--paper); }
	.reset { display: inline-flex; align-items: center; gap: .35rem; min-height: 2.5rem; padding: .4rem .25rem; border: 0; background: transparent; color: var(--ink-soft); font: .7rem var(--font-mono); cursor: pointer; }
	.reset:hover { color: var(--cobalt); }.reset svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; }
	.scene-area { background: var(--lab-scene); }.scene-area > p { padding: 1rem; }
	.frontier-plot { width: 100%; height: 470px; overflow: hidden; }.frontier-plot.narrow { height: 370px; }
	.camera-help { padding: .65rem 1rem; font-size: .83rem; color: var(--ink-soft); background: var(--lab-scene); }
	.legend { display: flex; flex-wrap: wrap; gap: 1.2rem; padding: .9rem 1rem; font: .65rem var(--font-mono); border-top: 1px solid var(--rule); }
	.legend span { display: flex; align-items: center; gap: .45rem; }.legend i { display: inline-block; width: .45rem; height: .45rem; background: currentColor; border-radius: 50%; }
	.other { color: var(--ink-muted); }.pareto { color: var(--cobalt); }.current { color: var(--ink-soft); }.current i { border-radius: 0; transform: rotate(45deg); }.selected { color: var(--lab-selection); }.selected i { width: .6rem; height: .6rem; border: 1.5px solid currentColor; background: transparent; }
	.error { color: var(--negative); }
	@media(max-width: 42rem) { .legend { gap: .85rem; padding: .8rem .75rem; }.camera-help { padding: .6rem .75rem; } }
</style>
