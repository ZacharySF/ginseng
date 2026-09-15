<script lang="ts">
 import { onDestroy } from 'svelte';
 import '$lib/chart-lab.css';
 import { NumericalStore, type PrecisionResult, type RiskSurface as SurfaceData } from '$lib/numerics.svelte';
 import RiskSurface from './RiskSurface.svelte';
 let { request, endpoint, supported = true }: {request:object;endpoint:string;supported?:boolean}=$props();
 const precision=new NumericalStore<PrecisionResult>();
 const surface=new NumericalStore<SurfaceData>();
 const inputKey=$derived(JSON.stringify({request,endpoint,supported}));
 $effect(()=>{inputKey;precision.reset();surface.reset();});
 onDestroy(()=>{precision.reset();surface.reset();});
 const percent=(value:number)=>(100*value).toFixed(2)+'%';
</script>
<section class="numerical-panel" aria-labelledby="numerical-title">
 <header><div><p class="lab-kicker">Risk laboratory / historical model</p><h2 id="numerical-title">How does extra cash change your risk?</h2></div><span class="tag">CASH SENSITIVITY</span></header>
 <p class="intro">Find when cash gets tight and how an opening cash cushion changes the outcome.</p>
 {#if !supported}<p class="unsupported">This analysis needs an unweighted historical forecast of up to 60 days. Use complete classified history, or explore the synthetic demo with stress weighting disabled.</p>
 {:else}
 <div class="precision">
  <div><h3>Check the estimate</h3><p>Refine shortfall probability to a target of ±0.5 percentage points.</p></div>
  <button class="lab-button" disabled={precision.loading} onclick={()=>precision.run(endpoint,request,'precision')}>{precision.loading?'Refining estimate…':'Refine estimate'}</button>
  {#if precision.loading}<p class="full-row" role="status">Calculating independent simulations within the 65,536-observation limit…</p>{/if}
  {#if precision.error}<p class="error" role="alert">{precision.error} You can retry the estimate.</p>{/if}
  {#if precision.data}
   {@const s=precision.data.summary}
   <div class="result" aria-live="polite"><div><small>Refined shortfall chance</small><strong>{percent(s.cash_shortfall_probability)}</strong></div><div><small>95% numerical interval</small><strong>{percent(s.numerical_probability_interval[0])}–{percent(s.numerical_probability_interval[1])}</strong></div><div><small>{s.actual_n.toLocaleString()} observations</small><strong class="status">{s.precision_met?'Precision target reached':'Computation limit reached'}</strong></div></div>
   <details class="precision-notes"><summary>What this interval means</summary><p>{precision.data.scope} {#if !s.precision_met}The interval remains wider than requested.{/if} This measures simulation uncertainty under the current model. It refines the strict-negative end-of-day failure estimate; reserve and funding calculations remain separate.</p></details>
  {/if}
 </div>
 <div class="surface-heading"><div><p class="lab-kicker">Interactive model</p><h3>Cash × time × risk</h3><p>{surface.data?`${surface.data.paths.toLocaleString()} shared simulations. `:''}Follow one cash level or explore the whole surface.</p></div><button class="primary" disabled={surface.loading} onclick={()=>surface.run(endpoint,request,'surface')}>{surface.loading?'Building surface…':surface.data?'Recalculate surface':'Explore in 3D'}</button></div>
 {#if surface.loading}<p class="loading" role="status">Calculating risk and deficit severity across the cash grid…</p>{/if}
 {#if surface.error}<p class="error" role="alert">{surface.error} You can retry the surface.</p>{/if}
 {#if surface.data}{#key surface.data.input_id}<RiskSurface data={surface.data}/>{/key}
 {:else if !surface.loading}<div class="empty"><div class="lab-axis-key" aria-label="Surface axes"><div><span class="axis-letter">X</span><div><strong>Forecast day</strong><small>When risk changes</small></div></div><div><span class="axis-letter">Y</span><div><strong>Extra cash</strong><small>Your opening cushion</small></div></div><div><span class="axis-letter">Z</span><div><strong>Shortfall risk</strong><small>Chance or severity</small></div></div></div><p>Build the surface to compare cash cushions across your forecast. Each point comes from the active historical model.</p></div>{/if}
 {/if}
</section>
<style>
 .numerical-panel{padding:clamp(1rem,3vw,2rem);background:var(--paper);border-top:1px solid var(--rule);color:var(--ink);min-width:0}header{display:flex;justify-content:space-between;align-items:center;gap:1rem}.tag{font-family:var(--font-mono);font-size:.63rem;letter-spacing:.08em;color:var(--cobalt);border:1px solid var(--rule);padding:.45rem .65rem;white-space:nowrap}h2{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:500;letter-spacing:-.025em;line-height:1.15;margin-top:.45rem}h3{font-size:1.1rem;font-weight:600}p{line-height:1.45}.intro{max-width:70ch;margin:.8rem 0 1.4rem;color:var(--ink-soft)}.precision{display:grid;grid-template-columns:1fr auto;gap:.85rem;padding:1rem 1.15rem;border:1px solid var(--rule)}.precision p,.surface-heading>div>p:last-child{color:var(--ink-soft);font-size:.9rem;margin-top:.25rem}.precision>.lab-button{align-self:center}.primary{min-height:2.75rem;padding:.55rem 1rem;border:1px solid var(--cobalt);background:var(--cobalt);color:var(--on-accent);font:.72rem var(--font-mono);cursor:pointer;align-self:center;white-space:nowrap}button:disabled{cursor:wait}.result{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--rule);padding-top:.9rem;gap:1rem}.result>div{display:grid;gap:.35rem}small{font-family:var(--font-mono);color:var(--ink-soft);font-size:.62rem;text-transform:uppercase;letter-spacing:.025em}.result strong{font-size:1.65rem;font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums;color:var(--cobalt)}.result .status{font-size:.97rem;align-self:center;color:var(--ink)}.precision-notes,.full-row,.error{grid-column:1/-1}.precision-notes{border-top:1px solid var(--rule);padding-top:.5rem}.precision-notes summary{font:.65rem var(--font-mono);cursor:pointer;color:var(--ink-soft);padding:.3rem 0}.precision-notes p{max-width:90ch;font-size:.82rem}.error{color:var(--negative)!important;padding:.65rem 0}.surface-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin:1.7rem 0 1rem}.surface-heading h3{font-size:1.35rem;font-weight:500;margin-top:.3rem}.empty{border:1px solid var(--rule);background:var(--lab-scene)}.empty>p{padding:1.2rem;color:var(--ink-soft);max-width:65ch;font-size:.9rem}.unsupported,.loading{padding:1rem;background:var(--paper-soft);font-size:.9rem}@media(max-width:42rem){.tag{display:none}.precision{grid-template-columns:1fr;padding:.9rem}.precision>.lab-button{justify-self:start}.result{grid-template-columns:1fr 1fr;gap:.9rem}.result>div:last-child{grid-column:1/-1;grid-template-columns:1fr 1fr;border-top:1px solid var(--rule);padding-top:.75rem;align-items:center}.result strong{font-size:1.35rem}.result .status{font-size:.9rem}.result small{font-size:.57rem}.surface-heading{align-items:start;flex-direction:column}.surface-heading button{align-self:start;width:100%}.surface-heading h3{font-size:1.25rem}}
</style>
