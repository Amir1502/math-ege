import { afterEach, describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { TaskContent } from '../src/components/task-content';
import {
  decodeMeta, decodePreview, decodeRevision, decodeSample, decodeTask, decodeWithdrawal, EditorError,
} from '../src/editor/adapters';
import { createEditorApi, prepareMutation, sendMutation } from '../src/editor/api';
import type { Mutation } from '../src/editor/api';
import { parseImport, parsePayload, parseSeed, starter } from '../src/editor/drafts';
import { EditorMutationQueue } from '../src/editor/mutation-queue';

const task = {
  id: 'editor-task', revision: 'ed-task', slot: 1, slot_id: 'slot-1', topic: 'Планиметрия', title: 'Площадь треугольника',
  statement: 'Найдите площадь.', formula: null, table: null, figure: null, rounding: null,
  skill_ids: ['area'], family_id: 'triangle-area', estimated_seconds: 120, review_status: 'demo', hint_count: 3,
  answer: '12', hints: ['Основание.', 'Высота.', 'Половина произведения.'], solution: ['6 × 4 / 2 = 12.'],
  source: { origin: 'Учебная проверка', rights: 'Тест', author: 'author', reviewed_by: null }, secret: 'private-marker',
};
const profile = {
  id: 'profile-one', title: 'Профиль теста', year: 2027, status: 'draft', revision: '1',
  verified_at: '2026-11-05', verification_note: 'Изолированный тест.', source_urls: [],
  slots: [{ id: 'slot-1', number: 1, title: 'Планиметрия', level: 'Б', summary: 'Площади.', lesson_id: 'lesson-one', skills: [{ id: 'area', title: 'Площадь' }] }],
};
const metadata = {
  actor: { id: 'author', role: 'methodist', owner_id: 'owner-one' }, profile,
  kinds: ['task', 'lesson', 'profile', 'template'], statuses: ['draft', 'review', 'ready', 'published', 'archived'],
  max_import_items: 10, max_request_bytes: 131_072, templates: [],
};
const revision = {
  id: 'revision-one', kind: 'task', content_id: task.id, content_revision: 'ed-revision-one', title: task.title,
  version: 1, revision: 1, status: 'draft', author_id: 'author', reviewer_id: null, change_note: 'Создана задача.',
  created_at: '2026-11-05T10:00:00Z', updated_at: '2026-11-05T10:00:00Z', published_at: null,
  capabilities: ['edit', 'submit', 'fork'], payload: { id: task.id, answer: task.answer }, audit: [], evidence: null, review_note: null,
};
const hash = 'a'.repeat(64);
const networkError = () => new EditorError('Ответ не получен.', 'network', 0, null, true);

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('private editor response boundaries', () => {
  it('passes only the public task allowlist to the shared renderer', () => {
    const value = decodeTask(task);
    expect(Object.keys(value).sort()).toEqual([
      'id', 'revision', 'slot', 'slot_id', 'topic', 'title', 'statement', 'formula', 'table', 'figure',
      'rounding', 'skill_ids', 'family_id', 'estimated_seconds', 'review_status', 'hint_count',
    ].sort());
    expect(JSON.stringify(value)).not.toContain('private-marker');
    expect(value).not.toHaveProperty('answer');
    expect(value).not.toHaveProperty('source');
  });

  it('keeps staff-only sample answers separate from render props and checks the snapshot hash', () => {
    const value = decodeSample({ seed: 4_294_967_295, output_hash: hash, task });
    expect(value.answer).toBe('12');
    expect(value.solution).toEqual(task.solution);
    expect(value.task).not.toHaveProperty('answer');
    expect(() => decodeSample({ seed: 0, output_hash: 'not-a-manifest', task })).toThrow(EditorError);
    expect(() => decodeSample({ seed: 4_294_967_296, output_hash: hash, task })).toThrow(EditorError);
  });

  it('escapes text even if an invalid upstream response contains markup', () => {
    const value = decodeTask({ ...task, statement: '<img src=x onerror="alert(1)">' });
    const markup = renderToStaticMarkup(createElement(TaskContent, { task: value }));
    expect(markup).toContain('&lt;img');
    expect(markup).not.toContain('<img');
    expect(markup).not.toContain('private-marker');
  });

  it.each([
    { ...revision, capabilities: ['execute_code'] },
    { ...revision, status: 'trusted' },
    { ...revision, revision: 0 },
    { ...revision, version: 1.5 },
    { ...revision, payload: [] },
    { ...revision, audit: 'not-a-list' },
  ])('rejects a malformed revision before the UI can use its capabilities', value => {
    expect(() => decodeRevision(value)).toThrow(EditorError);
  });

  it('accepts authenticated attribution only from the response envelope', () => {
    const value = decodeRevision({ ...revision, arbitrary: 'discarded', payload: { ...revision.payload, title: 'Задача' } });
    expect(value.author_id).toBe('author');
    expect(value).not.toHaveProperty('arbitrary');
    expect(() => decodeMeta({ ...metadata, actor: { ...metadata.actor, role: 'student' } })).toThrow(EditorError);
    expect(() => decodeMeta({ ...metadata, max_import_items: 11 })).toThrow(EditorError);
  });

  it('rejects incomplete preview and correction receipts', () => {
    expect(() => decodePreview({ kind: 'task', task: null, payload: {}, message: 'ok' })).toThrow(EditorError);
    expect(() => decodePreview({ kind: 'lesson', task: null, payload: { title: 'Урок' }, message: 'ok' })).toThrow(EditorError);
    expect(() => decodeWithdrawal({ task_id: 'one', task_revision: 'one', reason: 'Ошибка.', created_at: 'now', historical_scores_unchanged: false })).toThrow(EditorError);
  });
});

describe('bounded JSON and stable editor mappings', () => {
  it('counts UTF-8 bytes and rejects arrays, prototype keys and deep trees', () => {
    const source = JSON.stringify({ text: 'я'.repeat(10) });
    expect(() => parsePayload(source, source.length)).toThrow(/размер/);
    expect(parsePayload(source, 100)).toEqual({ text: 'я'.repeat(10) });
    for (const value of ['[]', 'null', '{', '{"__proto__":{"admin":true}}']) {
      expect(() => parsePayload(value, 1000)).toThrow();
    }
    const nested = Array.from({ length: 22 }).reduce<object>(value => ({ nested: value }), {});
    expect(() => parsePayload(JSON.stringify(nested), 1000)).toThrow();
  });

  it('bounds imports before the request but leaves indexed row validation to the server', () => {
    const row = { kind: 'task', payload: { id: 'new-id' }, change_note: 'Новый материал.' };
    const source = JSON.stringify({ version: '1', items: [row, { unknown: true }] });
    expect(parseImport(source, 1000, 10).items).toEqual([row, { unknown: true }]);
    for (const items of [[], Array.from({ length: 11 }, () => row)]) {
      expect(() => parseImport(JSON.stringify({ version: '1', items }), 10_000, 10)).toThrow(/items/);
    }
    expect(() => parseImport('{"version":"2","items":[{}]}', 1000, 10)).toThrow();
  });

  it.each(['', '-1', '1e3', '1.5', '0x10', '+1', ' 1', '1 ', '4294967296', '١'])('rejects ambiguous or out-of-range seed %j', value => {
    expect(() => parseSeed(value)).toThrow();
  });
  it('preserves both uint32 endpoints exactly', () => {
    expect(parseSeed('0')).toBe(0);
    expect(parseSeed('4294967295')).toBe(4_294_967_295);
  });

  it('builds new drafts with explicit stable mappings and no imported review claims', () => {
    const meta = decodeMeta(metadata);
    const draft = starter('task', meta);
    expect(draft).toMatchObject({ slot: 1, slot_id: 'slot-1', profile_id: 'profile-one', skill_ids: ['area'], source: { origin: '', rights: '' } });
    expect(draft).not.toHaveProperty('review_status');
    expect(draft).not.toHaveProperty('revision');
    expect(draft.source).not.toHaveProperty('author');
    const nextProfile = starter('profile', meta);
    expect(nextProfile.slots).toEqual(profile.slots);
    expect(nextProfile).not.toHaveProperty('revision');
    expect(meta.profile.revision).toBe('1');
  });
});

describe('isolated same-origin editor transport', () => {
  it('gets metadata without guest creation or student storage and binds subsequent reads', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(metadata)).mockResolvedValueOnce(Response.json(revision));
    vi.stubGlobal('fetch', fetcher);
    const database = vi.spyOn(indexedDB, 'open');
    expect((await createEditorApi().meta()).actor.id).toBe('author');
    expect((await createEditorApi('author').revision('revision-one')).id).toBe('revision-one');
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual(['/api/v1/editor/meta', '/api/v1/editor/revisions/revision-one']);
    for (const [, options] of fetcher.mock.calls) expect(options).toMatchObject({ credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    expect(fetcher.mock.calls[1][1]?.headers).toMatchObject({ 'X-Editor-Actor': 'author' });
    expect(database).not.toHaveBeenCalled();
  });

  it('sends one immutable body, UUID key and authenticated-actor expectation', async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => Response.json(revision));
    vi.stubGlobal('fetch', fetcher);
    const body = { expected_revision: 3, payload: { answer: '12' }, change_note: 'Изменено условие.' };
    const prepared = prepareMutation('author', '/revisions/revision-one', 'PUT', body, 131_072);
    body.payload.answer = '999'; body.expected_revision = 42;
    await sendMutation(prepared); await sendMutation(prepared);
    expect(Object.isFrozen(prepared)).toBe(true);
    expect(prepared.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.parse(prepared.body)).toMatchObject({ expected_revision: 3, payload: { answer: '12' } });
    expect(fetcher.mock.calls[0]).toEqual(fetcher.mock.calls[1]);
    expect(fetcher.mock.calls[0][1]?.headers).toMatchObject({
      'X-Requested-With': 'math-ege', 'X-Editor-Actor': 'author', 'Idempotency-Key': prepared.key, 'Content-Type': 'application/json',
    });
  });

  it('rejects oversized or executable values before any mutation can be queued', () => {
    expect(() => prepareMutation('author', '/import', 'POST', { text: 'я'.repeat(10) }, 25)).toThrow(EditorError);
    expect(() => prepareMutation('author', '/import', 'POST', { execute: () => null }, 1000)).toThrow(EditorError);
    expect(() => prepareMutation('author', '/import', 'POST', { answer: Infinity }, 1000)).toThrow(EditorError);
  });

  it('distinguishes validation, changed identity, failed transport and unreadable receipts', async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ error: { code: 'invalid_import', message: 'Строка 2: неверный ответ.', field: 'items' } }, { status: 422 }))
      .mockResolvedValueOnce(Response.json({ error: { code: 'editor_identity_changed', message: 'Аккаунт изменился.' } }, { status: 403 }))
      .mockRejectedValueOnce(new TypeError('connection reset'))
      .mockResolvedValueOnce(new Response('unreadable', { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    const request = prepareMutation('author', '/import', 'POST', {}, 1000);
    await expect(sendMutation(request)).rejects.toMatchObject({ code: 'invalid_import', field: 'items', uncertain: false });
    await expect(sendMutation(request)).rejects.toMatchObject({ code: 'editor_identity_changed', status: 403, uncertain: false });
    await expect(sendMutation(request)).rejects.toMatchObject({ code: 'network', uncertain: true });
    await expect(sendMutation(request)).rejects.toMatchObject({ code: 'invalid_response', uncertain: true });
  });
});

