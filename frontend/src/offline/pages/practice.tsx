import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ChevronDown, RotateCcw } from 'lucide-react';
import { Button } from '../../components/ui';
import type { OfflineRuntime } from '../practice';
import { LocalCourseNote, OfflineFailure, OfflineHeading } from './shared';
import type { Course, Failure, RuntimeState, StartOptions } from './shared';
import { acknowledgeOperation, failure, operationKey, readOperation, writeOperation } from './operations';
import type { PendingOperation } from './operations';

type Filter = { slots: number[]; length: 5 | 10 | 20; skill: string; family: string; difficulty: '' | '1' | '2' | '3'; repeat: string | null };

function initialFilter(course: Course, query: URLSearchParams): Filter {
  const slots = (query.get('slots') ?? '').split(',').map(Number).filter((number) => course.profile.slots.some((slot) => slot.number === number));
  const skill = (query.get('skills') ?? '').split(',')[0] ?? '';
  const family = (query.get('families') ?? '').split(',')[0] ?? '';
  const difficulty = query.get('difficulty');
  return {
    slots: [...new Set(slots)],
    length: query.get('length') === '10' ? 10 : query.get('length') === '20' ? 20 : 5,
    skill, family, difficulty: difficulty === '1' || difficulty === '2' || difficulty === '3' ? difficulty : '',
    repeat: query.get('repeat') || null,
  };
}

function toBody(filter: Filter): StartOptions {
  return {
    mode: 'practice', slots: [...filter.slots].sort((a, b) => a - b), length: filter.length,
    skill_ids: filter.skill ? [filter.skill] : [], family_ids: filter.family ? [filter.family] : [],
    difficulty: filter.difficulty ? Number(filter.difficulty) as 1 | 2 | 3 : null,
    selection: 'balanced', repeat_task_id: filter.repeat, until_stopped: false, target_minutes: null,
  };
}

function validPending(value: PendingOperation<StartOptions>, course: Course) {
  const body = value.body;
  return body && body.mode === 'practice' && [5, 10, 20].includes(body.length) && Array.isArray(body.slots)
    && body.slots.every((number) => course.profile.slots.some((slot) => slot.number === number));
}

