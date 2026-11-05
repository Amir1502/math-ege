import { useEffect, useRef, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { profileResource, useResource } from '../app/resources';
import { RichText } from '../components/math';
import { TaskContent } from '../components/task-content';
import { ActionLink, ErrorNotice, PageHeading } from '../components/ui';
import type { AssessmentRecord } from './model';
import type { AssessmentResult, ResultRow } from './types';
import { diagnosticFollowups, type DiagnosticFollowup } from './followups';

function outcome(row: ResultRow): string {
  if (row.skipped) return 'Пропущено';
  if (row.format_error) return 'Ошибка формата';
  return row.correct ? 'Верно' : 'Неверно';
}

function ResultLedger({ result, record, local, followups, children }: {
  result: AssessmentResult; record: AssessmentRecord; local: boolean; followups?: DiagnosticFollowup[]; children?: ReactNode;
}) {
  const titleId = local ? 'assessment-local-result' : 'assessment-server-result';
  return <section className="assessment-result" aria-labelledby={titleId}>
    <div className="assessment-result-heading">
      <div><h2 id={titleId}>{local ? 'Локальный учебный результат' : 'Серверный результат'}</h2>
        <p>{local ? 'Сервер проверил замороженный снимок с этого устройства. Он не создаёт второе достижение.' : 'Зафиксированный сервером итог. Только он используется для учёта результата.'}</p></div>
      <p className="assessment-score" aria-label={`${result.score} из ${result.total}`}><strong>{result.score}</strong><span>из {result.total}</span></p>
    </div>
    {children}
    <div className="assessment-result-ledger">
      {result.rows.map((row) => {
        const task = record.view.tasks.find((item) => item.id === row.task_id);
        const followup = followups?.find((item) => item.task_id === row.task_id);
        return <details key={row.task_id} className="assessment-result-row">
          <summary><span className="assessment-result-number">№ {task?.slot ?? '?'}</span><span className="assessment-result-answer">{row.raw_answer.trim() ? `Ваш ответ: ${row.raw_answer}` : 'Ответ не записан'}</span><strong className={row.correct ? 'assessment-outcome' : 'assessment-outcome assessment-outcome--attention'}>{outcome(row)}</strong></summary>
          <div className="assessment-result-detail">
            {task && <TaskContent task={task} />}
            <dl className="answer-comparison">
              <div><dt>Исходная запись</dt><dd>{row.raw_answer || 'Пусто'}</dd></div>
              {row.normalized_answer !== null && <div><dt>Нормализованный ответ</dt><dd>{row.normalized_answer}</dd></div>}
              <div><dt>Верный ответ</dt><dd><RichText text={row.expected_answer} /></dd></div>
            </dl>
            {row.format_error && <p className="notice">{row.format_message || 'Запись не соответствует формату целого числа или конечной десятичной дроби.'} Это ошибка формата, а не оценка хода решения.</p>}
            <p>{row.assisted ? 'Ранее для этой задачи открывалась помощь.' : row.independent ? 'Самостоятельный ответ.' : 'Ответ не отмечен как новый самостоятельный результат.'}</p>
            <h3>Разбор</h3><ol className="solution-steps">{row.solution.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol>
            {followup && <div className="row-actions"><ActionLink href={followup.href}>Проверить № {followup.slot} на 5 новых задачах</ActionLink></div>}
            {followups && !followup && <p className="assessment-start-note">Для этой позиции проверка недоступна в актуальном профиле.</p>}
          </div>
        </details>;
      })}
    </div>
    {result.recommendation && <p className="assessment-recommendation">{result.recommendation}</p>}
  </section>;
}

function DiagnosticResultLedger({ result, record }: { result: AssessmentResult; record: AssessmentRecord }) {
  const profile = useResource(profileResource);
  const followups = profile.data && !profile.loading && !profile.error && !profile.cached
    ? diagnosticFollowups(record.view, profile.data) : undefined;
  return <ResultLedger result={result} record={record} local={false} followups={followups}>
    <p className="assessment-start-note">Откройте разбор позиции, чтобы проверить её навыки на 5 новых задачах.</p>
    <div role="status" aria-live="polite">{profile.loading && <p>Загружаем актуальный профиль для проверки…</p>}</div>
    {profile.error && <ErrorNotice message={`Проверка пока недоступна. ${profile.error}`} retry={profile.retry} />}
  </ResultLedger>;
}

export function AssessmentResults({ record, onRefresh }: { record: AssessmentRecord; onRefresh(): void }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => { container.current?.querySelector('h1')?.focus(); }, []);
  if (record.view.status !== 'completed') return <div ref={container}><PageHeading title="Результат ещё не открыт" description="Сервер откроет результат и разбор после получения итогового снимка." /></div>;
  const { server_result: server, local_result: local } = record.view;
  const disrupted = record.connection_lost || server?.connection_lost || Boolean(local);
  return <div ref={container}>
    <PageHeading title={record.view.mode === 'exam' ? 'Пробник завершён' : 'Диагностика завершена'} description="Ответы зафиксированы. Можно спокойно разобрать каждую задачу." />
    {disrupted && <div className="notice assessment-connection-warning"><AlertCircle aria-hidden="true" /><div><strong>Соединение прерывалось</strong><p>Серверный и локальный снимки могут отличаться. Их результаты показаны отдельно.</p></div></div>}
    {record.view.result_notice && <p className="assessment-result-notice">{record.view.result_notice}</p>}
    {server ? record.view.mode === 'diagnostic' ? <DiagnosticResultLedger result={server} record={record} /> : <ResultLedger result={server} record={record} local={false} /> : <ErrorNotice message="Сервер подтвердил завершение, но не вернул результат. Обновите вариант." retry={onRefresh} />}
    {local && <ResultLedger result={local} record={record} local />}
    <p className="assessment-content-note">Учебный результат из 13. Это не полный тестовый балл ЕГЭ и не прогноз результата экзамена.</p>
    <div className="row-actions"><ActionLink href="/assessment" primary>Новый вариант</ActionLink><ActionLink href="/practice">К практике</ActionLink></div>
  </div>;
}