describe('single editor mutation writer and uncertain retries', () => {
  it('blocks competing writes while a request is in flight', async () => {
    let finish!: (value: unknown) => void;
    const send = vi.fn<(request: Mutation) => Promise<unknown>>().mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const queue = new EditorMutationQueue('author', 1000, send);
    const accepted = vi.fn();
    const first = queue.run('/revisions', 'POST', { content: 'first' }, accepted);
    expect(queue.getSnapshot().busy).toBe(true);
    await queue.run('/revisions', 'POST', { content: 'competing' }, accepted);
    await queue.retry();
    expect(send).toHaveBeenCalledOnce();
    finish({ id: 'one' }); await first;
    expect(accepted).toHaveBeenCalledExactlyOnceWith({ id: 'one' });
    expect(queue.getSnapshot()).toEqual({ busy: false, uncertain: false, error: null });
  });

  it('keeps the original body and key after network failure and prevents replacing the job', async () => {
    const send = vi.fn<(request: Mutation) => Promise<unknown>>().mockRejectedValueOnce(networkError()).mockResolvedValueOnce(revision);
    const queue = new EditorMutationQueue('author', 1000, send);
    const body = { expected_revision: 1, note: 'Предметная проверка.' };
    const accept = vi.fn();
    await queue.run('/revisions/revision-one/submit', 'POST', body, accept);
    expect(queue.getSnapshot()).toMatchObject({ busy: false, uncertain: true });
    body.expected_revision = 2;
    await queue.run('/revisions/revision-one/archive', 'POST', body, vi.fn());
    expect(send).toHaveBeenCalledOnce();
    await queue.retry();
    expect(send.mock.calls[1][0]).toBe(send.mock.calls[0][0]);
    expect(JSON.parse(send.mock.calls[1][0].body).expected_revision).toBe(1);
    expect(accept).toHaveBeenCalledExactlyOnceWith(revision);
  });

  it('retains an uncertain request across a pre-replay MFA interruption', async () => {
    const send = vi.fn<(request: Mutation) => Promise<unknown>>()
      .mockRejectedValueOnce(networkError())
      .mockRejectedValueOnce(new EditorError('Подтвердите MFA.', 'mfa_required', 403))
      .mockResolvedValueOnce(revision);
    const queue = new EditorMutationQueue('author', 1000, send);
    await queue.run('/publish', 'POST', { items: [{ id: 'one', expected_revision: 4 }] }, vi.fn());
    await queue.retry();
    expect(queue.getSnapshot().uncertain).toBe(true);
    await queue.retry();
    expect(new Set(send.mock.calls.map(([request]) => request.key)).size).toBe(1);
    expect(send.mock.calls.every(([request]) => request.actorId === 'author')).toBe(true);
    expect(queue.getSnapshot().uncertain).toBe(false);
  });

  it('retries malformed success DTOs and accepts only a decoded receipt', async () => {
    const send = vi.fn<(request: Mutation) => Promise<unknown>>().mockResolvedValueOnce({ ...revision, revision: null }).mockResolvedValueOnce(revision);
    const accepted = vi.fn();
    const queue = new EditorMutationQueue('author', 1000, send);
    await queue.run('/revisions', 'POST', {}, value => accepted(decodeRevision(value)));
    expect(accepted).not.toHaveBeenCalled();
    expect(queue.getSnapshot().uncertain).toBe(true);
    await queue.retry();
    expect(accepted).toHaveBeenCalledOnce();
    expect(send.mock.calls[0][0].key).toBe(send.mock.calls[1][0].key);
  });

  it('allows a corrected request with a new key after a definitive validation rejection', async () => {
    const send = vi.fn<(request: Mutation) => Promise<unknown>>()
      .mockRejectedValueOnce(new EditorError('Неверные данные.', 'invalid_content', 422))
      .mockResolvedValueOnce(revision);
    const queue = new EditorMutationQueue('author', 1000, send);
    await queue.run('/revisions', 'POST', { answer: 'bad' }, vi.fn());
    expect(queue.getSnapshot().uncertain).toBe(false);
    await queue.run('/revisions', 'POST', { answer: '12' }, vi.fn());
    expect(send.mock.calls[0][0].key).not.toBe(send.mock.calls[1][0].key);
  });
});
