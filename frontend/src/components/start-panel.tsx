import { useEffect, useState } from 'react';
import { ArrowRight, Check, LoaderCircle } from 'lucide-react';
import type { Profile, StartBody } from '../api/types';
import { errorText } from '../api/client';
import { storage } from '../storage/database';
import { startSession } from '../learning/start-session';
import { navigate, sessionPath } from '../app/router';
import { useOnline } from '../app/online';
import { Button, ErrorNotice } from './ui';
import { taskCount } from '../utils/format';

export function StartPanel({ profile, expanded = false, initialSlots }: { profile: Profile; expanded?: boolean; initialSlots?: number[] }) {
  const [length, setLength] = useState<5 | 10 | 20>(5);
  const [slots, setSlots] = useState(() => initialSlots?.length ? initialSlots : profile.slots.map((slot) => slot.number));
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
      setLength(saved.body.length);
      setSlots(saved.body.slots);
    }).catch(() => {
      if (alive) setError('Не удалось открыть локальное хранилище. Разрешите сохранение данных в браузере.');
    }).finally(() => { if (alive) setRestoring(false); });
    return () => { alive = false; };
  }, []);

  const disabled = busy || pending || restoring;
  const toggle = (number: number) => setSlots((current) => current.includes(number) ? current.filter((slot) => slot !== number) : [...current, number].sort((a, b) => a - b));

  const start = async () => {
    if (busy || restoring) return;
    if (slots.length === 0) { setError('Выберите хотя бы один номер для занятия.'); return; }
    setBusy(true);
    setError(null);
    try {
      const body: StartBody = { slots, length, mode: 'practice' };
      const id = await startSession(body);
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
        <input type="radio" name="length" value={value} checked={length === value} onChange={() => setLength(value)} />
        <span><strong>{value}</strong> задач</span>
      </label>)}</div>
    </fieldset>

    {expanded ? <fieldset className="slot-picker" disabled={disabled}>
      <legend>Номера для практики</legend>
      <div className="selection-toolbar"><span>Выбрано: {slots.length} из {profile.slots.length}</span><Button variant="quiet" disabled={disabled} onClick={() => setSlots(slots.length === profile.slots.length ? [] : profile.slots.map((slot) => slot.number))}>{slots.length === profile.slots.length ? 'Снять выбор' : 'Выбрать все'}</Button></div>
      <div className="slot-options">{profile.slots.map((slot) => <label key={slot.id} className={`slot-option ${slots.includes(slot.number) ? 'is-selected' : ''}`}>
        <input type="checkbox" checked={slots.includes(slot.number)} onChange={() => toggle(slot.number)} />
        <span className="slot-number">{slot.number}</span><span className="slot-option__text"><strong>{slot.title}</strong><small>{taskCount(slot.available_tasks)} в демобанке</small></span>
        <Check className="selection-check" aria-hidden="true" />
      </label>)}</div>
    </fieldset> : <div className="selection-description"><p>Смешанная практика по {slots.length} номерам.</p><a className="text-link" href="#/practice">Выбрать номера</a></div>}

    {pending && <p className="notice">Предыдущий запуск ещё не подтверждён. Кнопка повторит тот же запрос, а не создаст второе занятие.</p>}
    {error && <ErrorNotice message={error} />}
    {!online && <p className="notice">Для нового занятия нужна сеть. Ранее открытые уроки и сохранённое занятие доступны без неё.</p>}
    <Button variant="primary" onClick={() => void start()} disabled={busy || restoring || !online} aria-busy={busy}>
      {busy ? <LoaderCircle className="spin" aria-hidden="true" /> : <ArrowRight aria-hidden="true" />}<span>{busy ? 'Подбираем задачи…' : 'Начать занятие'}</span>
    </Button>
    <p className="microcopy">Новые экземпляры из выбранных номеров. Если задач меньше, сервер явно сократит серию.</p>
  </div>;
}
