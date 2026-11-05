import { afterEach, describe, expect, it, vi } from 'vitest';
import { request } from '../src/api/client';

afterEach(() => { vi.unstubAllGlobals(); });

describe('same-origin private API access', () => {
  it('never caches private GET responses and does not create a guest on GET', async () => {
    const fetcher = vi.fn(async () => Response.json({ slots: [] }));
    vi.stubGlobal('fetch', fetcher);
    await request('/progress');
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith('/api/v1/progress', expect.objectContaining({ method: 'GET', cache: 'no-store', credentials: 'same-origin' }));
  });
  it('passes raw JSON, the mutation header, and the supplied idempotency key', async () => {
    const fetcher = vi.fn(async () => Response.json({ id: 'one' }));
    vi.stubGlobal('fetch', fetcher);
    await request('/sessions/one/attempts', 'POST', { answer: '−2,50' }, 'same-key');
    expect(fetcher).toHaveBeenCalledWith('/api/v1/sessions/one/attempts', expect.objectContaining({
      headers: expect.objectContaining({ 'X-Requested-With': 'math-ege', 'Idempotency-Key': 'same-key' }),
      body: '{"answer":"−2,50"}',
    }));
  });
});
