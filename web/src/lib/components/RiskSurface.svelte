<script lang="ts">
 import { onMount } from 'svelte';
 import type { RiskSurface } from '$lib/numerics.svelte';
 import { themeStore } from '$lib/theme.svelte';
 import { formatCurrency } from '$lib/format';
 import type * as PlotlyType from 'plotly.js';
 let { data }: { data: RiskSurface } = $props();
 let chart: HTMLDivElement;
 let plotly = $state<typeof PlotlyType | null>(null);
 let metric = $state<'risk' | 'deficit'>('risk');
 let cashIndex = $state(0);
 let table = $state(false);
 let error = $state('');
 let narrow = $state(false);
 let lastNarrow: boolean | null = null;
 const values = $derived(metric === 'risk' ? data.shortfall_probability : data.expected_max_deficit);
 const label = $derived(metric === 'risk' ? 'Shortfall chance' : 'Expected worst deficit');
 const display = (v: number) => metric === 'risk' ? `${(100*v).toFixed(1)}%` : formatCurrency(v);
 const camera = {eye:{x:1.55,y:1.65,z:1.1}};
 const mobileCamera = {eye:{x:2.6,y:2.8,z:2.0}};
 onMount(() => {
  let active=true;
  narrow=chart.clientWidth<600;
  import('plotly.js-gl3d-dist-min').then(m=>{if(active) plotly=m.default;}).catch(()=>{if(active) error='The 3D renderer could not load. Use the cash slice table below.';});
  const resize=new ResizeObserver(()=>{narrow=chart.clientWidth<600;if(plotly && chart) void Promise.resolve(plotly.Plots.resize(chart)).catch(()=>{});});
  resize.observe(chart);
  return ()=>{active=false;resize.disconnect();if(plotly) plotly.purge(chart);};
 });
 $effect(()=>{
  const theme=themeStore.current;
  const p=plotly; const z=values; const d=data; const index=cashIndex; const title=label;
  if(!p || !chart) return;
  const style=getComputedStyle(document.documentElement);
  const color=(name:string)=>style.getPropertyValue(name).trim();
  const paper=color('--paper'), ink=color('--ink'), rule=color('--rule'), accent=color('--cobalt');
  const axis={gridcolor:rule,zerolinecolor:rule,color:ink,showbackground:true,backgroundcolor:paper};
  let active=true;
  const resetCamera = lastNarrow !== narrow; lastNarrow=narrow;
  const targetCamera = structuredClone(narrow?mobileCamera:camera);
  void p.react(chart,[{
   type:'surface',x:d.days,y:d.additional_cash,z,showscale:true,
   colorscale:[[0,theme==='dark'?'#17172c':'#e5e8fc'],[0.5,theme==='dark'?'#6565dc':'#5555d8'],[1,accent]],
   cmin:0,...(metric==='risk'?{cmax:1}:{}),
   colorbar:{thickness:10,len:.65,tickformat:metric==='risk'?'.0%': '$,.0f'},
   hovertemplate:`Day %{x}<br>Extra opening cash $%{y:,.0f}<br>${title}: %{z:${metric==='risk'?'.1%':'$,.2f'}}<extra></extra>`,
   contours:{z:{show:true,usecolormap:true,project:{z:true}}},
  },{type:'scatter3d',mode:'lines',x:d.days,y:d.days.map(()=>d.additional_cash[index]),z:z[index],
    line:{color:color('--negative'),width:6},showlegend:false,hoverinfo:'skip'}] as PlotlyType.Data[],{
    autosize:true,height:narrow?360:440,margin:{l:5,r:35,b:55,t:5},paper_bgcolor:paper,font:{color:ink,family:'Archivo Narrow, sans-serif'},
    uirevision:d.input_id+':'+narrow,scene:{camera:narrow?mobileCamera:camera,aspectmode:'manual',aspectratio:{x:1.4,y:1.2,z:.85},
     xaxis:{...axis,title:{text:narrow?'Day':'Forecast day'}},yaxis:{...axis,title:{text:narrow?'Extra cash':'Extra opening cash ($)'},tickprefix:'$',nticks:narrow?4:undefined,tickfont:{size:narrow?10:12}},
     zaxis:{...axis,title:{text:narrow?(metric==='risk'?'Chance':'Deficit ($)'):title},tickformat:metric==='risk'?'.0%':'$,.0f',...(metric==='risk'?{range:[0,1]}:{rangemode:'tozero'})}}
   },{responsive:true,displaylogo:false,displayModeBar:false,scrollZoom:false})
   .then(()=>{if(active && resetCamera) return p.relayout(chart,{'scene.camera':targetCamera} as unknown as Partial<PlotlyType.Layout>);})
   .catch(()=>{if(active) error='3D is unavailable in this browser. The cash slice table still shows the calculated values.';});
  return ()=>{active=false;};
 });
