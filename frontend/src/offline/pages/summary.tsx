import { useEffect, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { formatDate } from '../../utils/format';
import type { OfflineRuntime } from '../practice';
import { OfflineFailure, OfflineHeading, OfflineLoading, SessionResultRows, SummaryLedger } from './shared';
import type { Course, Failure, Session } from './shared';
import { failure } from './operations';

export default function SummaryPage({ id, course, runtime }: { id: string; course: Course; runtime: OfflineRuntime }) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const [request, setRequest] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let stopped = false;
    void runtime.session(id).then((value) => {
      if (!stopped) { setSession(value); setError(null); setLoading(false); }
    }).catch((caught: unknown) => {
      if (!stopped) { setError(failure(caught)); setLoading(false); }
    });
    return () => { stopped = true; };
  }, [id, runtime, request]);
  const retry = () => { setLoading(true); setRequest((value) => value + 1); };
  if (loading && !session) return <><OfflineHeading title="Итог занятия" /><OfflineLoading label="Читаем сохранённый итог" /></>;
  if (!session) return <><OfflineHeading title="Итог недоступен" /><OfflineFailure error={error} retry={retry} /><a className="text-link" href="#/progress">К истории занятий</a></>;
  if (session.status !== 'completed') return <><OfflineHeading title="Занятие ещё не завершено">Итог появится после подтверждения сохранения на устройстве.</OfflineHeading><a className="button button--primary" href={`#/session/${encodeURIComponent(id)}`}>Вернуться к занятию<ArrowRight aria-hidden="true" /></a></>;
  return <>
    <OfflineHeading title="Занятие завершено">{session.completed_at ? formatDate(session.completed_at) : 'Итог сохранён на этом устройстве.'}</OfflineHeading>
    {error && <OfflineFailure error={error} retry={retry} />}
    <section className="worksheet offline-summary-sheet"><h2>Что получилось</h2><SummaryLedger summary={session.summary} />
      <p className="muted">Проверено или отмечено пропуском: {session.summary.answered} из {session.summary.total}. Непроверенный черновик не становится ответом.</p>
    </section>
    <div className="offline-summary-next"><div><h2>Первый ответ остаётся в истории</h2><p>Разберите ошибки или выберите новые условия. Исправление не превращает исходную ошибку в самостоятельный успех.</p></div>
      <a className="button button--primary" href="#/practice">Выбрать новую серию<ArrowRight aria-hidden="true" /></a>
    </div>
    <section className="offline-session-review"><h2>Все задачи занятия</h2><SessionResultRows session={session} course={course} /></section>
    <a className="text-link" href="#/progress">К общему прогрессу<ArrowRight aria-hidden="true" /></a>
    <p className="offline-bottom-note muted">Это учебный итог демонстрационного курса. Он не является пробником, оценкой освоения или прогнозом балла ЕГЭ.</p>
  </>;
}
