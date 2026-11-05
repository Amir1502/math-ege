import { useRef, useState } from 'react';
import { ArrowRight, LoaderCircle } from 'lucide-react';
import { navigate, sessionPath } from '../app/router';
import { useOnline } from '../app/online';
import { Button, ErrorNotice } from '../components/ui';
import { formatDuration, taskCount } from '../utils/format';
import { identity } from '../storage/identity';
import { useLearningIdentity, useTimePlan } from './hooks';
import { beginPlannedPractice } from './planned-start';
import { learningError } from './resource';
import { mixedPracticePath } from './view-models';
import type { PlanMinutes } from './types';

export function TimePlanChooser() {
  const [minutes, setMinutes] = useState<PlanMinutes>(10);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ owner: string | null; message: string } | null>(null);
  const locked = useRef(false);
  const owner = useLearningIdentity();
  const plan = useTimePlan(minutes);
  const online = useOnline();

  const start = async () => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const id = await beginPlannedPractice(minutes);
      if (!identity.getSnapshot().changing) navigate(sessionPath(id));
    } catch (error) {
      setFailure({ owner: identity.current(), message: learningError(error) });
    } finally {
      locked.current = false;
      setBusy(false);
    }
  };

  return <div className="start-panel learning-time-plan">
    <fieldset className="length-picker" disabled={busy}>
      <legend>Сколько времени есть сегодня?</legend>
      <div className="segmented">{([10, 20, 30] as const).map((value) => <label key={value} className={minutes === value ? 'is-selected' : ''}>
        <input type="radio" name="plan-minutes" value={value} checked={minutes === value} onChange={() => { setMinutes(value); setFailure(null); }} />
        <span><strong>{value}</strong> мин</span>
      </label>)}</div>
    </fieldset>
    <div className="learning-plan-estimate" aria-live="polite" aria-busy={plan.loading}>
      {plan.data ? <><p><strong>{taskCount(plan.data.length)}</strong>, ориентировочно {formatDuration(plan.data.estimated_seconds)}.</p><p className="microcopy">Смешанная практика: слабые навыки, повторение и новые типы. Номера: {plan.data.slots.join(', ') || 'подбор недоступен'}.</p></>
        : <p className="muted">{plan.loading ? 'Оцениваем объём занятия…' : 'Подберём объём по оценкам задач. Когда накопятся ответы, план учтёт ваш темп.'}</p>}
    </div>
    {plan.data?.notice && <p className="notice">{plan.data.notice}</p>}
    {plan.error && <ErrorNotice message={plan.error} retry={plan.retry} />}
    {failure?.owner === owner && <ErrorNotice message={failure.message} retry={() => void start()} />}
    {!online && <p className="notice">Для подбора нового занятия нужна сеть. Сохранённое занятие можно продолжить по ссылке выше.</p>}
    <Button variant="primary" onClick={() => void start()} disabled={busy || !online || plan.data?.slots.length === 0} aria-busy={busy}>
      {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : <ArrowRight aria-hidden="true" />}
      <span>{busy ? 'Подбираем задачи…' : 'Начать занятие'}</span>
    </Button>
    <a className="text-link learning-plan-settings" href={`#${plan.data ? mixedPracticePath(plan.data) : '/practice?selection=mixed'}`}>Настроить серию по задачам</a>
    <p className="microcopy">Время ориентировочное: текущая задача не прервётся по истечении выбранных минут.</p>
  </div>;
}
