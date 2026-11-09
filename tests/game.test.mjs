// Plays through the beak8v level in the real viewer (Playwright, visible window) and checks the game rules:
// the keys, the locked cupboard and lift, the bedroom door shutting again, the one-way bathroom door,
// the hole from the loft and the golden cup.
//
// Run:  npm test                 (from the repo root, after npm install)
//       npm test -- --keep       (leave the window open at the end to look round)
//       SHOTS=<folder> npm test  (also save screenshots of the logos and the cup there)
import { chromium } from 'playwright';
import { fileURLToPath, pathToFileURL } from 'url';
import path from 'path';
import assert from 'assert/strict';

const here = path.dirname(fileURLToPath(import.meta.url));
const viewerUrl = pathToFileURL(path.join(here, '..', 'viewer', 'viewer.html')).href;
const keepOpen = process.argv.includes('--keep');
const shots = process.env.SHOTS;

const browser = await chromium.launch({ headless: false, slowMo: 20 });
const page = await browser.newPage({ viewport: { width: 960, height: 600 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(e.message));
await page.goto(viewerUrl);
await page.waitForFunction(() => window.__qmv && window.__qmv.P && window.__qmv.ents.length > 0, null, { timeout: 60000 });

// ---------- helpers that run inside the page ----------
// put the player somewhere (Quake coordinates), facing a compass angle, walking (not noclip)
const putPlayer = (org, face = 0) => page.evaluate(([org, face]) => {
  const q = window.__qmv;
  q.P.org = org; q.P.vel = [0, 0, 0]; q.P.noclip = false;
  q.P.yaw = (face - 90) * Math.PI / 180; q.P.pitch = 0;
}, [org, face]);
// run the game forward by this many seconds
const step = secs => page.evaluate(s => window.__qmv.step(s), secs);
// a brush entity's state, found by its model number
const entState = model => page.evaluate(mi => window.__qmv.ents.find(e => e.model === mi).state, model);
const centerText = () => page.evaluate(() => window.__qmv.centerText());
const items = () => page.evaluate(() => ({ ...window.__qmv.P.items }));
const isOpen = state => state === 1 || state === 2;   // TOP or UP
// pick up the item made from this classname by standing on it
async function pickUp(classname) {
  const org = await page.evaluate(c => window.__qmv.ents.find(e => e.classname === c).origin, classname);
  await putPlayer(org);
  await step(0.1);
}
async function screenshot(name, org, face) {
  if (!shots) return;
  await page.evaluate(() => { document.getElementById('hud').style.display = 'none'; document.getElementById('play').style.display = 'none'; });
  await page.evaluate(([org, face]) => { const q = window.__qmv; q.P.noclip = true; q.P.org = org; q.P.vel = [0, 0, 0]; q.P.yaw = (face - 90) * Math.PI / 180; q.P.pitch = 0; }, [org, face]);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(shots, name + '.png') });
  await page.evaluate(() => { window.__qmv.P.noclip = false; document.getElementById('hud').style.display = ''; });
}

const results = [];
async function test(name, fn) {
  try { await fn(); results.push(['PASS', name]); }
  catch (e) { results.push(['FAIL', name, e.message]); }
}

// model numbers in beak8v
const BEDROOM_DOOR = 3, BATHROOM_DOOR = 7, CUPBOARD_DOORS = [22, 23], CUPBOARD_BUTTON = 24, LIFT_BUTTON = 27, LIFT = 44, HOLE_ROOM_DOOR = 28;

// ---------- tests ----------
await test('the gold key is now the silver key, and the biosuit is the gold key', async () => {
  const names = await page.evaluate(() => {
    const ents = window.__qmv.ents;
    return { key2: ents.find(e => e.classname === 'item_key2').name, suit: ents.find(e => e.classname === 'item_artifact_envirosuit').name };
  });
  assert.equal(names.key2, 'silver key');
  assert.equal(names.suit, 'gold key');
});

await test('the bedroom door needs the silver key and its logo is silver', async () => {
  const door = await page.evaluate(mi => window.__qmv.ents.find(e => e.model === mi).master.items, BEDROOM_DOOR);
  assert.equal(door, 'silver');
  const silverMats = await page.evaluate(() => window.__qmv.world.mesh.material.filter(m => m.uniforms.silver.value === 1).length);
  assert.equal(silverMats, 1);
});

await test('both cupboard doors show the gold key logo', async () => {
  for (const mi of CUPBOARD_DOORS) {
    const logo = await page.evaluate(mi => {
      const door = window.__qmv.ents.find(e => e.model === mi);
      const child = door.mesh.children[0];
      return child ? { silver: child.material.uniforms.silver.value } : null;
    }, mi);
    assert.ok(logo, `door *${mi} has no logo`);
    assert.equal(logo.silver, 0, 'the cupboard logo should stay gold');
  }
});

await test('without the gold key the cupboard stays shut and the lift does not move', async () => {
  await page.evaluate(mi => { const b = window.__qmv.ents.find(e => e.model === mi); b.touch(b); }, CUPBOARD_BUTTON);
  assert.match(await centerText(), /You need the gold key/);
  await step(2);
  for (const mi of CUPBOARD_DOORS) assert.equal(await entState(mi), 0, `cupboard door *${mi} opened`);
  await page.evaluate(b => window.__qmv.shoot(window.__qmv.ents.find(x => x.model === b)), LIFT_BUTTON);
  assert.match(await centerText(), /You need the gold key/);
  await step(1);
  assert.equal(await entState(LIFT), 0, 'the lift moved');
});

