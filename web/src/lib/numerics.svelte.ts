import { requestEngine } from './api';
export interface PrecisionOptions {
 absolute_error: number; confidence: number; max_paths: number; time_limit_seconds: number;
 estimator: 'path' | 'initial-block-cmc';
}
export interface PrecisionResult {
 kind: 'precision'; input_id: string; method: string; scope: string;
 summary: { cash_shortfall_probability: number | null; numerical_probability_interval: [number,number];
  absolute_error_bound: number | null; requested_absolute_error: number; confidence: number;
  precision_met: boolean; stop_reason: string; actual_n: number; interval_observations?: number; model_identity?: string;
  status?: 'precision_met' | 'budget_exhausted' | 'cancelled' | 'unsupported_estimator' | 'numerical_failure' };
}
export interface RiskSurface {
 kind: 'surface'; input_id: string; days: number[]; additional_cash: number[]; opening_cash: number;
 shortfall_probability: number[][]; expected_max_deficit: number[][]; paths: number; scope: string;
}
export class NumericalStore<T> {
 data = $state<T | null>(null); loading = $state(false); error = $state('');
 #sequence = 0; #controller: AbortController | null = null;
 reset() { this.#sequence++; this.#controller?.abort(); this.data=null; this.loading=false; this.error=''; }
 async run(endpoint: string, request: object, action: 'surface' | 'precision', options: Partial<PrecisionOptions> = {}) {
  this.reset(); const sequence=this.#sequence; this.#controller=new AbortController(); this.loading=true;
  const result=await requestEngine<T>(endpoint, { method:'POST', headers:{'content-type':'application/json'},
   body:JSON.stringify({...request,options:{...options,action}}),signal:this.#controller.signal },{requiresAuth:true,timeoutMs:60000});
  if(sequence!==this.#sequence) return;
  this.loading=false;
  if(result.status==='ok') this.data=result.data; else this.error=result.message;
 }
}
