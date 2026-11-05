import { useEffect, useState } from 'react';
import { ArrowRight, Check, LoaderCircle } from 'lucide-react';
import type { Profile, StartBody } from '../api/types';
import type { Curriculum } from '../app/curriculum';
import { errorText } from '../api/client';
import { storage } from '../storage/database';
import { startSession } from '../learning/start-session';
import { navigate, sessionPath } from '../app/router';
import { useOnline } from '../app/online';
import { Button, ErrorNotice } from './ui';
import { taskCount } from '../utils/format';
import { PracticeFilters } from './practice-filters';

export function StartPanel({ profile, curriculum, expanded = false, initialSlots, initialOptions }: {
  profile: Profile; curriculum?: Curriculum; expanded?: boolean; initialSlots?: number[]; initialOptions?: Partial<StartBody>;
}) {
  const [options, setOptions] = useState<StartBody>(() => ({
    length: 5, ...initialOptions, mode: 'practice',
    slots: initialOptions?.slots?.length ? initialOptions.slots : initialSlots?.length ? initialSlots : profile.slots.map((slot) => slot.number),
  }));
  const { length, slots } = options;
  const [pending, setPending] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const online = useOnline();

  useEffect(() => {
    let alive = true;
    void storage.pendingStart().then((saved) => {
      if (!alive || !saved) return;
      setPending(true);
      setOptions(saved.body);
    }).catch(() => {
      if (alive) setError('Не удалось открыть локальное хранилище. Разрешите сохранение данных в браузере.');
    }).finally(() => { if (alive) setRestoring(false); });
    return () => { alive = false; };
  }, []);

  const disabled = busy || pending || restoring;
  const change = (value: Partial<StartBody>) => setOptions((current) => ({ ...current, ...value }));
  const setSlots = (value: number[]) => change({ slots: value, family_ids: [], skill_ids: [], repeat_task_id: null });
  const toggle = (number: number) => setSlots(slots.includes(number) ? slots.filter((slot) => slot !== number) : [...slots, number].sort((a, b) => a - b));

  const start = async () => {
    if (busy || restoring) return;
    if (slots.length === 0) { setError('Выберите хотя бы один номер для занятия.'); return; }
    setBusy(true);
    setError(null);
    try {
      const id = await startSession(options);
      navigate(sessionPath(id));
    } catch (failure) {
      setError(errorText(failure));
      setPending(Boolean(await storage.pendingStart().catch(() => null)));
    } finally {
      setBusy(false);
    }
  };

  return <div className="start-panel">
    <fieldset className="length-picker" disabled={disabled}>
      <legend>Длина занятия</legend>
      <div className="segmented">{([5, 10, 20] as const).map((value) => <label key={value} className={length === value ? 'is-selected' : ''}>
        <input type="radio" name="length" value={value} checked={length === value} onChange={() => change({ length: value })} />
        <span><strong>{value}</strong> задач</span>
      </label>)}</div>
    </fieldset>

    {expanded ? <fieldset className="slot-picker" disabled={disabled}>
      <legend>Номера для практики</legend>
      <div className="selection-toolbar"><span>Выбрано: {slots.length} из {profile.slots.length}</span><Button variant="quiet" disabled={disabled} onClick={() => setSlots(slots.length === profile.slots.length ? [] : profile.slots.map((slot) => slot.number))}>{slots.length === profile.slots.length ? 'Снять выбор' : 'Выбрать все'}</Button></div>
      <div className="slot-options">{profile.slots.map((slot) => <label key={slot.id} className={`slot-option ${slots.includes(slot.number) ? 'is-selected' : ''}`}>
        <input type="checkbox" name="slot" value={slot.number} checked={slots.includes(slot.number)} onChange={() => toggle(slot.number)} />
        <span className="slot-number">{slot.number}</span><span className="slot-option__text"><strong>{slot.title}</strong><small>{taskCount(slot.available_tasks)} в банке</small></span>
        <Check className="selection-check" aria-hidden="true" />
      </label>)}</div>
    </fieldset> : <div className="selection-description"><p>Смешанная практика по {slots.length} номерам.</p><a className="text-link" href="#/practice">Выбрать номера</a></div>}

    {expanded && <PracticeFilters profile={profile} curriculum={curriculum} options={options} disabled={disabled} change={change} />}
    {options.repeat_task_id && <p className="notice">Явный повтор выбранной задачи. Он не считается новым независимым достижением. <Button variant="quiet" disabled={disabled} onClick={() => change({ repeat_task_id: null })}>Подобрать другой экземпляр</Button></p>}
    {pending && <p className="notice">Предыдущий запуск ещё не подтверждён. Кнопка повторит тот же запрос, а не создаст второе занятие.</p>}
    {error && <ErrorNotice message={error} />}
    {!online && <p className="notice">Для нового занятия нужна сеть. Ранее открытые уроки и сохранённое занятие доступны без неё.</p>}
    <Button variant="primary" onClick={() => void start()} disabled={busy || restoring || !online} aria-busy={busy}>
      {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : <ArrowRight aria-hidden="true" />}<span>{busy ? 'Подбираем задачи…' : 'Начать занятие'}</span>
    </Button>
    <p className="microcopy">Новые экземпляры из выбранных номеров. Если задач меньше, сервер явно сократит серию.</p>
  </div>;
}
