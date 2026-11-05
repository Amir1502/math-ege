import { expect, test } from '@playwright/test';

test('иконки установки доступны как PNG заявленного размера', async ({ page }) => {
  await page.goto('/');
  const response = await page.request.get('/manifest.webmanifest');
  expect(response.ok()).toBe(true);
  const manifest: { icons: Array<{ src: string; sizes: string; type: string }> } = await response.json();
  for (const size of [192, 512]) {
    const icon = manifest.icons.find(item => item.sizes === `${size}x${size}` && item.type === 'image/png');
    expect(icon).toBeDefined();
    const image = await page.request.get(icon!.src);
    expect(image.ok()).toBe(true);
    expect(image.headers()['content-type']).toContain('image/png');
    const dimensions = await page.evaluate(async (src) => {
      const image = new Image();
      image.src = src;
      await image.decode();
      return [image.naturalWidth, image.naturalHeight];
    }, icon!.src);
    expect(dimensions).toEqual([size, size]);
  }
});

test('уведомление PWA не перекрывает начало занятия на телефоне', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const notice = page.getByRole('complementary', { name: 'Установка и обновление приложения' });
  await expect(notice).toContainText('Оболочка доступна без сети');
  const start = page.getByRole('button', { name: 'Начать занятие', exact: true });
  await start.scrollIntoViewIfNeeded();
  const actionBox = await start.boundingBox();
  const noticeBox = await notice.boundingBox();
  expect(actionBox).not.toBeNull();
  expect(noticeBox).not.toBeNull();
  expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(noticeBox!.y);
  await start.click();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
});

test('оболочка, открытый урок и черновик восстанавливаются без сети', async ({ page, context }) => {
  await page.goto('/');
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const answer = page.getByLabel('Ответ', { exact: true });
  await expect(answer).toBeVisible();
  const sessionUrl = page.url();
  const sessionId = sessionUrl.split('/').at(-1)!;
  await page.getByRole('link', { name: 'Вернуться к теории', exact: true }).click();
  await expect(page.getByRole('article')).toBeVisible();
  const lessonTitle = await page.getByRole('heading', { level: 1 }).innerText();
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(lessonTitle);
  await expect(page.getByRole('article')).toBeVisible();
  await page.goto(sessionUrl);
  await expect(answer).toBeVisible();
  await answer.fill('2,50');
  await page.reload();
  await expect(answer).toHaveValue('2,50');
  await expect(page.getByText('Сохранено на устройстве', { exact: true })).toBeVisible();
  await context.setOffline(false);
  const session = await (await page.request.get(`/api/v1/sessions/${sessionId}`)).json();
  expect(session.attempts).toEqual([]);
  const apiCaches = await page.evaluate(async () => {
    const stores = await Promise.all((await caches.keys()).map(name => caches.open(name)));
    const requests = (await Promise.all(stores.map(store => store.keys()))).flat();
    return requests.filter(request => new URL(request.url).pathname.startsWith('/api/')).map(request => request.url);
  });
  expect(apiCaches).toEqual([]);
});
