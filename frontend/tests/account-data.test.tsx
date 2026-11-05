import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AccountData } from '../src/accounts/data-controls';
import type { DeletionRequest } from '../src/accounts/types';

const requested: DeletionRequest = {
  id: '11111111-1111-4111-8111-111111111111', status: 'requested',
  requested_at: '2026-11-05T10:00:00Z', deadline_at: '2026-12-05T10:00:00Z',
};
const resource = vi.hoisted(() => ({
  snapshot: { data: null as DeletionRequest | null, loading: true, error: null as string | null },
  retry: vi.fn(), replace: vi.fn(),
}));
vi.mock('../src/accounts/use-account-resource', () => ({
  useAccountResource: () => ({ ...resource.snapshot, retry: resource.retry, replace: resource.replace }),
}));

function render() {
  return renderToStaticMarkup(<AccountData scope="1:owner-one" email="student@example.org" />);
}

beforeEach(() => { resource.snapshot = { data: null, loading: true, error: null }; });

describe('account deletion cancellation controls', () => {
  it('offers an explicitly named cancel action only for a successfully loaded requested receipt', () => {
    resource.snapshot = { data: requested, loading: false, error: null };
    expect(render()).toContain('Отменить запрос удаления');
    expect(render()).toContain('<button');
    expect(render()).not.toContain('Запросить удаление аккаунта</button>');
  });

  it.each([
    ['initial loading', { data: null, loading: true, error: null }],
    ['refreshing a cached request', { data: requested, loading: true, error: null }],
    ['failed initial status read', { data: null, loading: false, error: 'Не удалось проверить статус.' }],
    ['failed read with cached data', { data: requested, loading: false, error: 'Не удалось проверить статус.' }],
  ])('does not offer cancellation or show cached receipts while %s', (_name, snapshot) => {
    resource.snapshot = snapshot;
    const markup = render();
    expect(markup).not.toContain('Отменить запрос удаления');
    expect(markup).not.toContain('Запрос на удаление принят');
    expect(markup).not.toContain('Запросить удаление аккаунта</button>');
  });

  it('offers a new deletion request instead of cancellation for a confirmed absent status', () => {
    resource.snapshot = { data: null, loading: false, error: null };
    const markup = render();
    expect(markup).not.toContain('Отменить запрос удаления');
    expect(markup).toContain('Запросить удаление аккаунта</button>');
  });

  it.each(['canceled', 'completed', 'failed', 'unknown'])('does not treat unsupported status %s as a pending request', (status) => {
    // The transport rejects these statuses; this also keeps the rendering boundary fail-closed.
    resource.snapshot = { data: { ...requested, status } as DeletionRequest, loading: false, error: null };
    const markup = render();
    expect(markup).not.toContain('Отменить запрос удаления');
    expect(markup).not.toContain('Запрос на удаление принят');
    expect(markup).not.toContain('Запросить удаление аккаунта</button>');
  });
});
