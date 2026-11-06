import { readFile } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import type { BrowserContext } from '@playwright/test';

export const ORIGIN = 'https://appassets.androidplatform.net';
export const PREFIX = '/assets/www/';
const root = resolve(import.meta.dirname, '../dist-offline');
const media: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff',
  '.ttf': 'font/ttf',
};
const headers = {
  'X-Content-Type-Options': 'nosniff',
  'Cache-Control': 'no-store',
  'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'; manifest-src 'none'",
};

export async function mountBundledAssets(context: BrowserContext) {
  const denied: string[] = [];
  await context.setOffline(true);
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET' || url.origin !== ORIGIN || !url.pathname.startsWith(PREFIX)) {
      denied.push(url.origin + url.pathname);
      await route.abort('blockedbyclient');
      return;
    }
    const file = resolve(root, decodeURIComponent(url.pathname.slice(PREFIX.length)));
    if (!file.startsWith(root + sep) || !media[extname(file)]) {
      denied.push(url.pathname);
      await route.abort('blockedbyclient');
      return;
    }
    try {
      await route.fulfill({ status: 200, headers, contentType: media[extname(file)], body: await readFile(file) });
    } catch {
      denied.push(url.pathname);
      await route.fulfill({ status: 404, headers, contentType: 'text/plain', body: 'Ресурс отсутствует в пакете.' });
    }
  });
  return denied;
}
