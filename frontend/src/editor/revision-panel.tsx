import { useCallback, useEffect, useMemo, useState } from 'react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, Loading } from '../components/ui';
import type { EditorApi } from './api';
import { decodeRevision, EditorError } from './adapters';
import { starter } from './drafts';
import { EditorFailure } from './feedback';
import { JsonWorksheet } from './worksheet';
import { Workflow } from './workflow';
import { TemplateEvidencePanel } from './template-evidence';
import { WithdrawalForm } from './withdrawal';
import { statusLabels } from './types';
import type { BaseItem, EditorMeta, Kind, Revision, Withdrawal } from './types';
import type { EditorMutation } from './use-mutation';
import { useEditorResource } from './use-resource';

type Props = {
  api: EditorApi; meta: EditorMeta; mutation: EditorMutation; dirty: boolean;
  onDirty: (dirty: boolean) => void; onUpdated: (record: Revision) => void; onNotice: (message: string) => void;
};
const titles: Record<Kind, string> = { task: 'Новая задача', lesson: 'Новый урок', profile: 'Новый профиль', template: 'Новый шаблон' };

function DocumentHeading({ record }: { record: Revision }) {
  useEffect(() => { document.getElementById('editor-document-heading')?.focus(); }, [record.id]);
  return <header className="editor-document-heading"><h2 id="editor-document-heading" tabIndex={-1}>{record.title}</h2>
    <p className={`editor-status editor-status--${record.status}`}>{statusLabels[record.status]}</p>
    <p>Версия {record.version}, CAS {record.revision}<br /><code>{record.content_id}</code><br /><code>{record.content_revision}</code></p>
  </header>;
}

export function RevisionPanel({ id, ...props }: Props & { id: string }) {
  const { api, meta, mutation, dirty, onDirty, onUpdated, onNotice } = props;
  const load = useCallback((signal: AbortSignal) => api.revision(id, signal), [api, id]);
  const resource = useEditorResource(load, id);
  const record = resource.data;
  const updated = (value: Revision) => { if (value.id === id) resource.replace(value); onUpdated(value); };
  const withdrawn = (value: Withdrawal) => { onNotice(`Задача снята с новой выдачи. Причина: ${value.reason}`); resource.retry(); };

  if (resource.loading) return <div className="editor-document"><Loading label="Открываем редакцию материала" /></div>;
  if (resource.error) return <div className="editor-document"><EditorFailure error={resource.error} retry={resource.retry} /></div>;
  if (!record) return null;
  return <article className="editor-document" aria-labelledby="editor-document-heading">
    <DocumentHeading record={record} />
    {mutation.error?.code === 'revision_conflict' && <div className="editor-readonly"><p>Скачайте текущий ввод перед загрузкой новой серверной редакции.</p>
      <Button onClick={() => { if (!dirty || window.confirm('Загрузить серверную редакцию и заменить несохранённый ввод?')) resource.retry(); }}>Загрузить свежую редакцию</Button>
    </div>}
    <JsonWorksheet key={`${record.id}:${record.revision}`} api={api} kind={record.kind} payload={record.payload} record={record}
      maxBytes={meta.max_request_bytes} mutation={mutation} onSaved={updated} onDirty={onDirty} />
    {record.kind === 'template' && <TemplateEvidencePanel key={`evidence:${record.revision}`} api={api} record={record} mutation={mutation} dirty={dirty} onUpdated={updated}
      onChecked={result => { onNotice(result.passed ? `Серверный протокол записан: ${result.seed_count} seed. Предметную проверку выполняет рецензент.` : `Протокол не пройден. ${result.failure ?? 'Проверьте шаблон.'}`); resource.retry(); }} />}
    <Workflow key={`workflow:${record.revision}`} record={record} actorId={meta.actor.id} mutation={mutation} dirty={dirty} onUpdated={updated} onWithdrawn={withdrawn} />
  </article>;
}

export function NewRevisionPanel({ kind, ...props }: Props & { kind: Kind }) {
  const initial = useMemo(() => {
    try { return { payload: starter(kind, props.meta), error: null }; }
    catch (error) { return { payload: null, error: error instanceof EditorError ? error : new EditorError('Не удалось подготовить пустой материал.') }; }
  }, [kind, props.meta]);
  useEffect(() => { document.getElementById('editor-document-heading')?.focus(); }, []);
  return <article className="editor-document" aria-labelledby="editor-document-heading">
    <header className="editor-document-heading"><h2 id="editor-document-heading" tabIndex={-1}>{titles[kind]}</h2>
      <p>Заполните содержимое и стабильные ID. Материал сохранится как ваш черновик.</p>
    </header>
    {kind === 'template' && props.meta.templates.length === 0 && <p className="notice">На сервере нет зарегистрированных генераторов. Сохранение и публикация шаблона требуют поддерживаемого генератора.</p>}
    {initial.error && <EditorFailure error={initial.error} />}
    {initial.payload && <JsonWorksheet api={props.api} kind={kind} payload={initial.payload} maxBytes={props.meta.max_request_bytes}
      mutation={props.mutation} onSaved={props.onUpdated} onDirty={props.onDirty} />}
  </article>;
}

export function BaseRevisionPanel({ item, meta, mutation, onUpdated, onNotice, onDirty }: Pick<Props, 'meta' | 'mutation' | 'onUpdated' | 'onNotice' | 'onDirty'> & { item: BaseItem }) {
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [withdrawn, setWithdrawn] = useState(false);
  useEffect(() => { document.getElementById('editor-document-heading')?.focus(); }, []);
  useEffect(() => { onDirty(note.length > 0); }, [note, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);
  return <article className="editor-document" aria-labelledby="editor-document-heading">
    <header className="editor-document-heading"><h2 id="editor-document-heading" tabIndex={-1}>{item.title}</h2>
      <p>Исходный материал<br /><code>{item.content_id}</code><br />Редакция <code>{item.content_revision}</code></p>
    </header>
    <p>Создайте редакцию, чтобы открыть полный JSON и мобильный предпросмотр. Сервер сохранит стабильный ID и исходный снимок материала.</p>
    <form onSubmit={event => {
      event.preventDefault();
      if (note.trim().length < 5) { setError('Опишите планируемое изменение минимум пятью символами.'); return; }
      void mutation.run(`/base/${item.kind}/${encodeURIComponent(item.content_id)}`, 'POST', { change_note: note.trim() }, value => onUpdated(decodeRevision(value)));
    }}>
      <div className="editor-field"><label htmlFor="editor-base-note">Причина новой редакции</label>
        <textarea id="editor-base-note" rows={3} value={note} onChange={event => { setNote(event.target.value); setError(null); }} minLength={5} maxLength={2000} required disabled={mutation.locked}
          aria-invalid={Boolean(error)} aria-describedby={error ? 'editor-base-error' : undefined} />
        {error && <p className="editor-inline-error" id="editor-base-error" role="alert">{error}</p>}
      </div>
      <Button type="submit" variant="primary" disabled={mutation.locked}>Создать редакцию исходного материала</Button>
    </form>
    {meta.actor.role === 'admin' && item.kind === 'task' && !withdrawn && <WithdrawalForm taskId={item.content_id} taskRevision={item.content_revision} mutation={mutation}
      onWithdrawn={value => { setWithdrawn(true); onNotice(`Исходная задача снята с выдачи. Причина: ${value.reason}`); }} />}
    {withdrawn && <p className="editor-readonly" role="status">Эта задача снята с новой выдачи.</p>}
  </article>;
}
