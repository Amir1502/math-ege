import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ResourceSnapshot, SavedAnnotation } from '../src/extras/types';
import { WorksheetAnnotations } from '../src/components/worksheet-annotations';

const resource = vi.hoisted(() => ({ snapshot: {} as ResourceSnapshot<SavedAnnotation[]> }));
vi.mock('../src/extras/hooks', () => ({
  useSavedAnnotations: () => ({ ...resource.snapshot, retry: vi.fn() }),
  useTaskAnnotations: () => ({
    available: true, pending: null, confirmed: {}, saving: false, saved: false, error: null,
    save: vi.fn(), retry: vi.fn(), reconcile: vi.fn(),
  }),
}));

function render(props: Partial<Parameters<typeof WorksheetAnnotations>[0]> = {}) {
  return renderToStaticMarkup(<WorksheetAnnotations
    sessionId="session-1" taskId="task-1" showCause={true} {...props}
  />);
}

beforeEach(() => {
  resource.snapshot = { owner: 'owner-1', ready: false, loading: true, data: null, error: null };
});

describe('worksheet annotation loading boundary', () => {
  it('never offers false defaults while saved values are unknown', () => {
    expect(render()).toContain('Загружаем ваши отметки');
    expect(render()).not.toContain('<fieldset');
  });

  it('does not offer edits without a verified owner or after a failed read', () => {
    resource.snapshot.owner = null;
    expect(render()).not.toContain('<fieldset');
    resource.snapshot.owner = 'owner-1';
    resource.snapshot.error = 'Не удалось загрузить';
    expect(render()).toContain('Не удалось загрузить');
    expect(render()).not.toContain('<fieldset');
  });

  it('requires an actual successful collection, not just a completed request', () => {
    resource.snapshot.ready = true;
    resource.snapshot.loading = false;
    expect(render()).not.toContain('<fieldset');
  });

  it('uses empty defaults only after a successful read', () => {
    resource.snapshot = { ...resource.snapshot, ready: true, loading: false, data: [] };
    expect(render()).toContain('aria-pressed="false"');
    expect(render()).toContain('<fieldset');
  });

  it('keeps saved marks and reads only the matching session and task', () => {
    resource.snapshot = { ...resource.snapshot, ready: true, loading: false, data: [
      { session_id: 'other', task_id: 'task-1', favourite: false, manual: false, not_understood: false, cause: null },
      { session_id: 'session-1', task_id: 'task-1', favourite: true, manual: true, not_understood: true, cause: 'model' },
    ] };
    const html = render();
    expect(html).toContain('aria-pressed="true"');
    expect(html.match(/checked=""/g)).toHaveLength(2);
    expect(html).toContain('<option value="model" selected="">');
  });

  it('withholds cached marks after owner verification is lost', () => {
    resource.snapshot = { owner: null, ready: true, loading: false, error: null, data: [
      { session_id: 'session-1', task_id: 'task-1', favourite: true, manual: true, not_understood: true, cause: 'model' },
    ] };
    expect(render()).toContain('Подключитесь к серверу');
    expect(render()).not.toContain('<fieldset');
  });

  it('withholds cached marks after a failed saved-values refresh', () => {
    resource.snapshot = { ...resource.snapshot, ready: true, loading: false, error: 'Нет связи с сервером.', data: [
      { session_id: 'session-1', task_id: 'task-1', favourite: true, manual: true, not_understood: true, cause: 'model' },
    ] };
    expect(render()).toContain('Нет связи с сервером.');
    expect(render()).toContain('Повторить');
    expect(render()).not.toContain('<fieldset');
  });

  it('does not carry marks to a different task or session and restores them on return', () => {
    resource.snapshot = { ...resource.snapshot, ready: true, loading: false, data: [
      { session_id: 'session-1', task_id: 'task-1', favourite: true, manual: true, not_understood: true, cause: 'model' },
      { session_id: 'other-session', task_id: 'task-2', favourite: true, manual: true, not_understood: true, cause: 'graph' },
    ] };
    for (const props of [{ taskId: 'task-2' }, { sessionId: 'other-session', taskId: 'task-1' }]) {
      const html = render(props);
      expect(html).toContain('aria-pressed="false"');
      expect(html).not.toContain('checked=""');
      expect(html).toContain('<option value="" selected="">');
    }
    const restored = render();
    expect(restored).toContain('aria-pressed="true"');
    expect(restored.match(/checked=""/g)).toHaveLength(2);
    expect(restored).toContain('<option value="model" selected="">');
  });

  it('hides the cause selector when the worksheet does not allow it without losing flags', () => {
    resource.snapshot = { ...resource.snapshot, ready: true, loading: false, data: [
      { session_id: 'session-1', task_id: 'task-1', favourite: true, manual: true, not_understood: true, cause: 'model' },
    ] };
    const html = render({ showCause: false });
    expect(html).not.toContain('<select');
    expect(html).toContain('aria-pressed="true"');
    expect(html.match(/checked=""/g)).toHaveLength(2);
  });
});
