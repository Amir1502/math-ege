import { useEffect, useState } from 'react';
import { ArrowRight, RotateCcw } from 'lucide-react';
import { Button } from '../../components/ui';
import { TaskContent } from '../../components/task-content';
import { formatDate } from '../../utils/format';
import type { OfflineRuntime } from '../practice';
import { OfflineFailure, OfflineHeading, OfflineLoading } from './shared';
import type { Course, Failure, PracticeProgress } from './shared';
import { failure } from './operations';

export default function ProgressPage({ course, runtime }: { course: Course; runtime: OfflineRuntime }) {
  const [progress, setProgress] = useState<PracticeProgress | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const [request, setRequest] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let stopped = false;
    void runtime.progress().then((value) => {
      if (!stopped) { setProgress(value); setError(null); setLoading(false); }
    }).catch((caught: unknown) => {
      if (!stopped) { setError(failure(caught)); setLoading(false); }
    });
    return () => { stopped = true; };
  }, [runtime, request]);
  const retry = () => { setLoading(true); setError(null); setRequest((value) => value + 1); };
  return <>
    <OfflineHeading title="Прогресс">Фактические ответы на этом устройстве. Без оценки освоения и прогноза балла ЕГЭ.</OfflineHeading>
    {loading && <OfflineLoading label="Читаем локальную историю" />}
    {error && <OfflineFailure error={error} title="Не удалось прочитать прогресс" retry={retry} />}
    {progress && <>
      <section className="worksheet offline-progress-sheet" aria-labelledby="progress-counters-title">
        <div className="offline-progress-number"><h2 id="progress-counters-title">Верно с первой самостоятельной попытки</h2>
          <p className="offline-big-number">{progress.independent_correct}<span> из {progress.independent_total}</span></p>
          <p className="muted">Это счётчик ответов, не доля освоенного курса. Помощь, повторы и исправления не заменяют первый результат.</p>
        </div>
        <dl className="stat-ledger offline-ledger"><div><dt>С помощью</dt><dd>{progress.assisted_total}</dd></div><div><dt>Исправления</dt><dd>{progress.corrections_total}</dd></div><div><dt>Пропуски</dt><dd>{progress.skipped_total}</dd></div></dl>
      </section>
      {progress.active_session_id && <div className="notice"><div><strong>Занятие не завершено</strong><p>Можно продолжить с сохранённой задачи и черновика.</p><a className="text-link" href={`#/session/${encodeURIComponent(progress.active_session_id)}`}>Продолжить занятие<ArrowRight aria-hidden="true" /></a></div></div>}
      {progress.recent_sessions.length === 0 && <section className="empty-state"><h2>Истории занятий пока нет</h2><p>Начните с пяти задач. Здесь появятся реальные ответы, помощь и итог серии.</p><a className="button button--primary" href="#/practice">К практике<ArrowRight aria-hidden="true" /></a></section>}
      <section className="offline-progress-positions"><h2>Ответы по номерам</h2><p className="muted">Первые самостоятельные ответы. Верный ответ ещё не означает «освоено».</p>
        <ul className="offline-slot-ledger">{course.profile.slots.map((slot) => {
          const row = progress.slots.find((item) => item.number === slot.number);
          return <li key={slot.number}><a href={`#/lessons?slot=${slot.number}`}><span className="slot-number">{slot.number}</span><span>{slot.title}</span><span className="offline-slot-count">{row?.correct ?? 0} / {row?.attempts ?? 0}<span className="sr-only"> верных из первых самостоятельных ответов</span></span></a></li>;
        })}</ul>
      </section>
      {progress.recent_sessions.length > 0 && <section className="offline-recent-sessions"><h2>Недавние занятия</h2><ul>
        {progress.recent_sessions.map((session) => <li key={session.id}><a href={`#/${session.status === 'active' ? 'session' : 'summary'}/${encodeURIComponent(session.id)}`}>
          <span><strong>{session.status === 'active' ? 'Продолжить занятие' : 'Итог занятия'}</strong><span className="offline-lesson-meta">{formatDate(session.created_at)}</span></span>
          <span className="offline-session-count">{session.summary.independent_correct} / {session.summary.independent_total}<span className="offline-lesson-meta">самостоятельно</span></span><ArrowRight aria-hidden="true" />
        </a></li>)}
      </ul></section>}
      <section id="mistakes" className="offline-mistakes"><h2>Ошибки и пропуски</h2>
        {progress.mistakes.length === 0 ? <p className="muted">В доступной истории нет первых неверных ответов и пропусков. Это не оценка готовности к экзамену.</p>
          : <><p className="muted">Исправления не скрывают исходный ответ. Явный повтор не даёт второго самостоятельного достижения.</p><div className="offline-result-list">{progress.mistakes.map(({ task, attempt }) => <details className="offline-result-row" key={attempt.id}>
            <summary><span className="slot-number">{task.slot}</span><span><strong>{task.title}</strong><span className="offline-result-status">{attempt.skipped ? 'Пропуск' : `Первый ответ: «${attempt.raw_answer}»`}</span></span></summary>
            <div className="offline-result-content"><TaskContent task={task} /><p>{attempt.skipped ? 'Ответ был пропущен.' : `Первый ответ: «${attempt.raw_answer}». Он остаётся в истории.`}</p>
              <a className="text-link" href={`#/practice?slots=${task.slot}&length=5&repeat=${encodeURIComponent(task.id)}`}><RotateCcw aria-hidden="true" />Явно повторить эту задачу</a>
              <a className="text-link" href={`#/lessons?slot=${task.slot}`}>К урокам номера {task.slot}<ArrowRight aria-hidden="true" /></a>
            </div>
          </details>)}</div></>}
      </section>
      <div className="offline-progress-footer"><Button variant="quiet" disabled={loading} onClick={retry}>Прочитать историю снова</Button><p className="muted">Локальная история не объединяется с серверной и не переносится между устройствами.</p></div>
    </>}
  </>;
}
