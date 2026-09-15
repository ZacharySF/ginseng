// Real component/browser test using frozen synthetic engine output and mocked transport.
import assert from 'node:assert/strict';
import { checkKeyboardOrbit } from './helpers/graph-camera.mjs';
import {mkdtemp,readFile,writeFile,symlink,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {svelte} from '@sveltejs/vite-plugin-svelte';
import {chromium} from 'playwright';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const temp=await mkdtemp(join(tmpdir(),'ginseng-risk-browser-'));
await symlink(join(root,'node_modules'),join(temp,'node_modules'),'dir');
await writeFile(join(temp,'package.json'),'{"type":"module"}');
await writeFile(join(temp,'index.html'),'<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"/></head><body><div id="app"></div><script type="module" src="/main.ts"></script></body></html>');
await writeFile(join(temp,'mock-api.ts'),`export async function requestEngine(path,init){try{const r=await fetch('/mock'+path,init);return r.ok?{status:'ok',data:await r.json()}:{status:'engine-error',message:'The engine is busy. Try again.'};}catch{return {status:'engine-error',message:'Cancelled'};}}`);
await writeFile(join(temp,'main.ts'),`import {mount} from 'svelte';import Panel from '${root}/src/lib/components/NumericalRiskPanel.svelte';import '${root}/src/app.css';import '@fontsource-variable/archivo-narrow';mount(Panel,{target:document.getElementById('app'),props:{request:{seed:42},endpoint:'/demo/numerics'}});`);
const fixture=JSON.parse(await readFile(join(root,'tests/fixtures/risk-explorer.json'),'utf8'));
const server=await createServer({configFile:false,root:temp,plugins:[svelte({configFile:false})],resolve:{alias:{'$lib':join(root,'src/lib'),'./api':join(temp,'mock-api.ts')},dedupe:['svelte']},server:{port:0,host:'127.0.0.1',fs:{allow:[root,temp]}}});
let browser;
try{
 await server.listen();const address=server.httpServer.address();
 browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1280,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let fail=false;
 await page.route('**/mock/demo/numerics',async route=>{const {options}=route.request().postDataJSON();await route.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify(fixture[options.action])});});
 await page.goto(`http://127.0.0.1:${address.port}`);
 await page.getByRole('button',{name:'Refine estimate',exact:true}).click();
 await page.getByText('Precision target reached',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Explore in 3D'}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?._fullLayout?.scene?._scene?.glplot);
 assert.equal(await page.locator('.surface-workbench .lab-axis-key > div').count(),3,'each axis has an external reading key');
 assert.equal(await page.locator('.surface-footer details[open]').count(),0,'method notes start collapsed');
 assert.deepEqual(await page.locator('.plot').evaluate(el=>el.data[0].z),fixture.surface.shortfall_probability,'camera and styling preserve every calculated grid value');
 assert.equal(await page.locator('.plot').evaluate(el=>el.data[0].cmax),1,'probability color scale stays0–100%');
 assert.ok(await page.locator('.height-scale').isVisible(),'adaptive vertical scale is explicitly labeled');
 assert.equal(await page.locator('.plot').evaluate(el=>el.layout.paper_bgcolor),'#071321','light application still uses a navy plotting instrument');
 assert.equal(await page.locator('.plot').evaluate(el=>el.layout.font.color),'#e3faff','graph labels use local instrument colors');
 const wire=await page.locator('.plot').evaluate(el=>{const t=el.data.find(trace=>trace.name==='Sampled grid');return {x:t.x,y:t.y,z:t.z,color:t.line.color};});
 assert.equal(wire.color,'#359aff','cash surface has a visible blue wire grid');
 const expected={x:[],y:[],z:[]};
 const append=(day,cash,value)=>{expected.x.push(day);expected.y.push(cash);expected.z.push(value);};
 const separator=()=>append(null,null,null);
 for(let row=0;row<fixture.surface.additional_cash.length;row++){
  for(let column=0;column<fixture.surface.days.length;column++)append(fixture.surface.days[column],fixture.surface.additional_cash[row],fixture.surface.shortfall_probability[row][column]);
  separator();
 }
 for(let column=0;column<fixture.surface.days.length;column++){
  for(let row=0;row<fixture.surface.additional_cash.length;row++)append(fixture.surface.days[column],fixture.surface.additional_cash[row],fixture.surface.shortfall_probability[row][column]);
  separator();
 }
 assert.deepEqual({x:wire.x,y:wire.y,z:wire.z},expected,'mesh rows and columns use every original node without invented heights');
 const gizmoBefore=await page.locator('.orientation-gizmo').innerHTML();
 const original=await page.locator('.plot').evaluate(el=>el.layout.scene.camera);
 const plot=page.locator('.plot');const box=await plot.boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.6,{steps:12});await page.mouse.up();
 assert.equal(await plot.evaluate(el=>document.activeElement===el),true,'pointer interaction focuses the chart for keyboard controls');
 const rotated=await plot.evaluate(el=>el.layout.scene.camera);
 assert.notDeepEqual(rotated,original,'drag changes 3D camera');
 await page.waitForFunction(before=>document.querySelector('.orientation-gizmo')?.innerHTML!==before,gizmoBefore);
 assert.notEqual(await page.locator('.orientation-gizmo').innerHTML(),gizmoBefore,'orientation triad follows the real camera');
 await page.getByRole('button',{name:'Reset view'}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout.scene.camera.eye.x===1.5);
 await checkKeyboardOrbit(page,'.plot',{
  reset:'Reset view',flat:'Overhead',perspective:'3D view',control:'#cash-slice',
  metrics:()=>plot.evaluate(el=>({grid:el.data[0].z,selectedCash:el.data[1].y,selectedValues:el.data[1].z}))
 });
 assert.equal(await page.getByRole('button',{name:'Shortfall chance',exact:true}).getAttribute('aria-pressed'),'true','camera controls preserve the selected surface metric');
 await page.getByRole('button',{name:'Overhead',exact:true}).click();
 await page.waitForFunction(()=>{const c=document.querySelector('.plot')?.layout.scene.camera;return c?.eye.z===1.55&&c?.projection.type==='orthographic';});
 assert.equal(await plot.evaluate(el=>el.data[0].showscale),true,'overhead colors retain the numerical scale');
 const shots=process.env.RISK_SCREENSHOTS;
 if(shots){await mkdir(shots,{recursive:true});await page.screenshot({path:join(shots,'risk-overhead.png'),fullPage:true});}
 await page.getByRole('button',{name:'Cash slice',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout.scene.camera.eye.y===-2.65);
 assert.equal(await plot.evaluate(el=>el.data[0].opacity),.12,'cash slice keeps selected line legible through the surface');
 const cameraBeforeSlider=await plot.evaluate(el=>el.layout.scene.camera);
 await page.getByRole('slider').focus(); await page.keyboard.press('Home'); for(let i=0;i<8;i++) await page.keyboard.press('ArrowRight');
 assert.equal(await page.getByRole('slider').inputValue(),'8','native slider arrows change the cash selection');
 assert.deepEqual(await plot.evaluate(el=>el.layout.scene.camera),cameraBeforeSlider,'native slider arrows do not orbit the camera');
 await page.getByRole('button',{name:'Deficit severity',exact:true}).click();
 await page.getByRole('button',{name:'Show exact cash slice table'}).click();
 assert.equal(await page.locator('tbody tr').count(),30);
 assert.equal(await plot.evaluate(el=>el.data[0].z[8][29]),fixture.surface.expected_max_deficit[8][29]);
 assert.equal(await plot.evaluate(el=>el.data.find(t=>t.name==='Sampled grid').z[8*31+29]),fixture.surface.expected_max_deficit[8][29],'wire geometry follows the chosen metric');
 assert.equal(await plot.evaluate(el=>el.data[1].y[0]),fixture.surface.additional_cash[8],'highlight follows selected cash');
 await page.getByRole('button',{name:'Hide exact cash slice table'}).click();
 await page.getByRole('button',{name:'3D view',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout.scene.camera.eye.x===1.5);
 if(shots) await page.screenshot({path:join(shots,'risk-deficit.png'),fullPage:true});
 await page.getByRole('button',{name:'Shortfall chance',exact:true}).click();
 await page.waitForFunction(value=>document.querySelector('.plot')?.data[0].z[8][29]===value,fixture.surface.shortfall_probability[8][29]);
 assert.equal(await page.locator('.readout strong').textContent(),`${(100*fixture.surface.shortfall_probability[8][29]).toFixed(1)}%`,'inspector reports the actual selected end-of-horizon value');
 if(shots){await page.screenshot({path:join(shots,'risk-light.png'),fullPage:true});await page.locator('.surface-workbench').screenshot({path:join(shots,'risk-wireframe.png')});}
 // Theme uses the actual store, so plot colors update along with CSS.
 await page.evaluate(async root=>{const m=await import('/@fs'+root+'/src/lib/theme.svelte.ts');m.themeStore.toggle();},root);
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout?.paper_bgcolor==='#050e1a');
 if(shots) await page.screenshot({path:join(shots,'risk-dark.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.waitForFunction(()=>{const el=document.querySelector('.plot');return el?._fullLayout?.width<=el.clientWidth+1;});
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout?.scene?.camera?.eye?.x===2.15);
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'mobile has no horizontal overflow');
 await page.waitForTimeout(700);
 assert.ok(Math.abs((await plot.evaluate(el=>el._fullLayout.scene._scene.getCamera().eye.x))-2.15)<1e-6);
 if(shots) await page.screenshot({path:join(shots,'risk-mobile.png'),fullPage:true});
 await page.getByRole('button',{name:'Overhead',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout.scene.camera.eye.z===2.2);
 await page.getByRole('button',{name:'3D view',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout.scene.camera.eye.x===2.15);
 await page.evaluate(async root=>{const m=await import('/@fs'+root+'/src/lib/theme.svelte.ts');m.themeStore.toggle();},root);
 await page.waitForFunction(()=>document.querySelector('.plot')?.layout?.paper_bgcolor==='#071321');
 if(shots) await page.screenshot({path:join(shots,'risk-mobile-light.png'),fullPage:true});
 fail=true;await page.getByRole('button',{name:'Refine estimate',exact:true}).click();await page.getByRole('alert').first().waitFor();
 assert.equal(await page.getByText('Precision target reached',{exact:true}).count(),0);
 assert.deepEqual(errors,[]);
 console.log('Browser passed: precision,exact wire-mesh geometry,navy instrument frame,camera-synced triad,pointer and keyboard rotation/reset,focus/native-slider isolation,perspective and orthographic presets,metric toggle,exact slice,selected inspector,both themes,mobile layout and error state.');
}finally{if(browser)await browser.close();await server.close();await rm(temp,{recursive:true,force:true});}
