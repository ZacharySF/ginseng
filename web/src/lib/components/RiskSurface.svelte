<script lang="ts">
 import { onMount, tick } from 'svelte';
 import { graphCameraKeys } from '$lib/graph-camera';
 import { createGraphFullscreen } from '$lib/graph-fullscreen';
 import '$lib/graph-fullscreen.css';
 import '$lib/chart-lab.css';
 import type { RiskSurface } from '$lib/numerics.svelte';
 import { themeStore } from '$lib/theme.svelte';
 import { formatCurrency } from '$lib/format';
 import type * as PlotlyType from 'plotly.js';
 import OrientationGizmo from './OrientationGizmo.svelte';
 let { data }: { data: RiskSurface } = $props();
 let chart: HTMLDivElement;
 let expanded = $state(false);
 const fullscreen = createGraphFullscreen(value => expanded = value, () => chart);
 const attachFullscreen = fullscreen.attach;
 let cameraListener: (() => void) | null = null;
 let rendering: Promise<unknown> = Promise.resolve();
 let orientation = $state<Partial<PlotlyType.Camera>>({eye:{x:1.5,y:1.85,z:1.4},up:{x:0,y:0,z:1},center:{x:0,y:0,z:-.32}});
 let plotly = $state<typeof PlotlyType | null>(null);
 let metric = $state<'risk' | 'deficit'>('risk');
 let cashIndex = $state(0);
 let table = $state(false);
 let error = $state('');
 let narrow = $state(false);
 let preset = $state<'perspective' | 'overhead' | 'slice'>('perspective');
 let resetCount = $state(0);
 const values = $derived(metric === 'risk' ? data.shortfall_probability : data.expected_max_deficit);
 const maxValue = $derived(Math.max(0,...values.flat()));
 const scaleTop = $derived(metric==='risk'?Math.min(1,Math.max(.05,Math.ceil(maxValue*20)/20)):Math.max(100,Math.ceil(maxValue/100)*100));
 const label = $derived(metric === 'risk' ? 'Shortfall chance' : 'Expected worst deficit');
 const finalDay = $derived(data.days.at(-1) ?? 1);
 const selectedCash = $derived(data.additional_cash[cashIndex]);
 const endValue = $derived(values[cashIndex].at(-1) ?? 0);
 const noCashEnd = $derived(values[0].at(-1) ?? 0);
 const reduction = $derived(Math.max(0, noCashEnd - endValue));
 const display = (v: number) => metric === 'risk' ? `${(100*v).toFixed(1)}%` : formatCurrency(v);
 const cameraFor = (view: typeof preset, compact: boolean) => {
  if(view==='overhead') return {eye:{x:0,y:0,z:compact?2.2:1.55},up:{x:0,y:1,z:0},projection:{type:'orthographic' as const}};
  if(view==='slice') return {eye:{x:0,y:-2.65,z:0.04},up:{x:0,y:0,z:1},projection:{type:'orthographic' as const}};
  return {eye:compact?{x:2.15,y:2.25,z:1.6}:{x:1.5,y:1.85,z:1.4},up:{x:0,y:0,z:1},center:{x:0,y:0,z:compact?0:-.32},projection:{type:'perspective' as const}};
 };
 const keyboardControls = {
  toggleFullscreen: fullscreen.toggle,
  read: () => !plotly || error ? null : preset === 'perspective' ? (chart as unknown as PlotlyType.PlotlyHTMLElement).layout?.scene?.camera ?? cameraFor('perspective', narrow) : cameraFor('perspective', narrow),
  apply: async (camera: Partial<PlotlyType.Camera>) => {
   preset = 'perspective';
   await tick();
   await rendering;
   if (plotly && chart.isConnected) await plotly.relayout(chart, { 'scene.camera': camera } as unknown as Partial<PlotlyType.Layout>);
  },
  onError: () => { error = 'The camera could not update. Use Reset view or the cash slice table below.'; }
 };
 onMount(() => {
  let active=true;
  narrow=chart.clientWidth<600;
  import('plotly.js-gl3d-dist-min').then(m=>{if(active) plotly=m.default;}).catch(()=>{if(active) error='The 3D renderer could not load. Use the cash slice table below.';});
  const resize=new ResizeObserver(()=>{
   if(!chart.clientWidth || !chart.clientHeight) return;
   if(!expanded) narrow=chart.clientWidth<600;
   if(plotly) void plotly.relayout(chart,{width:chart.clientWidth,height:chart.clientHeight}).catch(()=>{});
  });
  resize.observe(chart);
  return ()=>{active=false;resize.disconnect();if(plotly) plotly.purge(chart);cameraListener=null;};
 });
 $effect(()=>{
  const theme=themeStore.current;
  const p=plotly; const z=values; const d=data; const index=cashIndex; const title=label; const view=preset;
  const revision=`${d.input_id}:${narrow}:${view}:${resetCount}`;
  if(!p || !chart) return;
  const style=getComputedStyle(chart);
  const color=(name:string)=>style.getPropertyValue(name).trim();
  const paper=color('--lab-scene'), ink=color('--lab-selection'), muted=color('--ink-muted'), rule=color('--lab-grid'), wire=color('--lab-wire'), hot=color('--lab-hot');
  const glowStrength=Number(color('--lab-glow-strength'));
  const axis={gridcolor:rule,zerolinecolor:rule,color:muted,showbackground:false,showspikes:false,showline:false,
   tickfont:{size:narrow?10:11,family:style.getPropertyValue('--font-mono').trim()},nticks:4};
  let active=true;
  const targetCamera=cameraFor(view,narrow);
  const mesh: {x:(number|null)[];y:(number|null)[];z:(number|null)[]} = {x:[],y:[],z:[]};
  // Every line endpoint is an original sampled grid node. Nulls separate
  // rows/columns; the mesh introduces neither smoothing nor new estimates.
  const node=(day:number,cash:number,value:number)=>{mesh.x.push(day);mesh.y.push(cash);mesh.z.push(value);};
  const separator=()=>{mesh.x.push(null);mesh.y.push(null);mesh.z.push(null);};
  for(let row=0;row<d.additional_cash.length;row++){
   for(let column=0;column<d.days.length;column++) node(d.days[column],d.additional_cash[row],z[row][column]);
   separator();
  }
  for(let column=0;column<d.days.length;column++){
   for(let row=0;row<d.additional_cash.length;row++) node(d.days[column],d.additional_cash[row],z[row][column]);
   separator();
  }
  const meshTrace={type:'scatter3d',mode:'lines',...mesh,connectgaps:false,hoverinfo:'skip',showlegend:false};
  const selected={type:'scatter3d',mode:'lines',x:d.days,y:d.days.map(()=>d.additional_cash[index]),z:z[index],showlegend:false,hoverinfo:'skip'};
  rendering=p.react(chart,[{
   type:'surface',x:d.days,y:d.additional_cash,z,showscale:view!=='slice',opacity:view==='slice'?.12:.93,
   colorscale:theme==='dark'
    ? [[0,'#07192f'],[.08,'#103363'],[.2,'#1252b8'],[.4,'#1182cf'],[.65,'#23b7d8'],[.85,'#86e7df'],[1,'#e0fff0']]
    : [[0,'#f3f5ff'],[.08,'#e2e9ff'],[.2,'#b2c4fb'],[.4,'#7c9ae7'],[.65,'#416bd0'],[.85,'#233ebb'],[1,'#0100f4']],
   cmin:0,cmax:metric==='risk'?1:scaleTop,
   lighting:theme==='dark'?{ambient:.8,diffuse:.6,specular:.18,roughness:.6,fresnel:.08}:{ambient:1,diffuse:.15,specular:0,roughness:1,fresnel:0},
   lightposition:{x:0,y:-1500,z:1800},
   colorbar:{thickness:8,len:.64,x:1.01,xpad:0,outlinewidth:1,outlinecolor:rule,tickfont:{size:10,color:muted},tickformat:metric==='risk'?'.0%':'$~s',nticks:3},
   hovertemplate:`Day %{x}<br>Extra cash $%{y:,.0f}<br>${title}: %{z:${metric==='risk'?'.1%':'$,.2f'}}<extra></extra>`,
  },{...selected,name:'Selected cash slice',line:{color:ink,width:3.5}},
   {type:'scatter3d',mode:'markers',x:[finalDay],y:[d.additional_cash[index]],z:[z[index].at(-1)],
    marker:{color:ink,size:4,line:{color:hot,width:1.5}},showlegend:false,
    hovertemplate:`Selected cash · $%{y:,.0f}<br>By day %{x}: %{z:${metric==='risk'?'.1%':'$,.2f'}}<extra></extra>`}
   ,{...meshTrace,name:'Grid halo',line:{color:wire,width:4.5},opacity:(view==='slice'?.025:.13)*glowStrength},
   {...meshTrace,name:'Sampled grid',line:{color:wire,width:1.3},opacity:view==='slice'?.12:theme==='dark'?.9:.7},
   {...selected,name:'Selected slice halo',line:{color:hot,width:10},opacity:.17*glowStrength}
   ] as PlotlyType.Data[],{
    autosize:true,height:chart.clientHeight,margin:{l:0,r:view==='slice'?10:50,b:15,t:10},paper_bgcolor:paper,
    font:{color:ink,family:'Archivo Narrow, sans-serif'},
    hoverlabel:{bgcolor:color('--paper'),bordercolor:color('--rule-strong'),font:{color:color('--ink')}},
    uirevision:revision,scene:{camera:targetCamera,aspectmode:'manual',aspectratio:narrow?{x:1.2,y:1,z:.85}:{x:2.4,y:1.15,z:.8},
     xaxis:{...axis,title:{text:'X',font:{size:12}},tickmode:'array',tickvals:[...new Set([1,Math.ceil(finalDay/2),finalDay])]},
     yaxis:{...axis,title:{text:view==='slice'?'':'Y',font:{size:12}},tickformat:'$~s',showticklabels:view!=='slice',showgrid:view!=='slice'},
     zaxis:{...axis,showbackground:true,backgroundcolor:color('--lab-floor'),title:{text:view==='overhead'?'':'Z',font:{size:12}},showticklabels:view!=='overhead',
      tickformat:metric==='risk'?'.0%':'$~s',range:[0,scaleTop]}}
   },{responsive:true,displaylogo:false,displayModeBar:false,scrollZoom:false})
   .then(()=>{
    if(!active) return;
    const rendered=chart as unknown as PlotlyType.PlotlyHTMLElement;
    orientation=structuredClone(rendered.layout.scene?.camera ?? targetCamera);
    if(!cameraListener){
     cameraListener=()=>{orientation=structuredClone(rendered.layout.scene?.camera ?? targetCamera);};
     rendered.on('plotly_relayout',cameraListener);
    }
   })
   .catch(()=>{if(active) error='3D is unavailable in this browser. The cash slice table still shows the calculated values.';});
  return ()=>{active=false;};
 });
