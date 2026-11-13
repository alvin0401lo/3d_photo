import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

test('Streamlit shell embeds the real editor, object orbit and still downloads', async ({ page, request }) => {
  test.skip(!process.env.DEPTHFRAME_TEST_BASE_URL, 'Run with the Streamlit test base URL.');
  let id = ''; const errors: string[] = [];
  const root = process.env.DEPTHFRAME_TEST_ROOT_PATH || '/';
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(root);
    await expect(page.getByRole('heading', { name: 'DepthFrame AI', exact: true })).toBeVisible();
    const editor = page.frameLocator('iframe[title="DepthFrame photo editor with environment and object 360 degree viewers"]');
    await expect(editor.getByRole('heading', { name: 'Photo editor', exact: true })).toBeVisible();
    await expect(editor.locator('.workspace-name')).toContainText('Hosted workspace');
    await expect(editor.getByAltText('Example photograph of a lake, forest, and distant mountains')).toHaveJSProperty('naturalWidth', 1600);
    if (root !== '/') {
      const opened = page.waitForEvent('popup');
      await page.getByRole('link', { name: 'Open full editor', exact: true }).click();
      const full = await opened;
      await expect(full.getByRole('heading', { name: 'Photo editor', exact: true })).toBeVisible();
      await expect(full.locator('.workspace-name')).toContainText('Hosted workspace');
      await full.close();
    }
    await editor.getByRole('button', { name: 'Object 360°', exact: true }).click();
    const created = page.waitForResponse(r => r.url().endsWith('/api/object-examples') && r.status() === 201);
    await editor.getByRole('button', { name: 'Try 3D person example', exact: true }).click();
    id = (await (await created).json()).id;
    await expect(editor.getByRole('button', { name: 'Reset object camera', exact: true })).toBeEnabled();
    const stage = editor.getByTestId('object-stage');
    await stage.focus();
    for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowRight');
    await expect(editor.getByTestId('object-heading')).toHaveText('180° around');
    const downloaded = page.waitForEvent('download');
    await editor.getByRole('button', { name: 'Save object still', exact: true }).click();
    const target = path.resolve('../artifacts/streamlit-object-still.png');
    await (await downloaded).saveAs(target);
    expect((await fs.readFile(target)).subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    const modelLink = editor.getByRole('link', { name: 'Download GLB', exact: true });
    expect((await modelLink.getAttribute('href'))?.startsWith(root + 'api/')).toBe(true);
    const modelDownload = page.waitForEvent('download');
    await modelLink.click();
    const modelPath = path.resolve('../artifacts/streamlit-orbit-model.glb');
    await (await modelDownload).saveAs(modelPath);
    expect((await fs.readFile(modelPath)).subarray(0, 4).toString()).toBe('glTF');
    await page.screenshot({ path: path.resolve(root === '/' ? '../artifacts/streamlit-desktop.png' : '../artifacts/streamlit-cloud-prefix.png'), fullPage: true });
    expect(errors).toEqual([]);
  } finally { if (id) await request.delete(root + 'api/projects/' + id); }
});
