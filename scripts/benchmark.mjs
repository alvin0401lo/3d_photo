import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const root = path.resolve(import.meta.dirname, '..');
const evidence = JSON.parse(await fs.readFile(path.join(root, 'artifacts/real-model-smoke.json'), 'utf8'));
const browser = await chromium.launch({ executablePath: process.env.DEPTHFRAME_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, args: ['--enable-unsafe-swiftshader'] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await page.goto('http://127.0.0.1:8000');
  await page.evaluate(id => localStorage.setItem('depthframe-project', id), evidence.project_id);
  await page.reload();
  await page.getByRole('button', { name: 'Reset camera', exact: true }).waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.querySelector('button[aria-label="Reset camera"]')?.disabled);
  await page.getByLabel('Preview quality', { exact: true }).selectOption('balanced');
  await page.getByRole('button', { name: 'Start auto-orbit', exact: true }).click();
  console.log('Measuring 60 seconds of continuous default-quality rendering...');
  const performanceResult = await page.evaluate(() => new Promise(resolve => {
    const times = []; let start = null; let previous = null;
    function tick(now) {
      if (start === null) start = now;
      if (previous !== null) times.push(now - previous);
      previous = now;
      if (now - start < 60000) { requestAnimationFrame(tick); return; }
      const sorted = [...times].sort((a, b) => a - b);
      const context = document.querySelector('canvas').getContext('webgl2');
      const debug = context?.getExtension('WEBGL_debug_renderer_info');
      resolve({ frames: times.length, elapsed_ms: now - start, fps: times.length * 1000 / (now - start), median_frame_ms: sorted[Math.floor(sorted.length / 2)], p95_frame_ms: sorted[Math.floor(sorted.length * .95)], renderer: debug ? context.getParameter(debug.UNMASKED_RENDERER_WEBGL) : context?.getParameter(context.RENDERER) });
    }
    requestAnimationFrame(tick);
  }));
  console.log(JSON.stringify(performanceResult));
  await page.getByRole('button', { name: 'Pause auto-orbit', exact: true }).click();
  await page.getByRole('button', { name: 'Reset settings', exact: true }).click();
  const session = await page.context().newCDPSession(page);
  const memory = [];
  for (let cycle = 0; cycle <= 20; cycle++) {
    if (cycle > 0) {
      await page.getByRole('button', { name: 'Project library', exact: true }).click();
      await page.getByRole('button', { name: 'Photo editor', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('button[aria-label="Reset camera"]')?.disabled);
    }
    if (cycle % 5 === 0) {
      await session.send('HeapProfiler.collectGarbage');
      const metrics = await session.send('Performance.getMetrics');
      memory.push({ cycle, js_heap_bytes: metrics.metrics.find(item => item.name === 'JSHeapUsedSize')?.value || (await page.evaluate(() => performance.memory?.usedJSHeapSize)) });
    }
  }
  const report = { hardware: { cpu: os.cpus()[0].model, logical_processors: os.cpus().length, ram_gib: +(os.totalmem() / 2 ** 30).toFixed(2) }, browser: await browser.version(), viewport: [1440, 1000], quality: 'balanced', measurement: performanceResult, target_fps: 30, target_met: performanceResult.fps >= 30, reopen_js_heap: memory, limitations: 'Headless desktop browser. Phone widths are emulated; physical mobile validation and process/GPU memory profiling are not included.' };
  await fs.writeFile(path.join(root, 'artifacts/performance.json'), JSON.stringify(report, null, 2));
  await page.screenshot({ path: path.join(root, 'artifacts/final-example-desktop.png'), fullPage: true });
  console.log(JSON.stringify(report, null, 2));
  if (!report.target_met) process.exitCode = 1;
} finally { await browser.close(); }
