import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { chromium, expect as browserExpect, type Browser, type Page, type Route } from '@playwright/test';
import react from '@vitejs/plugin-react';
import { build } from 'vite';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { LearningSession } from '../src/api/types';

type Harness = {
  app(): void;
  prompt(key: string, activeTask: boolean): void;
  saveSession(session: LearningSession): Promise<void>;
  refreshIdentity(): Promise<unknown>;
};
type WorkerFixture = { installed(): void; waiting(): void; updates: number };

function activeSessionFixture(): LearningSession {
  return {
    id: 'test-session', profile_id: 'test-profile', mode: 'practice', status: 'active',
    created_at: '2026-11-05T12:00:00Z', completed_at: null, current_index: 0,
    requested_length: 5, notice: null, draft_revision: 0,
    tasks: [1, 2].map((slot) => ({
      id: `task-${slot}`, revision: '1', slot, topic: 'Тестовый номер', title: 'Тестовое условие',
      statement: 'Тестовый контент существует только в тестах.', formula: null, table: null,
      skill_ids: ['skill'], family_id: 'family', estimated_seconds: 60, review_status: 'demo', hint_count: 3,
    })),
    attempts: [], drafts: {}, help: {},
    summary: { total: 2, answered: 0, independent_total: 0, independent_correct: 0, assisted: 0, corrections: 0, skipped: 0, active_seconds: 0 },
  };
}

// Real React, App, identity and installed PWA registration clients. Only Workbox's browser boundary is controlled.
async function promptBundle(artifacts: string) {
  const root = resolve(import.meta.dirname, '..').replaceAll('\\', '/');
  const entry = '\0virtual:pwa-prompt-unit';
  const workbox = '\0virtual:pwa-workbox-fixture';
  const clients = `${root}/node_modules/vite-plugin-pwa/dist/client/build`;
  const built = await build({
    root, configFile: false, logLevel: 'silent', cacheDir: resolve(artifacts, 'vite-cache'),
    define: { 'process.env.NODE_ENV': JSON.stringify('development') },
    plugins: [react(), {
      name: 'pwa-prompt-mounted-entry',
      enforce: 'pre',
      resolveId(id) {
        if (id === 'virtual:pwa-prompt-unit') return entry;
        if (id === 'workbox-window') return workbox;
        if (id === 'virtual:pwa-register/react') return `${clients}/react.js`;
        if (id === 'virtual:pwa-register') return `${clients}/register.js`;
      },
      load(id) {
        if (id === workbox) return `
          const registrations = [];
          const fixture = window.workerFixture = {
            updates: 0,
            installed() { registrations[0].dispatchEvent(Object.assign(new Event('installed'), { isExternal: false })); },
            waiting() { registrations[0].dispatchEvent(new Event('waiting')); },
          };
          export class Workbox extends EventTarget {
            register() { registrations.push(this); return Promise.resolve({}); }
            messageSkipWaiting() { fixture.updates += 1; }
          }
        `;
        if (id === entry) return `
          import { createElement } from 'react';
          import { createRoot } from 'react-dom/client';
          import { flushSync } from 'react-dom';
          import App from '${root}/src/app/app.tsx';
          import { PwaPrompt } from '${root}/src/components/pwa-prompt.tsx';
          import { identity } from '${root}/src/storage/identity.ts';
          import { storage } from '${root}/src/storage/database.ts';
          import { createRecord } from '${root}/src/learning/model.ts';
          const root = createRoot(document.getElementById('root'));
          window.pwaHarness = {
            app: () => flushSync(() => root.render(createElement(App))),
            prompt: (key, activeTask) => flushSync(() => root.render(createElement(PwaPrompt, { key, activeTask }))),
            saveSession: async (session) => { await storage.saveSession(createRecord(session)); await storage.setActive(session.id); },
            refreshIdentity: () => identity.refresh(),
          };
        `;
      },
    }],
    build: {
      write: false, minify: false, outDir: resolve(artifacts, 'bundle'),
      lib: { entry: 'virtual:pwa-prompt-unit', name: 'PwaPromptUnit', formats: ['iife'] },
      rolldownOptions: { input: 'virtual:pwa-prompt-unit' },
    },
  });
  const output = (Array.isArray(built) ? built : [built]).flatMap((item) => {
    if (!('output' in item)) throw new Error('PWA component build unexpectedly returned a watcher.');
    return item.output;
  });
  const script = output.find((item) => item.type === 'chunk');
  if (!script || script.type !== 'chunk') throw new Error('PWA component bundle is missing.');
  writeFileSync(resolve(artifacts, 'prompt-bundle.js'), script.code);
  return script.code;
}

