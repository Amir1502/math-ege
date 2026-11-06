import { defineConfig, devices } from '@playwright/test';

const evidence = process.env.MATH_EGE_OFFLINE_EVIDENCE ?? `offline-reports/${new Date().toISOString().replace(/[:.]/g, '-')}`;

export default defineConfig({
  testDir: './offline-e2e',
  outputDir: `${evidence}/test-results`,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  globalTimeout: 300_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: `${evidence}/browser-report` }],
    ['json', { outputFile: `${evidence}/results.json` }], ['junit', { outputFile: `${evidence}/junit.xml` }]],
  use: {
    baseURL: 'https://appassets.androidplatform.net/assets/www/',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'offline-chromium', use: { ...devices['Desktop Chrome'] } }],
});