</script>

<div class="surface-workbench lab-view graph-stage" use:attachFullscreen>
 <div class="controls lab-toolbar">
  <div class="tabs lab-switch" role="group" aria-label="Surface metric">
   <button class:active={metric==='risk'} aria-pressed={metric==='risk'} onclick={()=>metric='risk'}>Shortfall chance</button>
   <button class:active={metric==='deficit'} aria-pressed={metric==='deficit'} onclick={()=>metric='deficit'}>Deficit severity</button>
  </div>
  <span class="grid-note">{data.days.length} days · {data.additional_cash.length} cash levels</span>
 </div>
 <div class="lab-axis-key" aria-label="How to read the surface">
  <div><span class="axis-letter">X</span><div><strong>Forecast day</strong><small>When cash may run short</small></div></div>
  <div><span class="axis-letter">Y</span><div><strong>Extra cash</strong><small>Added to opening cash</small></div></div>
  <div><span class="axis-letter">Z</span><div><strong>{metric==='risk'?'Shortfall chance':'Deficit severity'}</strong><small>{metric==='risk'?'Lower is less likely':'Lower is less severe'}</small></div></div>
 </div>
 <div class="camera-toolbar">
  <div class="camera-presets" role="group" aria-label="Chart viewpoint">
   <button class:selected={preset==='perspective'} aria-pressed={preset==='perspective'} onclick={()=>preset='perspective'}>3D view</button>
   <button class:selected={preset==='overhead'} aria-pressed={preset==='overhead'} onclick={()=>preset='overhead'}>Overhead</button>
   <button class:selected={preset==='slice'} aria-pressed={preset==='slice'} onclick={()=>preset='slice'}>Cash slice</button>
  </div>
  <div class="graph-window-controls">
   <button class="graph-fullscreen-button" onclick={fullscreen.toggle} aria-keyshortcuts="f" aria-label={expanded ? 'Exit fullscreen' : 'Fullscreen'}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4"/></svg>{expanded ? 'Exit fullscreen' : 'Fullscreen'}</button>
   <button class="reset" onclick={()=>resetCount+=1}>Reset view ↗</button>
  </div>
 </div>
 <div class="scene-shell">
  <div class="scene-stamp" aria-hidden="true"><span>SAMPLED CASH SURFACE</span><span>{data.paths.toLocaleString()} PATHS / {data.days.length*data.additional_cash.length} NODES</span></div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex (This Plotly application has focus-scoped keyboard controls supplied by graphCameraKeys.) -->
  <div class="plot lab-camera" class:narrow bind:this={chart} use:graphCameraKeys={keyboardControls} tabindex="0" role="application" aria-roledescription="interactive 3D graph" aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown f" aria-label={`${label} across forecast days and additional opening cash. Left and right arrows turn horizontally; up and down raise and lower the view along Z. Arrows return flat views to 3D. F toggles fullscreen; Escape exits. Tab leaves the graph. Exact values are available in the cash slice table.`}></div>
  <div class="orientation"><OrientationGizmo camera={orientation}/></div>
 </div>
 {#if !plotly && !error}<p class="chart-message" role="status">Loading interactive 3D view…</p>{/if}
 {#if error}<p class="chart-message" role="alert">{error}</p>{/if}
 <div class="plot-caption"><span class="selection-key"><i aria-hidden="true"></i> Selected cash level</span><span class="height-scale">Height scale 0–{display(scaleTop)}</span><span class="caption-help">{preset==='overhead'?'Color shows the risk level.':preset==='slice'?'Your selected cash level, viewed through time.':'Drag to rotate · pinch to zoom'}</span></div>
 <p class="lab-keyboard-hint">Click or Tab into graph · <kbd>←</kbd> <kbd>→</kbd> turn · <kbd>↑</kbd> <kbd>↓</kbd> raise / lower view · <kbd>F</kbd> fullscreen{expanded ? ' · Esc to exit' : ''}{preset !== 'perspective' ? ' · Arrows return to 3D' : ''}</p>
 {#if data.shortfall_probability.every(row=>row.every(value=>value===0))}<p class="quiet-note">No shortfalls observed on this grid. Use the precision estimate to assess numerical uncertainty.</p>{/if}
 <div class="slice">
  <div class="cash-control">
   <label for="cash-slice"><span>Explore extra opening cash</span><strong>{formatCurrency(selectedCash)}</strong></label>
   <input id="cash-slice" aria-label="Extra opening cash slice" type="range" min="0" max={data.additional_cash.length-1} step="1" bind:value={cashIndex}/>
   <div class="range-labels"><span>{formatCurrency(data.additional_cash[0])}</span><span>{formatCurrency(data.additional_cash.at(-1) ?? 0)}</span></div>
  </div>
  <div class="readout" aria-live="polite"><small>{metric==='risk'?'Shortfall chance':'Expected worst deficit'} · by day {finalDay}</small><strong>{display(endValue)}</strong><span>{#if cashIndex===0}Baseline · no extra opening cash{:else}{metric==='risk'?`${(100*reduction).toFixed(1)} percentage points lower`:`${formatCurrency(reduction)} lower`} than no extra cash{/if}</span></div>
 </div>
 <div class="surface-footer">
  <button class="table-toggle lab-button" aria-expanded={table || !!error} onclick={()=>table=!table}>{table?'Hide':'Show'} exact cash slice table</button>
  <details><summary>Model & reading notes</summary><p>{data.scope} “By day” includes earlier shortfalls, even if cash later recovers. Deficit severity averages the worst cash deficit across all paths. The luminous mesh joins the calculated grid points without adding estimates between them. Color follows the page theme; the labeled color scale is independent of the visible height range. Use the table for the sampled values.</p></details>
 </div>
 {#if table || error}<div class="table-scroll"><table><caption>{label} with {formatCurrency(selectedCash)} extra cash from day one</caption><thead><tr><th>Forecast day</th><th>{label}</th></tr></thead><tbody>{#each data.days as day,i}<tr><td>{day}</td><td>{display(values[cashIndex][i])}</td></tr>{/each}</tbody></table></div>{/if}
</div>
<style>
 .surface-workbench{min-width:0}.controls{align-items:center}.tabs{flex-wrap:nowrap}.grid-note,.camera-presets button,.reset,.range-labels,.plot-caption,.readout small{font-family:var(--font-mono);font-size:.65rem;letter-spacing:.035em}.grid-note{color:var(--ink-muted)}.camera-toolbar{display:flex;justify-content:space-between;gap:.5rem;align-items:center;padding:.6rem 1rem;background:var(--lab-scene)}.camera-presets{display:flex;gap:.2rem}.camera-presets button,.reset{min-height:2.2rem;padding:.4rem .65rem;border:1px solid transparent;color:var(--ink-soft);background:transparent;cursor:pointer}.camera-presets .selected{background:var(--paper);border-color:var(--rule);color:var(--cobalt)}.reset:hover,.camera-presets button:hover{border-color:var(--control-border)}.scene-shell{position:relative;background:var(--lab-scene);isolation:isolate}.scene-stamp{position:absolute;z-index:2;top:.65rem;left:1.2rem;right:1.2rem;display:flex;justify-content:space-between;gap:.5rem;pointer-events:none;color:var(--lab-stamp);font:.58rem var(--font-mono);letter-spacing:.11em}.orientation{position:absolute;z-index:2;left:1rem;bottom:.75rem;pointer-events:none;opacity:.85}.plot{width:100%;height:480px;overflow:hidden;background:var(--lab-scene)}.plot.narrow{height:410px}.plot-caption{display:flex;justify-content:space-between;gap:1rem;padding:.45rem 1rem .8rem;color:var(--ink-muted);background:var(--lab-scene)}.selection-key{display:inline-flex;align-items:center;gap:.5rem;white-space:nowrap}.selection-key i{width:1.3rem;height:2px;background:var(--lab-selection);box-shadow:var(--lab-selection-shadow)}.chart-message,.quiet-note{padding:.6rem 1rem;color:var(--ink-soft);font-size:.85rem}.slice{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);border-block:1px solid var(--rule);background:var(--paper)}.cash-control{padding:1.15rem 1.2rem}.cash-control label{display:flex;justify-content:space-between;align-items:center;gap:.5rem;font-size:.95rem}.cash-control strong{font-family:var(--font-mono);font-size:1rem}input{width:100%;margin:.95rem 0 .3rem;accent-color:var(--cobalt);cursor:pointer}.range-labels{display:flex;justify-content:space-between;color:var(--ink-muted)}.readout{padding:1.1rem 1.2rem;border-left:1px solid var(--rule);display:grid;gap:.25rem;background:var(--paper-soft)}.readout small{color:var(--ink-soft);text-transform:uppercase}.readout strong{font-size:2.5rem;text-shadow:var(--lab-value-shadow);font-weight:500;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.035em;color:var(--cobalt)}.readout>span{font-size:.82rem;color:var(--ink-soft)}.surface-footer{display:flex;align-items:start;gap:1rem;justify-content:space-between;padding:.8rem 1rem}.table-toggle{min-height:2.2rem;font-size:.7rem;padding:.4rem .6rem}.surface-footer details{max-width:52%;font-size:.82rem;color:var(--ink-soft)}summary{cursor:pointer;padding:.45rem 0;font-family:var(--font-mono);font-size:.68rem}details p{padding:.4rem 0;line-height:1.5}.table-scroll{max-height:20rem;overflow:auto;padding:0 1rem .5rem}table{width:100%;border-collapse:collapse;text-align:left;font-family:var(--font-mono);font-size:.75rem}th,td{padding:.65rem .5rem;border-bottom:1px solid var(--rule)}thead{position:sticky;top:0;background:var(--paper)}caption{text-align:left;padding:.6rem 0;color:var(--ink-soft)}@media(max-width:42rem){.scene-stamp{left:.75rem;right:.75rem;font-size:.48rem;letter-spacing:.055em}.orientation{left:.5rem;bottom:.75rem;transform:scale(.85);transform-origin:left bottom}.grid-note{display:none}.tabs{width:100%}.tabs button{flex:1;padding:.45rem .5rem;font-size:.65rem}.camera-toolbar{padding:.5rem .5rem .2rem;gap:0}.camera-presets button,.reset{padding:.4rem .5rem;font-size:.61rem}.plot-caption{font-size:.59rem;padding:.45rem .7rem .7rem;gap:.4rem;flex-wrap:wrap}.caption-help{width:100%}.slice{grid-template-columns:1fr}.cash-control{padding:1rem}.readout{padding:.9rem 1rem;border-left:0;border-top:1px solid var(--rule);grid-template-columns:1fr auto;align-items:center}.readout strong{grid-column:2;grid-row:1/3;font-size:2.2rem}.readout small{font-size:.6rem;max-width:24ch}.readout>span{font-size:.74rem;max-width:28ch}.surface-footer{padding:.7rem;gap:.6rem;flex-wrap:wrap}.surface-footer details{max-width:100%;width:100%}.table-toggle{width:100%}}
</style>
