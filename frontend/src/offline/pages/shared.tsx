import { AlertCircle, ArrowRight, CheckCircle2, SkipForward, XCircle } from 'lucide-react';
import { Button } from '../../components/ui';
import { RichText } from '../../components/math';
import { TaskContent } from '../../components/task-content';
import { formatDuration } from '../../utils/format';
import type { OfflineCourse } from '../types';
import type { OfflineRuntime } from '../practice';

export type Course = OfflineCourse;
export type Session = Awaited<ReturnType<OfflineRuntime['session']>>;
export type RuntimeState = Awaited<ReturnType<OfflineRuntime['state']>>;
export type StartOptions = Parameters<OfflineRuntime['start']>[0];
export type AttemptInput = Parameters<OfflineRuntime['attempt']>[1];
export type DraftInput = Parameters<OfflineRuntime['draft']>[1];
export type PracticeProgress = Awaited<ReturnType<OfflineRuntime['progress']>>;
export type LeaveGuard = () => Promise<boolean>;
export type RegisterLeaveGuard = (guard: LeaveGuard) => () => void;
export type Failure = { code: string; message: string };

export function OfflineHeading({ title, children }: { title: string; children?: React.ReactNode }) {
  return <header className="page-heading offline-page-heading">
    <div><h1 tabIndex={-1}>{title}</h1>{children && <p>{children}</p>}</div>
  </header>;
}

export function OfflineFailure({ error, title = 'Действие не подтверждено', retry, retryLabel = 'Повторить' }: {
  error: unknown; title?: string; retry?: () => void; retryLabel?: string;
}) {
  const value = error && typeof error === 'object' ? error as { code?: unknown; message?: unknown } : null;
  const message = typeof value?.message === 'string' ? value.message : typeof error === 'string' ? error : 'Не удалось прочитать или сохранить данные на устройстве.';
  const code = typeof value?.code === 'string' ? value.code : null;
  return <div className="notice notice--error offline-failure" role="alert">
    <AlertCircle aria-hidden="true" />
    <div><strong>{title}</strong><p>{message}</p>{code && <p className="offline-error-code">Код: <code>{code}</code></p>}
      {retry && <Button onClick={retry}>{retryLabel}</Button>}
    </div>
  </div>;
}

export function OfflineLoading({ label }: { label: string }) {
  return <div className="offline-loading" role="status"><p>{label}…</p><div className="skeleton skeleton--block" aria-hidden="true" /></div>;
}

export function PositionRail({ course, active, destination = 'lessons' }: {
  course: Course; active?: number; destination?: 'lessons' | 'practice';
}) {
  return <nav className="offline-position-rail" aria-label="13 номеров первой части">
    {course.profile.slots.map((slot) => <a key={slot.number}
      href={`#/${destination}?${destination === 'lessons' ? 'slot' : 'slots'}=${slot.number}`}
      aria-label={`Номер ${slot.number}. ${slot.title}`}
      aria-current={active === slot.number ? 'page' : undefined}>
      {slot.number}
    </a>)}
  </nav>;
}

export function LocalCourseNote() {
  return <div className="offline-local-note">
    <strong>Демонстрационный курс. Только на этом устройстве.</strong>
    <p>История хранится локально и не отправляется в облако. Материалы проекта не прошли независимую предметную рецензию.</p>
  </div>;
}

export function SummaryLedger({ summary }: { summary: Session['summary'] }) {
  return <dl className="stat-ledger offline-ledger">
    <div><dt>Первые самостоятельные ответы</dt><dd>{summary.independent_total}</dd></div>
    <div><dt>Из них верные</dt><dd>{summary.independent_correct}</dd></div>
    <div><dt>С помощью</dt><dd>{summary.assisted}</dd></div>
    <div><dt>Исправления</dt><dd>{summary.corrections}</dd></div>
    <div><dt>Пропуски</dt><dd>{summary.skipped}</dd></div>
    <div><dt>Время решения</dt><dd>{formatDuration(summary.active_seconds)}</dd></div>
  </dl>;
}

