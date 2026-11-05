import { useEffect, useState } from 'react';
import { Download, Upload, X } from 'lucide-react';
import { Button } from '../components/ui';
import type { EditorApi } from './api';
import { decodeBatch, EditorError, errorText } from './adapters';
import { downloadJson, downloadText, parseImport } from './drafts';
import { EditorFailure } from './feedback';
import { statusLabels } from './types';
import type { EditorMeta, Revision, RevisionSummary } from './types';
import type { EditorMutation } from './use-mutation';

export function ImportPanel({ meta, mutation, onImported, onDirty }: {
  meta: EditorMeta; mutation: EditorMutation; onImported: (items: Revision[]) => void; onDirty: (dirty: boolean) => void;
}) {
  const [source, setSource] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const locked = mutation.locked || reading;
  useEffect(() => { onDirty(source.length > 0 || reading); }, [source, reading, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);
  return <details className="editor-disclosure editor-import"><summary>Импорт JSON</summary>
    <p>Пакет содержит <code>version: "1"</code> и массив <code>items</code> с полями <code>kind</code>, <code>payload</code>, <code>change_note</code>. До {meta.max_import_items} новых материалов, весь запрос до {Math.floor(meta.max_request_bytes / 1024)} КиБ.</p>
    <p className="muted">Сервер проверяет весь пакет до записи и возвращает ошибки с номерами строк. Для изменения существующего ID откройте его редакцию в каталоге.</p>
    <div className="editor-field"><label htmlFor="editor-import-file">Файл JSON</label>
      <input type="file" id="editor-import-file" accept=".json,application/json" disabled={locked} onChange={event => {
        const file = event.target.files?.[0]; event.target.value = '';
        if (!file) return;
        if (file.size > meta.max_request_bytes) { setError('Файл превышает размер запроса. Разделите пакет.'); return; }
        setReading(true); setError(null);
        void file.text().then(text => setSource(text)).catch(() => setError('Не удалось прочитать файл. Вставьте JSON в поле ниже.')).finally(() => setReading(false));
      }} />
    </div>
    <form onSubmit={event => {
      event.preventDefault();
      try {
        const body = parseImport(source, meta.max_request_bytes, meta.max_import_items); setError(null);
        void mutation.run('/import', 'POST', body, value => { const items = decodeBatch(value); setSource(''); onImported(items); });
      } catch (failure) { setError(failure instanceof Error ? failure.message : 'Проверьте пакет JSON.'); }
    }}>
      <div className="editor-field"><label htmlFor="editor-import-json">Содержимое пакета</label>
        <textarea id="editor-import-json" className="editor-json" value={source} onChange={event => { setSource(event.target.value); setError(null); }} rows={8} spellCheck={false} required readOnly={locked}
          aria-invalid={Boolean(error)} aria-describedby={error ? 'editor-import-error' : undefined} />
        {error && <p id="editor-import-error" className="editor-inline-error" role="alert">{error}</p>}
      </div>
      <div className="row-actions"><Button type="submit" disabled={locked}><Upload aria-hidden="true" />Импортировать пакет</Button>
        <Button variant="quiet" disabled={!source} onClick={() => downloadText('editor-import.json', source)}><Download aria-hidden="true" />Скачать ввод</Button></div>
      {reading && <p role="status">Читаем выбранный файл…</p>}
    </form>
  </details>;
}

export function PublicationPackage({ api, items, mutation, onRemove, onPublished }: {
  api: EditorApi; items: RevisionSummary[]; mutation: EditorMutation;
  onRemove: (record: RevisionSummary) => void; onPublished: (records: Revision[]) => void;
}) {
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<EditorError | null>(null);
  const publishable = items.length > 0 && items.every(item => item.capabilities.includes('publish'));
  const exportItems = async () => {
    setExporting(true); setError(null);
    try { downloadJson('editor-content.json', await api.export(items.map(item => item.id))); }
    catch (failure) { setError(failure instanceof EditorError ? failure : new EditorError(errorText(failure))); }
    finally { setExporting(false); }
  };
  return <section className="editor-package" aria-labelledby="editor-package-heading">
    <h2 id="editor-package-heading">Выбранный пакет ({items.length})</h2>
    <p className="muted">Профиль, задачи и уроки можно опубликовать одним согласованным пакетом. Сервер проверит все связи и версии атомарно.</p>
    <ul>{items.map(item => <li key={item.id}><div><strong>{item.title}</strong><p>{statusLabels[item.status]} · версия {item.version}, CAS {item.revision}</p><code>{item.content_id}</code></div>
      <Button variant="quiet" disabled={mutation.locked} onClick={() => onRemove(item)} aria-label={`Убрать из пакета: ${item.title}`}><X aria-hidden="true" /></Button>
    </li>)}</ul>
    {error && <EditorFailure error={error} retry={() => void exportItems()} />}
    <Button onClick={() => void exportItems()} disabled={exporting || items.length === 0 || items.length > 10}><Download aria-hidden="true" />{exporting ? 'Готовим экспорт…' : 'Экспортировать JSON'}</Button>
    {items.length > 10 && <p className="muted">За один экспорт доступно до 10 материалов.</p>}
    {publishable ? <form className="editor-package-publish" onSubmit={event => {
      event.preventDefault();
      if (note.trim().length < 5) { setProblem('Опишите публикацию минимум пятью символами.'); return; }
      void mutation.run('/publish', 'POST', { note: note.trim(), items: items.map(item => ({ id: item.id, expected_revision: item.revision })) }, value => onPublished(decodeBatch(value)));
    }}>
      <div className="editor-field"><label htmlFor="editor-package-note">Причина публикации пакета</label>
        <textarea id="editor-package-note" value={note} onChange={event => { setNote(event.target.value); setProblem(null); }} rows={3} minLength={5} maxLength={2000} required disabled={mutation.locked}
          aria-invalid={Boolean(problem)} aria-describedby={problem ? 'editor-package-error' : undefined} />
        {problem && <p id="editor-package-error" className="editor-inline-error" role="alert">{problem}</p>}
      </div>
      <Button type="submit" variant="primary" disabled={mutation.locked}>Опубликовать весь пакет</Button>
    </form> : <p className="editor-readonly">Публикация доступна администратору, когда каждый выбранный материал прошёл независимую проверку.</p>}
  </section>;
}
