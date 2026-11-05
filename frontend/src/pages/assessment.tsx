import { useEffect, useState, useSyncExternalStore } from 'react';
import { ArrowLeft, Clock, Cloud, CloudOff, LockKeyhole } from 'lucide-react';
import { identity } from '../storage/identity';
import { Button, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { FinishDialog } from '../components/finish-dialog';
import { assessmentDevice } from '../assessments/device';
import { assessmentPhase } from '../assessments/model';
import { AssessmentResults } from '../assessments/results';
import { AssessmentSetup } from '../assessments/setup';
import { useAssessment } from '../assessments/use-assessment';
import { AssessmentWorksheet } from '../assessments/worksheet';
import { WriterDialog } from '../assessments/writer-dialog';
import '../styles/assessment.css';

const digits = new Intl.NumberFormat('ru-RU', { minimumIntegerDigits: 2, useGrouping: false });
function countdown(seconds: number): string {
  return `${digits.format(Math.floor(seconds / 60))}:${digits.format(seconds % 60)}`;
}

function AssessmentRun({ id, ownerId, deviceId }: { id: string; ownerId: string; deviceId: string }) {
  const state = useAssessment(ownerId, id, deviceId);
  const { controller, record } = state;
  const [finishOpen, setFinishOpen] = useState(false);
  const [writerOpen, setWriterOpen] = useState(false);
  if (!record && state.loading) return <><PageHeading title="Ваш вариант" /><Loading label="Восстанавливаем вариант" /></>;
  if (!record) return <><PageHeading title="Вариант недоступен" /><ErrorNotice message={state.error ?? (state.online ? 'Не удалось загрузить вариант. Повторите загрузку.' : 'В этой вкладке нет сохранённого варианта. Подключитесь к сети для загрузки всех 13 условий.')} retry={() => void controller.refresh()} /><a className="back-link" href="#/assessment"><ArrowLeft aria-hidden="true" />К настройке варианта</a></>;

  const phase = assessmentPhase(record);
  if (phase === 'completed') return <AssessmentResults record={record} onRefresh={() => void controller.refresh()} />;
  const unanswered = Object.values(record.drafts).filter((answer) => !answer.answer.trim()).length;
  const writerConflict = record.conflict === 'writer' || !record.view.can_write;
  const currentTaskId = record.view.tasks[record.current_index].id;
  const saveLabel = state.storageError ? 'Сохранение не подтверждено'
    : record.frozen ? 'Итоговый снимок заморожен'
      : state.syncing ? 'Отправляем черновик…'
        : state.dirty || !state.online ? 'Сохранено на устройстве' : 'Сохранено на сервере';

  return <>
    <div className="session-topline assessment-topline"><a className="back-link" href="#/assessment"><ArrowLeft aria-hidden="true" />К вариантам</a><span className="save-state" role="status">{state.dirty || !state.online ? <CloudOff aria-hidden="true" /> : <Cloud aria-hidden="true" />}{saveLabel}</span></div>
    <PageHeading title={phase === 'prepared' ? 'Вариант подготовлен' : phase === 'awaiting_snapshot' ? 'Ответы зафиксированы' : record.view.mode === 'exam' ? 'Пробник' : 'Диагностика'}
      description={phase === 'prepared' ? 'Все 13 условий сохранены на устройстве.' : record.view.mode === 'exam' ? '13 задач. Учебный лимит тренажёра, не регламент ФИПИ.' : '13 задач без ограничения времени.'}
      action={phase === 'active' && <Button variant="quiet" disabled={state.readOnly} onClick={() => setFinishOpen(true)}>Завершить</Button>} />
    {state.storageError && <ErrorNotice message={state.storageError} retry={() => void controller.retry()} />}
    {state.error && state.error !== state.storageError && <ErrorNotice message={state.error} retry={record.conflict ? undefined : () => void controller.retry()} />}
    {record.conflict === 'access' && <div className="notice"><div><p>Запись приостановлена до подтверждения текущего профиля. Локальные ответы сохранены.</p><Button onClick={() => void identity.refresh()}>Обновить профиль</Button></div></div>}
    {writerConflict && <div className="conflict-panel assessment-writer-notice" role="status"><h2><LockKeyhole aria-hidden="true" />Только просмотр</h2><p>Право записи принадлежит другой вкладке или устройству.</p>
      {record.frozen ? <p>Итог этой вкладки заморожен. Его нельзя изменить или отправить от имени другого поколения записи.</p>
        : <Button disabled={!state.online || Boolean(state.busy)} onClick={() => setWriterOpen(true)}>Продолжить в этой вкладке</Button>}
      <Button variant="quiet" disabled={!state.online || Boolean(state.busy)} onClick={() => void controller.refresh()}>Обновить вариант</Button>
    </div>}
    {record.conflict === 'revision' && <section className="conflict-panel" aria-labelledby="assessment-conflict-title"><h2 id="assessment-conflict-title">Черновики расходятся</h2><p>Локальный ввод сохранён. Выберите, какой вариант отправить дальше. До выбора редактирование приостановлено.</p>
      <dl className="assessment-conflict-values"><div><dt>В этой вкладке, задача {record.current_index + 1}</dt><dd>{record.drafts[currentTaskId].answer || 'Пусто'}</dd></div><div><dt>На сервере</dt><dd>{record.view.drafts[currentTaskId]?.answer || 'Пусто'}</dd></div></dl>
      <div className="row-actions"><Button disabled={!state.online || Boolean(state.busy)} onClick={() => void controller.resolveConflict('local')}>{record.frozen ? 'Отправить мой итоговый снимок' : 'Отправить мой черновик'}</Button>{!record.frozen && <Button disabled={!state.online || Boolean(state.busy)} onClick={() => void controller.resolveConflict('server')}>Использовать серверный</Button>}</div>
    </section>}
    {!state.online && phase === 'active' && <p className="notice" role="status">Вы без сети. Все 13 условий и переходы доступны, ответы сохраняются на устройстве.{record.view.mode === 'exam' ? ' Лимит времени продолжает отсчитываться.' : ''}</p>}
    {phase === 'prepared' ? <section className="worksheet assessment-prepared" aria-labelledby="assessment-prepared-title">
      <h2 id="assessment-prepared-title">Можно начинать</h2>
      <p>{record.view.mode === 'exam' ? `После подтверждения начнётся учебный лимит: ${record.view.duration_minutes} минут. Сворачивание вкладки его не остановит.` : 'В диагностике нет таймера. Вы сможете вернуться к этому варианту позже.'}</p>
      <ol className="assessment-manifest">{record.view.tasks.map((task) => <li key={task.id}><span>№ {task.slot}</span><span>{task.topic}</span></li>)}</ol>
      {!state.online && <p className="notice">Для подтверждения начала подключитесь к сети. Условия уже сохранены.</p>}
      <Button variant="primary" disabled={!state.online || Boolean(state.busy) || Boolean(state.storageError) || Boolean(record.conflict)} aria-busy={state.busy === 'activate'} onClick={() => void controller.activate()}>{state.busy === 'activate' ? 'Подтверждаем начало…' : record.pending_activation ? 'Повторить подтверждение начала' : record.view.mode === 'exam' ? 'Начать пробник' : 'Начать диагностику'}</Button>
    </section> : <>
      {phase === 'awaiting_snapshot' && <section className="notice assessment-pending" aria-labelledby="assessment-pending-title" role="status"><CloudOff aria-hidden="true" /><div>
        <h2 id="assessment-pending-title">Результат ожидает снимка</h2>
        <p>{state.remainingSeconds === 0 ? 'Лимит времени истёк. ' : ''}Ответы менять нельзя. Сервер откроет результат и разбор после получения итогового снимка.</p>
        {!state.online && <p>Соединения нет. Снимок сохранён на устройстве и будет отправлен после восстановления сети.</p>}
        {state.online && <Button disabled={Boolean(state.busy) || Boolean(record.conflict)} onClick={() => void controller.finish()}>{state.busy === 'finish' ? 'Отправляем итоговый снимок…' : 'Отправить итоговый снимок'}</Button>}
      </div></section>}
      {phase === 'active' && state.remainingSeconds !== null && <div className={`assessment-clock ${state.remainingSeconds <= 60 ? 'assessment-clock--urgent' : ''}`}>
        <span><Clock aria-hidden="true" />Осталось по лимиту тренажёра</span><span role="timer" aria-live="off" aria-label="Оставшееся время">{countdown(state.remainingSeconds)}</span>
        <span className="sr-only" aria-live="polite">{state.remainingSeconds <= 60 ? 'До завершения меньше минуты.' : state.remainingSeconds <= 300 ? 'До завершения не больше пяти минут.' : ''}</span>
      </div>}
      <AssessmentWorksheet record={record} controller={controller} readOnly={state.readOnly} onFinish={() => setFinishOpen(true)} />
      {phase === 'active' && <p className="assessment-content-note">Можно оставить поле пустым и вернуться к нему позже. При завершении отправятся все последние записи, включая незавершённые.</p>}
    </>}
    <FinishDialog open={finishOpen && phase === 'active' && !state.readOnly} unanswered={unanswered} hasDraft={false} busy={false} onClose={() => setFinishOpen(false)} onConfirm={() => { setFinishOpen(false); void controller.finish(); }} />
    <WriterDialog open={writerOpen && !record.frozen} onClose={() => setWriterOpen(false)} onConfirm={() => { setWriterOpen(false); void controller.takeover(); }} />
  </>;
}

export default function AssessmentPage({ id, ownerId }: { id?: string; ownerId?: string }) {
  const access = useSyncExternalStore(identity.subscribe, identity.getSnapshot);
  const owner = ownerId ?? access.value?.id ?? null;
  const [device, setDevice] = useState<string | null>(null);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [deviceRetry, setDeviceRetry] = useState(0);
  useEffect(() => {
    let current = true;
    if (!identity.getSnapshot().ready) void identity.refresh();
    void assessmentDevice().then((value) => { if (current) { setDevice(value); setDeviceError(null); } }).catch((reason: unknown) => {
      if (current) setDeviceError(reason instanceof Error ? reason.message : 'Не удалось восстановить идентификатор вкладки. Проверьте хранилище браузера.');
    });
    return () => { current = false; };
  }, [deviceRetry]);
  if (deviceError) return <div className="assessment-page"><PageHeading title="Диагностика и пробник" /><ErrorNotice message={deviceError} retry={() => setDeviceRetry((value) => value + 1)} /></div>;
  if (!access.ready || access.changing || !device) return <div className="assessment-page"><PageHeading title="Диагностика и пробник" /><Loading label="Восстанавливаем профиль и вкладку" /></div>;
  if (id && !owner) return <div className="assessment-page"><PageHeading title="Нужен доступ к варианту" /><ErrorNotice message={access.error ?? 'Войдите в профиль, в котором был начат вариант. Гостевой доступ связан с cookie этого браузера.'} retry={() => void identity.refresh()} /><a className="back-link" href="#/assessment">К настройке варианта</a></div>;
  return <div className="assessment-page">{id && owner ? <AssessmentRun key={`${owner}:${device}:${id}`} id={id} ownerId={owner} deviceId={device} /> : <AssessmentSetup key={owner ?? 'new-guest'} ownerId={owner} deviceId={device} />}</div>;
}
