import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import type { AssessmentMode, AssessmentView } from '../src/assessments/types';

type WireResult = {
  score: number; total: 13; connection_lost: boolean;
  rows: Array<{ task_id: string; raw: string; normalized: string | null; format_error: boolean; skipped: boolean }>;
};
type WireAssessment = Omit<AssessmentView, 'server_result' | 'local_result'> & {
  server_result: WireResult | null; local_result: WireResult | null;
};

async function openSetup(page: Page) {
  await page.goto('/#/assessment');
  await expect(page.getByRole('heading', { level: 1, name: 'Диагностика и пробник', exact: true })).toBeVisible();
}

async function startAssessment(page: Page, mode: AssessmentMode = 'diagnostic', minutes = '65') {
  await openSetup(page);
  if (mode === 'exam') {
    await page.getByRole('radio', { name: /^Пробник/ }).check();
    await expect(page.getByLabel('Лимит тренажёра, минут')).toHaveValue('65');
    await page.getByLabel('Лимит тренажёра, минут').fill(minutes);
  }
  const preparedReply = page.waitForResponse(reply => reply.url().endsWith('/api/v1/assessments') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Подготовить 13 задач', exact: true }).click();
  const preparation = await preparedReply;
  expect(preparation.ok(), await preparation.text()).toBe(true);
  const prepared: WireAssessment = await preparation.json();
  expect(prepared.tasks).toHaveLength(13);
  expect(new Set(prepared.tasks.map(task => task.slot)).size).toBe(13);
  expect(prepared).toMatchObject({ status: 'prepared', started_at: null, deadline_at: null, server_result: null, local_result: null });
  await expect(page.getByRole('heading', { name: 'Вариант подготовлен', exact: true })).toBeVisible();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveCount(0);
  const activeReply = page.waitForResponse(reply => reply.url().endsWith(`/${prepared.id}/activate`) && reply.request().method() === 'POST');
  await page.getByRole('button', { name: mode === 'exam' ? 'Начать пробник' : 'Начать диагностику', exact: true }).click();
  const activation = await activeReply;
  expect(activation.ok(), await activation.text()).toBe(true);
  const active: WireAssessment = await activation.json();
  const identity = await (await page.request.get('/api/v1/identity')).json() as { id: string };
  expect(activation.request().headers()['x-learning-owner']).toBe(identity.id);
  expect(preparation.request().headers()['x-learning-owner']).toBe(identity.id);
  expect(active).toMatchObject({ status: 'active', can_write: true, server_result: null, local_result: null });
  await expect(page.getByLabel('Ответ', { exact: true })).toBeEditable();
  return active;
}

async function offlineReady(page: Page) {
  await openSetup(page);
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
}

async function confirmFinish(page: Page) {
  await page.getByRole('button', { name: 'Завершить', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Завершить занятие?' })).toBeVisible();
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
}

async function noOverflow(page: Page) {
  const size = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
  expect(size.content, `Переполнение на ширине ${size.viewport}`).toBeLessThanOrEqual(size.viewport);
}

async function captureAssessment(page: Page, filename: string) {
  // Keep fixed navigation and the offscreen skip link at their document-top positions.
  await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: 'instant' }));
  await page.screenshot({ path: test.info().outputPath(filename), fullPage: true });
}

