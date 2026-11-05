import { useCallback, useState } from 'react';
import { ArrowLeft, ArrowRight, Plus, Search } from 'lucide-react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, Loading } from '../components/ui';
import type { EditorApi, Filters } from './api';
import { EditorFailure } from './feedback';
import type { BaseItem, BaseList, Kind, RevisionList, RevisionSummary, Status } from './types';
import { kindLabels, statusLabels } from './types';
import { useEditorResource } from './use-resource';

type Result = { type: 'revisions'; value: RevisionList } | { type: 'base'; value: BaseList };
type Props = {
  api: EditorApi; refresh: number; locked: boolean; activeId?: string; chosen: string[];
  onOpen: (record: RevisionSummary) => void; onBase: (item: BaseItem) => void;
  onNew: (kind: Kind) => void; onChoose: (record: RevisionSummary, checked: boolean) => void;
};

export function Catalogue({ api, refresh, locked, activeId, chosen, onOpen, onBase, onNew, onChoose }: Props) {
  const [mode, setMode] = useState<'revisions' | 'base'>('revisions');
  const [query, setQuery] = useState('');
  /* viora-allow: url-state Filters belong to this in-memory worksheet; shared routing owns navigation. */
  const [filters, setFilters] = useState<Filters>({ kind: 'task', status: '', q: '', offset: 0 });
  const load = useCallback(async (signal: AbortSignal): Promise<Result> => mode === 'revisions'
    ? { type: 'revisions', value: await api.revisions(filters, signal) }
    : { type: 'base', value: await api.base(filters, signal) }, [api, mode, filters]);
  const resource = useEditorResource(load, `${mode}:${JSON.stringify(filters)}:${refresh}`);
  const size = mode === 'revisions' ? 10 : 30;
  const total = resource.data?.value.total ?? 0;
  const filtered = Boolean(filters.q || (mode === 'revisions' && filters.status));

  return <section className="editor-catalogue" aria-labelledby="editor-catalogue-heading">
    <div className="editor-region-heading"><h2 id="editor-catalogue-heading">Каталог</h2>
      <Button onClick={() => onNew(filters.kind)} disabled={locked} aria-label={`Создать материал: ${kindLabels[filters.kind]}`}><Plus aria-hidden="true" />Создать</Button>
    </div>
    <div className="editor-mode" role="group" aria-label="Источник материалов">
      <Button aria-pressed={mode === 'revisions'} onClick={() => { setMode('revisions'); setFilters({ ...filters, offset: 0 }); }}>Редакции</Button>
      <Button aria-pressed={mode === 'base'} onClick={() => { setMode('base'); setFilters({ ...filters, offset: 0 }); }}>Исходный банк</Button>
    </div>
    <div className="editor-field"><label htmlFor="editor-kind">Тип материала</label>
      <select id="editor-kind" value={filters.kind} onChange={event => setFilters({ ...filters, kind: event.target.value as Kind, offset: 0 })}>
        {Object.entries(kindLabels).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
      </select>
    </div>
    {mode === 'revisions' && <div className="editor-field"><label htmlFor="editor-filter-status">Статус</label>
      <select id="editor-filter-status" value={filters.status} onChange={event => setFilters({ ...filters, status: event.target.value as Status | '', offset: 0 })}>
        <option value="">Все статусы</option>{Object.entries(statusLabels).map(([status, label]) => <option key={status} value={status}>{label}</option>)}
      </select>
    </div>}
    <form className="editor-search" onSubmit={event => { event.preventDefault(); setFilters({ ...filters, q: query.trim(), offset: 0 }); }}>
      <label htmlFor="editor-search">Название или стабильный ID</label>
      <div><input id="editor-search" type="search" value={query} onChange={event => setQuery(event.target.value)} maxLength={200} autoComplete="off" enterKeyHint="search" />
        <Button type="submit" aria-label="Найти материал"><Search aria-hidden="true" /></Button></div>
    </form>
    {resource.loading && <Loading label="Загружаем каталог редактора" />}
    {resource.error && <EditorFailure error={resource.error} retry={resource.retry} />}
    {resource.data && <>
      <div className="editor-count"><p role="status">Найдено: {total.toLocaleString('ru-RU')}</p>
        {filtered && <Button variant="quiet" onClick={() => { setQuery(''); setFilters({ ...filters, q: '', status: '', offset: 0 }); }}>Сбросить</Button>}
      </div>
      {resource.data.value.items.length === 0 && <div className="editor-empty">
        <h3>{filtered ? 'Нет совпадений' : mode === 'revisions' ? 'Редакций пока нет' : 'Исходных материалов нет'}</h3>
        <p>{filtered ? 'Измените запрос или сбросьте фильтры.' : mode === 'revisions'
          ? 'Создайте материал или откройте исходный банк, чтобы подготовить первую редакцию.'
          : 'Шаблоны создаются по зарегистрированным серверным генераторам. Остальные материалы загружаются из банка.'}</p>
      </div>}
      <ul className="editor-catalogue-list">
        {resource.data.type === 'revisions' ? resource.data.value.items.map(item => <li key={item.id}>
          <button type="button" className="editor-catalogue-item" aria-pressed={activeId === item.id} disabled={locked} onClick={() => onOpen(item)}>
            <strong>{item.title}</strong><span>{statusLabels[item.status]} · версия {item.version}</span><code>{item.content_id}</code>
          </button>
          <label className="editor-check editor-package-check"><input type="checkbox" checked={chosen.includes(item.id)} disabled={locked}
            onChange={event => onChoose(item, event.target.checked)} /><span>В пакет<span className="sr-only">: {item.title}, версия {item.version}</span></span></label>
        </li>) : resource.data.value.items.map(item => <li key={item.content_id}>
          <button type="button" className="editor-catalogue-item" disabled={locked} onClick={() => onBase(item)}>
            <strong>{item.title}</strong><span>Исходная редакция {item.content_revision}</span><code>{item.content_id}</code>
          </button>
        </li>)}
      </ul>
      {total > size && <div className="editor-pagination" aria-label="Страницы каталога">
        <Button disabled={resource.loading || filters.offset === 0} onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - size) })} aria-label="Предыдущая страница"><ArrowLeft aria-hidden="true" /></Button>
        <span>{Math.floor(filters.offset / size) + 1} из {Math.ceil(total / size)}</span>
        <Button disabled={resource.loading || filters.offset + size >= total || filters.offset + size > 100_000} onClick={() => setFilters({ ...filters, offset: filters.offset + size })} aria-label="Следующая страница"><ArrowRight aria-hidden="true" /></Button>
      </div>}
    </>}
  </section>;
}
