import { BookOpen, Lightbulb, ChevronDown } from 'lucide-react';
import type { PublicTask } from '../api/types';
import type { SessionController } from '../learning/session-controller';
import type { SessionSnapshot } from '../learning/model';
import { Button } from './ui';
import { RichText } from './math';

export function TaskHelp({ task, controller, state }: { task: PublicTask; controller: SessionController; state: SessionSnapshot }) {
  const record = state.record!;
  const help = record.session.help[task.id];
  const disabled = Boolean(state.busy || record.pending_attempt || record.pending_finish || state.accessDenied);
  const nextLevel = (help?.hints.length ?? 0) + 1;
  const titles = ['Направление мысли', 'Формула или модель', 'Следующий шаг'];
  return <aside className="task-help" aria-labelledby="help-title"><h2 id="help-title"><Lightbulb aria-hidden="true" />Если нужна опора</h2><p className="muted">Помощь до первого ответа отметится в результате. Это часть учёбы, не штраф.</p>
    <div className="hint-levels">{([1, 2, 3] as const).filter((level) => level <= task.hint_count).map((level) => {
      const hint = help?.hints.find((item) => item.level === level);
      return <section className="hint-level" key={level}>{hint ? <><h3>Подсказка {level}</h3><p><RichText text={hint.text} /></p></> : <Button variant="quiet" disabled={disabled || level !== nextLevel} onClick={() => void controller.actions.hint(level)}><span className="hint-number">{level}</span><span><strong>Подсказка {level}</strong><small>{titles[level - 1]}</small></span><ChevronDown aria-hidden="true" /></Button>}</section>;
    })}</div>
    <section className="full-solution"><h3>Полное решение</h3>{help?.solution ? <div aria-live="polite"><ol className="solution-steps">{help.solution.steps.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol><p>Ответ: <strong>{help.solution.answer}</strong></p></div> : <><p>Откроет все шаги и ответ. До первой попытки это считается помощью.</p><Button disabled={disabled} onClick={() => void controller.actions.solution()}><BookOpen aria-hidden="true" />Показать решение</Button></>}
    </section><a className="text-link" href={`#/topics/${task.slot}`}>Вернуться к теории</a>
  </aside>;
}
