import { useState } from 'react';
import { ArrowUpRight, Download, LoaderCircle } from 'lucide-react';
import { api, errorText } from '../api/client';
import { profileResource, progressResource, useResource } from '../app/resources';
import { ActionLink, Button, EmptyState, ErrorNotice, GuestNote, Loading, PageHeading } from '../components/ui';
import { formatDate, downloadJson, formatDuration } from '../utils/format';
import { sessionPath } from '../app/router';

export default function ProgressPage() {
  const progress = useResource(progressResource, true);
  const profile = useResource(profileResource);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportHistory = async () => {
    if (exporting) return;
    setExporting(true);
    setExportError(null);
    try { downloadJson(await api.export(), 'ege-profile-history.json'); }
    catch (error) { setExportError(errorText(error)); }
    finally { setExporting(false); }
  };
  const data = progress.data;
  return <>
    <PageHeading title="Прогресс" description="Самостоятельные первые ответы. Без обещаний экзаменационного балла." action={data && <Button disabled={exporting} onClick={() => void exportHistory()}>{exporting ? <LoaderCircle className="spin" aria-hidden="true" /> : <Download aria-hidden="true" />}Скачать JSON</Button>} />
    {progress.loading && <Loading label="Загружаем прогресс" />}
    {progress.error && <ErrorNotice message={progress.error} retry={progress.retry} />}
    {exportError && <ErrorNotice message={exportError} retry={() => void exportHistory()} />}
    {!progress.loading && !progress.error && (!data ? <><EmptyState title="История ещё не начата" action={<ActionLink href="/practice" primary>Выбрать занятие</ActionLink>}>Начните практику без регистрации. Здесь появятся ваши ответы, помощь, исправления и история занятий.</EmptyState><GuestNote /></> : <>
      <section className="progress-overview" aria-labelledby="progress-stat-title"><div className="main-stat"><h2 id="progress-stat-title">Первые самостоятельные ответы</h2><span className="main-stat__value">{data.independent_correct}<span> / {data.independent_total}</span></span><p>верных ответов из отправленных без помощи</p></div><dl className="stat-ledger"><div><dt>Ответов с помощью</dt><dd>{data.assisted_total}</dd></div><div><dt>Повторных ответов</dt><dd>{data.corrections_total}</dd></div><div><dt>Пропусков</dt><dd>{data.skipped_total}</dd></div></dl></section>
      <section className="coverage-section"><div className="section-heading"><h2>Номера и навыки</h2><a className="text-link" href="#/topics">К темам<ArrowUpRight aria-hidden="true" /></a></div><p className="muted">Статусы описывают только ответы в тренажёре. Демобанк не покрывает всю матрицу.</p>
        <div className="coverage-ledger">{data.slots.map((slot) => <a className="coverage-row" href={`#/topics/${slot.number}`} key={slot.number}><span className="slot-number">{slot.number}</span><span><strong>{profile.data?.slots.find((item) => item.number === slot.number)?.title ?? `Номер ${slot.number}`}</strong><small>Навыков охвачено: {slot.covered_skills} из {slot.total_skills}</small></span><span className="coverage-result"><strong>{slot.correct} / {slot.attempts}</strong><small>{slot.status}</small></span></a>)}</div>
      </section>
      <section className="history-section"><h2>История занятий</h2>{data.recent_sessions.length === 0 ? <EmptyState title="Занятий пока нет">После первой серии здесь появятся дата, результат и активное время.</EmptyState> : <ol className="history-list">{data.recent_sessions.map((session) => <li key={session.id}><a href={`#${session.status === 'active' ? sessionPath(session.id) : `/summary/${encodeURIComponent(session.id)}`}`}><div><strong>{formatDate(session.created_at)}</strong><small>{session.status === 'active' ? 'Занятие продолжается' : 'Завершено'} · {formatDuration(session.summary.active_seconds)}</small></div><div><span>{session.summary.independent_correct} / {session.summary.independent_total}</span><small>самостоятельно</small></div><ArrowUpRight aria-hidden="true" /></a></li>)}</ol>}</section>
      <GuestNote />
    </>)}
  </>;
}