test('диагностика открывает разбор только после итогового снимка и отличает ошибку формата', async ({ page }) => {
  const active = await startAssessment(page);
  expect(active.deadline_at).toBeNull();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toHaveValue('');
  await expect(page.getByRole('timer')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Проверить|Подсказка|Показать решение/ })).toHaveCount(0);
  await answer.fill('1/2');
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  await expect(answer).toHaveValue('');
  await expect(page.getByRole('heading', { name: `№ ${active.tasks[1].slot}. ${active.tasks[1].title}`, exact: true })).toBeFocused();
  await answer.fill('−2,50');
  const finish = page.getByRole('button', { name: 'Завершить', exact: true });
  await finish.click();
  await expect(page.getByRole('button', { name: 'Продолжить решать', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(finish).toBeFocused();
  const finishedReply = page.waitForResponse(reply => reply.url().endsWith(`/${active.id}/finish`) && reply.request().method() === 'POST');
  await confirmFinish(page);
  const response = await finishedReply;
  expect(response.ok(), await response.text()).toBe(true);
  const finished: WireAssessment = await response.json();
  expect(finished.server_result?.rows[0]).toMatchObject({ raw: '1/2', normalized: null, format_error: true, skipped: false });
  expect(finished.server_result?.rows[1]).toMatchObject({ raw: '−2,50', format_error: false });
  expect(finished.server_result?.rows[2]).toMatchObject({ raw: '', skipped: true });
  await expect(page.getByRole('heading', { name: 'Диагностика завершена', exact: true })).toBeVisible();
  const result = page.getByRole('region', { name: 'Серверный результат', exact: true });
  await expect(result.locator('details')).toHaveCount(13);
  await result.locator('summary').first().click();
  await expect(result.getByText('Ошибка формата', { exact: true })).toBeVisible();
  await expect(result.getByText('Верный ответ', { exact: true }).first()).toBeVisible();
  expect((await new AxeBuilder({ page }).include('.assessment-page').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await captureAssessment(page, 'assessment-results.png');
});

test('все 13 условий, черновики и неизменяемое завершение переживают офлайн-перезагрузку', async ({ page, context }) => {
  await offlineReady(page);
  const active = await startAssessment(page, 'exam');
  await context.setOffline(true);
  const answer = page.getByLabel('Ответ', { exact: true });
  for (let index = 0; index < 13; index += 1) {
    await page.getByRole('button', { name: new RegExp(`^Задача ${index + 1},`) }).click();
    await expect(page.getByRole('heading', { name: `№ ${active.tasks[index].slot}. ${active.tasks[index].title}`, exact: true })).toBeVisible();
    await expect(page.locator('.assessment-task .task-statement')).not.toBeEmpty();
    if (index === 0) await answer.fill('1,25');
    if (index === 12) await answer.fill('−');
  }
  await page.reload();
  await expect(answer).toHaveValue('−');
  await page.getByRole('button', { name: /^Задача 1,/ }).click();
  await expect(answer).toHaveValue('1,25');
  await confirmFinish(page);
  await expect(page.getByRole('heading', { name: 'Результат ожидает снимка', exact: true })).toBeVisible();
  await expect(answer).toHaveAttribute('readonly', '');
  await expect(page.getByText('Верный ответ', { exact: true })).toHaveCount(0);
  await page.reload();
  await expect(answer).toHaveValue('1,25');
  await expect(answer).toHaveAttribute('readonly', '');
  await answer.focus();
  await page.keyboard.type('9');
  await expect(answer).toHaveValue('1,25');
  const finishedReply = page.waitForResponse(reply => reply.url().endsWith(`/${active.id}/finish`) && reply.request().method() === 'POST');
  await context.setOffline(false);
  const response = await finishedReply;
  expect(response.ok(), await response.text()).toBe(true);
  const finished: WireAssessment = await response.json();
  expect(finished.local_result).toMatchObject({ connection_lost: true, total: 13 });
  expect(finished.local_result?.rows[0].raw).toBe('1,25');
  expect(finished.local_result?.rows[12]).toMatchObject({ raw: '−', format_error: true });
  await expect(page.getByRole('heading', { name: 'Серверный результат', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Локальный учебный результат', exact: true })).toBeVisible();
  await expect(page.getByText('Соединение прерывалось', { exact: true })).toBeVisible();
});

test('скопированная вкладка получает новый device ID и запись только после подтверждённого takeover', async ({ page }) => {
  const active = await startAssessment(page);
  const saved = page.waitForResponse(reply => reply.url().endsWith(`/${active.id}/draft`) && reply.request().method() === 'PUT');
  await page.getByLabel('Ответ', { exact: true }).fill('17');
  expect((await saved).ok()).toBe(true);
  const device = await page.evaluate(() => sessionStorage.getItem('math-ege:assessment-device-v1'));
  const opened = page.waitForEvent('popup');
  await page.evaluate(() => { window.open(window.location.href, '_blank'); });
  const duplicate = await opened;
  const otherAnswer = duplicate.getByLabel('Ответ', { exact: true });
  await expect(otherAnswer).toHaveAttribute('readonly', '');
  await expect(otherAnswer).toHaveValue('17');
  const otherDevice = await duplicate.evaluate(() => sessionStorage.getItem('math-ege:assessment-device-v1'));
  expect(otherDevice).not.toBe(device);
  const trigger = duplicate.getByRole('button', { name: 'Продолжить в этой вкладке', exact: true });
  await trigger.click();
  await expect(duplicate.getByRole('button', { name: 'Оставить только просмотр', exact: true })).toBeFocused();
  await duplicate.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(otherAnswer).toHaveAttribute('readonly', '');
  await trigger.click();
  const claimedReply = duplicate.waitForResponse(reply => reply.url().endsWith(`/${active.id}/takeover`) && reply.request().method() === 'POST');
  await duplicate.getByRole('button', { name: 'Продолжить здесь', exact: true }).click();
  const claim = await claimedReply;
  expect(claim.ok(), await claim.text()).toBe(true);
  const claimed: WireAssessment = await claim.json();
  expect(claimed.writer_generation).toBe(active.writer_generation + 1);
  await expect(otherAnswer).toBeEditable();
  await page.bringToFront();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveAttribute('readonly', '');
  await expect(page.getByRole('heading', { name: 'Только просмотр', exact: true })).toBeVisible();
  await duplicate.close();
});

test('лимит пробника замораживает ответ вне страницы и остаётся истёкшим после офлайн-перезагрузки', async ({ page, context }) => {
  await page.clock.install();
  await offlineReady(page);
  await startAssessment(page, 'exam', '15');
  const location = page.url();
  await context.setOffline(true);
  await page.getByLabel('Ответ', { exact: true }).fill('−5');
  await page.getByRole('link', { name: 'К вариантам', exact: true }).click();
  await page.clock.fastForward('15:01');
  await page.goto(location);
  await expect(page.getByRole('heading', { name: 'Результат ожидает снимка', exact: true })).toBeVisible();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('−5');
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveAttribute('readonly', '');
  await page.reload();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('−5');
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveAttribute('readonly', '');
  await expect(page.getByText('Верный ответ', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Лимит времени истёк/)).toBeVisible();
  await captureAssessment(page, 'assessment-offline-deadline.png');
});

test.describe('потеря ответа подготовки', () => {
  test.use({ serviceWorkers: 'block' });
  test('сразу показывает и блокирует сохранённые настройки, повторяя тот же запрос после создания гостя', async ({ page }) => {
    await openSetup(page);
    await page.getByRole('radio', { name: /^Пробник/ }).check();
    const minutes = page.getByLabel('Лимит тренажёра, минут');
    await minutes.fill('14');
    await page.getByRole('button', { name: 'Подготовить 13 задач', exact: true }).click();
    await expect(minutes).toBeFocused();
    await expect(minutes).toHaveAttribute('aria-invalid', 'true');
    await minutes.fill('90');
    let original: { body: string | null; key: string; id: string } | undefined;
    await page.route('**/api/v1/assessments', async route => {
      const response = await route.fetch();
      const created: WireAssessment = await response.json();
      original = { body: route.request().postData(), key: route.request().headers()['idempotency-key'], id: created.id };
      await route.abort('failed');
    }, { times: 1 });
    await page.getByRole('button', { name: 'Подготовить 13 задач', exact: true }).click();
    await expect(page.getByText('Подготовка ещё не подтверждена.', { exact: false })).toBeVisible();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('radio', { name: /^Пробник/ })).toBeChecked();
    await expect(minutes).toHaveValue('90');
    await expect(minutes).toBeDisabled();
    const repeatedReply = page.waitForResponse(reply => reply.url().endsWith('/api/v1/assessments') && reply.request().method() === 'POST');
    await page.getByRole('button', { name: 'Повторить подготовку', exact: true }).click();
    const response = await repeatedReply;
    expect(response.ok(), await response.text()).toBe(true);
    expect(response.request().postData()).toBe(original?.body);
    expect(response.request().headers()['idempotency-key']).toBe(original?.key);
    expect((await response.json() as WireAssessment).id).toBe(original?.id);
    await expect(page.getByRole('heading', { name: 'Вариант подготовлен', exact: true })).toBeVisible();
    await expect(page.getByLabel('Ответ', { exact: true })).toHaveCount(0);
  });
});

test('настройка и рабочий лист доступны на 320–1440 CSS px и с текстом 200%', async ({ page }) => {
  test.setTimeout(60_000);
  await openSetup(page);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page);
    await captureAssessment(page, `assessment-setup-${width}.png`);
  }
  await startAssessment(page);
  await expect(page.getByRole('navigation', { name: 'Главная навигация', exact: true }).getByRole('link')).toHaveCount(5);
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page);
    const targets = await page.locator('.assessment-page .button, .assessment-rail button, #assessment-answer').evaluateAll(elements => elements
      .filter(element => element.getClientRects().length > 0)
      .map(element => ({ label: element.getAttribute('aria-label') ?? element.textContent, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height })));
    expect(targets.filter(target => target.width < 44 || target.height < 44), `Маленькая область нажатия на ${width}`).toEqual([]);
    if (width === 1440 || width === 390) {
      await captureAssessment(page, `assessment-worksheet-${width}.png`);
    }
  }
  await page.setViewportSize({ width: 320, height: 900 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  await noOverflow(page);
  await page.getByLabel('Ответ', { exact: true }).focus();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeFocused();
  expect((await new AxeBuilder({ page }).include('.assessment-page').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
});
