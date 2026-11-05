import { mkdtempSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

if (!process.env.LOCALAPPDATA) throw new Error('This isolated identity browser config requires Windows LOCALAPPDATA.');
const temporary = resolve(process.env.LOCALAPPDATA, 'Temp/opencode');
const root = process.env.IDENTITY_BROWSER_RUN_ROOT ?? mkdtempSync(resolve(temporary, 'identity-browser-'));
process.env.IDENTITY_BROWSER_RUN_ROOT = root;
// Playwright 1.64's automatic failure DOM snapshot can contain email/MFA fields.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1';

export default defineConfig({
  testDir: '../e2e', testMatch: 'identity.spec.ts', fullyParallel: false, workers: 1,
  retries: 0, timeout: 120_000, globalTimeout: 600_000, expect: { timeout: 10_000 },
  outputDir: resolve(root, 'test-results'), reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5193', trace: 'off', screenshot: 'off', video: 'off',
    actionTimeout: 10_000, navigationTimeout: 30_000,
  },
  projects: [{ name: 'identity-chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: process.env.IDENTITY_BROWSER_EXTERNAL_SERVER === 'true' ? undefined : {
    command: 'node scripts/identity-browser.mjs', cwd: resolve(import.meta.dirname, '..'),
    env: { IDENTITY_BROWSER_RUN_ROOT: root }, url: 'http://127.0.0.1:5193/api/v1/health',
    timeout: 120_000, reuseExistingServer: false,
  },
});
