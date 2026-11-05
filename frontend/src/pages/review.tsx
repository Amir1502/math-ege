import { useState } from 'react';
import { BookOpen, ArrowRight } from 'lucide-react';
import { progressResource, useResource } from '../app/resources';
import { ActionLink, EmptyState, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { TaskContent } from '../components/task-content';
import { RichText } from '../components/math';
import { formatDate } from '../utils/format';

export default function ReviewPage() {
  const progress = useResource(progressResource, true);
  const [filter, setFilter] = useState('all');
  const mistakes = progress.data?.mistakes ?? [];
  const numbers = [...new Set(mistakes.map((item) => item.task.slot))].sort((a, b) => a - b);
  const filtered = filter === 'all' ? mistakes : mistakes.filter((item) => item.task.slot === Number(filter));
  return <>
    <PageHeading title="Повторение" description="Журнал ошибок: понять ход, затем решить новый аналог." />
    <p className="scope-note">Сейчас здесь ошибки и пропуски. Интервальное повторение по расписанию появится на следующем этапе.</p>
    {progress.loading && <Loading label="Загружаем журнал ошибок" />}
    {progress.error && <ErrorNotice message={progress.error} retry={progress.retry} />}
    {!progress.loading && !progress.error && <>
      {!progress.data && <GuestNote />}
      {mistakes.length === 0 ? <EmptyState title="Журнал пока пуст" action={<ActionLink href="/practice" primary>Перейти к практике</ActionLink>}>После занятия здесь появятся неверные самостоятельные ответы и пропуски. Открытие решения само по себе не считается успехом.</EmptyState> : <>
        <div className="filter-toolbar"><label htmlFor="mistake-filter">Номер</label><select id="mistake-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">Все номера</option>{numbers.map((number) => <option key={number} value={number}>№ {number}</option>)}</select><span>{filtered.length} записей</span></div>
        <section className="mistake-ledger" aria-label="Задачи для разбора">{filtered.map(({ task, attempt }) => <details className="mistake-row" key={attempt.id}><summary><span className="topic-row__number">{String(task.slot).padStart(2, '0')}</span><span><strong>{task.title}</strong><small>{attempt.skipped ? 'Пропуск' : `Ваш ответ: ${attempt.raw_answer}`} · {formatDate(attempt.created_at)}</small></span><BookOpen aria-hidden="true" /></summary>
          <div className="mistake-row__body"><TaskContent task={task} /><dl className="answer-comparison"><div><dt>Ваш первый ответ</dt><dd>{attempt.skipped ? 'Пропуск' : attempt.raw_answer}</dd></div><div><dt>Эталон</dt><dd>{attempt.expected_answer}</dd></div></dl><h2>Разбор</h2><ol className="solution-steps">{attempt.solution.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol><div className="row-actions"><a className="button button--secondary" href={`#/topics/${task.slot}`}><BookOpen aria-hidden="true" />Открыть теорию</a><a className="button button--secondary" href={`#/practice?slots=${task.slot}`}>Решить новый аналог<ArrowRight aria-hidden="true" /></a></div><p className="microcopy">Новая серия по тому же номеру, если в демобанке остались невстречавшиеся экземпляры. Тот же тип не гарантируется.</p></div>
        </details>)}</section>
      </>}
    </>}
  </>;
}
