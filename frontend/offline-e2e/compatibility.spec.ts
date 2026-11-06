import { expect, test } from '@playwright/test';
import { mountBundledAssets } from './assets';

test('ES2020 WebView не требует более новых встроенных API', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await context.addInitScript(() => {
    Reflect.deleteProperty(Object, 'hasOwn');
    Reflect.deleteProperty(URLSearchParams.prototype, 'size');
    Reflect.deleteProperty(Array.prototype, 'at');
    Reflect.deleteProperty(String.prototype, 'replaceAll');
    Reflect.deleteProperty(window, 'structuredClone');
    Object.defineProperty(Crypto.prototype, 'randomUUID', { value: undefined });
  });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  await page.getByRole('link', { name: 'Уроки', exact: true }).click();
  await page.getByRole('searchbox', { name: 'Найти урок', exact: true }).fill('дроб');
  await page.getByRole('button', { name: 'Найти урок', exact: true }).click();
  await expect(page).toHaveURL(/\?q=/);
  await page.reload();
  await expect(page.getByRole('searchbox', { name: 'Найти урок', exact: true })).toHaveValue('дроб');
  await page.getByRole('link', { name: 'Практика', exact: true }).click();
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  await page.getByLabel('Ответ', { exact: true }).fill('1/0');
  await page.getByRole('button', { name: 'Проверить', exact: true }).click();
  await expect(page.getByText('Математическая попытка не создана.', { exact: true })).toBeVisible();
  expect(denied).toEqual([]);
});

test('без BigInt показана совместимость, а не приближённая проверка', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await context.addInitScript(() => { Object.defineProperty(window, 'BigInt', { value: undefined }); });
  await page.goto('offline.html');
  await expect(page.getByRole('heading', { name: 'Нужна новая версия WebView', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toHaveCount(0);
  await expect(page.locator('script:not([src])')).toHaveCount(0);
  expect(denied).toEqual([]);
});