await test('picking up the biosuit gives the gold key, which opens the cupboard and works the lift', async () => {
  await pickUp('item_artifact_envirosuit');
  assert.deepEqual(await items(), { gold: true });
  assert.match(await centerText(), /You got the gold key/);
  await page.evaluate(mi => { const b = window.__qmv.ents.find(e => e.model === mi); b.touch(b); }, CUPBOARD_BUTTON);
  await step(1);
  for (const mi of CUPBOARD_DOORS) assert.ok(isOpen(await entState(mi)), `cupboard door *${mi} did not open`);
  await page.evaluate(b => window.__qmv.shoot(window.__qmv.ents.find(x => x.model === b)), LIFT_BUTTON);
  await step(1);
  assert.ok(isOpen(await entState(LIFT)), 'the lift did not go up');
  assert.deepEqual(await items(), { gold: true }, 'the gold key should be kept (it is needed twice)');
});

await test('the bedroom door opens with the silver key, then shuts again when you walk away', async () => {
  await pickUp('item_key2');
  assert.ok((await items()).silver);
  await putPlayer([-30, 60, -85], 270);   // on the landing, in front of the door
  await page.evaluate(mi => { const d = window.__qmv.ents.find(e => e.model === mi); d.touch(d); }, BEDROOM_DOOR);
  await step(0.5);
  assert.ok(isOpen(await entState(BEDROOM_DOOR)), 'did not open');
  assert.equal((await items()).silver, undefined, 'the silver key should be used up');
  await putPlayer([784, -16, -290]);      // far away, at the start
  await step(8);
  assert.equal(await entState(BEDROOM_DOOR), 0, 'did not shut (it would stand up in the loft doorway)');
  await putPlayer([-30, 60, -85], 270);   // back again: it opens like any door now
  await step(0.5);
  assert.ok(isOpen(await entState(BEDROOM_DOOR)), 'did not reopen when walked up to');
});

await test('the bathroom door is locked from the landing', async () => {
  await putPlayer([784, -16, -290]);
  await step(8);
  await putPlayer([-150, 87, -85], 180);  // landing side
  await step(1.5);
  assert.equal(await entState(BATHROOM_DOOR), 0, 'opened from the landing');
  assert.match(await centerText(), /BATHROOM\nLocked/);
});

await test('dropping through the hole in the loft floor gets you in, and the bathroom door opens from inside', async () => {
  await putPlayer([-198, 184, 90], 180);  // in the loft, over the hole
  await step(3);
  const landed = await page.evaluate(() => window.__qmv.P.org);
  assert.ok(landed[2] < -60, `did not fall through (z ${landed[2]})`);
  assert.ok(isOpen(await entState(HOLE_ROOM_DOOR)), 'the door from the hole into the bathroom did not open');
  await putPlayer([-230, 87, -85], 0);    // bathroom side
  await step(0.5);
  assert.ok(isOpen(await entState(BATHROOM_DOOR)), 'did not open from inside');
});

await test('the golden cup is in the bathroom and picking it up completes the level', async () => {
  const cup = await page.evaluate(() => window.__qmv.ents.find(e => e.treasure).origin);
  const floor = await page.evaluate(o => window.__qmv.pointContents([o[0], o[1], o[2] - 1]), cup);
  assert.equal(floor, -2, 'the cup is not standing on the floor');
  await putPlayer([cup[0], cup[1], cup[2] + 25]);
  await step(0.2);
  assert.equal(await page.evaluate(() => window.__qmv.P.treasure), true);
  assert.match(await centerText(), /You found the golden cup!\nLevel complete in \d+:\d\d/);
});

await test('restart puts the keys and the cup back', async () => {
  await page.evaluate(() => window.__qmv.spawnPlayer());
  const back = await page.evaluate(() => window.__qmv.ents.filter(e => e.kind === 'item').every(e => !e.removed && e.mesh.visible));
  assert.ok(back);
  assert.deepEqual(await items(), {});
});

await test('no page errors', async () => { assert.deepEqual(pageErrors, []); });

await screenshot('cupboard', [-102, 340, -290], 90);
await screenshot('bedroom-door', [-30, 110, -80], 270);
const cupOrg = await page.evaluate(() => window.__qmv.ents.find(e => e.treasure).origin);
await screenshot('golden-cup', [cupOrg[0] + 60, cupOrg[1], cupOrg[2] + 40], 180);

// ---------- report ----------
for (const [r, name, why] of results) console.log(`${r}  ${name}${why ? '\n      ' + why : ''}`);
const failed = results.filter(r => r[0] === 'FAIL').length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
if (keepOpen) {
  await putPlayer([784, -16, -290]);
  await page.evaluate(() => window.__qmv.spawnPlayer());
  console.log('Window left open: close it when you are done.');
} else {
  await browser.close();
}
process.exitCode = failed ? 1 : 0;
