import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const backend = resolve(import.meta.dirname, '../backend');
const python = resolve(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const temporaryRoot = process.platform === 'win32' && process.env.LOCALAPPDATA
  ? resolve(process.env.LOCALAPPDATA, 'Temp/opencode')
  : tmpdir();
const database = resolve(temporaryRoot, `math-ege-e2e-${randomUUID()}.db`).replaceAll('\\', '/');
mkdirSync(temporaryRoot, { recursive: true });

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  globalTimeout: 300_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      name: 'api',
      command: `"${python}" -m alembic upgrade head && "${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`,
      cwd: backend,
      env: {
        DATABASE_URL: `sqlite:///${database}`,
        ALLOW_DEMO_CONTENT: 'true',
        COOKIE_SECURE: 'false',
        ALLOWED_ORIGINS: 'http://127.0.0.1:5173',
      },
      url: 'http://127.0.0.1:8000/api/v1/health',
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      name: 'client',
      command: 'npm run build && npm run preview -- --port 5173 --strictPort',
      url: 'http://127.0.0.1:5173',
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
