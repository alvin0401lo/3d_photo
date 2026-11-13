import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const artifacts = path.resolve('../artifacts');
const compare = (a: string, b: string) => JSON.parse(execFileSync(path.resolve('../.venv/Scripts/python.exe'), [path.resolve('../scripts/compare_frames.py'), a, b], { encoding: 'utf8' })) as { mean_difference: number };

test('captured panorama supports full 360 turn, poles, held drag, touch, persistence and exports', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let id = '';
  try {
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await page.getByRole('button', { name: 'Environment 360°', exact: true }).click();
    const createdPromise = page.waitForResponse(r => r.url().endsWith('/api/panorama-examples') && r.status() === 201);
    await page.getByRole('button', { name: 'Try 360° example', exact: true }).click();
    id = (await (await createdPromise).json()).id;
    const stage = page.getByTestId('panorama-stage'), readout = page.getByTestId('panorama-heading');
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
    await expect(readout).toHaveAttribute('data-yaw', '0.0');
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(artifacts, '360-example-desktop.png'), fullPage: true });
    const front = path.join(artifacts, '360-front.png');
    await stage.locator('canvas').screenshot({ path: front });
    await stage.focus();
    for (const [direction, target] of [['right', '90.0'], ['back', '180.0'], ['left', '270.0'], ['returned', '0.0']]) {
      for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowRight');
      await expect(readout).toHaveAttribute('data-yaw', target);
      const file = path.join(artifacts, `360-${direction}.png`);
      await stage.locator('canvas').screenshot({ path: file });
      if (direction === 'returned') expect(compare(front, file).mean_difference).toBeLessThan(.5);
      else expect(compare(front, file).mean_difference).toBeGreaterThan(5);
    }
    for (let i = 0; i < 8; i++) await page.keyboard.press('ArrowUp');
    await expect(readout).toHaveAttribute('data-pitch', '89.0');
    await stage.locator('canvas').screenshot({ path: path.join(artifacts, '360-zenith.png') });
    for (let i = 0; i < 16; i++) await page.keyboard.press('ArrowDown');
    await expect(readout).toHaveAttribute('data-pitch', '-89.0');
    await stage.locator('canvas').screenshot({ path: path.join(artifacts, '360-nadir.png') });
    await page.keyboard.press('Home');
    await expect(readout).toHaveAttribute('data-pitch', '0.0');
    const box = (await stage.boundingBox())!;
    await page.mouse.move(box.x + box.width * .75, box.y + box.height / 2); await page.mouse.down();
    await page.mouse.move(box.x + box.width * .25, box.y + box.height / 2, { steps: 12 }); await page.mouse.up();
    await page.mouse.move(10, 10);
    await expect.poll(async () => Number(await readout.getAttribute('data-yaw'))).toBeCloseTo(90, 0);
    const heldYaw = await readout.getAttribute('data-yaw');
    await page.waitForTimeout(500);
    await expect(readout).toHaveAttribute('data-yaw', heldYaw!);
    await page.getByRole('switch', { name: 'Auto look-around', exact: true }).check();
    await expect.poll(async () => Number(await readout.getAttribute('data-yaw'))).toBeGreaterThan(92);
    await stage.focus(); await page.keyboard.press('ArrowLeft');
    await expect(page.getByRole('switch', { name: 'Auto look-around', exact: true })).not.toBeChecked();
    await page.getByLabel('Zoom', { exact: true }).fill('1.25');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Project settings saved.' })).toBeVisible();
    await page.reload();
    await expect(stage).toBeVisible();
    await expect(page.getByLabel('Zoom', { exact: true })).toHaveValue('1.25');
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
    for (const [label, filename] of [['Still image', '360-still.png'], ['360° panorama', '360-export.jpg']]) {
      await page.getByRole('button', { name: 'Export', exact: true }).click();
      const downloaded = page.waitForEvent('download');
      await page.getByRole('dialog').getByRole(label === 'Still image' ? 'button' : 'link', { name: new RegExp(label) }).click();
      await (await downloaded).saveAs(path.join(artifacts, filename));
      if (await page.getByRole('dialog').isVisible()) await page.getByRole('button', { name: 'Close export', exact: true }).click();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await stage.scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    const mobile = (await stage.boundingBox())!;
    const client = await page.context().newCDPSession(page);
    await client.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
    const scrollBefore = await page.evaluate(() => scrollY);
    const x = mobile.x + mobile.width * .7, y = mobile.y + mobile.height / 2;
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y, id: 1 }] });
    for (let i = 1; i <= 12; i++) await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - mobile.width * .4 * i / 12, y, id: 1 }] });
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await expect.poll(async () => Number(await readout.getAttribute('data-yaw'))).toBeCloseTo(72, 0);
    expect(await page.evaluate(() => scrollY)).toBe(scrollBefore);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: path.join(artifacts, '360-example-mobile.png'), fullPage: true });
    expect(errors).toEqual([]);
    await fs.writeFile(path.join(artifacts, '360-viewer-checks.json'), JSON.stringify({ source: 'Captured Poly Haven panorama, not AI generation', yaw_0_90_180_270_360_pixels: true, full_turn_returns_to_start: true, poles: [-89, 89], held_mouse_drag: true, touch_yaw_degrees: 72, manual_pauses_auto_rotation: true, save_reopen: true, still_and_panorama_downloads: true, browser_errors: errors }, null, 2));
  } finally { if (id) await request.delete('/api/projects/' + id); }
});

