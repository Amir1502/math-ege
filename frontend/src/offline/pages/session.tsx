import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, CircleHelp, Minus, RotateCcw, Save, SkipForward } from 'lucide-react';
import { TaskContent } from '../../components/task-content';
import { RichText } from '../../components/math';
import { FinishDialog } from '../../components/finish-dialog';
import { Button } from '../../components/ui';
import type { OfflineRuntime } from '../practice';
import { AttemptRecord, OfflineFailure, OfflineHeading, OfflineLoading, SessionResultRows, SummaryLedger } from './shared';
import type { Course, Failure, RegisterLeaveGuard, Session } from './shared';
import { failure } from './operations';
import { WorksheetController } from './session-state';
import type { WorksheetState } from './session-state';

function AnswerForm({ controller, state, next }: { controller: WorksheetController; state: WorksheetState; next: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const task = state.session.tasks[state.session.current_index];
  const draft = state.drafts[task.id];
  const attempts = state.session.attempts.filter((attempt) => attempt.task_id === task.id);
  const result = attempts[attempts.length - 1];
  const locked = Boolean(state.busy || state.pendingAttempt || state.pendingFinish || state.queueError);
  const unchanged = result && !result.skipped && result.raw_answer === draft.answer;
  const settled = result?.correct || result?.skipped || unchanged;
  const last = state.session.current_index === state.session.tasks.length - 1;

  useEffect(() => { if (state.formError) input.current?.focus(); }, [state.formError]);

  const insert = (symbol: string) => {
    const field = input.current;
    if (!field || locked) return;
    const start = field.selectionStart ?? draft.answer.length;
    const end = field.selectionEnd ?? start;
    const answer = symbol === '−' ? /^[-−]/.test(draft.answer) ? draft.answer.slice(1) : `−${draft.answer}`
      : draft.answer.slice(0, start) + symbol + draft.answer.slice(end);
    if (answer.length > 64) return;
    controller.edit(answer);
    field.focus();
    const position = symbol === '−' ? answer.length : start + 1;
    requestAnimationFrame(() => field.setSelectionRange(position, position));
  };

  return <form className="answer-form" onSubmit={(event) => { event.preventDefault(); if (!locked) void controller.submit(); }}>
    <label htmlFor="offline-answer">Ответ</label>
    <div className="answer-input-row">
      <input ref={input} id="offline-answer" name="answer" type="text" inputMode="decimal" enterKeyHint="done"
        autoComplete="off" autoCapitalize="off" spellCheck={false} maxLength={64} value={draft.answer}
        onChange={(event) => controller.edit(event.target.value)} readOnly={locked}
        aria-invalid={Boolean(state.formError)} aria-describedby="offline-answer-help offline-answer-feedback" />
      <Button className="symbol-button" aria-label="Вставить или убрать минус" disabled={locked} onClick={() => insert('−')}><Minus aria-hidden="true" /></Button>
      <Button className="symbol-button" aria-label="Вставить запятую" disabled={locked} onClick={() => insert(',')}>,</Button>
      <Button className="symbol-button" aria-label="Вставить дробную черту" disabled={locked} onClick={() => insert('/')}>/</Button>
    </div>
    <p id="offline-answer-help" className="microcopy">Целое число, десятичная или обычная дробь. Например: −2; 0,5; 1/2. Без единиц измерения.</p>
    <div className="answer-actions">
      {state.pendingAttempt ? <Button variant="primary" disabled={Boolean(state.busy)} onClick={() => void controller.submit()}>
        <RotateCcw aria-hidden="true" />{state.busy === 'attempt' ? 'Проверяем…' : 'Повторить проверку'}</Button>
        : <Button type="submit" variant={settled ? 'secondary' : 'primary'} disabled={locked || Boolean(unchanged)} aria-busy={state.busy === 'attempt'}>
          <CheckCircle2 aria-hidden="true" />{state.busy === 'attempt' ? 'Проверяем…' : result && !result.skipped ? 'Проверить исправление' : 'Проверить'}</Button>}
      {result && !state.pendingAttempt && <Button variant={settled ? 'primary' : 'secondary'} disabled={locked} onClick={next}>
        {last ? 'К завершению' : 'Следующая задача'}<ArrowRight aria-hidden="true" /></Button>}
      {!result && !state.pendingAttempt && <Button variant="quiet" disabled={locked} onClick={() => void controller.submit(true)}><SkipForward aria-hidden="true" />Пропустить</Button>}
    </div>
    <div id="offline-answer-feedback" className="answer-feedback" aria-live="polite" aria-atomic="true">
      {state.formError ? <div className="notice notice--error" role="alert"><div><strong>Проверьте формат, не решение</strong>
        <p>{state.formError.message}</p><p>Математическая попытка не создана.</p></div></div>
        : state.pendingAttempt ? <div className="notice"><div><strong>Проверка пока не подтверждена</strong>
          <p>Повтор использует исходный ответ и тот же ключ. Новая попытка не создаётся.</p></div></div>
          : result ? <AttemptRecord attempt={result} />
            : <p className="feedback-placeholder">Результат появится после проверки. Исправления не скрывают первый ответ.</p>}
    </div>
  </form>;
}

function Worksheet({ initial, course, runtime, registerLeaveGuard }: {
  initial: Session; course: Course; runtime: OfflineRuntime; registerLeaveGuard: RegisterLeaveGuard;
}) {
  const [controller] = useState(() => new WorksheetController(runtime, initial));
  const state = useSyncExternalStore(controller.subscribe, controller.state);
  const [confirming, setConfirming] = useState(false);
  const taskHeading = useRef<HTMLHeadingElement>(null);
  const task = state.session.tasks[state.session.current_index];
  const help = state.session.help[task.id];
  const locked = Boolean(state.busy || state.pendingAttempt || state.pendingFinish || state.queueError);
  const answered = new Set(state.session.attempts.map((attempt) => attempt.task_id));
  const hasDraft = state.session.tasks.some((item) => state.drafts[item.id].answer
    && !state.session.attempts.some((attempt) => attempt.task_id === item.id && !attempt.skipped && attempt.raw_answer === state.drafts[item.id].answer));
  const lesson = course.lessons.find((item) => item.practice_task_ids?.includes(task.id))
    ?? course.lessons.find((item) => item.family_ids?.includes(task.family_id))
    ?? course.lessons.find((item) => item.slot === task.slot);
  const saving = { saved: 'Сохранено на устройстве', dirty: 'Есть несохранённый ввод', saving: 'Сохраняем на устройстве…', error: 'Черновик пока не сохранён' }[state.saving];

  useEffect(() => controller.attach(), [controller]);
  useEffect(() => registerLeaveGuard(controller.leave), [controller, registerLeaveGuard]);
  useEffect(() => { taskHeading.current?.focus({ preventScroll: true }); }, [task.id]);

  const finish = async () => {
    const completed = await controller.finish();
    setConfirming(false);
    if (completed) window.location.hash = `/summary/${encodeURIComponent(completed.id)}`;
  };
  const retry = () => state.queueError ? void controller.retrySave() : state.pendingAttempt ? void controller.submit()
    : state.pendingFinish ? void finish() : void controller.retrySave();
  const retryLabel = state.queueError ? 'Прочитать и сохранить снова' : state.pendingAttempt ? 'Повторить проверку'
    : state.pendingFinish ? 'Повторить завершение' : 'Прочитать и сохранить снова';

  if (state.session.status === 'completed') return <>
    <OfflineHeading title="Занятие завершено">Итог сохранён на устройстве. Черновики не проверялись автоматически.</OfflineHeading>
    {state.error && <OfflineFailure error={state.error} retry={retry} retryLabel={retryLabel} />}
    {!state.error && (state.pendingAttempt || state.pendingFinish) && <div className="notice"><div>
      <strong>Подтверждение операции ещё не сохранено</strong>
      <p>Итог не меняется. Повтор использует исходный ключ и не создаёт дубль.</p>
      <Button disabled={Boolean(state.busy || state.queueError)} onClick={retry}>{retryLabel}</Button>
    </div></div>}
    <SummaryLedger summary={state.session.summary} /><SessionResultRows session={state.session} course={course} />
    <a className="button button--primary" href="#/practice">К новой серии<ArrowRight aria-hidden="true" /></a>
  </>;

  return <>
    <div className="session-topline"><a className="back-link" href="#/practice"><ArrowLeft aria-hidden="true" />К выбору серии</a>
      <div className="save-state" role="status"><Save aria-hidden="true" /><span>{saving}</span></div></div>
    <OfflineHeading title="Занятие">Демонстрационная практика. Ответы и помощь сохраняются только на этом устройстве.</OfflineHeading>
    {state.session.notice && <div className="notice"><p>{state.session.notice}</p></div>}
    {state.error && <OfflineFailure error={state.error} title="Изменение не подтверждено" retry={retry}
      retryLabel={retryLabel} />}
    {state.pendingFinish && <div className="notice"><div><strong>Завершение пока не подтверждено</strong>
      <p>Ввод и помощь заблокированы до повтора с тем же ключом. История не удалялась.</p>
      <Button disabled={Boolean(state.busy)} onClick={() => void finish()}>Повторить завершение</Button></div></div>}
    <div className="session-position"><p>Задача {state.session.current_index + 1} из {state.session.tasks.length}</p>
      <Button variant="quiet" disabled={locked} onClick={() => setConfirming(true)}>Завершить занятие</Button></div>
    <nav className="task-position-rail" aria-label="Задачи занятия">
      {state.session.tasks.map((item, index) => <button key={item.id} type="button" disabled={locked}
        aria-label={`Задача ${index + 1}. Номер ${item.slot}${answered.has(item.id) ? '. Есть попытка' : ''}`}
        aria-current={index === state.session.current_index ? 'step' : undefined} onClick={() => void controller.move(index)}>{index + 1}</button>)}
    </nav>
    <div className="session-layout offline-session-layout">
      <article className="worksheet task-sheet" data-task-id={task.id} data-task-revision={task.revision}>
        <div className="task-title"><h2 ref={taskHeading} tabIndex={-1}>№ {task.slot}. {task.title}</h2><span className="demo-label">Демо</span></div>
        <div className="task-content"><TaskContent task={task} /></div>
        <AnswerForm controller={controller} state={state} next={() => {
          if (state.session.current_index === state.session.tasks.length - 1) setConfirming(true);
          else void controller.move(state.session.current_index + 1);
        }} />
      </article>
      <aside className="task-help" aria-labelledby="offline-help-title">
        <h2 id="offline-help-title"><CircleHelp aria-hidden="true" />Помощь по задаче</h2>
        <p className="muted">Открытая помощь учитывается отдельно. Самостоятельным останется только первый ответ без неё.</p>
        <div className="hint-levels">{help.hints.map((hint) => <section className="hint-level" key={hint.level}>
          <h3>Подсказка {hint.level}</h3><p><RichText text={hint.text} /></p>
        </section>)}</div>
        {help.hints.length < 3 && <Button disabled={locked} aria-busy={state.busy === 'hint'} onClick={() => void controller.help('hint')}>
          {state.busy === 'hint' ? 'Открываем подсказку…' : `Открыть подсказку ${help.hints.length + 1}`}</Button>}
        <section className="full-solution"><h3>Полное решение</h3>
          {help.solution ? <><ol className="solution-steps">{help.solution.steps.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol>
            <p>Ответ: <strong>{help.solution.answer}</strong></p></>
            : <><p className="muted">Открытие эталона отмечается как помощь, даже до первого ответа.</p>
              <Button disabled={locked} aria-busy={state.busy === 'solution'} onClick={() => void controller.help('solution')}>
                {state.busy === 'solution' ? 'Открываем решение…' : 'Открыть решение'}</Button></>}
        </section>
        {lesson && <a className="text-link" href={`#/lessons/${encodeURIComponent(lesson.id)}`}>К теории<ArrowRight aria-hidden="true" /></a>}
      </aside>
    </div>
    <p className="offline-bottom-note muted">Прогресс учитывает фактические первые ответы, а не прогноз балла. Повторы и исправления не заменяют первый результат.</p>
    <FinishDialog open={confirming} unanswered={state.session.tasks.length - answered.size} hasDraft={hasDraft}
      busy={state.busy === 'finish'} onClose={() => setConfirming(false)} onConfirm={() => void finish()} />
  </>;
}

export default function SessionPage({ id, course, runtime, registerLeaveGuard }: {
  id: string; course: Course; runtime: OfflineRuntime; registerLeaveGuard: RegisterLeaveGuard;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<Failure | null>(null);
  const [request, setRequest] = useState(0);
  useEffect(() => {
    let stopped = false;
    void runtime.session(id).then((value) => { if (!stopped) { setSession(value); setError(null); } })
      .catch((caught: unknown) => { if (!stopped) setError(failure(caught)); });
    return () => { stopped = true; };
  }, [id, runtime, request]);
  if (!session) return <><OfflineHeading title="Занятие" />{error ? <OfflineFailure error={error} title="Не удалось прочитать занятие"
    retry={() => { setError(null); setRequest((value) => value + 1); }} /> : <OfflineLoading label="Читаем сохранённую серию" />}</>;
  return <Worksheet initial={session} course={course} runtime={runtime} registerLeaveGuard={registerLeaveGuard} />;
}
