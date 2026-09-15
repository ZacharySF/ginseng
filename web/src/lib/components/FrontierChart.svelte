<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { graphCameraKeys } from '$lib/graph-camera';
	import { themeStore } from '$lib/theme.svelte';
	import '$lib/chart-lab.css';
	import OrientationGizmo from './OrientationGizmo.svelte';
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
	let rendering: Promise<unknown> = Promise.resolve();
	let orientation = $state<Partial<PlotlyType.Camera>>({ eye: { x: 1.3, y: -1.5, z: 1.15 } });
	function selectPoint(id: string) {
		if (performance.now() < ignoreClicksUntil) return;
		if (pointerOrigin) pendingPoint = id;
		else onSelect(id);
	}
	function cameraForView(viewpoint = angle): Partial<PlotlyType.Camera> & { projection: { type: 'orthographic' | 'perspective' } } {
		if (viewpoint === 'returns') return { eye: { x: 0, y: 0, z: narrow ? 1.95 : 1.75 }, up: { x: 0, y: 1, z: 0 }, projection: { type: 'orthographic' } };
		if (viewpoint === 'tail') return { eye: { x: narrow ? 1.95 : 1.75, y: 0, z: 0 }, up: { x: 0, y: 0, z: 1 }, projection: { type: 'orthographic' } };
		return { eye: narrow ? { x: 1.45, y: -1.65, z: 1.25 } : { x: 1.3, y: -1.5, z: 1.15 }, up: { x: 0, y: 0, z: 1 }, projection: { type: 'perspective' } };
	}
	function resetCamera() {
		if (plotly) void plotly.relayout(chart, { 'scene.camera': cameraForView() } as unknown as Partial<PlotlyType.Layout>);
	}
	const keyboardControls = {
		read: () => !plotly || error ? null : angle === 'space' ? (chart as unknown as PlotlyType.PlotlyHTMLElement).layout?.scene?.camera ?? cameraForView() : cameraForView('space'),
		apply: async (camera: Partial<PlotlyType.Camera>) => {
			angle = 'space';
			await tick();
			await rendering;
			if (plotly && chart.isConnected) await plotly.relayout(chart, { 'scene.camera': camera } as unknown as Partial<PlotlyType.Layout>);
		},
		onError: () => { error = 'The camera could not update. Use Reset or the allocation table below.'; }
	};
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
		const css = getComputedStyle(chart);
		const color = (name: string) => css.getPropertyValue(name).trim();
		const paper = color('--lab-scene'), ink = color('--ink'), grid = color('--lab-grid');
		const trace = (points: FrontierPoint[], name: string, marker: object): Partial<PlotlyType.PlotData> => ({
			type: 'scatter3d', mode: 'markers', name,
			x: points.map(point => point[mode].volatility),
			y: points.map(point => point[mode].mean_return),
			z: points.map(point => point[mode].pressure_cvar),
			text: points.map(point => point.label), customdata: points.map(point => point.id), marker,
			hovertemplate: '<b>%{text}</b><br>X · Volatility %{x:.2%}<br>Y · Return %{y:.2%}<br>Z · Pressure tail %{z:.2%}<extra></extra>'
		});
		const traces: PlotlyType.Data[] = [];
		const pareto = data.points.filter(point => point.pareto);
		const floor = Math.min(0, ...data.points.map(point => point[mode].pressure_cvar));
		const yOrigin = Math.min(0, ...data.points.map(point => point[mode].mean_return));
		if (angle === 'space') {
			const projected = only ? pareto : data.points;
			traces.push({ type: 'scatter3d', mode: 'markers', name: 'Floor projection',
				x: projected.map(point => point[mode].volatility), y: projected.map(point => point[mode].mean_return), z: projected.map(() => floor),
				marker: { size: 2, color: color('--lab-wire'), opacity: .23 }, hoverinfo: 'skip', showlegend: false
			} as PlotlyType.Data);
		}
		if (!only) traces.push(trace(data.points.filter(point => !point.pareto), 'Other explored allocations', { size: 3, color: color('--lab-point'), opacity: .65 }));
		for (const [size, opacity] of [[20, .025], [12, .055], [7, .12]]) {
			const halo = trace(pareto, 'Pareto light halo', { size, color: color('--lab-wire'), opacity });
			halo.hoverinfo = 'skip'; halo.hovertemplate = undefined; halo.customdata = undefined;
			traces.push(halo);
		}
		traces.push(trace(pareto, 'Discovery Pareto set', { size: 3.6, color: color('--lab-hot'), opacity: 1 }));
		if (current) traces.push(trace([current], 'Current allocation', { size: 7, symbol: 'diamond', color: '#b9cce3' }));
		if (selected) {
			const value = selected[mode];
			if (angle === 'space') traces.push({ type: 'scatter3d', mode: 'lines', name: 'Selected coordinate guides',
				x: [value.volatility, value.volatility, null, value.volatility, value.volatility, null, value.volatility, 0],
				y: [value.mean_return, value.mean_return, null, value.mean_return, yOrigin, null, value.mean_return, value.mean_return],
				z: [value.pressure_cvar, floor, null, floor, floor, null, floor, floor],
				line: { color: '#4186b6', width: 2, dash: 'dot' }, hoverinfo: 'skip', showlegend: false, connectgaps: false
			} as PlotlyType.Data);
			const glow = trace([selected], 'Selection light halo', { size: 21, color: color('--lab-hot'), opacity: .065 });
			glow.hoverinfo = 'skip'; glow.hovertemplate = undefined; glow.customdata = undefined;
			traces.push(glow as PlotlyType.Data);
			traces.push({ ...trace([selected], 'Selected allocation', { size: 11, symbol: 'circle-open', color: color('--lab-selection'), line: { color: color('--lab-selection'), width: 2 } }),
				mode: 'text+markers', text: [selected.id === 'current' ? 'CURRENT' : 'SELECTED'], textposition: 'top center', textfont: { size: 10, color: color('--lab-selection'), family: 'SFMono-Regular, Consolas, monospace' }
			} as PlotlyType.Data);
			if (mode === 'evaluation') traces.push({
				type: 'scatter3d', mode: 'lines+markers', name: 'Selected: discovery → check',
				x: [selected.discovery.volatility, selected.evaluation.volatility],
				y: [selected.discovery.mean_return, selected.evaluation.mean_return],
				z: [selected.discovery.pressure_cvar, selected.evaluation.pressure_cvar],
				line: { color: color('--lab-selection'), width: 4 }, marker: { size: 3, color: color('--lab-selection') }, hoverinfo: 'skip'
			} as PlotlyType.Data);
		}
		const axis = { color: color('--ink-soft'), gridcolor: grid, gridwidth: 1, zeroline: false, showline: true, linecolor: '#315777', linewidth: 1, showbackground: false, showspikes: false, tickformat: '.1%', nticks: 5, tickfont: { size: narrow ? 10 : 11 } };
		const reset = lastCameraKey !== cameraKey; lastCameraKey = cameraKey;
		let alive = true;
		rendering = p.react(chart, traces, {
			autosize: true, height: narrow ? 400 : 540, margin: { l: 10, r: 10, t: 8, b: narrow ? 38 : 35 },
			paper_bgcolor: paper, font: { color: ink, family: 'SFMono-Regular, Consolas, monospace', size: 11 },
			hoverlabel: { bgcolor: color('--paper'), bordercolor: color('--rule-strong'), font: { color: ink, size: 12 } },
			showlegend: false, uirevision: cameraKey,
			scene: { camera: targetCamera, aspectmode: angle === 'space' ? 'cube' : 'manual',
				aspectratio: angle === 'returns' ? { x: narrow ? 1.15 : 1.9, y: 1.15, z: 1 } : { x: 1, y: narrow ? 1.15 : 1.9, z: 1.15 },
				dragmode: angle === 'space' ? 'orbit' : 'pan',
				xaxis: { ...axis, tickangle: angle === 'returns' ? 0 : 'auto', showticklabels: angle !== 'tail', showgrid: angle !== 'tail', title: { text: angle === 'tail' ? '' : 'X', font: { size: 13, color: ink } } },
				yaxis: { ...axis, tickangle: angle === 'tail' ? 0 : 'auto', title: { text: 'Y', font: { size: 13, color: ink } } },
				zaxis: { ...axis, showticklabels: angle !== 'returns', showgrid: angle !== 'returns', showbackground: angle === 'space', backgroundcolor: color('--lab-floor'), title: { text: angle === 'returns' ? '' : 'Z', font: { size: 13, color: ink } } }
			}
		}, { responsive: true, displayModeBar: false, displaylogo: false, scrollZoom: false })
		.then(async graph => {
			if (!alive) return;
			graph.removeAllListeners('plotly_click');
			graph.on('plotly_click', event => {
				const id = event.points[0]?.customdata;
				if (typeof id === 'string') selectPoint(id);
			});
			graph.removeAllListeners('plotly_relayout');
			graph.on('plotly_relayout', () => { if (graph.layout.scene?.camera) orientation = structuredClone(graph.layout.scene.camera); });
			if (reset) await p.relayout(chart, { 'scene.camera': targetCamera } as unknown as Partial<PlotlyType.Layout>);
			if (graph.layout.scene?.camera) orientation = structuredClone(graph.layout.scene.camera);
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
		<div class="scene-caption"><span>PORTFOLIO / {angle === 'space' ? '3D COORDINATES' : 'ORTHOGRAPHIC'}</span><span>{view === 'discovery' ? 'SAMPLE 01' : 'SAMPLE 02'}</span></div>
		<!-- svelte-ignore a11y_no_noninteractive_tabindex (This Plotly application has focus-scoped keyboard controls supplied by graphCameraKeys.) -->
		<div class="frontier-plot lab-camera" class:narrow bind:this={chart} use:graphCameraKeys={keyboardControls} tabindex="0" role="application" aria-roledescription="interactive 3D graph" aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown" aria-label="Portfolio allocations by volatility, return and tail loss at the first cash-buffer breach. Left and right arrows turn horizontally; up and down raise and lower the view along Z. Arrows return flat views to 3D. Tab leaves the graph. Use the portfolio selector to inspect every point."></div>
		<div class="orientation"><OrientationGizmo camera={orientation}/></div>
		{#if !plotly && !error}<p role="status">Loading allocation space…</p>{/if}
		{#if error}<p class="error" role="alert">{error}</p>{/if}
	</div>
	<p class="camera-help">{angle === 'space' ? 'Drag to rotate · click to inspect. Faint floor points project return and volatility; dotted guides locate the selection.' : angle === 'returns' ? 'Flat view of volatility and return. Switch to 3D to include tail loss.' : 'Flat view of return and tail loss. Switch to 3D to include volatility.'}</p>
	<p class="lab-keyboard-hint">Click or Tab into graph · <kbd>←</kbd> <kbd>→</kbd> turn · <kbd>↑</kbd> <kbd>↓</kbd> raise / lower view{angle !== 'space' ? ' · Arrows return to 3D' : ''}</p>
	<div class="legend" aria-label="Portfolio point legend"><span class="other"><i></i>Explored</span><span class="pareto"><i></i>Pareto</span><span class="current"><i></i>Current</span><span class="selected"><i></i>Selected</span></div>
</div>
<style>
	.chart-frame { min-width: 0; background: var(--paper); }
	.reset { display: inline-flex; align-items: center; gap: .35rem; min-height: 2.5rem; padding: .4rem .25rem; border: 0; background: transparent; color: var(--ink-soft); font: .7rem var(--font-mono); cursor: pointer; }
	.reset:hover { color: var(--cobalt); }.reset svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; }
	.scene-area { position: relative; background: var(--lab-scene); }.scene-area > p { padding: 1rem; }
	.scene-caption { display: flex; justify-content: space-between; gap: 1rem; padding: 1rem 1.1rem .1rem; font: .58rem var(--font-mono); letter-spacing: .09em; color: #829fb9; }
	.orientation { position: absolute; left: .6rem; bottom: .5rem; pointer-events: none; }
	.frontier-plot { width: 100%; height: 540px; overflow: hidden; }.frontier-plot.narrow { height: 400px; }
	.camera-help { padding: .65rem 1rem; font-size: .83rem; color: var(--ink-soft); background: var(--lab-scene); }
	.legend { display: flex; flex-wrap: wrap; gap: 1.2rem; padding: .9rem 1rem; font: .65rem var(--font-mono); border-top: 1px solid var(--rule); }
	.legend span { display: flex; align-items: center; gap: .45rem; }.legend i { display: inline-block; width: .45rem; height: .45rem; background: currentColor; border-radius: 50%; }
	.other { color: var(--ink-muted); }.pareto { color: var(--lab-hot); }.pareto i { box-shadow: 0 0 9px #389dff; }.current { color: var(--ink-soft); }.current i { border-radius: 0; transform: rotate(45deg); }.selected { color: var(--lab-selection); }.selected i { width: .6rem; height: .6rem; border: 1.5px solid currentColor; background: transparent; }
	.error { color: var(--negative); }
	@media(max-width: 42rem) { .legend { gap: .85rem; padding: .8rem .75rem; }.camera-help { padding: .6rem .75rem; } }
</style>
