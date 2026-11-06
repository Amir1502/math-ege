import { readFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import { mountBundledAssets } from './assets';

async function reference(page: Page) {
  const id = await page.locator('.task-sheet').getAttribute('data-task-id');
  const tasks = JSON.parse(await readFile(new URL('../../backend/content/course/tasks.json', import.meta.url), 'utf8')) as { id: string; answer: string }[];
  const answer = tasks.find((task) => task.id === id)?.answer;
  if (answer === undefined) throw new Error(`Нет исходного эталона для ${id}`);
  return answer;
}

test('первый запуск, новый урок и проверка работают без сети и API', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  expect(await page.evaluate(() => navigator.onLine)).toBe(false);

  await page.getByRole('link', { name: 'Уроки', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Уроки/, level: 1 })).toBeVisible();
  const lesson = page.locator('.offline-lesson-list a').last();
  await lesson.click();
  await expect(page).toHaveURL(/#\/lessons\//);
  await expect(page.locator('.math-inline, .math-block').first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);

  await page.getByRole('link', { name: 'Практика', exact: true }).click();
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toBeVisible();
  await answer.fill('12,5');
  await expect(page.getByText(/Сохранено на устройстве/, { exact: false }).first()).toBeVisible();
  await page.reload();
  await expect(answer).toHaveValue('12,5');
  await answer.fill('1/0');
  await page.getByRole('button', { name: /^Проверить(?: исправление)?$/ }).click();
  await expect(page.getByText(/Знаменатель/).first()).toBeVisible();
  await answer.fill('9999999999999999');
  await page.getByRole('button', { name: /^Проверить(?: исправление)?$/ }).click();
  await expect(page.getByText(/Неверно|Пока неверно/).first()).toBeVisible();
  await answer.fill(await reference(page));
  await page.getByRole('button', { name: 'Проверить исправление', exact: true }).click();
  await expect(page.getByText('Исправлено', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Следующая задача', exact: true })).toBeEnabled();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  for (const level of [1, 2, 3]) {
    await page.getByRole('button', { name: `Открыть подсказку ${level}`, exact: true }).click();
    await expect(page.getByRole('heading', { name: `Подсказка ${level}`, exact: true })).toBeVisible();
  }
  await page.getByRole('button', { name: 'Открыть решение', exact: true }).click();
  await answer.fill(await reference(page));
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  await expect(page.getByText('До первого ответа была открыта помощь.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  await page.getByRole('button', { name: 'Пропустить', exact: true }).click();
  await expect(page.getByText('Пропущено', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Следующая задача', exact: true }).click();
  await answer.fill('1/0');
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  await expect(page).toHaveURL(/#\/summary\//);
  const ledger = (label: string) => page.locator('.offline-ledger > div').filter({ has: page.getByText(label, { exact: true }) }).locator('dd');
  await expect(ledger('Первые самостоятельные ответы')).toHaveText('1');
  await expect(ledger('Из них верные')).toHaveText('0');
  await expect(ledger('Исправления')).toHaveText('1');
  await expect(ledger('Пропуски')).toHaveText('1');
  await expect(page.getByText('Без проверенного ответа', { exact: true })).toHaveCount(2);
  await page.reload();
  await expect(ledger('Первые самостоятельные ответы')).toHaveText('1');
  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Прогресс/, level: 1 })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: /Прогресс/, level: 1 })).toBeVisible();
  expect(denied).toEqual([]);
  expect(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)).toBe(0);
});