</script>

<div class="surface-workbench">
 <div class="controls">
  <div class="tabs" aria-label="Surface metric">
   <button class:active={metric==='risk'} aria-pressed={metric==='risk'} onclick={()=>metric='risk'}>Shortfall chance</button>
   <button class:active={metric==='deficit'} aria-pressed={metric==='deficit'} onclick={()=>metric='deficit'}>Deficit severity</button>
  </div>
  <button onclick={()=>{if(plotly) void plotly.relayout(chart,{'scene.camera':narrow?mobileCamera:camera} as unknown as Partial<PlotlyType.Layout>);}}>Reset view ↗</button>
 </div>
 <p class="guide">X · forecast day <span>Y · extra opening cash</span> Z · {label.toLowerCase()}</p>
 <div class="plot" class:narrow bind:this={chart} role="img" aria-label={`${label} across forecast days and additional opening cash. Exact values are available in the cash slice table.`}></div>
 {#if !plotly && !error}<p role="status">Loading interactive 3D view…</p>{/if}
 {#if error}<p role="alert">{error}</p>{/if}
 {#if data.shortfall_probability.every(row=>row.every(value=>value===0))}<p class="hint">No shortfalls were observed on this grid. A flat zero surface does not establish zero underlying risk; refine the probability estimate for its numerical interval.</p>{/if}
 <p class="hint">Drag to rotate · pinch to zoom · the highlighted line follows your cash selection. The surface joins sampled grid points; it is not a precise boundary.</p>
 <div class="slice">
  <label for="cash-slice">Explore extra opening cash <strong>{formatCurrency(data.additional_cash[cashIndex])}</strong></label>
  <input id="cash-slice" aria-label="Extra opening cash slice" type="range" min="0" max={data.additional_cash.length-1} step="1" bind:value={cashIndex}/>
  <div class="readout"><span>By day {data.days.at(-1)}</span><strong>{display(values[cashIndex].at(-1) ?? 0)}</strong><span>{label.toLowerCase()}</span></div>
 </div>
 <button class="table-toggle" aria-expanded={table || !!error} onclick={()=>table=!table}>{table?'Hide':'Show'} exact cash slice table</button>
 {#if table || error}<div class="table-scroll"><table><caption>{label} with {formatCurrency(data.additional_cash[cashIndex])} extra cash from day one</caption><thead><tr><th>Forecast day</th><th>{label}</th></tr></thead><tbody>{#each data.days as day,i}<tr><td>{day}</td><td>{display(values[cashIndex][i])}</td></tr>{/each}</tbody></table></div>{/if}
 <p class="scope">{data.scope} “By day” includes earlier shortfalls, even if cash later recovers. Deficit severity averages the worst cash deficit across all paths.</p>
</div>
<style>
 .surface-workbench{border:1px solid var(--rule);background:var(--paper);min-width:0}.controls{display:flex;justify-content:space-between;gap:.5rem;flex-wrap:wrap;padding:.7rem;border-bottom:1px solid var(--rule)}button{min-height:2.6rem;padding:.5rem .8rem;background:var(--paper);color:var(--ink);border:1px solid var(--control-border);font:inherit;cursor:pointer}.tabs{display:flex;gap:.3rem}.active{background:var(--cobalt);color:var(--on-accent)}.guide{display:flex;gap:1rem;flex-wrap:wrap;padding:.8rem 1rem 0;color:var(--ink-soft);font-family:var(--font-mono);font-size:.7rem;text-transform:uppercase}.plot{width:100%;height:440px;overflow:hidden}.plot.narrow{height:360px}.hint,.scope{padding:.6rem 1rem;color:var(--ink-soft);font-size:.85rem;line-height:1.4}.slice{display:grid;grid-template-columns:1fr 1fr auto;align-items:center;gap:1rem;padding:1rem;background:var(--paper-soft);border-block:1px solid var(--rule)}label{display:grid;gap:.3rem;font-size:.85rem}label strong{font-family:var(--font-mono)}input{width:100%;accent-color:var(--cobalt)}.readout{display:grid;gap:.2rem;font-size:.8rem}.readout strong{font-size:1.7rem}.table-toggle{margin:.75rem 1rem}.table-scroll{max-height:18rem;overflow:auto;padding:0 1rem}table{width:100%;border-collapse:collapse;text-align:left;font-family:var(--font-mono);font-size:.8rem}th,td{padding:.5rem;border-bottom:1px solid var(--rule)}caption{text-align:left;padding:.5rem 0;color:var(--ink-soft)}@media(max-width:42rem){.slice{grid-template-columns:1fr}.guide{gap:.4rem}.plot{height:440px}.controls{padding:.5rem}.tabs button{padding:.4rem .6rem}}
</style>
