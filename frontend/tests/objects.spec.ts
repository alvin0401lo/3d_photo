import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const artifacts = path.resolve('../artifacts');
const compare = (a: string, b: string) => JSON.parse(execFileSync(path.resolve('../.venv/Scripts/python.exe'), [path.resolve('../scripts/compare_frames.py'), a, b], { encoding: 'utf8' })).mean_difference as number;

test('real sample character orbits through all sides, holds drag, resets, supports touch and exports', async ({ page, request }) => {
  let id = ''; const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/'); await page.getByRole('button', { name: 'Object 360°', exact: true }).click();
    const created = page.waitForResponse(r => r.url().endsWith('/api/object-examples') && r.status() === 201);
    await page.getByRole('button', { name: 'Try 3D person example', exact: true }).click();
    id = (await (await created).json()).id;
    const stage = page.getByTestId('object-stage'), heading = page.getByTestId('object-heading');
    const canvas = stage.locator('canvas');
    await expect(page.getByRole('button', { name: 'Reset object camera', exact: true })).toBeEnabled();
    await expect(page.getByText('Pre-existing sample · Cesium Man', { exact: true })).toBeVisible();
    await page.waitForTimeout(500);
    const front = path.join(artifacts, 'object-front.png'); await canvas.screenshot({ path: front });
    await stage.focus();
    for (const [name, angle] of [['right', '90° around'], ['back', '180° around'], ['left', '270° around'], ['returned', '0° around']]) {
      for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowRight');
      await expect(heading).toHaveText(angle);
      const frame = path.join(artifacts, `object-${name}.png`); await canvas.screenshot({ path: frame });
      if (name === 'returned') expect(compare(front, frame)).toBeLessThan(.5);
      else expect(compare(front, frame)).toBeGreaterThan(1);
    }
    const box = (await stage.boundingBox())!;
    await page.mouse.move(box.x + box.width * .65, box.y + box.height / 2); await page.mouse.down();
    await page.mouse.move(box.x + box.width * .3, box.y + box.height * .4, { steps: 12 }); await page.mouse.up(); await page.mouse.move(10, 10);
    const dragged = path.join(artifacts, 'object-dragged.png'); await canvas.screenshot({ path: dragged });
    expect(compare(front, dragged)).toBeGreaterThan(1);
    await page.waitForTimeout(400); const held = path.join(artifacts, 'object-held.png'); await canvas.screenshot({ path: held });
    expect(compare(dragged, held)).toBeLessThan(.5);
    await page.getByRole('switch', { name: 'Auto rotate object', exact: true }).check();
    await stage.focus(); await page.keyboard.press('Home');
    await expect(page.getByRole('switch', { name: 'Auto rotate object', exact: true })).not.toBeChecked();
    await expect(heading).toHaveText('0° around');
    await page.screenshot({ path: path.join(artifacts, 'object-studio-desktop.png'), fullPage: true });
    for (const [label, filename, role] of [['Save object still', 'object-still.png', 'button'], ['Download GLB', 'object-model.glb', 'link']] as const) {
      const next = page.waitForEvent('download'); await page.getByRole(role, { name: label, exact: true }).click(); await (await next).saveAs(path.join(artifacts, filename));
    }
    await page.reload(); await page.getByRole('button', { name: 'Object 360°', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Reset object camera', exact: true })).toBeEnabled();
    await page.setViewportSize({ width: 390, height: 844 }); await stage.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300); const mobile = (await stage.boundingBox())!;
    const cdp = await page.context().newCDPSession(page); await cdp.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
    const x = mobile.x + mobile.width * .65, y = mobile.y + mobile.height / 2, scroll = await page.evaluate(() => scrollY);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y, id: 1 }] });
    for (let i = 1; i <= 10; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - mobile.width * .3 * i / 10, y, id: 1 }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await expect(heading).not.toHaveText('0° around');
    expect(await page.evaluate(() => scrollY)).toBe(scroll);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: path.join(artifacts, 'object-studio-mobile.png'), fullPage: true });
    expect(errors).toEqual([]);
    await fs.writeFile(path.join(artifacts, 'object-viewer-checks.json'), JSON.stringify({ sample: 'Pre-existing Cesium Man, not an AI photo reconstruction', all_sides_differ: true, full_turn_returns_to_front: true, held_drag: true, reset: true, touch_turn_without_page_scroll: true, still_and_glb_download: true, page_errors: errors }, null, 2));
  } finally { if (id) await request.delete('/api/projects/' + id); }
});

test('subject box and confirmed crop persist; mocked Meshy submission sends only confirmed selection once', async ({ page, request }) => {
  const example = await (await request.post('/api/object-examples')).json();
  const fixtureImage = await (await request.get(example.assets.image)).body();
  const created = await request.post('/api/projects', { multipart: { file: { name: 'subject-workflow.jpg', mimeType: 'image/jpeg', buffer: fixtureImage } } });
  const project = await created.json(); let submitted = 0, generated = false;
  try {
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), project.id);
    await page.route('**/api/capabilities', async route => { const response = await route.fetch(); const body = await response.json(); body.object_generation = { configured: true, model: 'meshy-7.1', error: null }; await route.fulfill({ json: body }); });
    await page.route('**/api/projects?limit=*', async route => { const response = await route.fetch(); const body = await response.json(); if (generated) body.items = body.items.map((p: { id: string }) => p.id === project.id ? { ...p, object: { ...example.object, provider: 'meshy', ai_generated: true, model: 'EXPLICIT TEST FIXTURE' } } : p); await route.fulfill({ json: body }); });
    await page.route(`**/api/projects/${project.id}/object-jobs`, async route => { expect(route.request().postDataJSON()).toEqual({ pose: 'a-pose', allow_external_processing: true }); expect(route.request().headers()['idempotency-key']).toBeTruthy(); submitted++; generated = true; await route.fulfill({ status: 202, json: { id: 'mocked-task' } }); });
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/'); await page.getByRole('button', { name: 'Object 360°', exact: true }).click();
    const generate = page.getByRole('button', { name: 'Generate object with Meshy', exact: true });
    await expect(generate).toBeDisabled();
    const selector = page.getByTestId('subject-selector'); const box = (await selector.boundingBox())!;
    await page.mouse.move(box.x + box.width * .2, box.y + box.height * .1); await page.mouse.down(); await page.mouse.move(box.x + box.width * .8, box.y + box.height * .9, { steps: 8 }); await page.mouse.up();
    await page.getByRole('button', { name: 'Confirm selection', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Selection confirmed', exact: true })).toBeVisible();
    const saved = await (await request.get('/api/projects/' + project.id)).json();
    expect(saved.subject.width).toBeCloseTo(.6, 2); expect(saved.subject.height).toBeCloseTo(.8, 2);
    await page.reload(); await page.getByRole('button', { name: 'Object 360°', exact: true }).click();
    await expect(page.getByAltText('Confirmed crop sent to Meshy')).toBeVisible();
    await expect(generate).toBeDisabled(); expect(submitted).toBe(0);
    await page.getByLabel('Object pose', { exact: true }).selectOption('a-pose'); await page.getByRole('checkbox').check();
    await generate.click();
    await expect(page.getByText('AI reconstructed subject · Meshy', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reset object camera', exact: true })).toBeEnabled();
    expect(submitted).toBe(1);
  } finally { await request.delete('/api/projects/' + project.id); await request.delete('/api/projects/' + example.id); }
});
