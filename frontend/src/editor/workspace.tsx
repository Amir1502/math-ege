import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '../components/ui';
import { createEditorApi } from './api';
import { Catalogue } from './catalogue';
import { EditorFailure } from './feedback';
import { ProfileReference } from './profile-reference';
import { BaseRevisionPanel, NewRevisionPanel, RevisionPanel } from './revision-panel';
import { ImportPanel, PublicationPackage } from './transfer';
import { useEditorMutation } from './use-mutation';
import { statusLabels } from './types';
import type { BaseItem, EditorMeta, Kind, Revision, RevisionSummary } from './types';

type Selection = { type: 'revision'; id: string } | { type: 'new'; kind: Kind; sequence: number } | { type: 'base'; item: BaseItem };

export function EditorWorkspace({ meta }: { meta: EditorMeta }) {
  const api = useMemo(() => createEditorApi(meta.actor.id), [meta.actor.id]);
  const mutation = useEditorMutation(meta.actor.id, meta.max_request_bytes);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [importDirty, setImportDirty] = useState(false);
  const [items, setItems] = useState<RevisionSummary[]>([]);
  const [notice, setNotice] = useState('');
  const onDirty = useCallback((value: boolean) => setDirty(value), []);

  useEffect(() => {
    if (!dirty && !importDirty && !mutation.locked) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const navigate = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest('a') : null;
      if (!link || link.target === '_blank' || link.hasAttribute('download') || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (link.hash.startsWith('#/') && link.hash !== window.location.hash && !window.confirm('В редакторе есть несохранённый ввод или запрос без ответа. Покинуть страницу?')) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', navigate, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', navigate, true); };
  }, [dirty, importDirty, mutation.locked]);

  const select = (next: Selection) => {
    if (mutation.locked) return;
    if (selection?.type === 'revision' && next.type === 'revision' && selection.id === next.id) return;
    if (dirty && !window.confirm('Переключить материал и заменить несохранённый ввод? Сначала его можно скачать.')) return;
    setDirty(false); setSelection(next);
  };
  const updated = (record: Revision) => {
    setItems(current => current.map(item => item.id === record.id ? record : item));
    setDirty(false); setSelection({ type: 'revision', id: record.id }); setRefresh(value => value + 1);
    setNotice(`«${record.title}»: ${statusLabels[record.status].toLocaleLowerCase('ru-RU')}, версия ${record.version}.`);
  };
  const choose = (record: RevisionSummary, checked: boolean) => {
    if (checked && items.length >= 1000 && !items.some(item => item.id === record.id)) { setNotice('В пакете уже 1000 материалов. Опубликуйте его перед добавлением следующего.'); return; }
    setItems(current => checked ? current.some(item => item.id === record.id) ? current : [...current, record]
      : current.filter(item => item.id !== record.id));
  };
  const common = { api, meta, mutation, dirty, onDirty, onUpdated: updated, onNotice: setNotice };

  return <div className="editor-workspace">
    <p className="editor-actor">{meta.actor.role === 'admin' ? 'Администратор' : 'Методист'} · <code>{meta.actor.id}</code></p>
    <ProfileReference profile={meta.profile} />
    <div className="editor-operation-status" role="status" aria-live="polite">
      {mutation.busy ? 'Сервер выполняет запрос. Дождитесь результата…' : mutation.uncertain
        ? 'Результат запроса неизвестен. Повторите его с тем же телом и ключом; остальные изменения временно заблокированы.' : notice}
    </div>
    {mutation.error && <EditorFailure error={mutation.error} retry={mutation.uncertain && !mutation.busy ? () => void mutation.retry() : undefined} />}
    <div className="editor-layout">
      <Catalogue api={api} refresh={refresh} locked={mutation.locked} activeId={selection?.type === 'revision' ? selection.id : undefined}
        chosen={items.map(item => item.id)} onOpen={record => select({ type: 'revision', id: record.id })} onBase={item => select({ type: 'base', item })}
        onNew={kind => select({ type: 'new', kind, sequence: selection?.type === 'new' ? selection.sequence + 1 : 0 })} onChoose={choose} />
      {selection?.type === 'revision' ? <RevisionPanel key={selection.id} id={selection.id} {...common} />
        : selection?.type === 'new' ? <NewRevisionPanel key={`new:${selection.kind}:${selection.sequence}`} kind={selection.kind} {...common} />
          : selection?.type === 'base' ? <BaseRevisionPanel key={`base:${selection.item.kind}:${selection.item.content_id}`} item={selection.item} {...common} />
            : <section className="editor-document editor-welcome" aria-labelledby="editor-welcome-heading">
              <h2 id="editor-welcome-heading">Рабочий лист редактора</h2>
              <p>Выберите материал в каталоге или создайте задачу. Здесь будут JSON, мобильный вид и история предметной проверки.</p>
              <Button variant="primary" onClick={() => select({ type: 'new', kind: 'task', sequence: 0 })}>Создать задачу</Button>
              <p className="editor-welcome-note">Черновик → предметная проверка → готово к публикации → опубликовано. Автор и рецензент входят под разными аккаунтами; публикацию выполняет администратор.</p>
            </section>}
    </div>
    {items.length > 0 && <PublicationPackage api={api} items={items} mutation={mutation} onRemove={item => choose(item, false)} onPublished={records => {
      setItems([]); setRefresh(value => value + 1); setNotice(`Опубликован согласованный пакет: ${records.length} материалов.`);
      if (selection?.type === 'revision' && records.some(record => record.id === selection.id)) setSelection(null);
    }} />}
    <ImportPanel meta={meta} mutation={mutation} onDirty={setImportDirty} onImported={records => {
      setRefresh(value => value + 1); setNotice(`Созданы черновики из пакета: ${records.length}. Они ожидают предметной проверки.`);
    }} />
  </div>;
}
