import assert from 'node:assert/strict';

/** Real browser fullscreen plus the viewport fallback, with numerical invariants. */
export async function checkGraphFullscreen(page, selector, options) {
 const plot = page.locator(selector);
 const stage = plot.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " graph-stage ")]').first();
 const camera = () => plot.evaluate(el => el.layout.scene.camera);
 let metricValues;
 let selection;
 const inlineBox = await plot.boundingBox();
 await plot.focus();
 const initial = await camera();
 await page.keyboard.press('ArrowRight');
 await page.waitForFunction(({ selector, initial }) => {
  const eye = document.querySelector(selector)?.layout?.scene?.camera?.eye;
  return eye && Math.abs(eye.x - initial.eye.x) > 1e-6;
 }, { selector, initial });
 const selectedCamera = await camera();
 const assertPreserved = async () => {
  const currentCamera = await camera();
  for (const axis of ['x', 'y', 'z']) assert.ok(Math.abs(currentCamera.eye[axis] - selectedCamera.eye[axis]) < 1e-6, 'fullscreen preserves the chosen camera eye');
  assert.deepEqual(currentCamera.center, selectedCamera.center, 'fullscreen preserves the camera center');
  assert.deepEqual(currentCamera.up, selectedCamera.up, 'fullscreen preserves camera orientation');
  assert.deepEqual(await options.metrics(), metricValues, 'fullscreen preserves all metric values');
  assert.equal(await page.locator(options.control).inputValue(), selection, 'fullscreen preserves the cash or portfolio selection');
 };
 const waitForLayout = async expanded => {
  await page.waitForFunction(({ selector, expanded, inlineHeight }) => {
   const node = document.querySelector(selector);
   const stage = node?.closest('.graph-stage');
   if (!node?._fullLayout || !stage) return false;
   const bounds = stage.getBoundingClientRect();
   return Math.abs(node._fullLayout.width - node.clientWidth) < 2 &&
    Math.abs(node._fullLayout.height - node.clientHeight) < 2 &&
    (expanded ? bounds.width >= innerWidth - 2 && bounds.height >= innerHeight - 2 && node.clientHeight > inlineHeight + 100 : Math.abs(node.clientHeight - inlineHeight) < 2);
  }, { selector, expanded, inlineHeight: inlineBox.height });
 };
 const waitForNative = async active => page.waitForFunction(({ selector, active }) => {
  const stage = document.querySelector(selector)?.closest('.graph-stage');
  return active ? document.fullscreenElement === stage : document.fullscreenElement === null;
 }, { selector, active });
 const waitForExpanded = async active => page.waitForFunction(({ selector, active }) => {
  const stage = document.querySelector(selector)?.closest('.graph-stage');
  return stage && (stage.dataset.expanded === 'true') === active;
 }, { selector, active });
 // A native form control's F key must never enter fullscreen.
 await page.locator(options.control).focus();
 await page.keyboard.press('f');
 assert.equal(await page.evaluate(() => document.fullscreenElement === null), true);
 await waitForExpanded(false);
 await stage.getByRole('button', { name: 'Fullscreen', exact: true }).focus();
 await page.keyboard.press('f');
 assert.equal(await page.evaluate(() => document.fullscreenElement === null), true, 'F is scoped to the focused plot');
 await plot.focus();
 for (const modifier of ['ctrlKey', 'altKey', 'metaKey']) {
  const prevented = await plot.evaluate((node, modifier) => {
   const event = new KeyboardEvent('keydown', { key: 'f', bubbles: true, cancelable: true, [modifier]: true });
   node.dispatchEvent(event);
   return event.defaultPrevented;
  }, modifier);
  assert.equal(prevented, false, `${modifier}+F remains available to the browser`);
  assert.equal(await page.evaluate(() => document.fullscreenElement), null);
 }
 metricValues = await options.metrics();
 selection = await page.locator(options.control).inputValue();
 // Use actual user activation and Chromium's native Fullscreen API.
 await stage.getByRole('button', { name: 'Fullscreen', exact: true }).click();
 await waitForNative(true);
 await waitForLayout(true);
 await assertPreserved();
 assert.equal(await stage.getByRole('button', { name: 'Exit fullscreen', exact: true }).isVisible(), true);
 await plot.focus();
 await page.keyboard.press('ArrowUp');
 await page.waitForFunction(({ selector, z }) => document.querySelector(selector)?.layout?.scene?.camera?.eye?.z > z + 1e-6, { selector, z: selectedCamera.eye.z });
 await page.keyboard.press('ArrowDown');
 await page.waitForFunction(({ selector, z }) => Math.abs(document.querySelector(selector)?.layout?.scene?.camera?.eye?.z - z) < 1e-6, { selector, z: selectedCamera.eye.z });
 await assertPreserved();
 if (options.screenshot) await page.screenshot({ path: options.screenshot });
 await page.keyboard.press('Escape');
 await waitForNative(false);
 await waitForLayout(false);
 await assertPreserved();
 // Holding F generates repeated keydowns; only its first press toggles.
 await plot.focus();
 await page.keyboard.down('f');
 await waitForNative(true);
 for (let index = 0; index < 3; index++) await page.keyboard.down('f');
 await page.keyboard.up('f');
 await waitForNative(true);
 await waitForLayout(true);
 await assertPreserved();
 await plot.focus();
 await page.keyboard.press('Shift+f');
 await waitForNative(false);
 await waitForLayout(false);
 await assertPreserved();
 // Simulate both an unsupported API and a rejected native request. The
 // component must still provide an accessible expanded viewport and exit.
 for (const failure of ['missing', 'rejected']) {
  await stage.evaluate((node, failure) => Object.defineProperty(node, 'requestFullscreen', {
   configurable: true,
   value: failure === 'missing' ? undefined : () => Promise.reject(new Error('Fullscreen denied by browser'))
  }), failure);
  await stage.getByRole('button', { name: 'Fullscreen', exact: true }).click();
  await waitForExpanded(true);
  assert.equal(await page.evaluate(() => document.fullscreenElement), null, `${failure} API uses a viewport fallback`);
  await waitForLayout(true);
  await assertPreserved();
  if (failure === 'missing') await page.keyboard.press('Escape');
  else await stage.getByRole('button', { name: 'Exit fullscreen', exact: true }).click();
  await waitForExpanded(false);
  await waitForLayout(false);
  await assertPreserved();
  await stage.evaluate(node => delete node.requestFullscreen);
 }
 await page.getByRole('button', { name: options.reset }).click();
 await page.waitForFunction(({ selector, initial }) => {
  const eye = document.querySelector(selector)?.layout?.scene?.camera?.eye;
  return eye && ['x', 'y', 'z'].every(axis => Math.abs(eye[axis] - initial.eye[axis]) < 1e-6);
 }, { selector, initial });
}
