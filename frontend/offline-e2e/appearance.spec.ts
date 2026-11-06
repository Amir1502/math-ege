import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { mountBundledAssets } from './assets';

test('раздел «О приложении» удалён из меню и больше не открывается по ссылке', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  await expect(page.getByRole('navigation', { name: 'Разделы приложения' }).getByRole('link')).toHaveText(['Практика', 'Уроки', 'Прогресс']);
  await expect(page.getByRole('link', { name: 'О приложении', exact: true })).toHaveCount(0);

  await page.goto('offline.html#/help');
  await expect(page.getByRole('heading', { name: 'Такого экрана нет', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'К практике', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  expect(denied).toEqual([]);
});

test('сохранённая тема окрашивает экран загрузки ещё до запуска интерфейса', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('offline.html');
  const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');

  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/assets/offline-*.js', async (route) => {
    await waiting;
    await route.fallback();
  });
  try {
    await page.reload({ waitUntil: 'commit' });
    await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(10, 15, 20)');
    await expect(page.getByText('Открываем встроенный курс…', { exact: true })).toBeVisible();
    await expect(toggle).toHaveCount(0);
  } finally {
    release();
  }
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  expect(denied).toEqual([]);
});

test('системная тёмная тема доступна с первого запуска, а ручной выбор сохраняется', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('offline.html');
  const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(10, 15, 20)');

  await toggle.press('Space');
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(248, 250, 252)');
  await page.getByRole('link', { name: 'Уроки', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Уроки/, level: 1 })).toBeVisible();
  await page.reload();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'light');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.emulateMedia({ colorScheme: 'light' });
  await page.reload();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
  expect(denied).toEqual([]);
});

for (const stored of [null, 'unknown']) {
  test(`до ручного выбора тема следует системе, сохранённая настройка: ${stored ?? 'отсутствует'}`, async ({ page, context }) => {
    const denied = await mountBundledAssets(context);
    await context.addInitScript((value) => {
      if (value !== null) localStorage.setItem('math-ege-offline-theme-v1', value);
    }, stored);
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('offline.html');
    const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await page.emulateMedia({ colorScheme: 'dark' });
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#0a0f14');
    await page.emulateMedia({ colorScheme: 'light' });
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute('content', '#f8fafc');
    expect(await page.evaluate(() => localStorage.getItem('math-ege-offline-theme-v1'))).toBe(stored);
    expect(denied).toEqual([]);
  });
}

test('недоступное хранилище настройки не мешает запуску и выбору темы на время сеанса', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.addInitScript(() => {
    const get = Storage.prototype.getItem;
    const set = Storage.prototype.setItem;
    Storage.prototype.getItem = function (key) {
      if (key === 'math-ege-offline-theme-v1') throw new DOMException('Storage unavailable', 'SecurityError');
      return get.call(this, key);
    };
    Storage.prototype.setItem = function (key, value) {
      if (key === 'math-ege-offline-theme-v1') throw new DOMException('Storage unavailable', 'SecurityError');
      return set.call(this, key, value);
    };
  });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('link', { name: 'Уроки', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Уроки/, level: 1 })).toBeVisible();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  expect(errors).toEqual([]);
  expect(denied).toEqual([]);
});

test('смена системной темы поддерживает старый MediaQueryList.addListener', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await context.addInitScript(() => {
    const matchMedia = window.matchMedia.bind(window);
    window.matchMedia = (query) => {
      const result = matchMedia(query);
      Object.defineProperties(result, {
        addEventListener: { value: undefined },
        removeEventListener: { value: undefined },
      });
      return result;
    };
  });
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('offline.html');
  const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
  expect(denied).toEqual([]);
});

test('нижняя навигация компактна и не перекрывает содержимое на телефоне', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
  const bounds = await nav.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.height).toBeLessThanOrEqual(64);
  expect(bounds!.y + bounds!.height).toBe(844);
  for (const link of await nav.getByRole('link').all()) {
    const target = await link.boundingBox();
    expect(target!.height).toBeGreaterThanOrEqual(44);
    expect(target!.width).toBeGreaterThanOrEqual(44);
    const icon = await link.locator('svg').boundingBox();
    expect(icon!.width).toBe(20);
    expect(icon!.height).toBe(20);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const lastParagraph = await page.getByRole('main').locator('p').last().boundingBox();
  expect(lastParagraph!.y + lastParagraph!.height).toBeLessThanOrEqual(bounds!.y);
  expect(denied).toEqual([]);
});

