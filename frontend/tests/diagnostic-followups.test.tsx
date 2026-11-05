import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium, expect as browserExpect, type Browser, type Page, type Route } from '@playwright/test';
import react from '@vitejs/plugin-react';
import { build } from 'vite';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { Profile, PublicTask } from '../src/api/types';
import type { AssessmentResult, AssessmentView } from '../src/assessments/types';
import { createAssessmentRecord, type AssessmentRecord } from '../src/assessments/model';
import { diagnosticFollowups } from '../src/assessments/followups';
import { practiceOptions } from '../src/learning/practice-options';

function currentProfile(): Profile {
  return {
    id: 'profile-2027', year: 2027, title: 'Профиль 2027', status: 'draft', revision: '2',
    verified_at: '2026-11-05', verification_note: 'Учебный профиль.', source_urls: [],
    demo_mode: true, bank_size: 650,
    slots: Array.from({ length: 13 }, (_, index) => ({
      id: `slot-${index + 1}`, number: index + 1, title: `Позиция ${index + 1}`, level: 'Б',
      summary: 'Учебная тема.', skills: [{ id: `skill-${index + 1}`, title: `Навык ${index + 1}` }],
      available_tasks: 50, lesson_id: `lesson-${index + 1}`,
    })),
  };
}

const tasks: PublicTask[] = currentProfile().slots.map((slot) => ({
  id: `diagnostic-task-${slot.number}`, revision: '1', slot: slot.number, slot_id: slot.id,
  topic: slot.title, title: 'Найдите значение', statement: 'Вычислите 2 + 2.',
  formula: null, table: null, skill_ids: slot.skills.map((skill) => skill.id),
  family_id: `family-${slot.number}`, estimated_seconds: 60, review_status: 'demo', hint_count: 3,
}));

function serverResult(): AssessmentResult {
  return {
    score: 13, total: 13, connection_lost: false,
    recommendation: 'Карта предварительная. Одна верная задача не означает освоение.',
    rows: tasks.map((task) => ({
      task_id: task.id, raw_answer: '4', normalized_answer: '4', expected_answer: '4',
      correct: true, skipped: false, format_error: false, format_message: null,
      independent: true, assisted: false, solution: ['Сложите два числа.'],
    })),
  };
}

function completedView(overrides: Partial<AssessmentView> = {}): AssessmentView {
  return {
    id: 'diagnostic-one', mode: 'diagnostic', status: 'completed', server_now: '2026-11-05T12:00:00Z',
    started_at: '2026-11-05T11:50:00Z', deadline_at: null, duration_minutes: 65,
    writer_generation: 1, can_write: false, draft_revision: 1, current_index: 0,
    tasks: structuredClone(tasks), drafts: {}, server_result: serverResult(), local_result: null,
    result_notice: '', ...overrides,
  };
}

