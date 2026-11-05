import { useCallback, useEffect, useRef, useState } from 'react';
import { Braces, Download, Eye, Save } from 'lucide-react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, Loading } from '../components/ui';
import type { EditorApi } from './api';
import { decodeRevision, EditorError, errorText } from './adapters';
import { downloadText, parsePayload } from './drafts';
import { EditorFailure } from './feedback';
import { ContentPreview } from './preview';
import type { JsonObject, Kind, Preview, Revision } from './types';
import type { EditorMutation } from './use-mutation';

type Props = {
  api: EditorApi; kind: Kind; payload: JsonObject; record?: Revision; maxBytes: number;
  mutation: EditorMutation; onSaved: (record: Revision) => void; onDirty: (dirty: boolean) => void;
};

export function JsonWorksheet({ api, kind, payload, record, maxBytes, mutation, onSaved, onDirty }: Props) {
  const initial = JSON.stringify(payload, null, 2);
  const [source, setSource] = useState(initial);
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [noteProblem, setNoteProblem] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState<EditorError | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);
  const noteField = useRef<HTMLTextAreaElement>(null);
  const request = useRef<AbortController | null>(null);
  const editable = !record || record.capabilities.includes('edit');
  const dirty = editable && (source !== initial || note.length > 0);

  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);
  useEffect(() => () => { onDirty(false); request.current?.abort(); }, [onDirty]);

  const loadPreview = useCallback(async (value: JsonObject) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setPreviewLoading(true); setPreviewError(null); setPreview(null);
    try {
      const result = await api.preview(kind, value, controller.signal);
      if (!controller.signal.aborted) setPreview(result);
    } catch (failure) {
      if (!controller.signal.aborted) setPreviewError(failure instanceof EditorError ? failure : new EditorError(errorText(failure)));
    } finally { if (!controller.signal.aborted) setPreviewLoading(false); }
  }, [api, kind]);
  useEffect(() => { if (record) void loadPreview(record.payload); }, [loadPreview, record]);

  const parsed = (): JsonObject | null => {
    try { const result = parsePayload(source, maxBytes); setProblem(null); return result; }
    catch (failure) { setProblem(failure instanceof Error ? failure.message : 'Проверьте JSON.'); field.current?.focus(); return null; }
  };
  const showPreview = () => { const value = parsed(); if (value) void loadPreview(value); };
  const save = () => {
    if (!editable || mutation.locked) return;
    const value = parsed();
    if (!value) return;
    if (note.trim().length < 5) { setNoteProblem('Опишите изменение минимум пятью символами.'); noteField.current?.focus(); return; }
    const path = record ? `/revisions/${encodeURIComponent(record.id)}` : '/revisions';
    const body = record ? { expected_revision: record.revision, payload: value, change_note: note.trim() }
      : { kind, payload: value, change_note: note.trim() };
    void mutation.run(path, record ? 'PUT' : 'POST', body, result => onSaved(decodeRevision(result)));
  };

  return <div className="editor-writing">
    <form className="editor-json-form" onSubmit={event => { event.preventDefault(); save(); }}>
      <div className="editor-region-heading"><h3>Рабочий JSON</h3>
        <Button variant="quiet" onClick={() => downloadText(`draft-${kind}.json`, source)}><Download aria-hidden="true" />Скачать ввод</Button>
      </div>
      <p className="muted" id="editor-json-help">Ответы задаются строками. Автор, рецензент и редакция назначаются сервером. LaTeX в JSON требует удвоенного обратного слеша.</p>
      {!editable && <p className="editor-readonly">Эта редакция доступна для чтения. Для правок создайте новую редакцию.</p>}
      <label htmlFor="editor-json">Данные материала</label>
      <textarea id="editor-json" ref={field} className="editor-json" value={source} rows={22} spellCheck={false} autoComplete="off"
        readOnly={!editable || mutation.locked} aria-invalid={Boolean(problem)} aria-describedby={`editor-json-help${problem ? ' editor-json-error' : ''}`}
        onChange={event => {
          request.current?.abort(); setPreviewLoading(false); setPreview(null); setPreviewError(null);
          setSource(event.target.value); setProblem(null);
        }} />
      {problem && <p className="editor-inline-error" id="editor-json-error" role="alert">{problem}</p>}
      <div className="row-actions editor-json-tools">
        <Button onClick={showPreview} disabled={previewLoading}><Eye aria-hidden="true" />Проверить и показать</Button>
        {editable && <Button variant="quiet" disabled={mutation.locked} onClick={() => { const value = parsed(); if (value) setSource(JSON.stringify(value, null, 2)); }}><Braces aria-hidden="true" />Форматировать</Button>}
      </div>
      {editable && <>
        <div className="editor-field"><label htmlFor="editor-change-note">Что изменено</label>
          <textarea id="editor-change-note" ref={noteField} value={note} rows={3} required minLength={5} maxLength={2000} readOnly={mutation.locked}
            aria-invalid={Boolean(noteProblem)} aria-describedby={noteProblem ? 'editor-note-error' : undefined}
            onChange={event => { setNote(event.target.value); setNoteProblem(null); }} />
          {noteProblem && <p className="editor-inline-error" id="editor-note-error" role="alert">{noteProblem}</p>}
        </div>
        <div className="row-actions"><Button variant="primary" type="submit" disabled={mutation.locked}><Save aria-hidden="true" />{record ? 'Сохранить черновик' : 'Создать черновик'}</Button>
          <span className="muted">{dirty ? 'Есть несохранённый ввод' : record ? 'Сохранённая редакция' : 'Заполните поля JSON'}</span>
        </div>
      </>}
    </form>
    <aside className="editor-preview" aria-labelledby="editor-preview-heading">
      <h3 id="editor-preview-heading">Мобильный вид</h3>
      {previewLoading && <Loading label="Проверяем структуру и формулы" />}
      {previewError && <EditorFailure error={previewError} retry={showPreview} />}
      {!preview && !previewLoading && !previewError && <div className="editor-preview-empty"><p>Проверьте JSON, чтобы увидеть материал в узкой компоновке.</p><p className="muted">После правок предпросмотр строится заново.</p></div>}
      {preview && <><ContentPreview preview={preview} /><p className="editor-preview-note">{preview.message}</p></>}
    </aside>
  </div>;
}
