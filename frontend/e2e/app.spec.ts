import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import type { Attempt, LearningSession, Solution } from '../src/api/types';

async function startPractice(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
}

async function submitAnswer(page: Page, value: string): Promise<Attempt> {
  await page.getByLabel('Ответ', { exact: true }).fill(value);
  const response = page.waitForResponse(reply => reply.url().endsWith('/attempts') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: /^Проверить(?: исправление)?$/ }).click();
  const reply = await response;
  expect(reply.ok()).toBe(true);
  return reply.json();
}

test('сохраняет первую ошибку, помощь, пропуск, итог и JSON-историю', async ({ page }) => {
  await startPractice(page);
  const first = await submitAnswer(page, '9999999999999999');
  expect(first).toMatchObject({ correct: false, independent: true, first_attempt: true, assisted: false });
  const correction = await submitAnswer(page, first.expected_answer);
  expect(correction).toMatchObject({ correct: true, independent: false, first_attempt: false });
  await expect(page.getByText('Исправлено', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  await page.getByRole('button', { name: /Подсказка 1/ }).click();
  const solutionReply = page.waitForResponse(reply => reply.url().endsWith('/solution') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Показать решение', exact: true }).click();
  const solution: Solution = await (await solutionReply).json();
  const assisted = await submitAnswer(page, solution.answer);
  expect(assisted).toMatchObject({ correct: true, assisted: true, independent: false, first_attempt: true });
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  await page.getByRole('button', { name: 'Пропустить', exact: true }).click();
  await expect(page.getByText('Задача пропущена', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Завершить', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Завершить', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Завершить', exact: true }).click();
  const finishedReply = page.waitForResponse(reply => reply.url().endsWith('/finish') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  const finished: LearningSession = await (await finishedReply).json();
  expect(finished.summary).toMatchObject({ total: 5, answered: 2, independent_total: 1, independent_correct: 0, assisted: 2, corrections: 1, skipped: 1 });
  await expect(page.getByRole('heading', { name: 'Занятие завершено', exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('link', { name: 'К журналу ошибок', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Задачи для разбора' }).locator('details')).toHaveCount(2);
  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать JSON', exact: true }).click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toBe('ege-profile-history.json');
  const stream = await download.createReadStream();
  if (!stream) throw new Error('Выгрузка не создала поток JSON');
  let content = '';
  for await (const chunk of stream) content += chunk.toString();
  const exported = JSON.parse(content);
  expect(exported.sessions).toHaveLength(1);
  expect(exported.sessions[0].attempts).toHaveLength(4);
  expect(exported.sessions[0].summary).toEqual(finished.summary);
  expect(content).not.toMatch(/token_digest|guest_id|request_key|idempotency_key/);
});

test('сохраняет гостевой черновик после перезагрузки', async ({ page }) => {
  await startPractice(page);
  const location = page.url();
  const saved = page.waitForResponse(response => response.url().endsWith('/draft') && response.request().method() === 'PUT');
  await page.getByLabel('Ответ', { exact: true }).fill('12,5');
  expect((await saved).ok()).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('12,5');
  expect(page.url()).toBe(location);
});

test('сохраняет одну форму ответа при работе таймера и смене задачи', async ({ page }) => {
  const keyErrors: string[] = [];
  page.on('console', message => {
    if (message.type() === 'error' && /same key/i.test(message.text())) keyErrors.push(message.text());
  });
  await startPractice(page);
  const singleWorksheet = async () => {
    await expect(page.locator('form.answer-form')).toHaveCount(1);
    await expect(page.locator('[id="answer"]')).toHaveCount(1);
    await expect(page.getByRole('group', { name: 'Ваши отметки', exact: true })).toHaveCount(1);
  };
  await expect(page.locator('.session-position > div > span')).not.toHaveText('0 с');
  await singleWorksheet();
  await page.getByRole('button', { name: 'Пауза', exact: true }).click();
  const saved = page.waitForResponse(response => response.url().endsWith('/draft') && response.request().method() === 'PUT');
  await page.getByLabel('Ответ', { exact: true }).fill('12,5');
  expect((await saved).ok()).toBe(true);
  await page.getByRole('button', { name: 'В избранное', exact: true }).click();
  await expect(page.getByRole('button', { name: 'В избранном', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const positions = page.getByRole('navigation', { name: 'Задачи занятия', exact: true }).getByRole('button');
  await positions.nth(1).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('');
  await expect(page.getByRole('button', { name: 'В избранное', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await singleWorksheet();
  await positions.nth(0).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('12,5');
  await expect(page.getByRole('button', { name: 'В избранном', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await singleWorksheet();
  await page.reload();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('12,5');
  await singleWorksheet();
  await page.getByLabel('Ответ', { exact: true }).focus();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeFocused();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  expect(keyErrors).toEqual([]);
});

test('проходит все 20 задач одной серии и сохраняет исходную историю после reload', async ({ page }) => {
  test.setTimeout(120_000);
  const pageErrors: string[] = [];
  const keyErrors: string[] = [];
  let starts = 0;
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error' && /same key/i.test(message.text())) keyErrors.push(message.text());
  });
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/sessions')) starts += 1;
  });
  await page.goto('/#/practice');
  await page.getByRole('radio', { name: '20 задач', exact: true }).check();
  const prepared = page.waitForResponse(response => response.url().endsWith('/api/v1/sessions') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const response = await prepared;
  expect(response.ok()).toBe(true);
  const session = await response.json() as LearningSession;
  expect(session.tasks).toHaveLength(20);
  expect(new Set(session.tasks.map(task => task.id)).size).toBe(20);
  await expect(page.getByLabel('Ответ', { exact: true })).toBeEditable();
  const location = page.url();
  const attempts: Attempt[] = [];
  for (let index = 0; index < 20; index += 1) {
    await expect(page).toHaveURL(location);
    await expect(page.locator('.session-position > span')).toHaveText(`Задача ${index + 1} из 20`);
    await expect(page.locator('form.answer-form')).toHaveCount(1);
    await expect(page.locator('[id="answer"]')).toHaveCount(1);
    await expect(page.getByRole('group', { name: 'Ваши отметки', exact: true })).toHaveCount(1);
    if (index === 9) {
      const saved = page.waitForResponse(reply => reply.url().endsWith(`/${session.id}/draft`)
        && reply.request().postDataJSON().task_id === session.tasks[index].id
        && reply.request().postDataJSON().answer === '9999999999999999');
      await page.getByLabel('Ответ', { exact: true }).fill('9999999999999999');
      expect((await saved).ok()).toBe(true);
      await page.reload();
      await expect(page).toHaveURL(location);
      await expect(page.locator('.session-position > span')).toHaveText('Задача 10 из 20');
      await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('9999999999999999');
    }
    const attempt = await submitAnswer(page, '9999999999999999');
    expect(attempt).toMatchObject({ task_id: session.tasks[index].id, first_attempt: true, independent: true, assisted: false, skipped: false });
    attempts.push(attempt);
    await page.getByRole('button', { name: index === 19 ? 'К завершению' : 'Следующая задача', exact: true }).click();
  }
  await expect(page.getByRole('dialog')).toContainText('Все задачи получили ответ или отметку о пропуске.');
  const finished = page.waitForResponse(reply => reply.url().endsWith(`/${session.id}/finish`) && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  const reply = await finished;
  expect(reply.ok()).toBe(true);
  const completed = await reply.json() as LearningSession;
  expect(completed.tasks).toEqual(session.tasks);
  expect(completed.profile).toEqual(session.profile);
  expect(completed.attempts).toEqual(attempts);
  expect(new Set(attempts.map(attempt => attempt.id)).size).toBe(20);
  expect(completed.summary).toMatchObject({ total: 20, answered: 20, independent_total: 20, assisted: 0, corrections: 0, skipped: 0 });
  await expect(page.getByRole('heading', { name: 'Занятие завершено', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Занятие завершено', exact: true })).toBeVisible();
  await expect(page.locator('.session-review > details')).toHaveCount(20);
  await expect(page.locator('form.answer-form')).toHaveCount(0);
  expect(starts).toBe(1);
  expect(pageErrors).toEqual([]);
  expect(keyErrors).toEqual([]);
});

test('не считает неверный формат математической попыткой', async ({ page }) => {
  await startPractice(page);
  await page.getByLabel('Ответ', { exact: true }).fill('1/0');
  const response = page.waitForResponse(value => value.url().endsWith('/attempts') && value.request().method() === 'POST');
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  expect((await response).status()).toBe(422);
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('1/0');
  await expect(page.getByRole('alert')).toBeVisible();
});

test('подсказка перед первым ответом сохраняет признак помощи', async ({ page }) => {
  await startPractice(page);
  const hintResponse = page.waitForResponse(value => value.url().endsWith('/hints') && value.request().method() === 'POST');
  await page.getByRole('button', { name: /подсказка 1/i }).click();
  expect((await hintResponse).ok()).toBe(true);
  await page.getByLabel('Ответ', { exact: true }).fill('9999999999999999');
  const attemptResponse = page.waitForResponse(value => value.url().endsWith('/attempts') && value.request().method() === 'POST');
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  const attempt = await (await attemptResponse).json();
  expect(attempt.assisted).toBe(true);
  expect(attempt.independent).toBe(false);
  expect(attempt.first_attempt).toBe(true);
  expect(attempt.correct).toBe(false);
});

test('сеть не превращает ответ в математическую ошибку и черновик остаётся', async ({ page, context }) => {
  await startPractice(page);
  await context.setOffline(true);
  await page.getByLabel('Ответ', { exact: true }).fill('2,50');
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('2,50');
  await expect(page.getByText(/нет сети|без сети|соединени|отправк/i).first()).toBeVisible();
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByLabel('Ответ', { exact: true })).toHaveValue('2,50');
});

for (const width of [320, 360, 390, 768, 1024, 1440]) {
  test(`план читается без горизонтальной прокрутки на ${width} CSS px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    }));
    expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(result.violations).toEqual([]);
  });
}

test('имя главной ссылки совпадает с видимым названием проекта', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  const brand = page.locator('.sidebar .brand');
  await expect(brand).toBeVisible();
  const result = await new AxeBuilder({ page }).include('.sidebar .brand').withRules(['label-content-name-mismatch']).analyze();
  expect(result.violations).toEqual([]);
  await expect(brand).toHaveAccessibleName('ЕГЭ Профиль Математика 2027');
  await expect(brand).toHaveAttribute('href', '#/');
  await brand.focus();
  await expect(brand).toBeFocused();
  await page.screenshot({ path: test.info().outputPath('brand-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.mobile-brand')).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('brand-mobile.png'), fullPage: true });
});

test('поле ответа доступно на 320 CSS px с увеличенным текстом', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await startPractice(page);
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await page.getByLabel('Ответ', { exact: true }).focus();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeFocused();
});

test('длинная формула доступна с клавиатуры на узком экране', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#/topics/6');
  await expect(page.getByRole('article')).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  const formula = page.getByRole('group', { name: 'Формула', exact: true }).last();
  await formula.focus();
  await expect(formula).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => formula.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
});
