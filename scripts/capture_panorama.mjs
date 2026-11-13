import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const base = 'http://127.0.0.1:8000';
const listing = await (await fetch(base + '/api/projects')).json();
let project = listing.items.find(p => p.kind === 'panorama' && p.name === 'Kiara dawn · 360°');
if (!project) project = await (await fetch(base + '/api/panorama-examples', { method: 'POST' })).json();
if (!project.id) throw new Error('Could not create the captured panorama example.');
const browser = await chromium.launch({ executablePath: process.env.DEPTHFRAME_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
try {
  for (const [width, height, label] of [[1440, 1000, 'desktop'], [768, 1024, 'tablet'], [390, 844, 'mobile']]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), project.id);
    await page.goto(base);
    await page.getByRole('button', { name: 'Reset camera', exact: true }).isEnabled();
    await page.waitForFunction(() => /\d+ FPS/.test(document.querySelector('.editor-footnote')?.textContent || ''));
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(root, `artifacts/final-360-${label}.png`), fullPage: true });
    const stage = page.getByTestId('panorama-stage');
    await stage.locator('canvas').screenshot({ path: path.join(root, `artifacts/final-360-view-${label}.png`) });
    if (width < 1050) await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
    await page.getByRole('button', { name: 'Environment 360°', exact: true }).click();
    await page.getByRole('heading', { name: 'See what surrounds you.', exact: true }).waitFor();
    await page.screenshot({ path: path.join(root, `artifacts/final-environment-studio-${label}.png`), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow) throw new Error(`Environment studio overflows at ${width}px.`);
    await page.close();
  }
  await fs.writeFile(path.join(root, 'artifacts/panorama-example.json'), JSON.stringify({ project_id: project.id, source: 'Poly Haven Kiara 1 Dawn, Greg Zaal, CC0', ai_generated: false }, null, 2));
  console.log('Captured 360° viewer and generation screen at 1440, 768 and 390px. Captured example retained in the library.');
} finally { await browser.close(); }
