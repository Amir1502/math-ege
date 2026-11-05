import { useRef, type KeyboardEvent } from 'react';
import { navigate, useRoute } from '../app/router';
import { ActionLink, EmptyState, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { useLearningDashboard, useLearningIdentity, useSavedAnnotations } from '../extras/hooks';
import { LearningPagination } from '../extras/pagination';
import { ReviewQueue, ReviewTask } from '../extras/review-panels';
import { journalForFavourite, orderedReviews, pageOffset } from '../extras/view-models';
import type { DashboardCollection } from '../extras/types';
import '../styles/extras.css';

const tabs = [
  { id: 'errors', label: 'Ошибки', collection: 'journal' },
  { id: 'repeat', label: 'Повторение', collection: 'reviews' },
  { id: 'favourites', label: 'Избранное', collection: 'favourites' },
] as const;
type Tab = typeof tabs[number]['id'];

function reviewPath(tab: Tab, filter: string, offset = 0) {
  const query = new URLSearchParams({ tab });
  if (filter !== 'all') query.set('slot', filter);
  if (offset) query.set('offset', String(offset));
  return `/review?${query}`;
}

export default function ReviewPage() {
  useLearningIdentity();
  const route = useRoute();
  const activeTab = tabs.find((tab) => tab.id === route.query.get('tab')) ?? tabs[0];
  const filter = /^([1-9]|1[0-3])$/.test(route.query.get('slot') ?? '') ? route.query.get('slot')! : 'all';
  const learning = useLearningDashboard(pageOffset(route.query.get('offset')));
  const annotations = useSavedAnnotations();
  const tabButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const data = learning.data;
  const matches = (number: number | null) => filter === 'all' || number === Number(filter);
  const journal = data?.journal.filter((entry) => matches(entry.task.slot)) ?? [];
  const favourites = data?.favourites.filter((item) => matches(item.task.slot)) ?? [];
  const reviews = orderedReviews(data?.reviews.filter((review) => matches(review.slot)) ?? []);
  const count = activeTab.id === 'errors' ? journal.length : activeTab.id === 'repeat' ? reviews.length : favourites.length;
  const numbers = [...new Set(data ? activeTab.id === 'errors' ? data.journal.map((entry) => entry.task.slot)
    : activeTab.id === 'repeat' ? data.reviews.flatMap((review) => review.slot === null ? [] : [review.slot])
      : data.favourites.map((item) => item.task.slot) : [])].sort((a, b) => a - b);

  const selectTab = (tab: Tab) => navigate(reviewPath(tab, filter));
  const tabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(tabs[next].id);
    tabButtons.current[next]?.focus();
  };

  return <>
    <PageHeading title="Повторение" description="Разберите ошибку, выберите причину и вернитесь к навыку через время." />
    <div className="learning-tabs" role="tablist" aria-label="Разделы повторения">{tabs.map((tab, index) => <button
      type="button" role="tab" key={tab.id} id={`review-tab-${tab.id}`} aria-selected={activeTab.id === tab.id}
      aria-controls={`review-panel-${tab.id}`} tabIndex={activeTab.id === tab.id ? 0 : -1}
      ref={(element) => { tabButtons.current[index] = element; }}
      onClick={() => selectTab(tab.id)} onKeyDown={(event) => tabKey(event, index)}
    >{tab.label}</button>)}</div>
    {learning.loading && !data && <Loading label="Загружаем учебные записи" />}
    {learning.error && <ErrorNotice message={learning.error} retry={learning.retry} />}
    {annotations.loading && !annotations.data && <Loading label="Загружаем ваши отметки" />}
    {annotations.error && <ErrorNotice message={`Не удалось загрузить отметки. ${annotations.error}`} retry={annotations.retry} />}
    {data && <div className="filter-toolbar learning-review-filter">
      <label htmlFor="mistake-filter">Номер</label>
      <select id="mistake-filter" value={filter} onChange={(event) => navigate(reviewPath(activeTab.id, event.target.value, data.pagination.offset))}>
        <option value="all">Все номера</option>
        {[...new Set([...numbers, ...(filter === 'all' ? [] : [Number(filter)])])].sort((a, b) => a - b).map((number) => <option key={number} value={number}>№ {number}</option>)}
      </select>
      <span role="status">{learning.loading ? 'Обновляем…' : `Записей на странице: ${count}`}</span>
    </div>}
    {tabs.map((tab) => <section key={tab.id} id={`review-panel-${tab.id}`} role="tabpanel" aria-labelledby={`review-tab-${tab.id}`} hidden={tab.id !== activeTab.id} tabIndex={0} className="learning-tab-panel">
      {tab.id === activeTab.id && <>
        <h2 className="sr-only">{tab.label}</h2>
        {!data && !learning.loading && !learning.error && <><EmptyState title="Начните с первой задачи" action={<ActionLink href="/practice" primary>Перейти к практике</ActionLink>}>Здесь появятся ошибки, ваши отметки и расписание повторений. Для первой практики регистрация не нужна.</EmptyState><GuestNote /></>}
        {data && <>
          {tab.id === 'errors' && <>
            <p className="scope-note">Неверные самостоятельные ответы, пропуски и ваши отметки. Исправление сохраняет исходную историю. Диагностика и пробник попадают сюда только после открытия результатов.</p>
            {journal.length ? <section className="mistake-ledger" aria-label="Задачи для разбора">{journal.map((entry) => <ReviewTask key={entry.id} item={entry} entry={entry} dashboard={data} annotations={annotations.data} />)}</section>
              : <EmptyState title={filter === 'all' ? 'Журнал пока пуст' : 'На этой странице нет записей по номеру'} action={<ActionLink href={filter === 'all' ? '/practice' : reviewPath(tab.id, 'all', data.pagination.offset)}>{filter === 'all' ? 'Перейти к практике' : 'Показать все номера'}</ActionLink>}>Можно добавить задачу вручную или отметить «Не понимаю тему». Причина ошибки не назначается автоматически.</EmptyState>}
          </>}
          {tab.id === 'repeat' && <>
            <p className="scope-note">Интервалы: 1, 3, 7, 14 и 30&nbsp;дней. Засчитывается первый самостоятельный ответ на другом экземпляре того же семейства. Раннее решение не переносит срок; ошибка или помощь возвращает начальный интервал.</p>
            {reviews.length ? <ReviewQueue reviews={reviews} dashboard={data} /> : <EmptyState title={filter === 'all' ? 'Повторений пока нет' : 'На этой странице нет повторений по номеру'} action={<ActionLink href={filter === 'all' ? '/practice' : reviewPath(tab.id, 'all', data.pagination.offset)}>{filter === 'all' ? 'Решить новые задачи' : 'Показать все номера'}</ActionLink>}>После ошибки или пропуска здесь появится срок следующей проверки навыка. День без занятий не обнуляет ваши результаты.</EmptyState>}
          </>}
          {tab.id === 'favourites' && <>
            <p className="scope-note">Сохранённые условия для возвращения к задаче. Добавление в избранное само по себе не меняет освоение навыка.</p>
            {favourites.length ? <section className="mistake-ledger" aria-label="Избранные задачи">{favourites.map((item) => <ReviewTask key={`${item.session_id}:${item.task.id}`} item={item} entry={journalForFavourite(data, item)} dashboard={data} annotations={annotations.data} />)}</section>
              : <EmptyState title={filter === 'all' ? 'В избранном пока пусто' : 'На этой странице нет избранных задач по номеру'} action={<ActionLink href={filter === 'all' ? '/practice' : reviewPath(tab.id, 'all', data.pagination.offset)}>{filter === 'all' ? 'Перейти к практике' : 'Показать все номера'}</ActionLink>}>Отметьте задачу кнопкой «В избранное» во время разбора, чтобы быстро найти её здесь.</EmptyState>}
          </>}
          <LearningPagination dashboard={data} collection={tab.collection as DashboardCollection} href={(offset) => reviewPath(tab.id, filter, offset)} />
        </>}
      </>}
    </section>)}
  </>;
}
