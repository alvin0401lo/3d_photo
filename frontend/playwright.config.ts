import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  reporter: [['list'], ['json', { outputFile: '../artifacts/browser-tests.json' }]],
  outputDir: '../artifacts/browser-test-output',
  use: {
    baseURL: process.env.DEPTHFRAME_TEST_BASE_URL || 'http://127.0.0.1:8000',
    viewport: { width: 1440, height: 1000 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: process.env.DEPTHFRAME_TEST_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      args: ['--enable-unsafe-swiftshader'],
    },
  },
});
