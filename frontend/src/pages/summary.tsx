import { CheckCircle2, SkipForward, XCircle } from 'lucide-react';
import { useSession } from '../learning/use-session';
import { ActionLink, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { SummaryStats } from '../components/summary-stats';
import { TaskContent } from '../components/task-content';
import { RichText } from '../components/math';
import { formatDate } from '../utils/format';
import { sessionPath } from '../app/router';

export default function SummaryPage({ id }: { id: string }) {
  const state = useSession(id);
  const { record } = state;
  if (state.loading && !record) return <><PageHeading title="Итог занятия" /><Loading label="Загружаем итог" /></>;
  if (!record) return <><PageHeading title="Итог недоступен" /><ErrorNotice message={state.error ?? 'Занятие не найдено.'} retry={() => void state.controller.refresh()} /></>;
  if (record.session.status !== 'completed') return <><PageHeading title="Занятие ещё не завершено" description="Итог появится после подтверждения сервера." /><ActionLink href={sessionPath(id)} primary>Вернуться к занятию</ActionLink></>;
  const session = record.session;
  const mistakes = session.attempts.filter((attempt) => attempt.first_attempt && (!attempt.correct || attempt.skipped));
  return <>
    <PageHeading title="Занятие завершено" description={session.completed_at ? formatDate(session.completed_at) : undefined} />
    {state.error && <ErrorNotice message={state.error} retry={() => void state.controller.refresh()} />}
    <section className="worksheet summary-sheet"><h2>Что получилось</h2><SummaryStats summary={session.summary} /><p className="muted">Отвечено на {session.summary.answered} из {session.summary.total} задач. Это учебный результат, не прогноз балла ЕГЭ.</p></section>
    <section className="next-step"><div><h2>{mistakes.length ? 'Сначала разберите ошибки' : 'Закрепите на новых задачах'}</h2><p>{mistakes.length ? 'Первая попытка остаётся в истории. Исправление помогает учиться, но не превращает её в самостоятельный успех.' : 'Один верный ответ не означает освоение номера. Продолжайте на других экземплярах.'}</p></div><ActionLink href={mistakes.length ? '/review' : '/practice'} primary>{mistakes.length ? 'К журналу ошибок' : 'Выбрать новую серию'}</ActionLink></section>
    <section className="session-review"><h2>Все задачи занятия</h2>{session.tasks.map((task, index) => {
      const attempts = session.attempts.filter((attempt) => attempt.task_id === task.id);
      const first = attempts[0];
      const last = attempts.at(-1);
      const help = session.help[task.id]?.solution;
      const steps = last?.solution ?? help?.steps;
      const answer = last?.expected_answer ?? help?.answer;
      const Icon = last?.skipped ? SkipForward : last?.correct ? CheckCircle2 : XCircle;
      return <details className="result-row" key={task.id}><summary><span className="result-row__index">{index + 1}</span><span><strong>№ {task.slot}. {task.title}</strong><small>{!last ? 'Не отправлено' : last.skipped ? 'Пропущено' : last.correct ? last.first_attempt ? 'Верно' : 'Исправлено' : 'Есть ошибка'}</small></span><Icon aria-hidden="true" /></summary>
        <div className="result-row__content"><TaskContent task={task} />
          <dl className="answer-comparison"><div><dt>Первый ответ</dt><dd>{first ? first.skipped ? 'Пропуск' : first.raw_answer : 'Не отправлен'}</dd></div>{answer && <div><dt>Эталон</dt><dd>{answer}</dd></div>}</dl>
          {attempts.length > 1 && <p>Повторных ответов: {attempts.length - 1}. Последний: «{last?.raw_answer}».</p>}
          {steps && <ol className="solution-steps">{steps.map((step, stepIndex) => <li key={stepIndex}><RichText text={step} /></li>)}</ol>}
          {!steps && <p className="muted">Ответ не проверялся, поэтому сервер не выдавал решение этой задачи.</p>}
          <a className="text-link" href={`#/topics/${task.slot}`}>Теория по номеру {task.slot}</a>
        </div></details>;
    })}</section>
  </>;
}