describe('PWA notifications across identity shell replacement', () => {
  let browser: Browser;
  let page: Page;
  let bundle: string;
  let pendingIdentity: Route | undefined;
  let errors: string[];

  beforeAll(async () => {
    const base = process.env.LOCALAPPDATA ? resolve(process.env.LOCALAPPDATA, 'Temp', 'opencode') : resolve(tmpdir(), 'opencode');
    mkdirSync(base, { recursive: true });
    const artifacts = mkdtempSync(resolve(base, 'math-ege-pwa-prompt-'));
    bundle = await promptBundle(artifacts);
    browser = await chromium.launch({
      headless: true, env: { ...process.env, TEMP: artifacts, TMP: artifacts, TMPDIR: artifacts },
    });
  }, 60_000);
  afterAll(async () => { await browser?.close(); });
  beforeEach(async () => {
    pendingIdentity = undefined;
    errors = [];
    page = await browser.newPage();
    page.on('pageerror', (error) => { errors.push(error.message); });
    await page.route('**/*', (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="ru"><body><div id="root"></div></body></html>' });
      if (path === '/api/v1/identity') { pendingIdentity = route; return; }
      return route.abort();
    });
    await page.goto('https://pwa-unit.test/#/missing');
    await page.addScriptTag({ content: bundle });
  });
  afterEach(async () => { await page?.close(); expect(errors).toEqual([]); });

  function notice() { return page.getByRole('complementary', { name: 'Установка и обновление приложения' }); }
  async function workerReady() {
    await browserExpect.poll(() => page.evaluate(() => Boolean((window as unknown as { workerFixture?: WorkerFixture }).workerFixture)), { timeout: 1_000 }).toBe(true);
    await page.evaluate(async () => { await new Promise<void>((done) => requestAnimationFrame(() => done())); });
  }
  async function identify() {
    await browserExpect.poll(() => Boolean(pendingIdentity)).toBe(true);
    await pendingIdentity!.fulfill({ json: { id: 'pwa-owner', kind: 'guest', owner_ids: ['pwa-owner'] } });
  }

  it('keeps the installed-shell notice when canonical identity bootstrap replaces the shell', async () => {
    await page.evaluate(() => (window as unknown as { pwaHarness: Harness }).pwaHarness.app());
    await workerReady();
    await page.evaluate(() => (window as unknown as { workerFixture: WorkerFixture }).workerFixture.installed());
    await browserExpect(notice()).toContainText('Оболочка доступна без сети');
    await identify();
    await browserExpect(page.getByRole('heading', { name: 'Страница не найдена', exact: true })).toBeVisible();
    await browserExpect(notice()).toContainText('Оболочка доступна без сети', { timeout: 1_000 });
    await page.getByRole('button', { name: 'Позже', exact: true }).click();
    await page.evaluate(() => (window as unknown as { pwaHarness: Harness }).pwaHarness.prompt('after-dismissal', false));
    await browserExpect(notice()).toHaveCount(0);
  });

  it('retains update prompts across remounts without updating an active or durably saved session', async () => {
    await page.evaluate(() => (window as unknown as { pwaHarness: Harness }).pwaHarness.prompt('active-route', true));
    await workerReady();
    await page.evaluate(() => (window as unknown as { workerFixture: WorkerFixture }).workerFixture.waiting());
    await browserExpect(notice()).toContainText('Обновление отложено.');
    await browserExpect(notice().getByRole('button', { name: 'Обновить', exact: true })).toHaveCount(0);
    const refresh = page.evaluate(() => (window as unknown as { pwaHarness: Harness }).pwaHarness.refreshIdentity());
    await identify();
    await refresh;
    await page.evaluate((session) => (window as unknown as { pwaHarness: Harness }).pwaHarness.saveSession(session), activeSessionFixture());
    await page.evaluate(() => (window as unknown as { pwaHarness: Harness }).pwaHarness.prompt('another-route', false));
    await browserExpect(notice()).toContainText('Доступна новая версия', { timeout: 1_000 });
    await notice().getByRole('button', { name: 'Обновить', exact: true }).click();
    await browserExpect(notice()).toContainText('Обновление отложено.');
    expect(await page.evaluate(() => (window as unknown as { workerFixture: WorkerFixture }).workerFixture.updates)).toBe(0);
  });
});
