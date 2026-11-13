import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..'), base = 'http://127.0.0.1:8000';
const metadata = path.join(root, 'artifacts/object-example.json');
let project;
try { const saved = JSON.parse(await fs.readFile(metadata, 'utf8')); const response = await fetch(base + '/api/projects/' + saved.project_id); if (response.ok) project = await response.json(); } catch {}
if (!project) {
  const response = await fetch(base + '/api/object-examples', { method: 'POST' });
  if (!response.ok) throw new Error('Object example could not be created.');
  project = await response.json();
  await fetch(base + `/api/projects/${project.id}/subject`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ x: 0, y: 0, width: 1, height: 1 }) });
}
const browser = await chromium.launch({ executablePath: process.env.DEPTHFRAME_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
try {
  for (const [width, height, label] of [[1440, 1000, 'desktop'], [768, 1024, 'tablet'], [390, 844, 'mobile']]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), project.id);
    await page.goto(base);
    if (width < 1050) await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.getByRole('button', { name: 'Object 360°', exact: true }).click();
    await page.getByRole('button', { name: 'Reset object camera', exact: true }).waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('button[aria-label="Reset object camera"]')?.disabled === false);
    await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(250);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Horizontal overflow at ${width}px`);
    await page.screenshot({ path: path.join(root, `artifacts/final-object-${label}.png`), fullPage: true });
    await page.getByTestId('object-stage').locator('canvas').screenshot({ path: path.join(root, `artifacts/final-object-view-${label}.png`) });
    await page.close();
  }
  await fs.writeFile(metadata, JSON.stringify({ project_id: project.id, source: 'Cesium Man, Cesium, CC BY 4.0; separate logo notice', ai_generated: false, note: 'Pre-existing sample, not generated from selected photo' }, null, 2));
  console.log('Captured Object 360 at 1440, 768, 390px; retained the credited sample in the library.');
} finally { await browser.close(); }