for (const colorScheme of ['light', 'dark'] as const) {
  test(`навигация адаптивна на телефоне, планшете и компьютере, тема: ${colorScheme}`, async ({ page, context }) => {
    const denied = await mountBundledAssets(context);
    await page.emulateMedia({ colorScheme });
    await page.goto('offline.html');
    await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
    await page.evaluate(() => document.fonts.ready);
    const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
    for (const { width, height } of [
      { width: 320, height: 740 }, { width: 360, height: 800 }, { width: 375, height: 812 },
      { width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 844, height: 390 },
      { width: 1024, height: 768 }, { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize({ width, height });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `Переполнение на ${width} × ${height}`).toBe(true);
      const bounds = await nav.boundingBox();
      expect(bounds).not.toBeNull();
      for (const link of await nav.getByRole('link').all()) {
        const target = await link.boundingBox();
        expect(target!.height).toBeGreaterThanOrEqual(48);
        expect(target!.width).toBeGreaterThanOrEqual(48);
      }
      if (width < 1024) {
        expect(bounds!.height).toBeLessThanOrEqual(64);
        expect(bounds!.y + bounds!.height).toBe(height);
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const lastParagraph = await page.getByRole('main').locator('p').last().boundingBox();
        expect(lastParagraph!.y + lastParagraph!.height).toBeLessThanOrEqual(bounds!.y);
      } else {
        const main = await page.getByRole('main').boundingBox();
        expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(main!.x);
      }
    }
    expect(denied).toEqual([]);
  });
}

test('крупный текст не прячет содержимое за переносами подписей в нижней навигации', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  await page.evaluate(async () => {
    await document.fonts.ready;
    document.documentElement.style.fontSize = '200%';
  });
  const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
  await expect(nav.getByRole('link').first()).toHaveCSS('font-size', '24px');
  for (const width of [320, 360, 375, 390, 768, 844, 1024, 1440]) {
    await page.setViewportSize({ width, height: width === 844 ? 390 : 740 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `Переполнение крупного текста на ${width} CSS px`).toBe(true);
    if (width < 1024) {
      await expect.poll(async () => {
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        const bounds = await nav.boundingBox();
        const lastParagraph = await page.getByRole('main').locator('p').last().boundingBox();
        return bounds!.y - (lastParagraph!.y + lastParagraph!.height);
      }).toBeGreaterThanOrEqual(0);
    } else {
      const bounds = await nav.boundingBox();
      const main = await page.getByRole('main').boundingBox();
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(main!.x);
    }
  }
  await page.setViewportSize({ width: 320, height: 740 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '100%'; });
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeLessThanOrEqual(64);
  expect(denied).toEqual([]);
});

test('в тёмной теме переключатель и навигация доступны с клавиатуры', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  const toggle = page.getByRole('button', { name: 'Тёмная тема', exact: true });
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Перейти к содержанию', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'ЕГЭ Профиль 2027. Практика', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(toggle).toBeFocused();
  await expect(toggle).toHaveCSS('outline-style', 'solid');
  await expect(toggle).toHaveCSS('outline-width', '3px');
  await toggle.press('Space');
  await expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await toggle.press('Enter');
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
  for (const link of await nav.getByRole('link').all()) {
    await page.keyboard.press('Tab');
    await expect(link).toBeFocused();
    await expect(link).toHaveCSS('outline-style', 'solid');
  }
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: /Прогресс/, level: 1 })).toBeFocused();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  expect(denied).toEqual([]);
});

test('тёмная тема доступна в основных разделах, уроке и задаче', async ({ page, context }) => {
  const denied = await mountBundledAssets(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('offline.html');
  await expect(page.getByRole('button', { name: 'Начать занятие', exact: true })).toBeEnabled();
  for (const name of ['Практика', 'Уроки', 'Прогресс']) {
    await page.getByRole('link', { name, exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
    expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  }
  await page.getByRole('link', { name: 'Уроки', exact: true }).click();
  await page.locator('.offline-lesson-list a').last().click();
  await expect(page.locator('.math-inline, .math-block').first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  await page.getByRole('link', { name: 'Практика', exact: true }).click();
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'dark');
  expect((await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations).toEqual([]);
  expect(denied).toEqual([]);
});