test('сбой записи черновика не имитирует сохранение и не выпускает со страницы до восстановления', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toBeVisible();
  await page.evaluate(() => {
    const put = IDBObjectStore.prototype.put;
    Object.assign(window, { restoreOfflineWrites: () => { IDBObjectStore.prototype.put = put; } });
    IDBObjectStore.prototype.put = function (value, key) {
      if (this.name === 'sessions') throw new DOMException('Quota exceeded', 'QuotaExceededError');
      return put.call(this, value, key);
    };
  });
  await answer.fill('12,5');
  await expect(page.getByText('Черновик пока не сохранён', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await expect(page).toHaveURL(/#\/session\//);
  await expect(answer).toHaveValue('12,5');
  await page.evaluate(() => (window as unknown as { restoreOfflineWrites: () => void }).restoreOfflineWrites());
  await page.getByRole('button', { name: 'Прочитать и сохранить снова', exact: true }).click();
  await expect(page.getByText('Сохранено на устройстве', { exact: true })).toBeVisible();
  await page.reload();
  await expect(answer).toHaveValue('12,5');
  expect(denied).toEqual([]);
});

test('неубранный подтверждённый UUID остаётся заблокированным повтором и не создаёт второй ответ', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toBeVisible();
  await page.evaluate(() => {
    const remove = Storage.prototype.removeItem;
    Object.assign(window, { restoreOfflineQueue: () => { Storage.prototype.removeItem = remove; } });
    Storage.prototype.removeItem = function (key) {
      if (key.startsWith('math-ege-offline-ui-v1:attempt:')) throw new DOMException('Storage unavailable', 'SecurityError');
      return remove.call(this, key);
    };
  });
  await answer.fill(await reference(page));
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  await expect(page.getByText('ui_queue_acknowledgement_failed', { exact: true })).toBeVisible();
  await expect(answer).toHaveAttribute('readonly', '');
  await page.evaluate(() => (window as unknown as { restoreOfflineQueue: () => void }).restoreOfflineQueue());
  await page.locator('.answer-form').getByRole('button', { name: 'Повторить проверку', exact: true }).click();
  await expect(page.getByText('Верно', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await expect(page.locator('.offline-big-number')).toHaveText('1 из 1');
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith('math-ege-offline-ui-v1:attempt:')))).toEqual([]);
  expect(denied).toEqual([]);
});

test('повреждённая локальная очередь не заменяется новым UUID после повторного чтения', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toBeVisible();
  await page.evaluate(() => {
    const id = decodeURIComponent(location.hash.split('/').pop()!);
    localStorage.setItem(`math-ege-offline-ui-v1:attempt:${id}`, '{"original":"unreadable-key"}');
  });
  await page.reload();
  await expect(page.getByText('ui_queue_invalid', { exact: true })).toBeVisible();
  await expect(answer).toHaveAttribute('readonly', '');
  await page.getByRole('button', { name: 'Прочитать и сохранить снова', exact: true }).click();
  await expect(page.getByText('ui_queue_invalid', { exact: true })).toBeVisible();
  await expect(answer).toHaveAttribute('readonly', '');
  expect(await page.evaluate(() => {
    const id = decodeURIComponent(location.hash.split('/').pop()!);
    return localStorage.getItem(`math-ege-offline-ui-v1:attempt:${id}`);
  })).toBe('{"original":"unreadable-key"}');
  expect(denied).toEqual([]);
});

test('finish-UUID сохраняется до подтверждения очереди, включая повторный запуск', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const remove = Storage.prototype.removeItem;
    Storage.prototype.removeItem = function (key) {
      if (key.startsWith('math-ege-offline-ui-v1:finish:')) throw new DOMException('Storage unavailable', 'SecurityError');
      return remove.call(this, key);
    };
  });
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  await expect(page).toHaveURL(/#\/session\//);
  await expect(page.getByText('ui_queue_acknowledgement_failed', { exact: true })).toBeVisible();
  const original = await page.evaluate(() => Object.entries(localStorage).filter(([key]) => key.startsWith('math-ege-offline-ui-v1:finish:')));
  expect(original).toHaveLength(1);
  await page.reload();
  await page.getByRole('button', { name: 'Повторить завершение', exact: true }).click();
  await expect(page).toHaveURL(/#\/summary\//);
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith('math-ege-offline-ui-v1:finish:')))).toEqual([]);
  await page.getByRole('link', { name: 'Прогресс', exact: true }).click();
  await expect(page.locator('.offline-recent-sessions > ul > li')).toHaveCount(1);
  expect(denied).toEqual([]);
});

test('ссылка пропуска переводит фокус к содержанию, не меняя раздел', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  const url = page.url();
  const skip = page.getByRole('link', { name: 'Перейти к содержанию', exact: true });
  await skip.focus();
  await skip.click();
  await expect(page.getByRole('main')).toBeFocused();
  await expect(page).toHaveURL(url);
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  expect(denied).toEqual([]);
});

for (const width of [320, 390, 1440]) {
  test(`автономный старт доступен на ${width} CSS px`, async ({ page, context }) => {
    const denied = await mountBundledAssets(context);
    await page.setViewportSize({ width, height: 900 });
    await page.goto('offline.html');
    await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`offline-${width}.png`), fullPage: true });
    await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
    await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`offline-session-${width}.png`), fullPage: true });
    expect(denied).toEqual([]);
  });
}
