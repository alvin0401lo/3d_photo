import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const artifacts = path.resolve('../artifacts');
const examplePath = path.resolve('../examples/alpine-lake.jpg');

test('real photo upload, AI depth, editor, persistence, all exports, gallery and deletion', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const createdIds: string[] = [];
  page.on('response', async response => {
    if (response.url().endsWith('/api/projects') && response.request().method() === 'POST' && response.status() === 201) createdIds.push((await response.json()).id);
  });
  await fs.mkdir(artifacts, { recursive: true });
  try {
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await expect(page.getByRole('heading', { name: 'Photo editor', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Try example photo' })).toBeEnabled();
    await page.screenshot({ path: path.join(artifacts, 'welcome-desktop.png'), fullPage: true });
    await page.getByLabel('Upload photo', { exact: true }).setInputFiles(examplePath);
    await expect(page.getByRole('heading', { name: 'alpine-lake', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '3D photo', exact: true })).toBeEnabled({ timeout: 60000 });
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
    await expect(page.getByText('Depth ready', { exact: true })).toBeVisible();
    await page.getByLabel('Depth intensity', { exact: true }).fill('0.62');
    await page.getByLabel('Camera movement', { exact: true }).fill('0.55');
    await page.getByLabel('Preview quality', { exact: true }).selectOption('high');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Project settings saved.' })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel('Depth intensity', { exact: true })).toHaveValue('0.62');
    await expect(page.getByLabel('Preview quality', { exact: true })).toHaveValue('high');
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
    await page.getByTestId('photo-stage').focus();
    await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowUp');
    await page.screenshot({ path: path.join(artifacts, 'editor-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: 'Reset camera', exact: true }).click();
    await page.getByRole('button', { name: 'Depth', exact: true }).click();
    await expect(page.getByAltText('Relative depth map, light areas are nearer')).toBeVisible();
    await page.screenshot({ path: path.join(artifacts, 'depth-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: 'Original', exact: true }).click();
    await expect(page.locator('.stage-image')).toBeVisible();
    await page.getByRole('button', { name: '3D photo', exact: true }).click();

    for (const [label, file] of [['Still image', 'example-3d.png'], ['Textured depth mesh', 'example-scene.glb'], ['Depth map', 'example-depth16.png'], ['Project bundle', 'example-project.zip'], ['Original photograph', 'example-original.jpg']] as const) {
      await page.getByRole('button', { name: 'Export', exact: true }).click();
      const dialog = page.getByRole('dialog');
      const downloadPromise = page.waitForEvent('download');
      await dialog.getByRole(label === 'Still image' || label === 'Textured depth mesh' ? 'button' : 'link', { name: new RegExp(label) }).click();
      const download = await downloadPromise;
      const target = path.join(artifacts, file); await download.saveAs(target);
      const bytes = await fs.readFile(target); expect(bytes.length).toBeGreaterThan(100);
      if (file.endsWith('.png')) expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
      if (file.endsWith('.glb')) {
        expect(bytes.subarray(0, 4).toString()).toBe('glTF');
        const jsonLength = bytes.readUInt32LE(12);
        const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString());
        expect(gltf.images[0].bufferView).toBeDefined();
        expect(gltf.meshes.length).toBe(1);
      }
      if (await dialog.isVisible()) await page.getByRole('button', { name: 'Close export', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Export', exact: true }).click();
    const videoDownload = page.waitForEvent('download', { timeout: 20000 });
    await page.getByRole('button', { name: /Orbit animation/ }).click();
    const video = await videoDownload; await video.saveAs(path.join(artifacts, 'example-orbit.webm'));
    expect((await fs.stat(path.join(artifacts, 'example-orbit.webm'))).size).toBeGreaterThan(1000);
    const videoCheck = await page.evaluate(async () => {
      // Capability check only. Downloaded-file decoding is checked by a separate local validation script.
      return { encoder: MediaRecorder.isTypeSupported('video/webm'), webgl: Boolean(document.querySelector('canvas')) };
    });
    expect(videoCheck.encoder && videoCheck.webgl).toBe(true);
    await expect(page.getByText('Animation downloaded.', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Export', exact: true }).click();
    await page.getByRole('button', { name: /Orbit animation/ }).click();
    await expect(page.getByText(/Recording animation/)).toBeVisible();
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Recording cancelled.');
    await page.getByRole('button', { name: 'Dismiss error', exact: true }).click();

    await page.getByRole('button', { name: 'Rename project', exact: true }).click();
    await page.getByLabel('Photo name', { exact: true }).fill('Browser test landscape');
    await page.getByRole('button', { name: 'Save name', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Browser test landscape', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Project library', exact: true }).click();
    await expect(page.getByRole('button', { name: /Browser test landscape/ }).last()).toBeVisible();
    await page.getByRole('button', { name: /Browser test landscape/ }).last().click();
    await expect(page.getByLabel('Depth intensity', { exact: true })).toHaveValue('0.62');
    await page.getByRole('button', { name: 'Rename project', exact: true }).click();
    await page.getByRole('button', { name: 'Delete photo', exact: true }).click();
    await page.getByRole('button', { name: 'Delete photo', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Project library', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Browser test landscape/ })).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    for (const id of createdIds) await request.delete(`/api/projects/${id}`);
  }
});

test('example action, responsive layouts, keyboard dialogs and environment studio', async ({ page, request }) => {
  let createdId = '';
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await expect(page.getByRole('button', { name: 'Try example photo' })).toBeEnabled();
    const created = page.waitForResponse(response => response.url().endsWith('/api/examples') && response.status() === 201);
    await page.getByRole('button', { name: 'Try example photo' }).click();
    createdId = (await (await created).json()).id;
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled({ timeout: 60000 });
    for (const [width, height, label] of [[1440, 1000, 'desktop'], [768, 1024, 'tablet'], [390, 844, 'mobile']] as const) {
      await page.setViewportSize({ width, height });
      await expect(page.getByTestId('photo-stage')).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow, `horizontal overflow at ${width}px`).toBe(false);
      const contained = await page.evaluate(() => {
        const shell = document.querySelector('.viewport-shell')!.getBoundingClientRect();
        const content = document.querySelector('.viewport-content')!.getBoundingClientRect();
        return content.left >= shell.left && content.right <= shell.right && content.bottom <= shell.bottom;
      });
      expect(contained, `photo viewport clipped by its panel at ${width}px`).toBe(true);
      const framePath = path.join(artifacts, `reference-frame-${label}.png`);
      await page.locator('.photo-stage canvas').screenshot({ path: framePath });
      execFileSync(path.resolve('../.venv/Scripts/python.exe'), [path.resolve('../scripts/check_frame.py'), framePath, String(1600 / 1078)]);
      await page.screenshot({ path: path.join(artifacts, `example-${label}.png`), fullPage: true });
    }
    await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.getByRole('button', { name: 'Environment 360°', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'See what surrounds you.' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate with OpenAI', exact: true })).toBeDisabled();
    await page.screenshot({ path: path.join(artifacts, 'studio-mobile.png'), fullPage: true });
    await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.getByRole('button', { name: 'Photo editor', exact: true }).click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: 'Help', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    if (createdId) await request.delete(`/api/projects/${createdId}`);
  }
});

test('invalid upload shows a clear error and leaves the editor usable', async ({ page }) => {
  await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
  await page.getByLabel('Upload photo', { exact: true }).setInputFiles({ name: 'corrupt.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('invalid-image') });
  await expect(page.getByRole('alert')).toContainText('could not be decoded safely');
  await page.getByRole('button', { name: 'Dismiss error', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Try example photo' })).toBeEnabled();
});

test('drag changes the rendered angle and keeps it after leaving; keys and reset take control from auto-orbit', async ({ page, request }) => {
  const created = await request.post('/api/examples');
  expect(created.status()).toBe(201);
  const project = await created.json();
  const compare = (first: string, second: string) => JSON.parse(execFileSync(path.resolve('../.venv/Scripts/python.exe'), [path.resolve('../scripts/compare_frames.py'), first, second], { encoding: 'utf8' })) as { mean_difference: number; changed_fraction: number };
  try {
    const queued = await request.post(`/api/projects/${project.id}/depth-jobs`, { data: { inference_size: 384 } });
    expect(queued.status()).toBe(202);
    const job = await queued.json();
    await expect.poll(async () => (await (await request.get(`/api/jobs/${job.id}`)).json()).status, { timeout: 60000 }).toBe('completed');
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), project.id);
    await page.goto(process.env.DEPTHFRAME_TEST_EDITOR_PATH || '/');
    await expect(page.getByRole('button', { name: 'Reset camera', exact: true })).toBeEnabled();
    await page.getByLabel('Camera movement', { exact: true }).fill('1');
    await page.getByLabel('Depth intensity', { exact: true }).fill('0.65');
    const stage = page.getByTestId('photo-stage');
    await stage.scrollIntoViewIfNeeded();
    const box = (await stage.boundingBox())!;
    const center = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(center.x, center.y);
    await page.waitForTimeout(900); // Allow the damped camera to settle before comparing actual pixels.
    const reference = path.join(artifacts, 'camera-reference.png');
    await page.locator('.photo-stage canvas').screenshot({ path: reference });
    await page.mouse.down();
    await page.mouse.move(center.x + box.width * .3, center.y - box.height * .2, { steps: 20 });
    await page.mouse.up();
    await page.mouse.move(20, 20);
    await page.waitForTimeout(1100);
    const dragged = path.join(artifacts, 'camera-dragged.png');
    await page.locator('.photo-stage canvas').screenshot({ path: dragged });
    const change = compare(reference, dragged);
    expect(change.mean_difference, 'drag must visibly change the angle and not reset when the pointer leaves').toBeGreaterThan(1);
    expect(change.changed_fraction).toBeGreaterThan(.01);
    await page.waitForTimeout(600);
    const held = path.join(artifacts, 'camera-held.png');
    await page.locator('.photo-stage canvas').screenshot({ path: held });
    expect(compare(dragged, held).mean_difference, 'released drag angle must remain steady').toBeLessThan(.5);
    await stage.focus();
    await page.keyboard.press('Home');
    await page.waitForTimeout(800);
    const reset = path.join(artifacts, 'camera-reset.png');
    await page.locator('.photo-stage canvas').screenshot({ path: reset });
    expect(compare(reference, reset).mean_difference).toBeLessThan(.5);
    await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowUp');
    await page.waitForTimeout(800);
    const keyboard = path.join(artifacts, 'camera-keyboard.png');
    await page.locator('.photo-stage canvas').screenshot({ path: keyboard });
    expect(compare(reference, keyboard).mean_difference).toBeGreaterThan(1);
    await page.getByRole('button', { name: 'Start auto-orbit', exact: true }).click();
    await expect(page.getByRole('switch', { name: 'Auto-orbit', exact: true })).toBeChecked();
    await page.mouse.move(center.x, center.y); await page.mouse.down(); await page.mouse.up();
    await expect(page.getByRole('switch', { name: 'Auto-orbit', exact: true })).not.toBeChecked();
    await page.getByRole('button', { name: 'Reset camera', exact: true }).click();
    await page.mouse.move(20, 20); await page.waitForTimeout(800);
    const final = path.join(artifacts, 'camera-final-reset.png');
    await page.locator('.photo-stage canvas').screenshot({ path: final });
    expect(compare(reference, final).mean_difference).toBeLessThan(.5);
    await page.setViewportSize({ width: 390, height: 844 });
    await stage.scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    await page.waitForTimeout(800);
    const mobileBox = (await stage.boundingBox())!;
    const mobileReference = path.join(artifacts, 'camera-touch-reference.png');
    await page.locator('.photo-stage canvas').screenshot({ path: mobileReference });
    const client = await page.context().newCDPSession(page);
    await client.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
    const touchX = mobileBox.x + mobileBox.width / 2, touchY = mobileBox.y + mobileBox.height / 2;
    const scrollBefore = await page.evaluate(() => scrollY);
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: touchX, y: touchY, id: 1 }] });
    for (let step = 1; step <= 12; step++) {
      await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: touchX + mobileBox.width * .25 * step / 12, y: touchY - mobileBox.height * .15 * step / 12, id: 1 }] });
    }
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(1000);
    const mobileDragged = path.join(artifacts, 'camera-touch-dragged.png');
    await page.locator('.photo-stage canvas').screenshot({ path: mobileDragged });
    const touchChange = compare(mobileReference, mobileDragged);
    expect(touchChange.mean_difference, 'a touch drag must visibly change the held angle').toBeGreaterThan(1);
    expect(await page.evaluate(() => scrollY), 'dragging the photo must rotate it instead of scrolling the page').toBe(scrollBefore);
    await fs.writeFile(path.join(artifacts, 'camera-interaction.json'), JSON.stringify({ drag_pixel_difference: change, released_angle_persists: true, keyboard: true, reset: true, manual_input_pauses_auto_orbit: true, emulated_touch_pixel_difference: touchChange }, null, 2));
  } finally { await request.delete(`/api/projects/${project.id}`); }
});
