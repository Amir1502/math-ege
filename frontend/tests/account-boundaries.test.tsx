import { mkdirSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { chromium, expect as browserExpect, type Browser, type Locator, type Page, type Route } from '@playwright/test';
import react from '@vitejs/plugin-react';
import { build } from 'vite';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { Account, AuthConfig, DeletionCancellation, DeletionRequest, MfaEnrollment } from '../src/accounts/types';
import type { HistoryExport } from '../src/api/types';
import type { IdentityManager, IdentityView } from '../src/storage/identity';

const account: Account = {
  id: 'account-one', email: 'student@example.org', email_verified: true, role: 'student',
  root_guest_id: 'owner-one', owner_ids: ['owner-one'], created_at: '2026-11-05T10:00:00Z',
  policy_version: '2026-11', consented_at: '2026-11-05T10:00:00Z', daily_minutes: 20,
  mfa_enabled: false, mfa_verified_until: null,
};
const config: AuthConfig = {
  enabled: true, policy_version: '2026-11', policy_url: 'https://example.org/privacy', link_ttl_seconds: 900,
};
const owner: IdentityView = { id: account.root_guest_id, kind: 'account', owner_ids: account.owner_ids };
const guest: IdentityView = { id: 'guest-after-logout', kind: 'guest', owner_ids: ['guest-after-logout'] };
const otherAccount: Account = { ...account, id: 'account-two', email: 'other@example.org', root_guest_id: 'owner-two', owner_ids: ['owner-two'] };
const firstRequest: DeletionRequest = {
  id: '11111111-1111-4111-8111-111111111111', status: 'requested',
  requested_at: '2026-11-05T10:00:00Z', deadline_at: '2026-12-05T10:00:00Z',
};
const newerRequest: DeletionRequest = {
  id: '22222222-2222-4222-8222-222222222222', status: 'requested',
  requested_at: '2026-11-06T10:00:00Z', deadline_at: '2026-12-06T10:00:00Z',
};
const canceledFirst: DeletionCancellation = { ...firstRequest, status: 'canceled', canceled_at: '2026-11-06T10:05:00Z' };
const history: HistoryExport = {
  version: '1', exported_at: '2026-11-06T10:05:00Z', profile_id: 'profile-2027', sessions: [], assessments: [],
  learning: { algorithm_version: 'v1', annotations: [], reviews: [], corrections: [] },
  account: {
    id: account.id, email: account.email, created_at: account.created_at, email_verified_at: account.created_at,
    role: 'student', daily_minutes: 20, consents: [{ policy_version: '2026-11', accepted_at: account.consented_at }],
    deletion_request: null,
  },
};
const statusKey = 'GET /api/v1/account/deletion-request';
const cancelKey = `POST /api/v1/account/deletion-request/${firstRequest.id}/cancel`;
function enrollmentFixture(): MfaEnrollment {
  return {
    provisioning_uri: 'otpauth://totp/AccountBoundary?secret=ABCDEFGHIJKLMNOPQRSTUVWXYZ234567',
    expires_at: new Date(Date.now() + 600_000).toISOString(),
  };
}
type Surface = 'page' | 'retained-page' | 'data' | 'settings' | 'security';
type NativeObservations = { blobs: number; objectUrls: number; downloadClicks: number };

type Harness = {
  mount(surface: Surface, account: Account): void;
  refreshIdentity(): Promise<unknown>;
  externalChange(): Promise<void>;
  identitySnapshot(): ReturnType<IdentityManager['getSnapshot']>;
  flowSnapshot(): { action: string | null; lastAction: string | null; error: string | null };
  callbacks(): { settings: Account[]; verified: number };
  enrollment(owner: string): MfaEnrollment | null;
};
type Reply = (route: Route) => Promise<void> | void;
type RequestLog = { key: string; owner: string | undefined; body: string | null };
type Fixture = {
  identity: IdentityView | null;
  account: Account | null;
  deletion: DeletionRequest | null;
  replies: Map<string, Reply>;
  requests: RequestLog[];
  unexpected: string[];
};

// Like diagnostic-followups.test.tsx: real React + real browser, no DOM shim or listening server.
async function accountBundle(artifacts: string) {
  const root = resolve(import.meta.dirname, '..').replaceAll('\\', '/');
  const entry = '\0virtual:account-boundaries';
  const built = await build({
    root, configFile: false, logLevel: 'silent', cacheDir: resolve(artifacts, 'vite-cache'),
    define: { 'process.env.NODE_ENV': JSON.stringify('development') },
    plugins: [react(), {
      name: 'account-boundaries-mounted-entry',
      resolveId: (id) => id === 'virtual:account-boundaries' ? entry : undefined,
      load: (id) => id === entry ? `
        import { createElement, StrictMode, useState, useSyncExternalStore } from 'react';
        import { createRoot } from 'react-dom/client';
        import { flushSync } from 'react-dom';
        import AccountPage from '${root}/src/pages/account.tsx';
        import { AccountData } from '${root}/src/accounts/data-controls.tsx';
        import { AccountSettings } from '${root}/src/accounts/settings.tsx';
        import { StaffSecurity } from '${root}/src/accounts/staff-security.tsx';
        import { Loading } from '${root}/src/components/ui.tsx';
        import { useRoute } from '${root}/src/app/router.ts';
        import { identity } from '${root}/src/storage/identity.ts';
        import { accountFlow } from '${root}/src/accounts/runtime.ts';
        import '${root}/src/styles/tokens.css';
        import '${root}/src/styles/base.css';
        import '${root}/src/styles/components.css';
        const root = createRoot(document.getElementById('root'));
        const callbacks = { settings: [], verified: 0 };
        function SettingsHost({ account }) {
          const [current, setCurrent] = useState(account);
          return createElement(AccountSettings, { account: current, onChange(updated) {
            callbacks.settings.push(updated);
            setCurrent(updated);
          } });
        }
        function Boundary({ surface, account }) {
          const route = useRoute();
          const access = useSyncExternalStore(identity.subscribe, identity.getSnapshot);
          if (surface === 'retained-page') return createElement(AccountPage);
          if (route.path !== '/account') return createElement('h1', null, 'Помощь');
          // The page case follows App's transition unmount. Isolated panels stay mounted to prove transition latching.
          if (surface === 'page' && access.changing) return createElement(Loading, { label: 'Переключаем доступ' });
          const scope = access.epoch + ':' + (access.value?.id ?? 'none');
          if (surface === 'data') return createElement(AccountData, { scope, email: account.email });
          if (surface === 'settings') return createElement(SettingsHost, { account });
          if (surface === 'security') return createElement(StaffSecurity, {
            account, available: true, onVerified() { callbacks.verified += 1; },
          });
          return createElement(AccountPage);
        }
        window.accountBoundary = {
          mount: (surface, account) => flushSync(() => {
            const view = createElement(Boundary, { surface, account });
            root.render(surface === 'page' || surface === 'retained-page' ? createElement(StrictMode, null, view) : view);
          }),
          refreshIdentity: () => identity.refresh(),
          externalChange: () => identity.externalChange(),
          identitySnapshot: () => identity.getSnapshot(),
          flowSnapshot: () => accountFlow.getSnapshot(),
          callbacks: () => callbacks,
          enrollment: (owner) => accountFlow.enrollment(owner),
        };
      ` : undefined,
    }],
    build: {
      write: false, minify: false, outDir: resolve(artifacts, 'bundle'),
      lib: { entry: 'virtual:account-boundaries', name: 'AccountBoundaries', formats: ['iife'] },
      rolldownOptions: { input: 'virtual:account-boundaries' },
    },
  });
  const output = (Array.isArray(built) ? built : [built]).flatMap((item) => {
    if (!('output' in item)) throw new Error('Account component build unexpectedly returned a watcher.');
    return item.output;
  });
  const script = output.find((item) => item.type === 'chunk');
  if (!script || script.type !== 'chunk') throw new Error('Account component bundle is missing.');
  const css = output.filter((item) => item.type === 'asset' && item.fileName.endsWith('.css'))
    .map((item) => item.type === 'asset' ? String(item.source) : '').join('\n');
  return { script: script.code, css };
}

describe('mounted account lifetime boundaries', () => {
  let browser: Browser;
  let page: Page;
  let artifacts: string;
  let bundle: Awaited<ReturnType<typeof accountBundle>>;
  let fixture: Fixture;
  let pageErrors: string[];
  let finishedRequests: string[];
  let downloads: string[];

  beforeAll(async () => {
    const base = process.env.LOCALAPPDATA ? resolve(process.env.LOCALAPPDATA, 'Temp', 'opencode') : resolve(tmpdir(), 'opencode');
    mkdirSync(base, { recursive: true });
    artifacts = mkdtempSync(resolve(base, 'math-ege-account-boundaries-'));
    bundle = await accountBundle(artifacts);
    browser = await chromium.launch({
      headless: true, downloadsPath: resolve(artifacts, 'downloads'),
      env: { ...process.env, TMP: artifacts, TEMP: artifacts, TMPDIR: artifacts },
    });
  }, 60_000);
  afterAll(async () => { await browser?.close(); });
  beforeEach(async () => {
    fixture = { identity: owner, account, deletion: null, replies: new Map(), requests: [], unexpected: [] };
    pageErrors = [];
    finishedRequests = [];
    downloads = [];
    page = await browser.newPage({ serviceWorkers: 'block', timezoneId: 'UTC', locale: 'ru-RU' });
    page.setDefaultTimeout(2_000);
    page.on('pageerror', (error) => { pageErrors.push(error.message); });
    const finished = (request: { method(): string; url(): string }) => { finishedRequests.push(`${request.method()} ${new URL(request.url()).pathname}`); };
    page.on('requestfinished', finished);
    page.on('requestfailed', finished);
    page.on('download', (download) => { downloads.push(download.suggestedFilename()); });
    await page.addInitScript(() => {
      const observed = { blobs: 0, objectUrls: 0, downloadClicks: 0 };
      (window as unknown as { accountNative: NativeObservations }).accountNative = observed;
      // Observers delegate to the native APIs; no download or Blob implementation is mocked.
      window.Blob = new Proxy(Blob, { construct(target, args, newTarget) {
        observed.blobs += 1;
        return Reflect.construct(target, args, newTarget);
      } });
      const createObjectURL = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (object) => { observed.objectUrls += 1; return createObjectURL(object); };
      document.addEventListener('click', (event) => {
        if (event.target instanceof HTMLAnchorElement && event.target.download) observed.downloadClicks += 1;
      }, true);
    });
  });
  afterEach(async () => {
    await page?.close();
    expect(fixture.unexpected, 'No external request may escape the mocked API fixture.').toEqual([]);
    expect(pageErrors, 'The mounted component must not raise uncaught errors.').toEqual([]);
  });

  async function mount(surface: Surface = 'page') {
    await page.route('**/*', async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/') return route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<!doctype html><html lang="ru"><head><meta charset="utf-8"></head><body><nav><a href="#/help">Помощь</a></nav><main id="root"></main></body></html>' });
      const key = `${route.request().method()} ${path}`;
      fixture.requests.push({ key, owner: route.request().headers()['x-learning-owner'], body: route.request().postData() });
      const reply = fixture.replies.get(key);
      if (reply) return reply(route);
      if (key === 'GET /api/v1/identity') return route.fulfill(fixture.identity ? { json: fixture.identity } : { status: 401, json: {} });
      if (key === 'GET /api/v1/auth/config') return route.fulfill({ json: config });
      if (key === 'GET /api/v1/account') return route.fulfill(fixture.account
        ? { json: fixture.account } : { status: 401, json: { error: { code: 'not_authenticated' } } });
      if (key === 'GET /api/v1/account/sessions') return route.fulfill({ json: { sessions: [] } });
      if (key === statusKey) return route.fulfill({ json: { request: fixture.deletion } });
      if (key === 'GET /api/v1/export') return route.fulfill({ json: history });
      fixture.unexpected.push(key);
      return route.abort();
    });
    await page.goto('http://account-boundaries.test/#/account');
    await page.addStyleTag({ content: bundle.css });
    await page.addScriptTag({ content: bundle.script });
    await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.refreshIdentity());
    await page.evaluate(({ surface, account }) => (window as unknown as { accountBoundary: Harness }).accountBoundary.mount(surface, account), { surface, account });
    if (surface === 'page' || surface === 'retained-page') await browserExpect(page.getByRole('button', { name: 'Выйти', exact: true })).toBeVisible();
  }

  async function settle() {
    // Drain promise continuations and React commits, not an arbitrary network delay.
    await page.evaluate(async () => {
      await new Promise<void>((done) => requestAnimationFrame(() => done()));
      await new Promise<void>((done) => requestAnimationFrame(() => done()));
    });
  }

  function hold(key: string) {
    const pending: Route[] = [];
    fixture.replies.set(key, (route) => { pending.push(route); });
    return async () => {
      await browserExpect.poll(() => pending.length).toBeGreaterThan(0);
      return pending.shift()!;
    };
  }

  function requests(key: string) { return fixture.requests.filter((request) => request.key === key); }
  function deletionControls() { return page.locator('.account-deletion'); }
  async function identitySnapshot() {
    return page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.identitySnapshot());
  }
  async function nativeObservations() {
    return page.evaluate(() => (window as unknown as { accountNative: NativeObservations }).accountNative);
  }
  async function clickTwice(button: Locator) {
    // Two native clicks in one event turn exercise the in-flight latch, not only a later disabled attribute.
    await button.evaluate((element) => {
      if (!(element instanceof HTMLButtonElement)) throw new Error('Expected a native action button.');
      element.click(); element.click();
    });
  }
  async function leave() {
    await page.getByRole('link', { name: 'Помощь', exact: true }).click();
    await browserExpect(page.getByRole('heading', { name: 'Помощь', exact: true })).toBeVisible();
  }
  async function finished(key: string) {
    await browserExpect.poll(() => finishedRequests.includes(key)).toBe(true);
    await settle();
  }
  async function flowSettled() {
    await browserExpect.poll(() => page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.flowSnapshot().action)).toBeNull();
    await settle();
  }

  it('finishes canonical logout without letting the departed page replace the chosen help route', async () => {
    const pending = hold('POST /api/v1/auth/logout');
    await mount();
    if (process.env.ACCOUNT_BOUNDARY_SHOTS) {
      await browserExpect(page.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toBeVisible();
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await page.screenshot({ path: resolve(artifacts, `logout-account-${width}.png`), fullPage: true });
      }
      console.info(`Account boundary screenshots: ${artifacts}`);
    }
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    const response = await pending();
    expect((await identitySnapshot()).changing).toBe(true);
    await leave();
    fixture.identity = guest;
    fixture.account = null;
    await response.fulfill({ json: { ok: true } });
    await flowSettled();
    expect(await identitySnapshot()).toMatchObject({
      value: guest, ready: true, changing: false, error: null, epoch: 2,
    });
    expect(requests('POST /api/v1/auth/logout')).toEqual([
      { key: 'POST /api/v1/auth/logout', owner: 'owner-one', body: '{}' },
    ]);
    expect(new URL(page.url()).hash).toBe('#/help');
    await browserExpect(page.getByRole('heading', { name: 'Помощь', exact: true })).toBeVisible();
  });

  it('does not navigate from an old route even before the account page has unmounted', async () => {
    const pending = hold('POST /api/v1/auth/logout');
    await mount('retained-page');
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    const response = await pending();
    await page.getByRole('link', { name: 'Помощь', exact: true }).click();
    expect(new URL(page.url()).hash).toBe('#/help');
    await browserExpect(page.getByRole('heading', { name: 'Аккаунт', exact: true })).toBeVisible();
    fixture.identity = guest;
    fixture.account = null;
    await response.fulfill({ json: { ok: true } });
    await flowSettled();
    expect((await identitySnapshot()).value).toEqual(guest);
    expect(new URL(page.url()).hash).toBe('#/help');
  });

  it('keeps canonical logout failure observable without showing a departed page error or changing its route', async () => {
    const pending = hold('POST /api/v1/auth/logout');
    await mount();
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    const response = await pending();
    await leave();
    await response.fulfill({ status: 503, json: { error: { code: 'request_failed' } } });
    await flowSettled();
    expect(await identitySnapshot()).toMatchObject({ value: owner, ready: true, changing: false, error: null, epoch: 1 });
    expect(await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.flowSnapshot())).toMatchObject({
      action: null, lastAction: 'logout', error: 'Сервер не выполнил запрос. Повторите позже.',
    });
    expect(new URL(page.url()).hash).toBe('#/help');
    await browserExpect(page.getByRole('alert')).toHaveCount(0);
  });

  it('still completes a chosen logout and opens the signed-out account view when the visitor stays there', async () => {
    const pending = hold('POST /api/v1/auth/logout');
    await mount();
    await page.getByRole('button', { name: 'Выйти', exact: true }).click();
    const response = await pending();
    fixture.identity = guest;
    fixture.account = null;
    await response.fulfill({ json: { ok: true } });
    await flowSettled();
    expect(await identitySnapshot()).toMatchObject({ value: guest, ready: true, changing: false, epoch: 2 });
    expect(new URL(page.url()).hash).toBe('#/account');
    await browserExpect(page.getByRole('textbox', { name: 'Email', exact: true })).toBeVisible();
    expect(requests('POST /api/v1/auth/logout')).toHaveLength(1);
  });

  it('retries exactly R1 after its lost cancellation response reveals persisted R2, then rereads and leaves R2 intact', async () => {
    fixture.deletion = firstRequest;
    const pending = hold(cancelKey);
    await mount('data');
    const controls = deletionControls();
    const cancel = controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true });
    await browserExpect(cancel).toBeVisible();
    await clickTwice(cancel);
    const first = await pending();
    await browserExpect(controls).toHaveAttribute('aria-busy', 'true');
    await browserExpect(controls.getByRole('button', { name: 'Отменяем запрос…', exact: true })).toBeDisabled();
    await browserExpect(controls.getByRole('button', { name: 'Обновить статус', exact: true })).toBeDisabled();
    expect(requests(cancelKey)).toHaveLength(1);
    fixture.deletion = newerRequest;
    await first.abort('failed');
    const retry = controls.getByRole('button', { name: 'Повторить отмену этого запроса', exact: true });
    await browserExpect(retry).toBeVisible();
    await browserExpect(cancel).toBeVisible();
    await browserExpect(controls.locator('.account-receipt')).toContainText('6 ноября');
    await browserExpect(controls).toContainText('ранее выбранному запросу от 5 ноября');
    await browserExpect(controls).toContainText('Более новый запрос не будет отменён этим повтором.');
    expect(requests(cancelKey)).toHaveLength(1); // Status recovery must not automatically repeat the mutation.
    expect(requests(statusKey)).toHaveLength(2);
    await clickTwice(retry);
    const second = await pending();
    await browserExpect(controls.locator('button:enabled')).toHaveCount(0);
    expect(requests(cancelKey)).toHaveLength(2);
    const persisted = hold(statusKey);
    await second.fulfill({ json: canceledFirst });
    const reread = await persisted();
    await browserExpect(controls.getByText('Запрос удаления отменён', { exact: true })).toBeFocused();
    await browserExpect(controls.getByRole('status', { name: 'Проверяем статус запроса', exact: true })).toBeVisible();
    await browserExpect(cancel).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toHaveCount(0);
    await reread.fulfill({ json: { request: newerRequest } });
    await browserExpect(cancel).toBeEnabled();
    await browserExpect(controls.locator('.account-receipt').first()).toContainText('6 ноября');
    await browserExpect(controls.getByText('Запрос удаления отменён', { exact: true })).toBeVisible();
    await browserExpect(controls).toContainText('Отменён только этот запрос. Это действие не удаляет аккаунт или данные.');
    await browserExpect(retry).toHaveCount(0);
    expect(requests(statusKey)).toHaveLength(3);
    expect(fixture.requests.filter((request) => request.key.endsWith('/cancel'))).toEqual([
      { key: cancelKey, owner: 'owner-one', body: '{}' }, { key: cancelKey, owner: 'owner-one', body: '{}' },
    ]);
    expect(requests('POST /api/v1/account/deletion-request')).toHaveLength(0);
  });

  it('disables every deletion action during an explicit R1 retry after the persisted-status read has failed', async () => {
    fixture.deletion = firstRequest;
    const pending = hold(cancelKey);
    await mount('data');
    const controls = deletionControls();
    await browserExpect(controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true })).toBeVisible();
    fixture.replies.set(statusKey, (route) => route.fulfill({ status: 503, json: { error: { code: 'request_failed' } } }));
    await controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true }).click();
    await (await pending()).abort('failed');
    const retry = controls.getByRole('button', { name: 'Повторить отмену этого запроса', exact: true });
    await browserExpect(retry).toBeEnabled();
    await browserExpect(controls.getByRole('button', { name: 'Повторить', exact: true })).toBeEnabled();
    await browserExpect(controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true })).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toHaveCount(0);
    await clickTwice(retry);
    const response = await pending();
    await browserExpect(controls).toHaveAttribute('aria-busy', 'true');
    await browserExpect(controls.locator('button:enabled')).toHaveCount(0);
    expect(requests(cancelKey)).toHaveLength(2);
    await response.fulfill({ json: canceledFirst });
    await browserExpect(controls.getByText('Запрос удаления отменён', { exact: true })).toBeFocused();
    await browserExpect(controls.getByRole('alert')).toContainText('Сервер не выполнил запрос.');
    await browserExpect(retry).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true })).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toHaveCount(0);
    fixture.replies.delete(statusKey);
    fixture.deletion = null;
    await controls.getByRole('button', { name: 'Обновить статус', exact: true }).click();
    await browserExpect(controls.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toBeEnabled();
    expect(requests(cancelKey)).toHaveLength(2);
    expect(requests(statusKey)).toHaveLength(4);
  });

  it('withholds current deletion actions and cached receipts during initial loading, refresh loading and refresh failure', async () => {
    const pending = hold(statusKey);
    await mount('data');
    const controls = deletionControls();
    const first = await pending();
    await browserExpect(controls.getByRole('status', { name: 'Проверяем статус запроса', exact: true })).toBeVisible();
    await browserExpect(controls.getByRole('button', { name: /^(Отменить запрос удаления|Запросить удаление аккаунта)$/ })).toHaveCount(0);
    await first.fulfill({ json: { request: firstRequest } });
    await browserExpect(controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true })).toBeEnabled();
    await controls.getByRole('button', { name: 'Обновить статус', exact: true }).click();
    const refresh = await pending();
    await browserExpect(controls.getByRole('status', { name: 'Проверяем статус запроса', exact: true })).toBeVisible();
    await browserExpect(controls.getByText('Запрос на удаление принят', { exact: true })).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: /^(Отменить запрос удаления|Запросить удаление аккаунта)$/ })).toHaveCount(0);
    await refresh.fulfill({ status: 503, json: { error: { code: 'request_failed' } } });
    await browserExpect(controls.getByRole('alert')).toContainText('Сервер не выполнил запрос.');
    await browserExpect(controls.getByText('Запрос на удаление принят', { exact: true })).toHaveCount(0);
    await browserExpect(controls.getByRole('button', { name: /^(Отменить запрос удаления|Запросить удаление аккаунта)$/ })).toHaveCount(0);
    await controls.getByRole('button', { name: 'Повторить', exact: true }).click();
    await (await pending()).fulfill({ json: { request: newerRequest } });
    await browserExpect(controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true })).toBeEnabled();
    await browserExpect(controls.locator('.account-receipt')).toContainText('6 ноября');
    expect(fixture.requests.some((request) => request.key.startsWith('POST '))).toBe(false);
  });

  it('does not enable another mutation when an accepted cancellation receipt is followed by stale persisted R1', async () => {
    fixture.deletion = firstRequest;
    const pending = hold(cancelKey);
    await mount('data');
    const controls = deletionControls();
    await controls.getByRole('button', { name: 'Отменить запрос удаления', exact: true }).click();
    await (await pending()).fulfill({ json: canceledFirst });
    await browserExpect(controls.getByText('Запрос удаления отменён', { exact: true })).toBeFocused();
    await browserExpect(controls.getByRole('alert')).toContainText('Отмена подтверждена, но текущий статус ещё не обновлён.');
    await browserExpect(controls.getByRole('button', { name: /^(Отменить запрос удаления|Запросить удаление аккаунта|Повторить отмену этого запроса)$/ })).toHaveCount(0);
    expect(requests(cancelKey)).toHaveLength(1);
    expect(requests(statusKey)).toHaveLength(2);
    fixture.deletion = null;
    await controls.getByRole('button', { name: 'Обновить статус', exact: true }).click();
    await browserExpect(controls.getByRole('button', { name: 'Запросить удаление аккаунта', exact: true })).toBeEnabled();
    expect(requests(cancelKey)).toHaveLength(1);
    expect(requests(statusKey)).toHaveLength(3);
  });

  it('downloads the complete valid seven-field export through the native browser APIs only once', async () => {
    await mount('data');
    const download = page.waitForEvent('download');
    await clickTwice(page.getByRole('button', { name: 'Скачать историю JSON', exact: true }));
    const file = await download;
    const stream = await file.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(Buffer.from(chunk));
    const exported: unknown = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    expect(exported).toEqual(history);
    expect(Object.keys(exported as object)).toEqual(['version', 'exported_at', 'profile_id', 'sessions', 'assessments', 'learning', 'account']);
    expect(file.suggestedFilename()).toBe('ege-account-history.json');
    expect(downloads).toEqual(['ege-account-history.json']);
    expect(await nativeObservations()).toEqual({ blobs: 1, objectUrls: 1, downloadClicks: 1 });
    expect(requests('GET /api/v1/export')).toHaveLength(1);
    await browserExpect(page.getByText('Файл подготовлен. Сохраните его в надёжном месте.', { exact: true })).toBeVisible();
  });

  it.each(['unmount', 'different owner', 'same-owner transition'] as const)('never creates a Blob or download for a valid delayed export after %s', async (boundary) => {
    const key = 'GET /api/v1/export';
    const pending = hold(key);
    await mount('data');
    const before = await identitySnapshot();
    await clickTwice(page.getByRole('button', { name: 'Скачать историю JSON', exact: true }));
    const response = await pending();
    await browserExpect(page.getByRole('button', { name: 'Готовим файл…', exact: true })).toBeDisabled();
    expect(requests(key)).toHaveLength(1);
    expect(await nativeObservations()).toEqual({ blobs: 0, objectUrls: 0, downloadClicks: 0 });
    if (boundary === 'unmount') await leave();
    else {
      if (boundary === 'different owner') {
        fixture.identity = { id: otherAccount.root_guest_id, kind: 'account', owner_ids: otherAccount.owner_ids };
        fixture.account = otherAccount;
      }
      await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.externalChange());
      const after = await identitySnapshot();
      expect(after).toMatchObject({ ready: true, changing: false, error: null });
      if (boundary === 'same-owner transition') {
        expect(after.value).toEqual(before.value);
        expect(after.epoch).toBe(before.epoch);
      } else expect(after).toMatchObject({ value: { id: 'owner-two' }, epoch: 2 });
    }
    // This is exactly the DTO that the positive native-download test accepts, not a malformed response.
    await response.fulfill({ json: history });
    await finished(key);
    expect(await nativeObservations()).toEqual({ blobs: 0, objectUrls: 0, downloadClicks: 0 });
    expect(downloads).toEqual([]);
    await browserExpect(page.getByText('Файл подготовлен. Сохраните его в надёжном месте.', { exact: true })).toHaveCount(0);
  });

  it('delivers a valid live settings response to the real mounted consumer and focuses its saved status', async () => {
    const key = 'PATCH /api/v1/account';
    const pending = hold(key);
    const updated = { ...account, daily_minutes: 30 } satisfies Account;
    await mount('settings');
    await page.getByRole('radio', { name: '30 мин', exact: true }).check();
    await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click();
    const response = await pending();
    await browserExpect(page.getByRole('button', { name: 'Сохраняем…', exact: true })).toBeDisabled();
    await response.fulfill({ json: updated });
    await finished(key);
    expect(await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.callbacks())).toEqual({ settings: [updated], verified: 0 });
    await browserExpect(page.getByText('Настройки сохранены.', { exact: true })).toBeFocused();
    await browserExpect(page.getByRole('radio', { name: '30 мин', exact: true })).toBeChecked();
    expect(requests(key)).toEqual([{ key, owner: 'owner-one', body: '{"daily_minutes":30}' }]);
  });

  it('presents a valid live enrollment in the real mounted security panel without a duplicate transport', async () => {
    const key = 'POST /api/v1/auth/mfa/enroll';
    const pending = hold(key);
    const enrollment = enrollmentFixture();
    await mount('security');
    await clickTwice(page.getByRole('button', { name: 'Настроить подтверждение кодом', exact: true }));
    const response = await pending();
    await browserExpect(page.getByRole('button', { name: 'Готовим настройку…', exact: true })).toBeDisabled();
    await response.fulfill({ json: enrollment });
    await flowSettled();
    await browserExpect(page.getByRole('textbox', { name: 'Адрес настройки для приложения-аутентификатора', exact: true })).toHaveValue(enrollment.provisioning_uri);
    expect(await page.evaluate((id) => (window as unknown as { accountBoundary: Harness }).accountBoundary.enrollment(id), account.id)).toEqual(enrollment);
    expect(requests(key)).toEqual([{ key, owner: 'owner-one', body: '{}' }]);
  });

  describe.each(['unmount', 'same-owner transition'] as const)('valid delayed panel responses after %s', (boundary) => {
    it.each(['settings', 'enrollment', 'cancellation'] as const)('cannot repopulate %s or invoke expired consumer callbacks', async (operation) => {
      const key = operation === 'settings' ? 'PATCH /api/v1/account' : operation === 'enrollment' ? 'POST /api/v1/auth/mfa/enroll' : cancelKey;
      const pending = hold(key);
      if (operation === 'cancellation') fixture.deletion = firstRequest;
      await mount(operation === 'settings' ? 'settings' : operation === 'enrollment' ? 'security' : 'data');
      const before = await identitySnapshot();
      if (operation === 'settings') {
        await page.getByRole('radio', { name: '30 мин', exact: true }).check();
        await page.getByRole('button', { name: 'Сохранить настройки', exact: true }).click();
      } else if (operation === 'enrollment') await clickTwice(page.getByRole('button', { name: 'Настроить подтверждение кодом', exact: true }));
      else await deletionControls().getByRole('button', { name: 'Отменить запрос удаления', exact: true }).click();
      const response = await pending();
      expect(requests(key)).toHaveLength(1);
      if (boundary === 'unmount') await leave();
      else {
        if (operation === 'cancellation') fixture.deletion = newerRequest;
        await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.externalChange());
        const after = await identitySnapshot();
        expect(after).toMatchObject({ value: before.value, epoch: before.epoch, ready: true, changing: false, error: null });
        await settle();
        if (operation === 'cancellation') await browserExpect(deletionControls().locator('.account-receipt')).toContainText('6 ноября');
      }
      const statusReads = requests(statusKey).length;
      const enrollment = enrollmentFixture();
      await response.fulfill({ json: operation === 'settings' ? { ...account, daily_minutes: 30 }
        : operation === 'enrollment' ? enrollment : canceledFirst });
      await finished(key);
      if (operation === 'enrollment') await flowSettled();
      expect(await page.evaluate(() => (window as unknown as { accountBoundary: Harness }).accountBoundary.callbacks())).toEqual({ settings: [], verified: 0 });
      if (operation === 'settings') await browserExpect(page.getByText('Настройки сохранены.', { exact: true })).toHaveCount(0);
      if (operation === 'enrollment') {
        expect(await page.evaluate((id) => (window as unknown as { accountBoundary: Harness }).accountBoundary.enrollment(id), account.id)).toBeNull();
        await browserExpect(page.getByRole('textbox', { name: 'Адрес настройки для приложения-аутентификатора', exact: true })).toHaveCount(0);
        await browserExpect(page.locator('body')).not.toContainText(enrollment.provisioning_uri);
      }
      if (operation === 'cancellation') {
        await browserExpect(page.getByText('Запрос удаления отменён', { exact: true })).toHaveCount(0);
        expect(requests(statusKey)).toHaveLength(statusReads);
        if (boundary === 'same-owner transition') await browserExpect(deletionControls().locator('.account-receipt')).toContainText('6 ноября');
      }
    });
  });
});
