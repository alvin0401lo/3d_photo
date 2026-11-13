import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = path.resolve(import.meta.dirname, '..');
const sample = JSON.parse(await fs.readFile(path.join(root, 'artifacts/real-model-smoke.json'), 'utf8'));
const browser = await chromium.launch({ executablePath: process.env.DEPTHFRAME_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
try {
  for (const [width, height, name] of [[1440, 1000, 'desktop'], [768, 1024, 'tablet'], [390, 844, 'mobile']]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.addInitScript(id => localStorage.setItem('depthframe-project', id), sample.project_id);
    await page.goto('http://127.0.0.1:8000');
    await page.waitForFunction(() => document.querySelector('button[aria-label="Reset camera"]')?.disabled === false);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => /\d+ FPS/.test(document.querySelector('.editor-footnote')?.textContent || ''));
    await page.waitForFunction(() => {
      const canvas = document.querySelector('.photo-stage canvas');
      if (!canvas) return false;
      const rect = canvas.getBoundingClientRect();
      return Math.abs(canvas.width - rect.width * devicePixelRatio) < 2 && Math.abs(canvas.height - rect.height * devicePixelRatio) < 2;
    });
    await page.screenshot({ path: path.join(root, `artifacts/final-example-${name}.png`), fullPage: true });
    const frame = path.join(root, `artifacts/final-reference-${name}.png`);
    await page.locator('.photo-stage canvas').screenshot({ path: frame });
    execFileSync(path.join(root, '.venv/Scripts/python.exe'), [path.join(root, 'scripts/check_frame.py'), frame, String(1600 / 1078)]);
    await page.close();
  }
  console.log('Saved final example screenshots at 1440, 768, and 390px.');
} finally { await browser.close(); }
