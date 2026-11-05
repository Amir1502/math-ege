import { spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { isAbsolute, relative, resolve } from 'node:path';
import { expect, test, type Browser, type BrowserContext, type Page, type Route } from '@playwright/test';
import { parseHistoryExport } from '../src/api/history-export';
import type { Attempt, ExportAnnotation, HistoryExport, LearningSession } from '../src/api/types';
import type { AssessmentRecord } from '../src/assessments/model';
import type { AssessmentView } from '../src/assessments/types';
import type { PendingStart, SessionRecord } from '../src/learning/model';
import type { IdentityView } from '../src/storage/identity';

const origin = 'http://127.0.0.1:5193';
const runRoot = process.env.IDENTITY_BROWSER_RUN_ROOT;
if (runRoot) process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1';
test.use({ trace: 'off', screenshot: 'off', video: 'off' });
const exportKeys = ['account', 'assessments', 'exported_at', 'learning', 'profile_id', 'sessions', 'version'];
const accountKeys = ['consents', 'created_at', 'daily_minutes', 'deletion_request', 'email', 'email_verified_at', 'id', 'role'];
type Mail = { email: string; link: string };
type History = { before: LearningSession; originalCookies: Awaited<ReturnType<BrowserContext['cookies']>> };
type Mutation = { path: string; key: string | undefined; owner: string | undefined; body: string | null };

function directory() {
  if (!runRoot || !process.env.LOCALAPPDATA) throw new Error('An isolated identity runtime is required.');
  const base = resolve(process.env.LOCALAPPDATA, 'Temp/opencode');
  const path = resolve(runRoot);
  const suffix = relative(base, path);
  if (!suffix || suffix.startsWith('..') || isAbsolute(suffix)) throw new Error('Unapproved identity runtime directory.');
  return path;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(',')}}`;
  return JSON.stringify(value);
}
const same = (a: unknown, b: unknown) => canonical(a) === canonical(b);
const hash = (value: string) => createHash('sha256').update(value).digest('hex');
function evidence(check: string, facts: Record<string, boolean | number | string>) {
  // Only allowlisted booleans, counts and hashes: never identity IDs, mail or credentials.
  appendFileSync(resolve(directory(), 'browser-evidence.jsonl'), `${JSON.stringify({ check, at: new Date().toISOString(), ...facts })}\n`);
}
async function privateAction<T>(action: () => Promise<T>): Promise<T> {
  try { return await action(); }
  catch { throw new Error('Private browser interaction failed; secret-bearing details suppressed.'); }
}
async function get<T>(page: Page, path: string): Promise<T> {
  const response = await privateAction(() => page.request.get(`/api/v1${path}`));
  expect(response.status(), 'Normal isolated API read succeeds').toBe(200);
  return await response.json() as T;
}
async function access(page: Page) { return get<IdentityView>(page, '/identity'); }
async function routeTo(page: Page, path: string) {
  await page.evaluate(value => { window.location.hash = `#${value}`; }, path);
}
async function newContext(browser: Browser, serviceWorkers: 'allow' | 'block' = 'block') {
  const context = await browser.newContext({ baseURL: origin, serviceWorkers, acceptDownloads: true });
  await context.route('**/*', async route => {
    if (new URL(route.request().url()).origin !== origin) await route.abort('blockedbyclient');
    else await route.continue();
  });
  return context;
}
async function practice(page: Page, length: 5 | 20 = 5) {
  await page.goto('/#/practice');
  await expect(page.getByRole('heading', { name: 'Практика', exact: true })).toBeVisible();
  await page.getByRole('radio', { name: `${length} задач`, exact: true }).check();
  const reply = page.waitForResponse(response => response.url().endsWith('/api/v1/sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const response = await reply;
  expect(response.status()).toBe(200);
  const session = await response.json() as LearningSession;
  await expect(page.getByLabel('Ответ', { exact: true })).toBeEditable();
  return session;
}
async function task(page: Page, index: number) {
  await page.getByRole('button', { name: new RegExp(`^Задача ${index + 1},`) }).click();
}
async function pause(page: Page) {
  const button = page.locator('.session-position').getByRole('button', { name: 'Пауза', exact: true });
  if (await button.isEnabled()) await button.click();
}
async function submit(page: Page, answer: string) {
  const reply = page.waitForResponse(response => response.url().endsWith('/attempts') && response.request().method() === 'POST');
  await page.getByLabel('Ответ', { exact: true }).fill(answer);
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  const response = await reply;
  expect(response.status()).toBe(200);
  const attempt = await response.json() as Attempt;
  await expect(page.getByRole('button', { name: 'Следующая задача', exact: true })).toBeVisible();
  return attempt;
}
async function guestHistory(page: Page): Promise<History> {
  const session = await practice(page);
  await submit(page, '12345');
  await task(page, 1);
  await pause(page);
  const saved = page.waitForResponse(response => response.url().endsWith(`/${session.id}/draft`)
    && response.request().postDataJSON().answer === '−2,50');
  await page.getByLabel('Ответ', { exact: true }).fill('−2,50');
  expect((await saved).status()).toBe(200);
  await expect.poll(async () => (await get<LearningSession>(page, `/sessions/${session.id}`)).drafts[session.tasks[1].id]?.answer).toBe('−2,50');
  const before = await get<LearningSession>(page, `/sessions/${session.id}`);
  const originalCookies = (await page.context().cookies()).filter(cookie => cookie.name === 'math_ege_guest');
  expect(originalCookies.length, 'Guest credential captured in memory only').toBe(1);
  return { before, originalCookies };
}
function mailbox(): Mail[] {
  const content = readFileSync(resolve(directory(), 'mailbox.jsonl'), 'utf8');
  return content.trim() ? content.trim().split('\n').map(line => JSON.parse(line) as Mail) : [];
}
async function login(page: Page, email: string) {
  await page.goto('/#/account');
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible();
  const count = mailbox().length;
  await privateAction(() => page.getByLabel('Email', { exact: true }).fill(email));
  await page.getByRole('checkbox', { name: 'Я принимаю политику обработки данных этой версии.', exact: true }).check();
  const sent = page.waitForResponse(response => response.url().endsWith('/auth/request-link'));
  await page.getByRole('button', { name: 'Получить ссылку для входа', exact: true }).click();
  expect((await sent).status()).toBe(202);
  await expect.poll(() => mailbox().length).toBe(count + 1);
  const message = mailbox().at(-1)!;
  expect(message.email === email && message.link.startsWith(`${origin}/account#token=`), 'Private mailbox is bound to synthetic local request').toBe(true);
  // Do not give secret URLs to goto/toHaveURL, reporters, CLI source or artifacts.
  await privateAction(() => page.evaluate(href => { window.location.assign(href); }, message.link));
  await expect(page.getByRole('heading', { name: 'Подтвердите вход', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.location.hash === '#/auth/complete' && window.history.state === null), 'Fragment erased by production startup').toBe(true);
  const complete = page.waitForResponse(response => response.url().endsWith('/auth/complete'));
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  expect((await complete).status()).toBe(200);
  await expect(page.getByRole('button', { name: 'Выйти', exact: true })).toBeVisible();
  return access(page);
}
async function dbRead<T>(page: Page, database: string, store: string, key: string | string[]): Promise<T | undefined> {
  return await page.evaluate(async ({ database, store, key }) => {
    return await new Promise((accept, reject) => {
      const opening = indexedDB.open(database);
      opening.onerror = () => reject(new Error('Read-only evidence lookup failed.'));
      opening.onsuccess = () => {
        const connection = opening.result;
        const transaction = connection.transaction(store, 'readonly');
        const request = transaction.objectStore(store).get(key);
        request.onsuccess = () => accept(request.result);
        request.onerror = () => reject(new Error('Read-only evidence lookup failed.'));
        transaction.oncomplete = () => connection.close();
      };
    });
  }, { database, store, key }) as T | undefined;
}
const record = (page: Page, owner: string, id: string) => dbRead<SessionRecord>(page, 'math-ege-learning-v1', 'scoped_sessions', [owner, id]);
const pendingStart = (page: Page, owner: string) => dbRead<PendingStart>(page, 'math-ege-learning-v1', 'scoped_meta', [owner, 'pending_start']);
function mutation(route: Route): Mutation {
  const request = route.request();
  return { path: new URL(request.url()).pathname, key: request.headers()['idempotency-key'], owner: request.headers()['x-learning-owner'], body: request.postData() };
}
function gate() {
  let release!: () => void;
  const promise = new Promise<void>(accept => { release = accept; });
  return { promise, release };
}
async function download(page: Page, control: 'progress' | 'account', name: string) {
  await routeTo(page, control === 'progress' ? '/progress' : '/account');
  const button = page.getByRole('button', { name: control === 'progress' ? 'Скачать JSON' : 'Скачать историю JSON', exact: true });
  await expect(button).toBeEnabled();
  const started = page.waitForEvent('download');
  await button.click();
  const file = await started;
  expect(file.suggestedFilename()).toBe(control === 'progress' ? 'ege-profile-history.json' : 'ege-account-history.json');
  await file.saveAs(resolve(directory(), 'downloads', name));
  expect(await file.failure()).toBeNull();
  const raw = readFileSync(resolve(directory(), 'downloads', name), 'utf8');
  const payload = JSON.parse(raw) as HistoryExport;
  expect(Object.keys(payload).sort()).toEqual(exportKeys);
  expect(payload.version).toBe('1');
  expect(Object.keys(payload.learning).sort()).toEqual(['algorithm_version', 'annotations', 'corrections', 'reviews']);
  expect(payload.account !== null, 'Complete download includes minimal account').toBe(true);
  expect(Object.keys(payload.account!).sort()).toEqual(accountKeys);
  expect(same(parseHistoryExport(payload), payload), 'Actual saved file passes exact complete-export parser without truncation').toBe(true);
  return { payload, sha256: hash(raw), bytes: Buffer.byteLength(raw) };
}
function frozenUnchanged(before: LearningSession, after: LearningSession) {
  expect(after.id === before.id, 'Original practice session ID retained').toBe(true);
  expect(same(after.profile, before.profile) && after.profile_revision === before.profile_revision && same(after.tasks, before.tasks), 'Original profile and task snapshots retained').toBe(true);
  expect(same(after.attempts, before.attempts), 'Original attempt IDs and entire attempt DTOs retained').toBe(true);
  expect(same(after.drafts, before.drafts), 'Original server drafts retained through claim').toBe(true);
}

test.describe.serial('isolated mounted identity, linking and complete exports', () => {
  test.skip(!runRoot, 'Opt in only with scripts/identity-browser.config.ts; never shared ports or database.');
  let a: BrowserContext;
  let b: BrowserContext;
  let primary: Page;
  let secondary: Page;
  let first: History;
  let second: History;
  let guestA: IdentityView;
  let guestB: IdentityView;
  let claimedA: IdentityView;
  let claimedB: IdentityView;
  let owner: string;
  let email: string;
  const ownedContexts: BrowserContext[] = [];
  const knownSessions: LearningSession[] = [];

  test.beforeAll(async ({ browser }) => {
    writeFileSync(resolve(directory(), 'browser-evidence.jsonl'), '', { flag: 'wx', mode: 0o600 });
    mkdirSync(resolve(directory(), 'downloads'));
    a = await newContext(browser); b = await newContext(browser);
    ownedContexts.push(a, b);
    primary = await a.newPage(); secondary = await b.newPage();
    email = `browser-${randomUUID()}@example.invalid`;
    // Shared scenario population, not repeated acceptance: --grep can run remaining
    // checks in a NEW runtime without rerunning the two-guest claim assertions.
    first = await guestHistory(primary); second = await guestHistory(secondary);
    guestA = await access(primary); guestB = await access(secondary);
    claimedA = await login(primary, email); claimedB = await login(secondary, email);
    owner = claimedA.id;
    knownSessions.push(first.before, second.before);
  });
  test.afterAll(async () => { await Promise.allSettled(ownedContexts.map(context => context.close())); });

  test('two guest histories are claimed without rewriting snapshots, attempts or drafts', async ({ browser }) => {
    expect(first.before.id !== second.before.id, 'Two distinct UI-created guest histories').toBe(true);
    expect(claimedA.kind === 'account' && claimedB.kind === 'account' && claimedA.id === claimedB.id).toBe(true);
    expect(claimedB.owner_ids.includes(guestA.id) && claimedB.owner_ids.includes(guestB.id), 'Both original owners linked, not copied').toBe(true);
    frozenUnchanged(first.before, await get<LearningSession>(primary, `/sessions/${first.before.id}`));
    frozenUnchanged(second.before, await get<LearningSession>(primary, `/sessions/${second.before.id}`));
    for (const history of [first, second]) {
      const revoked = await newContext(browser); ownedContexts.push(revoked);
      await privateAction(() => revoked.addCookies(history.originalCookies));
      expect((await revoked.request.get(`${origin}/api/v1/identity`)).status(), 'Claim revokes old guest credential').toBe(401);
      const page = await revoked.newPage();
      await page.goto(`/#/session/${history.before.id}`);
      await expect(page.getByRole('heading', { name: 'Занятие недоступно', exact: true })).toBeVisible();
      await expect(page.getByLabel('Ответ', { exact: true })).toHaveCount(0);
    }
    for (const history of [first, second]) {
      await routeTo(primary, `/session/${history.before.id}`);
      await expect(primary.getByLabel('Ответ', { exact: true })).toBeEditable();
      await task(primary, 1); await pause(primary);
      await expect(primary.getByLabel('Ответ', { exact: true })).toHaveValue('−2,50');
      const stored = await record(primary, owner, history.before.id);
      // The second browser adopts its own old namespace when it links into root A.
      if (history === first) expect(stored?.session.id === history.before.id).toBe(true);
    }
    const adopted = await record(secondary, owner, second.before.id);
    expect(adopted?.drafts[second.before.tasks[1].id].answer === '−2,50', 'Guest B IndexedDB draft adopted into account root').toBe(true);
    evidence('two-guest-claims', { guest_histories: 2, original_attempts: 2, full_snapshots_unchanged: true, drafts_unchanged: true, revoked_credentials: 2, adopted_indexeddb_draft: true });
  });

  test('same-owner MFA transition rejects held real progress and both stale downloads', async () => {
    test.setTimeout(120_000);
    await primary.goto('/#/account');
    const before = await access(primary);
    await primary.evaluate(() => {
      (window as Window & { identityEvidenceEvents?: number }).identityEvidenceEvents = 0;
      window.addEventListener('math-ege:identity-change', () => {
        const evidence = window as Window & { identityEvidenceEvents?: number };
        evidence.identityEvidenceEvents = (evidence.identityEvidenceEvents ?? 0) + 1;
      });
    });
    const initialDashboard = primary.waitForResponse(response => response.url().includes('/api/v1/learning/dashboard'));
    await routeTo(primary, '/progress');
    expect((await initialDashboard).status()).toBe(200);
    await expect(primary.getByRole('button', { name: 'Скачать JSON', exact: true })).toBeVisible();
    const old = gate(); const fresh = gate();
    const held: string[] = []; const settled: string[] = [];
    let downloads = 0;
    primary.on('download', () => { downloads += 1; });
    const hold = async (route: Route) => {
      const path = new URL(route.request().url()).pathname;
      const response = await route.fetch();
      held.push(path);
      await old.promise;
      await route.fulfill({ response });
      settled.push(path);
    };
    await primary.route('**/api/v1/progress', hold, { times: 1 });
    await primary.route('**/api/v1/learning/dashboard*', hold, { times: 1 });
    await primary.route('**/api/v1/export', hold, { times: 2 });
    try {
      await routeTo(primary, '/practice');
      await expect(primary.getByRole('heading', { name: 'Практика', exact: true })).toBeVisible();
      await routeTo(primary, '/progress');
      await expect.poll(() => held.filter(path => path !== '/api/v1/export').length).toBe(2);
      await primary.getByRole('button', { name: 'Скачать JSON', exact: true }).click();
      await expect.poll(() => held.filter(path => path === '/api/v1/export').length).toBe(1);
      await routeTo(primary, '/account');
      await primary.getByRole('button', { name: 'Скачать историю JSON', exact: true }).click();
      await expect.poll(() => held.filter(path => path === '/api/v1/export').length).toBe(2);
      // The production client erases setup on leaving /account. Enroll only now,
      // after all navigation and while both old export responses are held.
      await primary.getByRole('button', { name: 'Настроить подтверждение кодом', exact: true }).click();
      await expect(primary.getByLabel('Адрес настройки для приложения-аутентификатора', { exact: true })).toBeVisible();
      const uri = await privateAction(() => primary.getByLabel('Адрес настройки для приложения-аутентификатора', { exact: true }).inputValue());
      const python = resolve(import.meta.dirname, '../../backend/.venv/Scripts/python.exe');
      // Provisioning URI enters only stdin; the child result never reaches console/reporters.
      const result = spawnSync(python, ['-c', 'import sys, pyotp; sys.stdout.write(pyotp.parse_uri(sys.stdin.read()).now())'], { input: uri, encoding: 'utf8', windowsHide: true });
      expect(result.status === 0 && /^\d{6}$/.test(result.stdout), 'Private library-generated MFA code available').toBe(true);
      await routeTo(secondary, `/session/${second.before.id}`);
      await expect(secondary.getByLabel('Ответ', { exact: true })).toBeEditable();
      await task(secondary, 2); await pause(secondary);
      await submit(secondary, '98765');
      await expect(primary.getByLabel('Код из приложения', { exact: true })).toBeVisible();
      await privateAction(() => primary.getByLabel('Код из приложения', { exact: true }).fill(result.stdout));
      const confirmed = primary.waitForResponse(response => response.url().endsWith('/auth/mfa/confirm'));
      await primary.getByRole('button', { name: 'Подтвердить настройку', exact: true }).click();
      expect((await confirmed).status()).toBe(200);
      await expect(primary.getByText('Приложение-аутентификатор настроено. Администратор может назначить роль сотрудника.', { exact: true })).toBeVisible();
      expect(same(await access(primary), before), 'Owner ID, kind and origins unchanged across real auth transition').toBe(true);
      expect(await primary.evaluate(() => ((window as Window & { identityEvidenceEvents?: number }).identityEvidenceEvents ?? 0) > 0), 'Production transition event occurred despite same owner').toBe(true);
      old.release();
      await expect.poll(() => settled.length).toBe(4);
      // Hold the new reads too, so a fresh response cannot hide resurrection of old state.
      let freshHeld = 0;
      const holdFresh = async (route: Route) => {
        const response = await route.fetch(); freshHeld += 1;
        await fresh.promise; await route.fulfill({ response });
      };
      await primary.route('**/api/v1/progress', holdFresh, { times: 1 });
      await primary.route('**/api/v1/learning/dashboard*', holdFresh, { times: 1 });
      await routeTo(primary, '/progress');
      await expect.poll(() => freshHeld).toBe(2);
      await expect(primary.getByRole('heading', { name: 'Первые самостоятельные ответы', exact: true })).toHaveCount(0);
      await expect(primary.getByRole('button', { name: 'Скачать JSON', exact: true })).toHaveCount(0);
      expect(downloads, 'Neither held export became a stale download').toBe(0);
      fresh.release();
      await expect(primary.locator('.main-stat__value')).toHaveText(/\/\s*3$/);
      evidence('same-owner-transition', { unchanged_owner: true, transition_event: true, held_real_responses: 4, stale_downloads: downloads, stale_state_absent_while_fresh_reads_held: true, fresh_independent_total: 3 });
    } finally { old.release(); fresh.release(); }
  });

  test('logout, document remount and relogin isolate both IndexedDB pending queues', async () => {
    await primary.goto(`/#/session/${first.before.id}`);
    await expect(primary.getByLabel('Ответ', { exact: true })).toBeEditable();
    await task(primary, 2); await pause(primary);
    let originalAttempt!: Mutation; let acceptedAttempt!: Attempt;
    await primary.route('**/api/v1/sessions/*/attempts', async route => {
      originalAttempt = mutation(route);
      const response = await route.fetch(); expect(response.status()).toBe(200);
      acceptedAttempt = await response.json() as Attempt;
      await route.abort('failed');
    }, { times: 1 });
    await primary.getByLabel('Ответ', { exact: true }).fill('54321');
    await primary.getByRole('button', { name: 'Проверить', exact: true }).click();
    await expect(primary.getByRole('button', { name: 'Повторить отправку', exact: true })).toBeEnabled();
    let originalStart!: Mutation; let acceptedStart!: LearningSession;
    await primary.route('**/api/v1/sessions', async route => {
      originalStart = mutation(route);
      const response = await route.fetch(); expect(response.status()).toBe(200);
      acceptedStart = await response.json() as LearningSession;
      await route.abort('failed');
    }, { times: 1 });
    await primary.goto('/#/practice');
    await primary.getByRole('button', { name: 'Начать занятие', exact: true }).click();
    await expect(primary.getByText('Предыдущий запуск ещё не подтверждён.', { exact: false })).toBeVisible();
    const savedAttempt = (await record(primary, owner, first.before.id))!.pending_attempt;
    const savedStart = await pendingStart(primary, owner);
    expect(savedAttempt !== null && savedAttempt.key === originalAttempt.key && same(savedAttempt.body, JSON.parse(originalAttempt.body!))).toBe(true);
    expect(savedStart !== undefined && savedStart.key === originalStart.key && same(savedStart.body, JSON.parse(originalStart.body!))).toBe(true);
    await routeTo(primary, '/account');
    await primary.getByRole('button', { name: 'Выйти', exact: true }).click();
    await expect(primary.getByLabel('Email', { exact: true })).toBeVisible();
    await primary.reload();
    await expect(primary.getByLabel('Email', { exact: true })).toBeVisible();
    const observed: Mutation[] = [];
    primary.on('request', request => {
      if (request.method() === 'POST' && /\/api\/v1\/sessions(?:$|\/[^/]+\/attempts$)/.test(new URL(request.url()).pathname)) {
        observed.push({ path: new URL(request.url()).pathname, key: request.headers()['idempotency-key'], owner: request.headers()['x-learning-owner'], body: request.postData() });
      }
    });
    const foreignGuestSession = await practice(primary);
    const guest = await access(primary);
    expect(guest.kind === 'guest' && guest.id !== owner).toBe(true);
    expect(observed.length === 1 && observed[0].owner === guest.id && observed[0].key !== originalStart.key && observed[0].key !== originalAttempt.key, 'New guest never replays account queues').toBe(true);
    expect(await record(primary, guest.id, first.before.id) === undefined, 'No foreign IndexedDB snapshot adopted').toBe(true);
    expect(await pendingStart(primary, guest.id) === undefined, 'New guest pending-start namespace is empty').toBe(true);
    await primary.goto(`/#/session/${first.before.id}`);
    await expect(primary.getByRole('heading', { name: 'Занятие недоступно', exact: true })).toBeVisible();
    await expect(primary.getByLabel('Ответ', { exact: true })).toHaveCount(0);
    expect((await primary.request.get(`/api/v1/sessions/${first.before.id}`)).status(), 'Mounted foreign-history denial is backed by actual API 404').toBe(404);
    expect(same((await record(primary, owner, first.before.id))?.pending_attempt, savedAttempt) && same(await pendingStart(primary, owner), savedStart), 'Original account queues remain intact while guest is active').toBe(true);
    const relogged = await login(primary, email);
    expect(relogged.id === owner && relogged.kind === 'account').toBe(true);
    expect(same((await record(primary, owner, first.before.id))?.pending_attempt, savedAttempt) && same(await pendingStart(primary, owner), savedStart), 'Frozen account queues survive logout/remount/relogin').toBe(true);
    await routeTo(primary, `/session/${first.before.id}`);
    await expect(primary.getByRole('button', { name: 'Повторить отправку', exact: true })).toBeEnabled();
    const retryAttempt = primary.waitForResponse(response => response.url().endsWith(`/${first.before.id}/attempts`));
    await primary.getByRole('button', { name: 'Повторить отправку', exact: true }).click();
    const attemptResponse = await retryAttempt;
    expect(attemptResponse.status()).toBe(200);
    expect(attemptResponse.request().postData() === originalAttempt.body && attemptResponse.request().headers()['idempotency-key'] === originalAttempt.key, 'Attempt retries exact frozen bytes and key').toBe(true);
    expect((await attemptResponse.json() as Attempt).id === acceptedAttempt.id, 'Lost accepted attempt response reconciles without duplicate').toBe(true);
    await primary.goto('/#/practice');
    await expect(primary.getByText('Предыдущий запуск ещё не подтверждён.', { exact: false })).toBeVisible();
    const retryStart = primary.waitForResponse(response => response.url().endsWith('/api/v1/sessions') && response.request().method() === 'POST');
    await primary.getByRole('button', { name: 'Начать занятие', exact: true }).click();
    const startResponse = await retryStart;
    expect(startResponse.status()).toBe(200);
    const retriedStart = await startResponse.json() as LearningSession;
    expect(startResponse.request().postData() === originalStart.body && startResponse.request().headers()['idempotency-key'] === originalStart.key, 'Start retries exact frozen bytes and key').toBe(true);
    expect(retriedStart.id === acceptedStart.id && same(retriedStart.tasks, acceptedStart.tasks), 'Lost accepted start response reconciles same frozen session').toBe(true);
    await expect.poll(async () => await pendingStart(primary, owner) === undefined).toBe(true);
    await expect.poll(async () => (await record(primary, owner, first.before.id))?.pending_attempt === null).toBe(true);
    const current = await get<LearningSession>(primary, `/sessions/${first.before.id}`);
    expect(current.attempts.filter(attempt => attempt.id === acceptedAttempt.id).length).toBe(1);
    knownSessions.push(acceptedStart, foreignGuestSession);
    evidence('queue-isolation', { real_lost_responses: 2, preserved_owner_queues: 2, cross_owner_replays: 0, foreign_api_status: 404, foreign_mounted_inputs: 0, frozen_keys_and_bytes_retried: true, duplicate_attempts: 0, duplicate_starts: 0 });
  });

  test('actual complete downloads retain >100 annotations and closed/distinct released assessments', async ({ browser }) => {
    test.setTimeout(240_000);
    const context = await newContext(browser, 'allow'); ownedContexts.push(context);
    // In-memory transfer of our own synthetic test credential; no storageState artifact.
    await privateAction(async () => context.addCookies((await a.cookies()).filter(cookie => cookie.name === 'math_ege_guest')));
    const page = await context.newPage();
    const annotations: ExportAnnotation[] = [];
    for (let index = 0; index < 5; index += 1) knownSessions.push(await practice(page, 20));
    const candidates = knownSessions.flatMap(session => session.tasks.map(item => ({ session_id: session.id, task_id: item.id }))).slice(0, 104);
    expect(candidates.length).toBe(104);
    for (const body of candidates) {
      const response = await privateAction(() => page.request.post('/api/v1/learning/annotations', {
        headers: { Origin: origin, 'X-Requested-With': 'math-ege', 'X-Learning-Owner': owner, 'Idempotency-Key': randomUUID() },
        data: { ...body, favourite: true, manual: true, not_understood: true, cause: 'calculation' },
      }));
      expect(response.status()).toBe(200);
      annotations.push(await response.json() as ExportAnnotation);
    }
    const paginated = await get<{ annotations: unknown[]; pagination: { totals: { annotations: number } } }>(page, '/learning/export?limit=100');
    expect(paginated.annotations.length).toBe(100);
    expect(paginated.pagination.totals.annotations).toBe(104);
    await page.clock.install();
    await page.goto('/#/assessment');
    await page.evaluate(async () => { await navigator.serviceWorker.ready; });
    await page.reload();
    await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
    await page.getByRole('radio', { name: /^Пробник/ }).check();
    await page.getByLabel('Лимит тренажёра, минут').fill('15');
    const preparedReply = page.waitForResponse(response => response.url().endsWith('/api/v1/assessments') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Подготовить 13 задач', exact: true }).click();
    const prepared = await preparedReply; expect(prepared.status()).toBe(200);
    const preparation = await prepared.json() as AssessmentView;
    expect(preparation.tasks.length === 13 && preparation.server_result === null && preparation.local_result === null).toBe(true);
    const activeReply = page.waitForResponse(response => response.url().endsWith(`/${preparation.id}/activate`));
    await page.getByRole('button', { name: 'Начать пробник', exact: true }).click();
    const activated = await activeReply; expect(activated.status()).toBe(200);
    const active = await activated.json() as AssessmentView;
    const saved = page.waitForResponse(response => response.url().endsWith(`/${active.id}/draft`) && response.request().method() === 'PUT'
      && response.request().postDataJSON().answers[active.tasks[0].id].answer === '17');
    await page.getByLabel('Ответ', { exact: true }).fill('17');
    expect((await saved).status()).toBe(200);
    await context.setOffline(true);
    await page.getByLabel('Ответ', { exact: true }).fill('−2,50');
    await page.clock.fastForward('15:01');
    await expect(page.getByRole('heading', { name: 'Результат ожидает снимка', exact: true })).toBeVisible();
    await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('−2,50');
    await expect(page.getByLabel('Ответ', { exact: true })).toHaveAttribute('readonly', '');
    await expect(page.getByText('Верный ответ', { exact: true })).toHaveCount(0);
    const device = await page.evaluate(() => sessionStorage.getItem('math-ege:assessment-device-v1'));
    const frozenRecord = () => dbRead<AssessmentRecord>(page, 'math-ege-assessments-v1', 'records', JSON.stringify([owner, active.id, device]));
    await expect.poll(async () => Boolean((await frozenRecord())?.frozen)).toBe(true);
    const frozen = (await frozenRecord())!.frozen!;
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Результат ожидает снимка', exact: true })).toBeVisible();
    await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('−2,50');
    expect(same((await frozenRecord())?.frozen, frozen), 'Frozen assessment key and answers survive genuine offline remount').toBe(true);
    const offset = Math.ceil((Date.parse(active.deadline_at!) - Date.now()) / 1000) + 2;
    expect(offset > 0 && offset <= 3600).toBe(true);
    writeFileSync(resolve(directory(), 'clock.json'), JSON.stringify({ offset_seconds: offset }));
    await expect.poll(async () => (await get<AssessmentView>(primary, `/assessments/${active.id}`)).status).toBe('awaiting_snapshot');
    const originalAttempts = knownSessions.reduce((total, session) => total + session.attempts.length, 0);
    expect(originalAttempts).toBe(2);
    const assertComplete = (payload: HistoryExport) => {
      expect(payload.sessions.length).toBe(knownSessions.length);
      expect(knownSessions.every(session => {
        const matches = payload.sessions.filter(item => item.id === session.id);
        return matches.length === 1 && matches[0].profile_revision === session.profile_revision
          && same(matches[0].profile, session.profile) && same(matches[0].tasks, session.tasks);
      }), 'Every UI-created original frozen history exported exactly once').toBe(true);
      expect(knownSessions.every(session => session.attempts.every(attempt => {
        const exported = payload.sessions.find(item => item.id === session.id)!;
        const matches = exported.attempts.filter(item => item.id === attempt.id);
        return matches.length === 1 && same(matches[0], attempt);
      })), 'Original attempt IDs and entire DTOs remain unchanged in every saved download').toBe(true);
      expect(payload.learning.annotations.length).toBe(104);
      expect(annotations.every(annotation => payload.learning.annotations.some(item => same(item, annotation))), 'All 104 complete annotation DTOs survive both download parsers').toBe(true);
      // Consent is unique per policy version, not per guest claim or login.
      expect(payload.account!.consents.length).toBe(1);
      expect(payload.account!.consents[0].policy_version === 'identity-browser-1'
        && Number.isFinite(Date.parse(payload.account!.consents[0].accepted_at)), 'Current test-policy consent is valid and deduplicated').toBe(true);
      expect(payload.account!.deletion_request === null, 'No deletion request exists in this isolated scenario').toBe(true);
      expect(payload.account!.email === email, 'Minimal account belongs to current synthetic owner; PII never reported').toBe(true);
    };
    for (const control of ['progress', 'account'] as const) {
      const file = await download(primary, control, `closed-${control}.json`); assertComplete(file.payload);
      const closed = file.payload.assessments.find(item => item.id === active.id)!;
      expect(closed.status === 'awaiting_snapshot' && closed.server_result === null && closed.local_result === null && closed.released_at === null, 'Unreleased assessment results remain closed in real downloads').toBe(true);
      expect(closed.tasks.every(item => !Object.hasOwn(item, 'answer') && !Object.hasOwn(item, 'solution') && item.hint_count === 0)).toBe(true);
      evidence(`closed-${control}-download`, { top_level_fields: 7, account_fields: 8, sessions: file.payload.sessions.length, original_attempts: originalAttempts, original_attempt_dtos_unchanged: true, annotations: 104, closed_results_null: true, bytes: file.bytes, sha256: file.sha256 });
    }
    await page.screenshot({ path: resolve(directory(), 'mounted-offline-pending.png'), fullPage: true });
    const finishedReply = page.waitForResponse(response => response.url().endsWith(`/${active.id}/finish`) && response.request().method() === 'POST');
    await context.setOffline(false);
    const finishedResponse = await finishedReply; expect(finishedResponse.status()).toBe(200);
    expect(finishedResponse.request().headers()['idempotency-key'] === frozen.key && same(finishedResponse.request().postDataJSON(), frozen.body), 'Reconnect submits exact immutable local finish').toBe(true);
    await expect(page.getByRole('heading', { name: 'Пробник завершён', exact: true })).toBeVisible();
    const serverRegion = page.getByRole('region', { name: 'Серверный результат', exact: true });
    const localRegion = page.getByRole('region', { name: 'Локальный учебный результат', exact: true });
    await expect(serverRegion.locator('details')).toHaveCount(13);
    await expect(localRegion.locator('details')).toHaveCount(13);
    await expect(serverRegion.locator('summary').first()).toContainText('Ваш ответ: 17');
    await expect(localRegion.locator('summary').first()).toContainText('Ваш ответ: −2,50');
    await page.screenshot({ path: resolve(directory(), 'mounted-distinct-results.png'), fullPage: true });
    let canonicalResults: unknown;
    for (const control of ['progress', 'account'] as const) {
      const file = await download(primary, control, `released-${control}.json`); assertComplete(file.payload);
      const released = file.payload.assessments.find(item => item.id === active.id)!;
      const server = released.server_result!; const local = released.local_result!;
      expect(released.status === 'completed' && released.released_at !== null).toBe(true);
      expect(server.source === 'server' && local.source === 'local' && server.reason === 'deadline' && local.connection_lost).toBe(true);
      expect(server.rows[0].raw === '17' && local.rows[0].raw === '−2,50' && server.snapshot_hash !== local.snapshot_hash).toBe(true);
      expect(server.rows.length === 13 && local.rows.length === 13 && /^[a-f0-9]{64}$/.test(server.snapshot_hash) && /^[a-f0-9]{64}$/.test(local.snapshot_hash)).toBe(true);
      const results = { server, local };
      if (canonicalResults) expect(same(results, canonicalResults), 'Released immutable results identical in both real downloads').toBe(true);
      canonicalResults = results;
      evidence(`released-${control}-download`, { top_level_fields: 7, account_fields: 8, sessions: file.payload.sessions.length, original_attempts: originalAttempts, original_attempt_dtos_unchanged: true, annotations: 104, separately_released_results: 2, result_rows: 26, bytes: file.bytes, sha256: file.sha256, server_snapshot_hash: server.snapshot_hash, local_snapshot_hash: local.snapshot_hash });
    }
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Пробник завершён', exact: true })).toBeVisible();
    const unchanged = await get<{ server_result: unknown; local_result: unknown }>(primary, `/assessments/${active.id}`);
    expect(same({ server: unchanged.server_result, local: unchanged.local_result }, canonicalResults), 'Released results remain immutable after mounted remount').toBe(true);
    evidence('assessment-freeze-and-release', { real_offline_remount: true, frozen_key_and_body_unchanged: true, private_clock_offset_seconds: offset, no_database_clock_edits: true, mounted_server_rows: 13, mounted_local_rows: 13, released_results_immutable: true });
  });
});
