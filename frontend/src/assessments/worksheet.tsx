import { useEffect, useRef } from 'react';
import { ArrowLeft, ArrowRight, Minus } from 'lucide-react';
import { TaskContent } from '../components/task-content';
import { Button } from '../components/ui';
import type { AssessmentController } from './controller';
import type { AssessmentRecord } from './model';

export function AssessmentWorksheet({ record, controller, readOnly, onFinish }: {
  record: AssessmentRecord; controller: AssessmentController; readOnly: boolean; onFinish(): void;
}) {
  const task = record.view.tasks[record.current_index];
  const draft = record.drafts[task.id];
  const heading = useRef<HTMLHeadingElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const previousTask = useRef(task.id);
  const last = record.current_index === 12;
  useEffect(() => {
    if (previousTask.current !== task.id) heading.current?.focus();
    previousTask.current = task.id;
  }, [task.id]);

  const insert = (symbol: '−' | ',') => {
    const field = input.current;
    if (!field || readOnly) return;
    const start = field.selectionStart ?? draft.answer.length;
    const end = field.selectionEnd ?? start;
    const next = symbol === '−'
      ? (/^[-−]/.test(draft.answer) ? draft.answer.slice(1) : `−${draft.answer}`)
      : draft.answer.slice(0, start) + symbol + draft.answer.slice(end);
    if (next.length > 64) return;
    controller.edit(next);
    field.focus();
    requestAnimationFrame(() => field.setSelectionRange(symbol === '−' ? next.length : start + 1, symbol === '−' ? next.length : start + 1));
  };

  return <>
    <div className="assessment-position"><p>Задача <strong>{record.current_index + 1}</strong> из 13</p><p>Записано ответов: <strong>{Object.values(record.drafts).filter((answer) => answer.answer.trim()).length}</strong></p></div>
    <nav className="task-position-rail assessment-rail" aria-label="Задачи варианта">
      {record.view.tasks.map((item, index) => {
        const filled = Boolean(record.drafts[item.id]?.answer.trim());
        return <button type="button" key={item.id} aria-current={index === record.current_index ? 'step' : undefined}
          className={filled ? 'has-answer' : ''}
          aria-label={`Задача ${index + 1}, номер ${item.slot}, ${filled ? 'ответ записан' : 'пока пусто'}`}
          onClick={() => controller.goTo(index)}>{index + 1}<span className="assessment-answer-mark" aria-hidden="true" /></button>;
      })}
    </nav>
    <section className="worksheet task-sheet assessment-task" aria-labelledby="assessment-task-title">
      <div className="task-title"><h2 ref={heading} id="assessment-task-title" tabIndex={-1}>№ {task.slot}. {task.title}</h2><span className="demo-label">Демозадача</span></div>
      <TaskContent task={task} />
      <form className="answer-form" onSubmit={(event) => { event.preventDefault(); if (!readOnly) { if (last) onFinish(); else controller.goTo(record.current_index + 1); } }}>
        <label htmlFor="assessment-answer">Ответ</label>
        <div className="answer-input-row">
          <input ref={input} id="assessment-answer" name="answer" type="text" inputMode="decimal" enterKeyHint={last ? 'done' : 'next'} autoComplete="off" autoCapitalize="off" spellCheck={false} maxLength={64}
            value={draft.answer} onChange={(event) => controller.edit(event.target.value)} readOnly={readOnly} aria-describedby="assessment-answer-help assessment-answer-status" />
          <Button className="symbol-button" disabled={readOnly} aria-label="Вставить или убрать минус" onClick={() => insert('−')}><Minus aria-hidden="true" /></Button>
          <Button className="symbol-button" disabled={readOnly} aria-label="Вставить запятую" onClick={() => insert(',')}>,</Button>
        </div>
        <p id="assessment-answer-help" className="assessment-answer-help">Целое число или конечная десятичная дробь. Например: −2; 0,5. Без единиц измерения.</p>
        <p id="assessment-answer-status" className="assessment-answer-help">{readOnly ? 'Ответ доступен только для чтения.' : 'Ответ сохраняется как черновик. Правильность пока не показывается.'}</p>
        <div className="assessment-task-actions">
          <Button disabled={record.current_index === 0} onClick={() => controller.goTo(record.current_index - 1)}><ArrowLeft aria-hidden="true" />Предыдущая</Button>
          {last ? <Button variant="primary" disabled={readOnly} onClick={onFinish}>Завершить вариант</Button>
            : <Button variant="primary" onClick={() => controller.goTo(record.current_index + 1)}>Следующая задача<ArrowRight aria-hidden="true" /></Button>}
        </div>
      </form>
    </section>
  </>;
}
