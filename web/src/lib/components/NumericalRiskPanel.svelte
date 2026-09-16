<script lang="ts">
 import { onDestroy } from 'svelte';
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
 <header><div><p class="eyebrow">Risk laboratory / historical model</p><h2 id="numerical-title">How much cash changes the outlook?</h2></div><span class="tag">NUMERICAL ANALYSIS</span></header>
 <p class="intro">Refine the current shortfall estimate, then explore how extra cash changes both the chance and severity of a shortfall over time.</p>
 {#if !supported}<p class="unsupported">This analysis needs an unweighted historical forecast of up to 60 days. Use complete classified history, or explore the synthetic demo with stress weighting disabled.</p>
 {:else}
 <div class="precision">
  <div><h3>Simulation precision</h3><p>A 95% numerical interval for the current cash-shortfall probability. Target: ±0.5 percentage points.</p></div>
  <button disabled={precision.loading} onclick={()=>precision.run(endpoint,request,'precision')}>{precision.loading?'Refining estimate…':'Refine estimate'}</button>
  {#if precision.loading}<p role="status">Calculating independent simulations within the 65,536-observation limit…</p>{/if}
  {#if precision.error}<p class="error" role="alert">{precision.error} You can retry the estimate.</p>{/if}
  {#if precision.data}
   {@const s=precision.data.summary}
   <div class="result" aria-live="polite"><div><small>Refined shortfall chance</small><strong>{percent(s.cash_shortfall_probability)}</strong></div><div><small>95% numerical interval</small><strong>{percent(s.numerical_probability_interval[0])}–{percent(s.numerical_probability_interval[1])}</strong></div><div><small>{s.actual_n.toLocaleString()} observations</small><strong class="status">{s.precision_met?'Precision target reached':'Computation limit reached'}</strong></div></div>
   <p class="scope">{precision.data.scope} {#if !s.precision_met}The interval remains wider than requested.{/if} This refines the strict-negative end-of-day failure estimate; it does not replace reserve or funding calculations.</p>
  {/if}
 </div>
 <div class="surface-heading"><div><h3>Cash × time × risk</h3><p>Two views of the same 2,048 simulated futures. Extra cash is available on day one.</p></div><button disabled={surface.loading} onclick={()=>surface.run(endpoint,request,'surface')}>{surface.loading?'Building surface…':surface.data?'Recalculate surface':'Explore in 3D'}</button></div>
 {#if surface.loading}<p role="status">Calculating risk and deficit severity across the cash grid…</p>{/if}
 {#if surface.error}<p class="error" role="alert">{surface.error} You can retry the surface.</p>{/if}
 {#if surface.data}{#key surface.data.input_id}<RiskSurface data={surface.data}/>{/key}
 {:else if !surface.loading}<div class="empty"><span>X / time</span><span>Y / extra cash</span><span>Z / risk or deficit</span><p>Find when risk first rises, and how much additional cash reduces it. Every point is calculated from your active historical model.</p></div>{/if}
 {/if}
</section>
<style>
 .numerical-panel{padding:clamp(1rem,3vw,2rem);background:var(--paper);border-top:1px solid var(--rule);color:var(--ink);min-width:0}header{display:flex;justify-content:space-between;align-items:center;gap:1rem}.eyebrow,.tag{font-family:var(--font-mono);font-size:.68rem;letter-spacing:.07em;color:var(--ink-soft)}.eyebrow{margin-bottom:.4rem}h2{font-size:clamp(1.5rem,3vw,2.2rem);letter-spacing:-.035em}h3{font-size:1.1rem}p{line-height:1.45}.intro{max-width:70ch;margin:.8rem 0 1.5rem;color:var(--ink-soft)}.precision{display:grid;grid-template-columns:1fr auto;gap:1rem;padding:1.2rem;background:var(--paper-soft);border:1px solid var(--rule)}.precision p,.surface-heading p{color:var(--ink-soft);font-size:.9rem;margin-top:.35rem}button{min-height:2.75rem;padding:.5rem 1rem;border:1px solid var(--cobalt);background:var(--cobalt);color:var(--on-accent);font:inherit;cursor:pointer;align-self:center}button:disabled{cursor:wait}.result{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;border-block:1px solid var(--rule);padding:1rem 0}.result>div{display:grid;gap:.4rem}small{font-family:var(--font-mono);color:var(--ink-soft);font-size:.68rem}.result strong{font-size:1.6rem;letter-spacing:-.025em}.result .status{font-size:1rem;align-self:center}.scope,.error{grid-column:1/-1}.error{color:var(--negative)!important}.surface-heading{display:flex;justify-content:space-between;align-items:center;gap:1rem;margin:1.5rem 0 1rem}.empty{padding:2rem;border:1px dashed var(--rule-strong);background:var(--paper-soft)}.empty span{font-family:var(--font-mono);font-size:.75rem;color:var(--cobalt);display:inline-block;margin:0 1rem .8rem 0}.empty p{color:var(--ink-soft);max-width:65ch}.unsupported{padding:1rem;background:var(--paper-soft)}@media(max-width:42rem){.tag{display:none}.precision{grid-template-columns:1fr}.result{grid-template-columns:1fr}.surface-heading{align-items:start;flex-direction:column}.surface-heading button{align-self:start}}
</style>
