import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-finance-test-'));
after(() => rm(temporary, {recursive:true, force:true}));
await symlink(join(root,'node_modules'), join(temporary,'node_modules'),'dir');
globalThis.window = {addEventListener(){}, removeEventListener(){}};
await writeFile(join(temporary,'mocks.mjs'), `
export const browser=true;
export const authStore={user:{id:'owner-a'},status:'signed-in'};
export const supabase=null;
export const WORKSPACE_SAVED_EVENT='workspace-saved';
export const calls=[];
export function forecastFinance(request){return new Promise(resolve=>calls.push({request:structuredClone(request),resolve}));}
export const loadedWorkspace={revision:1,inputs:{policy:{operating_buffer_cents:100000},scenarios:[]}};
export async function getFinanceWorkspace(){return {status:'ok',data:loadedWorkspace};}
export function saveFinanceWorkspace(){};
export const backtests=[];
export function runBacktest(request){return new Promise(resolve=>backtests.push({request:structuredClone(request),resolve}));}
`);
let source=ts.transpileModule(await readFile(join(root,'src/lib/finance.svelte.ts'),'utf8'),{
 compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}
}).outputText;
source=source.replace(/from ['"][^'"]+['"]/g,"from './mocks.mjs'");
await writeFile(join(temporary,'store.mjs'),compileModule(source,{generate:'client'}).js.code);
const {FinancialStore}=await import(pathToFileURL(join(temporary,'store.mjs')).href);
const {calls,authStore,backtests}=await import(pathToFileURL(join(temporary,'mocks.mjs')).href);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(){
 authStore.user={id:'owner-a'};
 const store=new FinancialStore();
 store.workspace={revision:1,inputs:{policy:{operating_buffer_cents:100000},scenarios:[]}};
 return store;
}
function complete(call,marker){call.resolve({status:'ok',data:{baseline:{marker},preview:null,changes:[]}});}

test('a workspace conflict invalidates a historical check still in flight',async()=>{
 const store=setup(),start=calls.length,index=backtests.length;
 const historical=store.backtest();
 const forecast=store.refresh();
 calls[start].resolve({status:'engine-error',http_status:409,message:'Workspace changed'});
 await forecast;
 assert.equal(store.accuracyLoading,false);
 backtests[index].resolve({status:'ok',data:{marker:'obsolete-evidence'}});
 await historical;
 assert.equal(store.accuracy,null);
});

test('personal edits coalesce and superseded results never become ready',async()=>{
 const store=setup(),start=calls.length;
 const pending=store.refresh();
 void store.setPolicy({operating_buffer_cents:200000});
 void store.setPolicy({operating_buffer_cents:300000});
 assert.equal(calls.length,start+1);
 complete(calls[start],'obsolete');await tick();
 assert.equal(store.forecast,null);
 assert.equal(store.forecastStatus,'loading');
 assert.equal(calls.length,start+2);
 assert.equal(calls[start+1].request.overrides.policy.operating_buffer_cents,300000);
 complete(calls[start+1],'latest');await pending;
 assert.equal(store.forecast.marker,'latest');
 assert.equal(store.forecastStatus,'ready');
});

test('an owner reset discards the pending forecast and queued edits',async()=>{
 const store=setup(),start=calls.length;
 const pending=store.refresh();
 void store.setPolicy({operating_buffer_cents:200000});
 store.reset();authStore.user={id:'owner-b'};
 complete(calls[start],'private-old-owner');await pending;
 assert.equal(store.forecast,null);
 assert.equal(calls.length,start+1);
});

test('a queued latest request can recover after an obsolete timeout',async()=>{
 const store=setup(),start=calls.length;
 const pending=store.refresh();
 void store.setPolicy({operating_buffer_cents:500000});
 calls[start].resolve({status:'engine-unreachable',message:'Timed out'});await tick();
 assert.equal(store.forecastError,null);
 complete(calls[start+1],'recovered');await pending;
 assert.equal(store.forecast.marker,'recovered');
});

test('comparison changes coalesce while the active forecast finishes first',async()=>{
 const store=setup(),start=calls.length;
 store.workspace.inputs.scenarios=[{id:'one',name:'One',overrides:{mode:'scheduled'}},{id:'two',name:'Two',overrides:{mode:'history'}}];
 const comparison=store.compareScenario('one');
 const forecast=store.refresh();
 assert.equal(calls.length,start+2);
 complete(calls[start+1],'forecast');await forecast;
 const latest=store.compareScenario('two');
 assert.equal(calls.length,start+2); // no third simultaneous request
 complete(calls[start],'obsolete-comparison');await tick();
 assert.equal(store.comparison,null);
 assert.equal(calls.length,start+3);
 assert.equal(calls[start+2].request.overrides.mode,'history');
 complete(calls[start+2],'latest-comparison');await Promise.all([comparison,latest]);
 assert.equal(store.comparison.marker,'latest-comparison');
});

test('an account switch starts a new forecast without waiting for the previous account',async()=>{
 const store=setup(),start=calls.length;
 const old=store.refresh();
 authStore.user={id:'owner-b'};
 const loaded=store.load();await tick();
 assert.equal(calls.length,start+2);
 complete(calls[start],'old-private-data');await old;
 assert.equal(store.forecast,null);
 complete(calls[start+1],'new-owner');await loaded;
 assert.equal(store.forecast.marker,'new-owner');
 assert.equal(calls.length,start+2);
});

test('historical checks use the preview policy and discard evidence after a policy edit',async()=>{
 const store=setup(),start=calls.length,index=backtests.length;
 store.scenario={policy:{operating_buffer_cents:200000,coverage_target:.8}};
 const checked=store.backtest();
 assert.equal(backtests[index].request.policy.coverage_target,.8);
 const forecast=store.setPolicy({coverage_target:.9});
 backtests[index].resolve({status:'ok',data:{nominal_coverage:.8}});await checked;
 assert.equal(store.accuracy,null);
 assert.equal(store.accuracyLoading,false);
 complete(calls[start],'latest');await forecast;
});
