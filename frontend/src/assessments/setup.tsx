import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowRight, Clock, FileText } from 'lucide-react';
import { navigate } from '../app/router';
import { useOnline } from '../app/online';
import { ActionLink, Button, ErrorNotice, PageHeading } from '../components/ui';
import { assessmentErrorText } from './errors';
import { assessmentPreparation, assessmentRepository, prepareAssessment } from './runtime';
import type { AssessmentMode } from './types';

const noPreparation = { busy: false, pending: null, error: null };
const emptySnapshot = () => noPreparation;
const emptySubscribe = () => () => undefined;

export function AssessmentSetup({ ownerId, deviceId }: { ownerId: string | null; deviceId: string }) {
  const [mode, setMode] = useState<AssessmentMode>('diagnostic');
  const [minutes, setMinutes] = useState('65');
  const preparation = ownerId ? assessmentPreparation(ownerId, deviceId) : null;
  const progress = useSyncExternalStore(preparation?.subscribe ?? emptySubscribe, preparation?.getSnapshot ?? emptySnapshot);
  const pending = progress.pending;
  const selectedMode = pending?.body.mode ?? mode;
  const selectedMinutes = pending ? String(pending.body.duration_minutes) : minutes;
  const [last, setLast] = useState<string | null>(null);
  const [identifying, setIdentifying] = useState(false);
  const [localError, setError] = useState<string | null>(null);
  const busy = identifying || progress.busy;
  const error = localError ?? (progress.error ? assessmentErrorText(progress.error) : null);
  const [durationError, setDurationError] = useState(false);
  const duration = useRef<HTMLInputElement>(null);
  const online = useOnline();

  useEffect(() => {
    if (!ownerId || !preparation) return;
    let current = true;
    const storage = assessmentRepository();
    void Promise.all([preparation.restore(), storage.last(ownerId)]).then(([, id]) => {
      if (!current) return;
      setLast(id);
    }).catch((reason: unknown) => { if (current) setError(assessmentErrorText(reason)); });
    return () => { current = false; };
  }, [ownerId, preparation]);

  const prepare = async () => {
    if (busy || !online) return;
    const value = selectedMode === 'diagnostic' ? 65 : Number(selectedMinutes);
    if (selectedMode === 'exam' && (!selectedMinutes.trim() || !Number.isInteger(value) || value < 15 || value > 180)) {
      setDurationError(true);
      duration.current?.focus();
      return;
    }
    setIdentifying(true);
    setError(null);
    try {
      const id = await prepareAssessment(selectedMode, value, deviceId);
      // Leaving via normal browser/global navigation is never blocked or undone.
      if (window.location.hash.split('?')[0] === '#/assessment') navigate(`/assessment/${encodeURIComponent(id)}`);
    } catch (reason) { setError(assessmentErrorText(reason)); }
    finally { setIdentifying(false); }
  };

  return <>
    <PageHeading title="Диагностика и пробник" description="13 задач первой части. Ответы и разбор появятся после завершения варианта." />
    {error && <ErrorNotice message={error} retry={online ? () => void prepare() : undefined} />}
    {!online && <p className="notice" role="status">Вы без сети. Подготовка нового варианта требует сервера. Сохранённый вариант можно открыть ниже.</p>}
    {pending && <p className="notice">Подготовка ещё не подтверждена. Повторная отправка продолжит тот же вариант с прежними настройками.</p>}
    <div className="assessment-setup-layout">
      <form className="worksheet assessment-setup" noValidate onSubmit={(event) => { event.preventDefault(); void prepare(); }}>
        <h2>Настройка варианта</h2>
        <fieldset disabled={busy || Boolean(pending)}>
          <legend>Режим</legend>
          <div className="assessment-modes segmented">
            <label className={selectedMode === 'diagnostic' ? 'is-selected' : ''}>
              <input type="radio" name="assessment-mode" value="diagnostic" checked={selectedMode === 'diagnostic'} onChange={() => { setMode('diagnostic'); setDurationError(false); }} />
              <span><strong>Диагностика</strong><span>13 задач без таймера</span></span>
            </label>
            <label className={selectedMode === 'exam' ? 'is-selected' : ''}>
              <input type="radio" name="assessment-mode" value="exam" checked={selectedMode === 'exam'} onChange={() => setMode('exam')} />
              <span><strong>Пробник</strong><span>13 задач с лимитом</span></span>
            </label>
          </div>
          {selectedMode === 'exam' ? <div className="assessment-duration">
            <label htmlFor="assessment-minutes">Лимит тренажёра, минут</label>
            <input ref={duration} id="assessment-minutes" name="duration_minutes" type="number" inputMode="numeric" autoComplete="off" min={15} max={180} step={1} value={selectedMinutes} onChange={(event) => { setMinutes(event.target.value); setDurationError(false); }} aria-invalid={durationError} aria-describedby="assessment-duration-help assessment-duration-error" />
            {/* viora-allow: caps-shouting The institute's official acronym is intentional. */}
            <p id="assessment-duration-help">От 15 до 180 минут, по умолчанию 65. Это учебный лимит тренажёра, не регламент ФИПИ.</p>
            <p id="assessment-duration-error" className="assessment-field-error" role={durationError ? 'alert' : undefined}>{durationError ? 'Укажите целое число минут от 15 до 180.' : ''}</p>
          </div> : <p className="assessment-mode-description">Решайте в своём темпе. Можно выйти и вернуться к тому же варианту.</p>}
        </fieldset>
        <Button type="submit" variant="primary" disabled={busy || !online} aria-busy={busy}>{busy ? 'Сохраняем 13 условий…' : pending ? 'Повторить подготовку' : 'Подготовить 13 задач'}<ArrowRight aria-hidden="true" /></Button>
        <p className="assessment-start-note">Сначала все условия сохранятся на устройстве. Начало вы подтвердите отдельно.</p>
      </form>
      <aside className="assessment-rules" aria-labelledby="assessment-rules-title">
        <h2 id="assessment-rules-title">Самостоятельное решение</h2>
        <dl className="assessment-rule-ledger">
          <div><dt><FileText aria-hidden="true" />Все 13 номеров</dt><dd>По одной задаче на номер. Между задачами можно свободно переходить.</dd></div>
          <div><dt><Clock aria-hidden="true" />Время пробника</dt><dd>Отсчитывается по серверу, включая свёрнутую вкладку и время без сети.</dd></div>
          <div><dt>Одна итоговая запись</dt><dd>Учитывается последний ответ. После завершения менять его нельзя.</dd></div>
        </dl>
        <p>Во время варианта доступны условия и поле ответа. Проверка и разбор откроются после отправки итогового снимка.</p>
      </aside>
    </div>
    {last && <section className="assessment-resume" aria-labelledby="assessment-resume-title"><h2 id="assessment-resume-title">Сохранённый вариант</h2><p>Последний открытый вариант этого профиля.</p><ActionLink href={`/assessment/${encodeURIComponent(last)}`}>Открыть вариант</ActionLink></section>}
    <p className="assessment-content-note">Авторские демозадачи. Учебный результат из 13 не переводится в полный тестовый балл ЕГЭ.</p>
  </>;
}