describe('diagnostic follow-up practice links', () => {
  it('offers five new tasks after one correct answer and resolves renumbering by stable position ID', () => {
    const profile = currentProfile();
    profile.slots[0].number = 7;
    profile.slots[6].number = 1;
    const links = diagnosticFollowups(completedView(), profile);
    expect(links).toHaveLength(13);
    expect(links[0]).toMatchObject({
      task_id: 'diagnostic-task-1', slot: 7, skill_ids: ['skill-1'],
      href: '/practice?slots=7&skills=skill-1&length=5',
    });
    expect(practiceOptions(new URLSearchParams(links[0].href.split('?')[1]))).toMatchObject({
      slots: [7], skill_ids: ['skill-1'], length: 5, mode: 'practice', repeat_task_id: null,
    });
    expect(links[0].href).not.toContain('diagnostic-task-1');
  });

  it.each([
    ['prepared', { status: 'prepared' }],
    ['active', { status: 'active' }],
    ['awaiting snapshot', { status: 'awaiting_snapshot' }],
    ['exam', { mode: 'exam' }],
    ['local-only result', { server_result: null, local_result: serverResult() }],
    ['absent result', { server_result: null }],
  ] satisfies [string, Partial<AssessmentView>][])('withholds targeted links for %s', (_name, overrides) => {
    expect(diagnosticFollowups(completedView(overrides), currentProfile())).toEqual([]);
  });

  it('maps legacy conditions only through unambiguous stable skills, never their old number', () => {
    const view = completedView();
    view.tasks[0].slot_id = null;
    const profile = currentProfile();
    profile.slots[0].number = 7;
    profile.slots[6].number = 1;
    expect(diagnosticFollowups(view, profile)[0].href).toBe('/practice?slots=7&skills=skill-1&length=5');
    profile.slots[1].skills.push({ id: 'skill-1', title: 'Общий навык' });
    expect(diagnosticFollowups(view, profile).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
  });

  it('deduplicates only current in-position skills and preserves the frozen assessment', () => {
    const view = completedView();
    view.tasks[0].skill_ids = ['retired-skill', 'skill-1', 'skill-2', 'skill-1'];
    const before = structuredClone(view);
    expect(diagnosticFollowups(view, currentProfile())[0]).toMatchObject({
      skill_ids: ['skill-1'], href: '/practice?slots=1&skills=skill-1&length=5',
    });
    expect(view).toEqual(before);
  });

  it.each(['', 'skill,other'])('withholds a skill ID that cannot round-trip through practice options: %j', (id) => {
    const view = completedView();
    view.tasks[0].skill_ids = [id];
    const profile = currentProfile();
    profile.slots[0].skills = [{ id, title: 'Навык' }];
    expect(diagnosticFollowups(view, profile).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
  });

  it.each([0, 14, 1.5])('withholds an unsupported current practice position: %s', (number) => {
    const profile = currentProfile();
    profile.slots[0].number = number;
    expect(diagnosticFollowups(completedView(), profile).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
  });

  it('withholds unavailable or ambiguously numbered current positions', () => {
    const profile = currentProfile();
    profile.slots[0].available_tasks = 0;
    expect(diagnosticFollowups(completedView(), profile).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
    profile.slots[0].available_tasks = 50;
    profile.slots[1].number = 1;
    expect(diagnosticFollowups(completedView(), profile).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
  });

  it.each([
    { slot_id: 'retired-position' },
    { skill_ids: ['retired-skill'] },
    { skill_ids: ['skill-2'] },
  ])('never broadens retired or outside evidence into another current topic: %j', (change) => {
    const view = completedView();
    Object.assign(view.tasks[0], change);
    expect(diagnosticFollowups(view, currentProfile()).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
  });

  it('requires a known server-result task and a current profile, without falling back to local rows', () => {
    const view = completedView({ local_result: serverResult() });
    view.server_result!.rows[0].task_id = 'unknown-task';
    expect(diagnosticFollowups(view, currentProfile())).toHaveLength(12);
    expect(diagnosticFollowups(view, currentProfile()).some((link) => link.task_id === 'diagnostic-task-1')).toBe(false);
    expect(diagnosticFollowups(view, null)).toEqual([]);
  });

  it('encodes stable skills as filter values, not extra query controls', () => {
    const view = completedView();
    const id = 'skill&repeat=diagnostic-task-1';
    view.tasks[0].skill_ids = [id, 'skill-1'];
    const profile = currentProfile();
    profile.slots[0].skills.push({ id, title: 'Навык с особым идентификатором' });
    const query = new URLSearchParams(diagnosticFollowups(view, profile)[0].href.split('?')[1]);
    expect([...query.keys()]).toEqual(['slots', 'skills', 'length']);
    expect(practiceOptions(query)).toMatchObject({ skill_ids: [id, 'skill-1'], repeat_task_id: null, length: 5 });
  });
});

type ResultsHarness = { renderResults(record: AssessmentRecord): void; reloadProfile(): Promise<void> };

// Mount the real component with the installed browser, without a DOM dependency or a listening server.
async function resultsBundle() {
  const root = resolve(import.meta.dirname, '..').replaceAll('\\', '/');
  const entry = '\0virtual:diagnostic-results';
  const built = await build({
    root, configFile: false, logLevel: 'silent',
    define: { 'process.env.NODE_ENV': JSON.stringify('development') },
    plugins: [react(), {
      name: 'diagnostic-results-unit-entry',
      resolveId: (id) => id === 'virtual:diagnostic-results' ? entry : undefined,
      load: (id) => id === entry ? `
        import { createElement } from 'react';
        import { createRoot } from 'react-dom/client';
        import { flushSync } from 'react-dom';
        import { AssessmentResults } from '${root}/src/assessments/results.tsx';
        import { profileResource } from '${root}/src/app/resources.ts';
        import '${root}/src/styles/tokens.css';
        import '${root}/src/styles/base.css';
        import '${root}/src/styles/components.css';
        import '${root}/src/styles/assessment.css';
        const root = createRoot(document.getElementById('root'));
        window.renderResults = (record) => flushSync(() => root.render(createElement(AssessmentResults, { record, onRefresh() {} })));
        window.reloadProfile = () => profileResource.load(true);
      ` : undefined,
    }],
    build: {
      write: false, minify: false,
      lib: { entry: 'virtual:diagnostic-results', name: 'DiagnosticResultsUnit', formats: ['iife'] },
      rolldownOptions: { input: 'virtual:diagnostic-results' },
    },
  });
  const output = (Array.isArray(built) ? built : [built]).flatMap((item) => {
    if (!('output' in item)) throw new Error('Result component build unexpectedly returned a watcher.');
    return item.output;
  });
  const script = output.find((item) => item.type === 'chunk');
  if (!script || script.type !== 'chunk') throw new Error('Result component bundle is missing.');
  const css = output.filter((item) => item.type === 'asset' && item.fileName.endsWith('.css'))
    .map((item) => item.type === 'asset' ? String(item.source) : '').join('\n');
  return { script: script.code, css };
}

describe('mounted diagnostic result follow-ups', () => {
  let browser: Browser;
  let page: Page;
  let bundle: Awaited<ReturnType<typeof resultsBundle>>;

  beforeAll(async () => {
    bundle = await resultsBundle();
    browser = await chromium.launch({ headless: true });
  }, 60_000);
  afterAll(async () => { await browser?.close(); });
  beforeEach(async () => { page = await browser.newPage(); });
  afterEach(async () => { await page?.close(); });

  async function mount(view: AssessmentView, profile = currentProfile(), profileReply?: (route: Route) => Promise<void> | void) {
    await page.route('**/*', async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html lang="ru"><body><main id="root" class="assessment-page"></main></body></html>' });
      if (path === '/api/v1/profile') return profileReply ? profileReply(route) : route.fulfill({ json: profile });
      return route.abort();
    });
    await page.goto('http://assessment-unit.test/');
    await page.addStyleTag({ content: bundle.css });
    await page.addScriptTag({ content: bundle.script });
    await page.evaluate((record) => (window as unknown as ResultsHarness).renderResults(record), createAssessmentRecord(view, 'owner-one', 'device-one'));
  }

  it('keeps follow-up actions inside the server result details and navigates to the current five-task filters', async () => {
    const profile = currentProfile();
    profile.slots[0].number = 7;
    profile.slots[6].number = 1;
    await mount(completedView(), profile);
    const result = page.getByRole('region', { name: 'Серверный результат', exact: true });
    await browserExpect(result.locator('a[href*="length=5"]')).toHaveCount(13, { timeout: 1_000 });
    const detail = result.locator('details').first();
    const link = detail.getByRole('link', { name: 'Проверить № 7 на 5 новых задачах', exact: true, includeHidden: true });
    await browserExpect(link).not.toBeVisible();
    await detail.locator('summary').click();
    await browserExpect(link).toBeVisible();
    await browserExpect(link).toHaveAttribute('href', '#/practice?slots=7&skills=skill-1&length=5');
    await link.click();
    expect(new URL(page.url()).hash).toBe('#/practice?slots=7&skills=skill-1&length=5');
    expect(practiceOptions(new URLSearchParams(new URL(page.url()).hash.split('?')[1]))).toMatchObject({
      slots: [7], skill_ids: ['skill-1'], length: 5, repeat_task_id: null,
    });
    await browserExpect(result).not.toContainText('Освоено');
  });

  it('withholds targeted navigation until the current profile has loaded', async () => {
    let pending: Route | undefined;
    await mount(completedView(), currentProfile(), (route) => { pending = route; });
    await browserExpect(page.getByRole('status')).toHaveText('Загружаем актуальный профиль для проверки…', { timeout: 1_000 });
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(0);
    await browserExpect.poll(() => Boolean(pending)).toBe(true);
    await pending!.fulfill({ json: currentProfile() });
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(13);
  });

  it('keeps the result readable after a failed profile read and offers a retry instead of unsafe links', async () => {
    let reads = 0;
    const profile = currentProfile();
    await mount(completedView(), profile, (route) => route.fulfill(++reads === 1
      ? { status: 503, json: { error: { code: 'profile_unavailable', message: 'Актуальный профиль недоступен.' } } }
      : { json: profile }));
    await browserExpect(page.getByRole('alert')).toContainText('Актуальный профиль недоступен.', { timeout: 1_000 });
    await browserExpect(page.locator('details')).toHaveCount(13);
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(13);
    expect(reads).toBe(2);
  });

  it('explains an unavailable current mapping without falling back to unfiltered practice', async () => {
    const profile = currentProfile();
    profile.slots[0].skills = [{ id: 'replacement-skill', title: 'Другой навык' }];
    await mount(completedView(), profile);
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(12);
    const detail = page.locator('details').first();
    await detail.locator('summary').click();
    await browserExpect(detail).toContainText('Для этой позиции проверка недоступна в актуальном профиле.', { timeout: 1_000 });
    await browserExpect(detail.getByRole('link')).toHaveCount(0);
  });

  it.each(['prepared', 'active', 'awaiting_snapshot'] as const)('keeps results and targeted links closed before release: %s', async (status) => {
    await mount(completedView({ status }));
    await browserExpect(page.locator('details')).toHaveCount(0, { timeout: 1_000 });
    await browserExpect(page.getByText('Верный ответ', { exact: true })).toHaveCount(0);
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(0);
    await browserExpect(page.getByRole('heading', { name: 'Результат ещё не открыт', exact: true })).toBeVisible();
  });

  it('offers follow-ups for wrong, skipped, format-error, assisted and repeated answers without asserting mastery', async () => {
    const view = completedView();
    const result = view.server_result!;
    Object.assign(result.rows[0], { correct: false, raw_answer: '5', normalized_answer: '5' });
    Object.assign(result.rows[1], { correct: false, skipped: true, raw_answer: '', normalized_answer: null, independent: false });
    Object.assign(result.rows[2], { correct: false, format_error: true, raw_answer: '1/2', normalized_answer: null, independent: false });
    Object.assign(result.rows[3], { assisted: true, independent: false });
    result.rows[4].independent = false;
    result.score = 10;
    await mount(view);
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(13);
    const labels = ['Неверно', 'Пропущено', 'Ошибка формата', 'Верно', 'Верно'];
    for (const [index, label] of labels.entries()) {
      const detail = page.locator('details').nth(index);
      await browserExpect(detail.locator('summary')).toContainText(label);
      await detail.locator('summary').click();
      await browserExpect(detail.getByRole('link', { name: `Проверить № ${index + 1} на 5 новых задачах`, exact: true })).toBeVisible();
    }
    await browserExpect(page.locator('main')).not.toContainText('Освоено');
  });

  it('keeps local educational results separate and attaches follow-ups only to the canonical server ledger', async () => {
    const local = serverResult();
    local.score = 0;
    local.connection_lost = true;
    local.rows.forEach((row) => { row.correct = false; row.independent = false; });
    await mount(completedView({ local_result: local }));
    const canonical = page.getByRole('region', { name: 'Серверный результат', exact: true });
    const localLedger = page.getByRole('region', { name: 'Локальный учебный результат', exact: true });
    await browserExpect(canonical.locator('a[href*="length=5"]')).toHaveCount(13);
    await browserExpect(localLedger.locator('details')).toHaveCount(13);
    await browserExpect(localLedger.locator('a')).toHaveCount(0);
    await browserExpect(page.getByText('Соединение прерывалось', { exact: true })).toBeVisible();
  });

  it.each([
    ['exam', { mode: 'exam' }],
    ['local-only result', { server_result: null, local_result: serverResult() }],
  ] satisfies [string, Partial<AssessmentView>][])('does not load follow-up filters or expose a targeted link for %s', async (_name, overrides) => {
    let profileReads = 0;
    await mount(completedView(overrides), currentProfile(), (route) => { profileReads += 1; return route.fulfill({ json: currentProfile() }); });
    await browserExpect(page.locator('details')).toHaveCount(13);
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(0);
    expect(profileReads).toBe(0);
  });

  it('withholds old links after a failed refresh and updates stable-ID mappings when retry succeeds', async () => {
    const profile = currentProfile();
    let unavailable = false;
    await mount(completedView(), profile, (route) => route.fulfill(unavailable
      ? { status: 503, json: { error: { code: 'profile_unavailable', message: 'Обновление профиля не подтверждено.' } } }
      : { json: profile }));
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(13);
    unavailable = true;
    await page.evaluate(() => (window as unknown as ResultsHarness).reloadProfile());
    await browserExpect(page.getByRole('alert')).toContainText('Обновление профиля не подтверждено.');
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(0);
    profile.slots[0].number = 7;
    profile.slots[6].number = 1;
    unavailable = false;
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await browserExpect(page.locator('details').first().locator('a')).toHaveAttribute('href', '#/practice?slots=7&skills=skill-1&length=5');
  });

  it('keeps the follow-up keyboard reachable, touch-sized and within the worksheet at small widths and 200% text', async () => {
    await mount(completedView());
    await browserExpect(page.locator('a[href*="length=5"]')).toHaveCount(13);
    const detail = page.locator('details').first();
    await detail.locator('summary').click();
    const link = detail.getByRole('link', { name: 'Проверить № 1 на 5 новых задачах', exact: true });
    await link.focus();
    await browserExpect(link).toBeFocused();
    const shots = process.env.ASSESSMENT_FOLLOWUP_SHOTS;
    if (shots) mkdirSync(shots, { recursive: true });
    for (const width of [1440, 390, 320, 360, 768, 1024]) {
      await page.setViewportSize({ width, height: 900 });
      const target = await link.boundingBox();
      expect(target!.width).toBeGreaterThanOrEqual(44);
      expect(target!.height).toBeGreaterThanOrEqual(44);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      expect(overflow, `Follow-up overflow at ${width}px`).toBe(false);
      if (shots && (width === 1440 || width === 390)) await page.screenshot({ path: resolve(shots, `diagnostic-followup-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 320, height: 900 });
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    await browserExpect(link).toBeFocused();
  });
});
