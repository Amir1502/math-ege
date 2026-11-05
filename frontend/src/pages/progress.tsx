import { useRef, useState } from 'react';
import { ArrowUpRight, Download, LoaderCircle } from 'lucide-react';
import { boundApi } from '../api/client';
import { useRoute } from '../app/router';
import { ActionLink, Button, EmptyState, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { formatDate, downloadJson, formatDuration } from '../utils/format';
import { identity } from '../storage/identity';
import { useLearningDashboard, useLearningIdentity, usePracticeProgress } from '../extras/hooks';
import { AssessmentHistoryPanel, LearningNotifications, MasteryLedger } from '../extras/progress-panels';
import { coverageSlots, independentAccuracy, originalProfileLabel, pageOffset, practiceHistoryPath } from '../extras/view-models';
import { learningError } from '../extras/resource';
import { confirmedLearningOwner } from '../extras/identity';
import '../styles/extras.css';

export default function ProgressPage() {
  const owner = useLearningIdentity();
  const progress = usePracticeProgress();
  const route = useRoute();
  const learning = useLearningDashboard(pageOffset(route.query.get('offset')));
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<{ owner: string; message: string } | null>(null);
  const locked = useRef(false);
  const exportHistory = async () => {
    if (locked.current || !owner || confirmedLearningOwner() !== owner) return;
    locked.current = true;
    let current = true;
    const unsubscribe = identity.subscribe(() => { if (confirmedLearningOwner() !== owner) current = false; });
    setExporting(true);
    setExportError(null);
    try {
      const result = await boundApi(owner).export();
      if (current && confirmedLearningOwner() === owner) downloadJson(result, 'ege-profile-history.json');
    } catch (error) {
      if (current && confirmedLearningOwner() === owner) setExportError({ owner, message: learningError(error) });
    } finally {
      unsubscribe();
      locked.current = false;
      setExporting(false);
    }
  };
  const data = progress.data;
  const dashboard = learning.data;
  const slots = coverageSlots(dashboard);
  const evidence = dashboard ?? data;
  const accuracy = evidence ? independentAccuracy(evidence) : null;
  const empty = !progress.loading && !learning.loading && !progress.error && !learning.error && !data && !dashboard;

  return <>
    <PageHeading title="Прогресс" description="Самостоятельные ответы, покрытие навыков и результаты учебных проверок." action={data && <Button disabled={exporting} onClick={() => void exportHistory()} aria-busy={exporting}>{exporting ? <LoaderCircle className="spin" aria-hidden="true" /> : <Download aria-hidden="true" />}Скачать JSON</Button>} />
    {progress.loading && !data && <Loading label="Загружаем историю практики" />}
    {progress.error && <ErrorNotice message={progress.error} retry={progress.retry} />}
    {exportError?.owner === owner && <ErrorNotice message={exportError.message} retry={() => void exportHistory()} />}
    {empty && <><EmptyState title="История ещё не начата" action={<ActionLink href="/practice" primary>Выбрать занятие</ActionLink>}>Начните практику без регистрации. Здесь появятся ваши ответы, помощь, исправления и история занятий.</EmptyState><GuestNote /></>}
    {evidence && <section className="progress-overview" aria-labelledby="progress-stat-title">
      <div className="main-stat"><h2 id="progress-stat-title">Первые самостоятельные ответы</h2><span className="main-stat__value">{evidence.independent_correct}<span> / {evidence.independent_total}</span></span><p>верных ответов из учтённых без помощи. Включены открытые результаты диагностики и пробников.</p><p className="microcopy">{accuracy === null ? 'Для доли верных пока нет ответов.' : `Доля верных среди этих ответов: ${accuracy}%.`}</p></div>
      <dl className="stat-ledger"><div><dt>Ответов с помощью</dt><dd>{evidence.assisted_total}</dd></div><div><dt>Повторных ответов</dt><dd>{evidence.corrections_total}</dd></div><div><dt>Пропусков</dt><dd>{evidence.skipped_total}</dd></div></dl>
    </section>}
    {learning.loading && !dashboard && <Loading label="Загружаем карту навыков и результаты проверок" />}
    {learning.error && <ErrorNotice message={learning.error} retry={learning.retry} />}
    {evidence?.notice && <p className="notice learning-algorithm-note">{evidence.notice}</p>}
    {slots.length > 0 && <MasteryLedger slots={slots} dashboard={dashboard} />}
    <LearningNotifications dashboard={dashboard} excludedTotal={evidence?.excluded_total ?? 0} />
    {dashboard && <AssessmentHistoryPanel dashboard={dashboard} />}
    {data && <section className="history-section" aria-labelledby="practice-history-heading">
      <h2 id="practice-history-heading">История занятий</h2>
      {data.recent_sessions.length === 0 ? <EmptyState title="Занятий пока нет">После первой серии здесь появятся дата, результат и активное время.</EmptyState>
        : <ol className="history-list">{data.recent_sessions.map((session) => <li key={session.id}><a href={`#${practiceHistoryPath(session)}`}>
          <div><strong>{formatDate(session.created_at)}</strong><small>{session.status === 'active' ? 'Занятие продолжается' : 'Завершено'} · {formatDuration(session.summary.active_seconds)}</small>{session.profile && <small>{originalProfileLabel(session.profile)}</small>}</div>
          <div><span>{session.summary.independent_correct} / {session.summary.independent_total}</span><small>самостоятельно</small></div><ArrowUpRight aria-hidden="true" />
        </a></li>)}</ol>}
    </section>}
    {dashboard?.recommendation && <section className="next-step" aria-labelledby="progress-next-heading"><div><h2 id="progress-next-heading">Дальше по плану</h2><p>{dashboard.recommendation}</p></div><ActionLink href="/">Открыть план</ActionLink></section>}
    {(data || dashboard) && identity.getSnapshot().value?.kind === 'guest' && <GuestNote />}
  </>;
}
