import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const source = await readFile(new URL('../public/icon.svg', import.meta.url), 'utf8');
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  await page.setContent(`<style>html,body{width:100%;height:100%;margin:0}svg{display:block;width:100%;height:100%}</style>${source}`);
  await page.locator('svg > rect').first().evaluate(rect => rect.removeAttribute('rx'));
  for (const size of [192, 512]) {
    await page.setViewportSize({ width: size, height: size });
    await page.screenshot({ path: fileURLToPath(new URL(`../public/icon-${size}.png`, import.meta.url)) });
  }
} finally {
  await browser.close();
}