export default function PracticePage({ course, runtime, deviceState, storageError, retryStorage, checkingStorage, query }: {
  course: Course; runtime: OfflineRuntime; deviceState: RuntimeState | null; storageError: Failure | null;
  retryStorage: () => void; checkingStorage: boolean; query: URLSearchParams;
}) {
  const [filter, setFilter] = useState(() => initialFilter(course, query));
  const [pending, setPending] = useState<PendingOperation<StartOptions> | null>(null);
  const [operationError, setOperationError] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  const [exhausted, setExhausted] = useState(false);
  const [localState, setLocalState] = useState(deviceState);
  const pendingRef = useRef<PendingOperation<StartOptions> | null>(null);
  const busyRef = useRef(false);
  const owner = deviceState?.owner ?? null;

  useEffect(() => {
    let stopped = false;
    void runtime.state().then((state) => {
      if (!stopped) setLocalState(state);
    }).catch((error: unknown) => {
      if (!stopped) setOperationError(failure(error));
    });
    return () => { stopped = true; };
  }, [runtime]);

  useEffect(() => {
    if (!owner) return;
    let stopped = false;
    void Promise.resolve().then(() => {
      const stored = readOperation<StartOptions>('start', owner);
      if (stored && !validPending(stored, course)) throw { code: 'ui_queue_invalid', message: 'Сохранённые параметры занятия повреждены. История не удалялась; попробуйте снова прочитать данные.' };
      if (!stopped && stored) {
        pendingRef.current = stored;
        setPending(stored);
      }
    }).catch((error: unknown) => {
      if (!stopped) setOperationError(failure(error));
    });
    return () => { stopped = true; };
  }, [owner, course]);

  const slots = course.profile.slots;
  const selectedSlots = slots.filter((slot) => filter.slots.length === 0 || filter.slots.includes(slot.number));
  const allSkills = selectedSlots.flatMap((slot) => slot.skills);
  const skills = allSkills.filter((skill, index) => allSkills.findIndex((item) => item.id === skill.id) === index);
  const slotTasks = course.tasks.filter((task) => filter.slots.length === 0 || filter.slots.includes(task.slot));
  const familyTasks = slotTasks.filter((task) => !filter.skill || task.skill_ids.includes(filter.skill));
  const familyIds = [...new Set(familyTasks.map((task) => task.family_id))];
  const families = familyIds.map((id) => {
    const lesson = course.lessons.find((item) => item.family_ids?.includes(id));
    const task = familyTasks.find((item) => item.family_id === id)!;
    return { id, title: lesson?.title ?? task.title };
  });
  const matching = slotTasks.filter((task) => (!filter.skill || task.skill_ids.includes(filter.skill))
    && (!filter.family || task.family_id === filter.family)
    && (!filter.difficulty || task.difficulty === Number(filter.difficulty)));
  const repeatTask = filter.repeat ? course.tasks.find((task) => task.id === filter.repeat) : null;
  const activeId = localState?.active_session_id ?? deviceState?.active_session_id;
  const locked = busy || Boolean(pending) || checkingStorage;
  const fatalQueue = operationError?.code === 'ui_queue_invalid' || operationError?.code === 'ui_queue_acknowledgement_failed';
  const mayStart = Boolean(owner) && !storageError && !checkingStorage && !fatalQueue;

  const changeSlots = (number: number) => {
    setOperationError(null);
    setExhausted(false);
    setFilter((current) => ({ ...current, slots: current.slots.includes(number) ? current.slots.filter((item) => item !== number) : [...current.slots, number], skill: '', family: '', repeat: null }));
  };

  const start = async () => {
    if (busyRef.current || !owner || !mayStart) return;
    busyRef.current = true;
    setBusy(true);
    setExhausted(false);
    setOperationError(null);
    let operation = pendingRef.current;
    try {
      const stored = readOperation<StartOptions>('start', owner);
      if (stored) {
        if (!validPending(stored, course)) throw { code: 'ui_queue_invalid', message: 'Сохранённые параметры занятия повреждены. Не начинайте вторую копию занятия.' };
        operation = stored;
      }
      if (!operation) operation = { version: '1', key: operationKey(), body: toBody(filter) };
      writeOperation('start', owner, operation);
      pendingRef.current = operation;
      setPending(operation);
      const session = await runtime.start(operation.body, operation.key);
      acknowledgeOperation('start', owner);
      pendingRef.current = null;
      setPending(null);
      window.location.hash = `/session/${encodeURIComponent(session.id)}`;
    } catch (error) {
      const value = failure(error);
      const empty = /(?:exhaust|empty_bank|no_tasks|insufficient_tasks|not_enough_tasks)/i.test(value.code);
      setExhausted(empty);
      setOperationError(value);
      if (empty) {
        // Exhaustion is a definite failed selection, not an uncertain commit.
        // Its next action is a new explicit selection or a labeled repeat.
        try {
          acknowledgeOperation('start', owner);
          pendingRef.current = null;
          setPending(null);
        } catch (storageFailure) {
          setOperationError(failure(storageFailure));
        }
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const recoveryRetry = () => {
    setOperationError(null);
    retryStorage();
  };

  return <>
    <OfflineHeading title="Практика">Выберите номера и длину серии. Проверка, помощь и история работают на устройстве.</OfflineHeading>
    <div className="offline-practice-layout">
      <section className="worksheet offline-start-sheet" aria-labelledby="start-title">
        <h2 id="start-title">Начать с пяти задач</h2>
        <p className="muted">Пустой выбор номеров означает все 13. Узкие фильтры необязательны.</p>
        {activeId && <div className="notice offline-resume-note"><div><strong>Есть незавершённое занятие</strong>
          <p>Черновик и выбранная задача сохранены на этом устройстве.</p>
          <a className="text-link" href={`#/session/${encodeURIComponent(activeId)}`}>Продолжить занятие<ArrowRight aria-hidden="true" /></a>
        </div></div>}
        {storageError && <OfflineFailure error={storageError} title="Хранилище недоступно" retry={retryStorage} retryLabel="Проверить хранилище снова" />}
        {pending && <div className="notice"><div><strong>Начало занятия ещё не подтверждено</strong>
          <p>Повтор использует тот же ключ и параметры: {pending.body.length} задач, {pending.body.slots.length ? `номера ${pending.body.slots.join(', ')}` : 'все номера'}. Второе занятие не создаётся.</p>
        </div></div>}
        {operationError && <OfflineFailure error={operationError} title={exhausted ? 'Новых условий по выбору не осталось' : 'Не удалось начать занятие'}
          retry={fatalQueue || !owner ? recoveryRetry : pending ? () => void start() : undefined}
          retryLabel={pending ? 'Повторить начало занятия' : 'Прочитать историю снова'} />}
        <form onSubmit={(event) => { event.preventDefault(); void start(); }}>
          <fieldset disabled={locked || Boolean(storageError)} className="offline-start-fields">
            <fieldset className="offline-length-picker"><legend>Длина серии</legend>
              <div className="offline-length-options">{([5, 10, 20] as const).map((length) => <label key={length} className={filter.length === length ? 'is-selected' : ''}>
                <input type="radio" name="length" value={length} checked={filter.length === length} onChange={() => setFilter((current) => ({ ...current, length }))} />
                <strong>{length}</strong><span>задач</span>
              </label>)}</div>
            </fieldset>
            <fieldset className="offline-slot-picker"><legend>Номера первой части</legend>
              <div className="offline-position-rail offline-position-choices">{slots.map((slot) => <label key={slot.number} className={filter.slots.includes(slot.number) ? 'is-selected' : ''}>
                <input type="checkbox" name="slot" value={slot.number} checked={filter.slots.includes(slot.number)} onChange={() => changeSlots(slot.number)}
                  aria-label={`Номер ${slot.number}. ${slot.title}`} /><span>{slot.number}</span>
              </label>)}</div>
              <div className="offline-selection-line"><p>{filter.slots.length ? `Выбраны номера: ${[...filter.slots].sort((a, b) => a - b).join(', ')}.` : 'Выбраны все 13 номеров.'}</p>
                {filter.slots.length > 0 && <Button variant="quiet" onClick={() => { setFilter((current) => ({ ...current, slots: [], skill: '', family: '', repeat: null })); setExhausted(false); setOperationError(null); }}>Все номера</Button>}
              </div>
              {filter.slots.length > 0 && <ul className="offline-selected-topics">{slots.filter((slot) => filter.slots.includes(slot.number)).map((slot) => <li key={slot.number}>№ {slot.number}. {slot.title}</li>)}</ul>}
            </fieldset>
            <details className="offline-filter-details" open={Boolean(filter.skill || filter.family || filter.difficulty)}>
              <summary>Навык, тип и сложность <span className="muted">необязательно</span><ChevronDown aria-hidden="true" /></summary>
              <div className="offline-filter-fields">
                <label htmlFor="practice-skill">Навык<select id="practice-skill" name="skill" value={filter.skill} onChange={(event) => { setFilter((current) => ({ ...current, skill: event.target.value, family: '' })); setExhausted(false); setOperationError(null); }}>
                  <option value="">Любой навык</option>{skills.map((skill) => <option value={skill.id} key={skill.id}>{skill.title}</option>)}
                </select></label>
                <label htmlFor="practice-family">Тип задачи<select id="practice-family" name="family" value={filter.family} onChange={(event) => { setFilter((current) => ({ ...current, family: event.target.value })); setExhausted(false); setOperationError(null); }}>
                  <option value="">Любой тип</option>{families.map((family) => <option value={family.id} key={family.id}>{family.title}</option>)}
                </select></label>
                <label htmlFor="practice-difficulty">Сложность<select id="practice-difficulty" name="difficulty" value={filter.difficulty} onChange={(event) => { setFilter((current) => ({ ...current, difficulty: event.target.value as Filter['difficulty'] })); setExhausted(false); setOperationError(null); }}>
                  <option value="">Любая сложность</option><option value="1">1 · Начальная</option><option value="2">2 · Средняя</option><option value="3">3 · Повышенная</option>
                </select></label>
              </div>
            </details>
          </fieldset>
          {repeatTask && <div className="notice"><div><strong>Явный повтор знакомого условия</strong><p>«{repeatTask.title}». Этот повтор не добавляет второе самостоятельное достижение.</p></div></div>}
          {filter.repeat && !repeatTask && <OfflineFailure error="Задача для повтора отсутствует в этом пакете. Выберите новые условия." />}
          <div className="offline-start-action"><Button type="submit" variant="primary" disabled={busy || !mayStart || (!pending && (matching.length === 0 || Boolean(filter.repeat && !repeatTask)))} aria-busy={busy}>
            {busy ? 'Начинаем…' : 'Начать занятие'}<ArrowRight aria-hidden="true" />
          </Button><p className="muted">{matching.length} условий в пакете подходят фильтрам. Знакомые за последние 30 дней исключаются при старте.</p></div>
        </form>
        {!pending && (exhausted || matching.length === 0) && <section className="offline-exhaustion" aria-labelledby="exhaustion-title">
          <h3 id="exhaustion-title">Банк конечный</h3><p>Приложение не подмешивает знакомые задачи молча. Расширьте выбор или откройте явно отмеченный повтор.</p>
          <a className="text-link" href="#/practice">Изменить выбор номеров</a>
          {matching.length > 0 && <details><summary>Выбрать условие для явного повтора</summary><ul className="offline-repeat-list">{matching.map((task) => <li key={task.id}>
            <a className="text-link" href={`#/practice?slots=${task.slot}&length=5&repeat=${encodeURIComponent(task.id)}`}><RotateCcw aria-hidden="true" />№ {task.slot}. {task.title}</a>
          </li>)}</ul></details>}
        </section>}
      </section>
      <aside className="offline-practice-aside" aria-labelledby="local-course-title">
        <h2 id="local-course-title">Спокойная учебная практика</h2>
        <p>{course.lessons.length} уроков и {course.tasks.length} задач включены в пакет. Откройте любой урок до первого занятия.</p>
        <ul><li>Три подсказки открываются по очереди.</li><li>Числовой ответ можно исправить. Первый остаётся в истории.</li><li>Занятие и его итог сохраняются на устройстве.</li></ul>
        <a className="text-link" href="#/lessons">Выбрать урок<ArrowRight aria-hidden="true" /></a>
        <LocalCourseNote />
      </aside>
    </div>
  </>;
}
