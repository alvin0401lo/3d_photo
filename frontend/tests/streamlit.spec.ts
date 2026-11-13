import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

test('Streamlit shell embeds the real editor, object orbit and still downloads', async ({ page, request }) => {
  test.skip(!process.env.DEPTHFRAME_TEST_BASE_URL, 'Run with the Streamlit test base URL.');
  let id = ''; const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'DepthFrame AI', exact: true })).toBeVisible();
    const editor = page.frameLocator('iframe[title="DepthFrame photo editor with environment and object 360 degree viewers"]');
    await expect(editor.getByRole('heading', { name: 'Photo editor', exact: true })).toBeVisible();
    await expect(editor.locator('.workspace-name')).toContainText('Hosted workspace');
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
    await page.screenshot({ path: path.resolve('../artifacts/streamlit-desktop.png'), fullPage: true });
    expect(errors).toEqual([]);
  } finally { if (id) await request.delete('/api/projects/' + id); }
});