test('panorama import rejects a normal photo and accepts a 2:1 environment', async ({ page, request }) => {
  let id = '';
  try {
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await page.getByRole('button', { name: 'Environment 360°', exact: true }).click();
    await page.getByLabel('Import panorama', { exact: true }).setInputFiles(path.resolve('../examples/alpine-lake.jpg'));
    await expect(page.getByRole('alert')).toContainText('2:1');
    await page.getByRole('button', { name: 'Dismiss error', exact: true }).click();
    const created = page.waitForResponse(r => r.url().endsWith('/api/projects?kind=panorama') && r.status() === 201);
    await page.getByLabel('Import panorama', { exact: true }).setInputFiles(path.resolve('../examples/kiara-panorama.jpg'));
    id = (await (await created).json()).id;
    await expect(page.getByTestId('panorama-stage')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
  } finally { if (id) await request.delete('/api/projects/' + id); }
});

test('OpenAI studio requires consent and displays an explicitly mocked job result without any external request', async ({ page, request }) => {
  const created = await request.post('/api/examples');
  const project = await created.json();
  let generated = false, submitted = 0;
  const job = { id: 'mocked-job', project_id: project.id, job_type: 'panorama', status: 'completed', progress: 100, stage: 'Ready', error: null };
  try {
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), project.id);
    await page.route('**/api/capabilities', route => route.fulfill({ json: { panorama_generation: { configured: true, model: 'gpt-image-2', error: null } } }));
    await page.route('**/api/projects?limit=*', async route => {
      const response = await route.fetch(); const body = await response.json();
      if (generated) body.items = body.items.map((item: { id: string }) => item.id === project.id ? { ...item, job, panorama: { job_id: job.id, width: 4096, height: 2048, projection: 'equirectangular', ai_generated: true, provider: 'openai', model: 'EXPLICIT TEST FIXTURE', assets: { panorama: '/api/panorama-example-photo' } } } : item);
      await route.fulfill({ json: body });
    });
    await page.route(`**/api/projects/${project.id}/panorama-jobs`, async route => {
      expect(route.request().postDataJSON()).toEqual({ description: 'Preserve the dawn lighting', quality: 'low', allow_external_processing: true });
      expect(route.request().headers()['idempotency-key']).toBeTruthy();
      submitted++; generated = true;
      await route.fulfill({ status: 202, json: job });
    });
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await page.getByRole('button', { name: 'Environment 360°', exact: true }).click();
    const generate = page.getByRole('button', { name: 'Generate with OpenAI', exact: true });
    await expect(generate).toBeDisabled();
    expect(submitted).toBe(0);
    await page.getByLabel('Scene guidance', { exact: true }).fill('Preserve the dawn lighting');
    await page.getByLabel('Generation quality', { exact: true }).selectOption('low');
    await page.getByRole('checkbox').check();
    await expect(generate).toBeEnabled();
    await generate.click();
    await page.getByRole('button', { name: 'Open 360° environment', exact: true }).click();
    await expect(page.getByTestId('panorama-stage')).toBeVisible();
    await expect(page.getByText('AI imagined environment · OpenAI', { exact: true })).toBeVisible();
    expect(submitted).toBe(1);
  } finally { await request.delete('/api/projects/' + project.id); }
});
