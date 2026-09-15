import assert from 'node:assert/strict';

// Exercise the real keyboard events against Plotly's camera, including held
// keys. These checks use geometry and unchanged engine values, not screenshots.
export async function checkKeyboardOrbit(page, selector, options) {
 const plot = page.locator(selector);
 const camera = () => plot.evaluate(el => el.layout.scene.camera);
 const offset = value => {
  const center = value.center ?? { x: 0, y: 0, z: 0 };
  const x = value.eye.x - center.x, y = value.eye.y - center.y, z = value.eye.z - center.z;
  const radius = Math.hypot(x, y, z);
  return { radius, azimuth: Math.atan2(y, x), elevation: Math.asin(z / radius) };
 };
 const near = (actual, expected, label) => assert.ok(Math.abs(actual - expected) < 1e-6, `${label}: ${actual} vs ${expected}`);
 const angleDifference = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b));
 const initial = await camera();
 const initialOrbit = offset(initial);
 const originalMetrics = await options.metrics();
 const originalSelection = await page.locator(options.control).inputValue();
 const unchangedOrbit = value => {
  near(offset(value).radius, initialOrbit.radius, 'camera keeps its orbit radius');
  assert.deepEqual(value.center ?? { x: 0, y: 0, z: 0 }, initial.center ?? { x: 0, y: 0, z: 0 }, 'camera keeps its center');
  assert.ok(Object.values(value.eye).every(Number.isFinite), 'camera eye stays finite');
  assert.ok(value.up.z > 0, 'camera stays upright');
 };
 const waitForEye = async expected => page.waitForFunction(({ selector, expected }) => {
  const eye = document.querySelector(selector)?.layout?.scene?.camera?.eye;
  return eye && ['x', 'y', 'z'].every(axis => Math.abs(eye[axis] - expected[axis]) < 1e-6);
 }, { selector, expected });
 const move = async key => {
  const before = await camera();
  await page.keyboard.press(key);
  await page.waitForFunction(({ selector, before }) => {
   const eye = document.querySelector(selector)?.layout?.scene?.camera?.eye;
   return eye && ['x', 'y', 'z'].some(axis => Math.abs(eye[axis] - before.eye[axis]) > 1e-7);
  }, { selector, before });
  return camera();
 };
 // Tab reaches the chart after its reset button, and leaves it normally.
 await page.getByRole('button', { name: options.reset }).focus();
 await page.keyboard.press('Tab');
 assert.equal(await plot.evaluate(el => document.activeElement === el), true, 'Tab reaches the chart itself');
 const scrollBefore = await page.evaluate(() => [window.scrollX, window.scrollY]);
 const gizmoBefore = await page.locator('.orientation-gizmo').innerHTML();
 const right = await move('ArrowRight');
 near(angleDifference(offset(right).azimuth, initialOrbit.azimuth), Math.PI / 30, 'Right increases azimuth by six degrees');
 near(offset(right).elevation, initialOrbit.elevation, 'horizontal rotation preserves elevation');
 unchangedOrbit(right);
 await page.waitForFunction(before => document.querySelector('.orientation-gizmo')?.innerHTML !== before, gizmoBefore);
 const left = await move('ArrowLeft');
 near(angleDifference(offset(left).azimuth, initialOrbit.azimuth), 0, 'Left reverses Right');
 const up = await move('ArrowUp');
 near(offset(up).elevation - initialOrbit.elevation, Math.PI / 30, 'Up increases elevation by six degrees');
 unchangedOrbit(up);
 await page.waitForTimeout(150);
 assert.deepEqual(await page.evaluate(() => [window.scrollX, window.scrollY]), scrollBefore, 'focused ArrowUp does not scroll the page');
 const down = await move('ArrowDown');
 near(offset(down).elevation, initialOrbit.elevation, 'Down reverses Up');
 await page.waitForTimeout(150);
 assert.deepEqual(await page.evaluate(() => [window.scrollX, window.scrollY]), scrollBefore, 'focused camera arrows do not scroll the page');
 await page.keyboard.press('Tab');
 assert.equal(await page.locator(options.control).evaluate(el => document.activeElement === el), true, 'Tab leaves the chart for its native value control');
 // Modified shortcuts remain available to the browser rather than orbiting.
 for (const modifier of ['Control', 'Alt', 'Meta', 'Shift']) {
  await plot.focus();
  const before = await camera();
  await page.keyboard.press(`${modifier}+ArrowUp`);
  await page.waitForTimeout(50);
  assert.deepEqual(await camera(), before, `${modifier}+ArrowUp does not control the camera`);
 }
 await plot.focus();
 // Repeated keydowns deliberately omit keyup, exercising event.repeat and
 // accumulation while earlier Plotly relayout work can still be pending.
 for (let index = 0; index < 18; index++) await page.keyboard.down('ArrowUp');
 await page.keyboard.up('ArrowUp');
 await page.waitForFunction(selector => {
  const c = document.querySelector(selector)?.layout?.scene?.camera;
  return c && Math.asin((c.eye.z - (c.center?.z ?? 0)) / Math.hypot(c.eye.x - (c.center?.x ?? 0), c.eye.y - (c.center?.y ?? 0), c.eye.z - (c.center?.z ?? 0))) > 1.4;
 }, selector);
 const upper = await camera();
 unchangedOrbit(upper);
 assert.ok(offset(upper).elevation < Math.PI / 2, 'upper pole remains below inversion');
 for (let index = 0; index < 36; index++) await page.keyboard.down('ArrowDown');
 await page.keyboard.up('ArrowDown');
 await page.waitForFunction(selector => {
  const c = document.querySelector(selector)?.layout?.scene?.camera;
  return c && Math.asin((c.eye.z - (c.center?.z ?? 0)) / Math.hypot(c.eye.x - (c.center?.x ?? 0), c.eye.y - (c.center?.y ?? 0), c.eye.z - (c.center?.z ?? 0))) < -1.4;
 }, selector);
 const lower = await camera();
 unchangedOrbit(lower);
 assert.ok(offset(lower).elevation > -Math.PI / 2, 'lower pole remains above inversion');
 await page.getByRole('button', { name: options.reset }).click();
 await waitForEye(initial.eye);
 await page.getByRole('button', { name: options.flat, exact: true }).click();
 await page.waitForFunction(selector => document.querySelector(selector)?.layout?.scene?.camera?.projection?.type === 'orthographic', selector);
 await plot.focus();
 await page.keyboard.press('ArrowRight');
 await page.waitForFunction(selector => document.querySelector(selector)?.layout?.scene?.camera?.projection?.type === 'perspective', selector);
 await waitForEye(right.eye);
 assert.equal(await page.getByRole('button', { name: options.perspective, exact: true }).getAttribute('aria-pressed'), 'true', 'an arrow leaves the flat preset for 3D');
 assert.deepEqual(await options.metrics(), originalMetrics, 'camera keys and presets preserve every metric value');
 assert.equal(await page.locator(options.control).inputValue(), originalSelection, 'camera keys preserve the selected allocation or cash');
 await page.getByRole('button', { name: options.reset }).click();
 await waitForEye(initial.eye);
}