export function AttemptRecord({ attempt }: { attempt: Session['attempts'][number] }) {
  const Icon = attempt.skipped ? SkipForward : attempt.correct ? CheckCircle2 : XCircle;
  const title = attempt.skipped ? 'Пропущено' : attempt.correct ? attempt.first_attempt ? 'Верно' : 'Исправлено' : 'Пока неверно';
  return <div className={`offline-attempt ${!attempt.correct && !attempt.skipped ? 'offline-attempt--wrong' : ''}`}>
    <Icon aria-hidden="true" /><div><strong>{title}</strong>
      <p>{attempt.skipped ? 'Пропуск учтён отдельно. Можно вернуться к задаче до завершения занятия.'
        : attempt.correct ? `Ответ принят: ${attempt.normalized_answer ?? attempt.raw_answer}.`
          : 'Числовой ответ не совпал с эталоном. Попробуйте другой ход или откройте помощь.'}</p>
      <p>{!attempt.first_attempt ? 'Исправление не меняет результат первой попытки.'
        : attempt.assisted ? 'До первого ответа была открыта помощь.'
          : attempt.independent ? 'Первая самостоятельная попытка.'
            : 'Знакомое условие. Повтор не добавляет новое самостоятельное достижение.'}</p>
    </div>
  </div>;
}

export function SessionResultRows({ session, course }: { session: Session; course: Course }) {
  return <div className="offline-result-list">
    {session.tasks.map((task, index) => {
      const attempts = session.attempts.filter((attempt) => attempt.task_id === task.id);
      const first = attempts.find((attempt) => attempt.first_attempt) ?? attempts[0];
      const last = attempts[attempts.length - 1];
      const solution = session.help[task.id]?.solution;
      const steps = solution?.steps ?? last?.solution;
      const expected = solution?.answer ?? last?.expected_answer;
      const lesson = course.lessons.find((item) => item.practice_task_ids?.includes(task.id))
        ?? course.lessons.find((item) => item.family_ids?.includes(task.family_id))
        ?? course.lessons.find((item) => item.slot === task.slot);
      return <details className="offline-result-row" key={task.id} data-task-id={task.id}>
        <summary><span className="slot-number">{index + 1}</span><span>
          <strong>№ {task.slot}. {task.title}</strong>
          <span className="offline-result-status">{!first ? 'Без проверенного ответа'
            : first.skipped ? 'Первая попытка: пропуск'
              : first.correct ? 'Первая попытка: верно' : 'Первая попытка: неверно'}
            {attempts.length > 1 && (last?.correct ? '. Позже исправлено' : '. Есть повторные ответы')}
          </span>
        </span></summary>
        <div className="offline-result-content"><TaskContent task={task} />
          <dl className="answer-comparison">
            <div><dt>Первый ответ</dt><dd>{first ? first.skipped ? 'Пропуск' : first.raw_answer : 'Не проверялся'}</dd></div>
            {expected !== undefined && <div><dt>Эталон</dt><dd>{expected}</dd></div>}
          </dl>
          {attempts.length > 1 && <section><h3>История ответов</h3><ol className="offline-attempt-history">
            {attempts.map((attempt) => <li key={attempt.id}>
              {attempt.skipped ? 'Пропуск' : `«${attempt.raw_answer}»: ${attempt.correct ? 'верно' : 'неверно'}`}.
              {attempt.first_attempt ? ' Первая попытка.' : ' Исправление.'}
              {attempt.assisted && ' С помощью.'}
            </li>)}
          </ol></section>}
          {!first && session.drafts[task.id]?.answer && <p>Сохранённый черновик: «{session.drafts[task.id].answer}». Он не был отправлен на проверку.</p>}
          {steps && steps.length > 0 && <section><h3>Разбор</h3><ol className="solution-steps">
            {steps.map((step, stepIndex) => <li key={stepIndex}><RichText text={step} /></li>)}
          </ol></section>}
          {!steps?.length && <p className="muted">Разбор не открывался. Это не означает, что черновик был проверен.</p>}
          {lesson && <a className="text-link" href={`#/lessons/${encodeURIComponent(lesson.id)}`}>К теории по этому типу<ArrowRight aria-hidden="true" /></a>}
        </div>
      </details>;
    })}
  </div>;
}
