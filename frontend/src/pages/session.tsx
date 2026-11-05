import { useEffect, useState } from 'react';
import { ArrowLeft, Check, Clock, Cloud, CloudOff, Pause, SkipForward } from 'lucide-react';
import { useActiveClock, useSession } from '../learning/use-session';
import { hasDirtyDrafts } from '../learning/model';
import { useOnline } from '../app/online';
import { navigate } from '../app/router';
import { Button, EmptyState, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { TaskContent } from '../components/task-content';
import { AnswerForm } from '../components/answer-form';
import { TaskHelp } from '../components/task-help';
import { FinishDialog } from '../components/finish-dialog';
import { WorksheetAnnotations } from '../components/worksheet-annotations';
import { formatDuration } from '../utils/format';

export default function SessionPage({ id }: { id: string }) {
  const state = useSession(id);
  const { record, controller } = state;
  const online = useOnline();
  const [finishOpen, setFinishOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const task = record?.session.tasks[record.current_index];
  const latestAttempt = record?.session.attempts.filter((attempt) => attempt.task_id === task?.id).at(-1);
  const hasResult = Boolean(latestAttempt && latestAttempt.raw_answer === (task ? record?.drafts[task.id].answer : undefined));
  const clockEnabled = Boolean(record?.session.status === 'active' && !paused && !finishOpen && !state.busy && !record.pending_attempt && !record.pending_finish && !record.extension_key && !hasResult && !state.accessDenied);
  useActiveClock(controller, task?.id, clockEnabled);

  useEffect(() => {
    if (record?.session.status === 'completed') navigate(`/summary/${encodeURIComponent(id)}`);
  }, [record?.session.status, id]);

  if (state.loading && !record) return <><PageHeading title="Ваше занятие" /><Loading label="Восстанавливаем занятие" /></>;
  if (!record) return <><PageHeading title="Занятие недоступно" /><ErrorNotice message={state.error ?? 'Не удалось загрузить занятие.'} retry={() => void controller.refresh()} /><a className="back-link" href="#/practice"><ArrowLeft aria-hidden="true" />К настройке практики</a></>;
  if (!task) return <><PageHeading title="В серии нет задач" /><EmptyState title="Сервер не выдал условия">Вернитесь в практику и выберите другие номера.</EmptyState></>;
  const locked = Boolean(state.busy || record.pending_attempt || record.pending_finish || record.extension_key || state.accessDenied);
  const answeredIds = new Set(record.session.attempts.map((attempt) => attempt.task_id));
  const unanswered = record.session.tasks.length - answeredIds.size;
  const hasDraft = Object.entries(record.drafts).some(([taskId, draft]) => draft.answer && record.session.attempts.filter((attempt) => attempt.task_id === taskId).at(-1)?.raw_answer !== draft.answer);
  const last = record.current_index === record.session.tasks.length - 1;
  const continued = record.session.options?.until_stopped && !record.session.options?.repeat_task_id;
  const target = record.session.options?.target_minutes;
  const activeSeconds = Object.values(record.drafts).reduce((total, draft) => total + draft.active_seconds, 0);
  const next = () => {
    if (last && continued) { void controller.actions.extend(); setPaused(false); }
    else if (last) setFinishOpen(true);
    else { void controller.goTo(record.current_index + 1); setPaused(false); }
  };
  const dirty = hasDirtyDrafts(record);

  return <>
    <div className="session-topline"><a className="back-link" href="#/"><ArrowLeft aria-hidden="true" />К плану</a><span className="save-state" aria-live="polite">{dirty || !online ? <CloudOff aria-hidden="true" /> : <Cloud aria-hidden="true" />}{state.storageError ? 'Ошибка сохранения' : state.syncing ? 'Сохраняем…' : dirty || !online ? 'Сохранено на устройстве' : 'Сохранено на сервере'}</span></div>
    <PageHeading title={`Практика · № ${task.slot}`} description={task.topic} action={<Button variant="quiet" disabled={locked} onClick={() => setFinishOpen(true)}>Завершить</Button>} />
    {record.session.notice && <p className="notice">{record.session.notice}</p>}
    {state.storageError && <ErrorNotice message={state.storageError} retry={() => void controller.update((value) => value).catch(() => undefined)} />}
    {state.error && <ErrorNotice message={state.error} retry={state.conflict ? undefined : () => void controller.retry()} />}
    {state.conflict && <div className="conflict-panel"><p>Проверьте другие открытые вкладки. Подтверждение отправит именно ваш локальный текст поверх серверного черновика.</p><Button disabled={Boolean(state.syncing)} onClick={() => void controller.sync.keepLocal()}>Сохранить мой черновик на сервере</Button><Button variant="quiet" onClick={() => navigate('/help')}>Как работает сохранение</Button></div>}
    {!online && <p className="notice">Вы без сети. Условие и черновик доступны. Проверка, подсказки и завершение требуют сервера.</p>}
    {record.pending_finish && <div className="notice"><p>Завершение ожидает сервера. Ответы заморожены; это ещё не итог занятия.</p><Button disabled={Boolean(state.busy)} onClick={() => void controller.actions.finish()}>Повторить завершение</Button></div>}
    {record.extension_key && <div className="notice"><p>Следующая порция ожидает подтверждения. Старые условия и ответы сохранены.</p><Button disabled={Boolean(state.busy)} onClick={() => void controller.actions.extend()}>Повторить продолжение</Button></div>}
    {target && <p className={activeSeconds >= target * 60 ? 'notice' : 'microcopy'}>Активная работа: {formatDuration(activeSeconds)}. Ориентир: {target} мин.{activeSeconds >= target * 60 ? ' Ориентир достигнут. Можно завершить занятие или продолжить в своём темпе.' : ' Автоматического завершения нет.'}</p>}
    <div className="session-position"><span>Задача <strong>{record.current_index + 1}</strong> из {record.session.tasks.length}</span><div><Clock aria-hidden="true" /><span>{formatDuration(record.drafts[task.id].active_seconds)}</span><Button variant="quiet" disabled={locked || Boolean(hasResult)} onClick={() => setPaused(!paused)}><Pause aria-hidden="true" />{paused ? 'Продолжить' : 'Пауза'}</Button></div></div>
    <nav className="task-position-rail" aria-label="Задачи занятия">{record.session.tasks.map((item, index) => {
      const attempt = record.session.attempts.filter((value) => value.task_id === item.id).at(-1);
      return <button type="button" key={item.id} disabled={locked} aria-current={index === record.current_index ? 'step' : undefined} aria-label={`Задача ${index + 1}, номер ${item.slot}${attempt ? attempt.skipped ? ', пропущена' : attempt.correct ? ', верно' : ', есть ошибка' : ''}`} onClick={() => { void controller.goTo(index); setPaused(false); }}>{attempt?.correct ? <Check aria-hidden="true" /> : attempt?.skipped ? <SkipForward aria-hidden="true" /> : index + 1}</button>;
    })}</nav>
    <div className="session-layout">
      <section className="worksheet task-sheet"><div className="task-title"><h2>{task.title}</h2>{task.review_status === 'demo' && <span className="demo-label">Демозадача</span>}</div>
        {paused && <p className="notice">Учёт времени на паузе. Нажмите «Продолжить», когда вернётесь к решению.</p>}
        <TaskContent task={task} />
        <AnswerForm key={`answer:${task.id}`} taskId={task.id} controller={controller} state={state} onNext={next} last={last} nextLabel={last && continued ? 'Следующая порция задач' : undefined} />
        {!state.accessDenied && <WorksheetAnnotations key={`annotations:${task.id}`} sessionId={id} taskId={task.id} showCause={Boolean(latestAttempt && !latestAttempt.correct)} />}
      </section>
      <TaskHelp key={task.id} task={task} controller={controller} state={state} />
    </div>
    <p className="microcopy">Время учитывается только на экране этой задачи. Свёрнутая вкладка и открытая теория не добавляют секунды.</p>
    <FinishDialog open={finishOpen} unanswered={unanswered} hasDraft={hasDraft} busy={state.busy === 'finish'} onClose={() => setFinishOpen(false)} onConfirm={() => { setFinishOpen(false); void controller.actions.finish(); }} />
  </>;
}
