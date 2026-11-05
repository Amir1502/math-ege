import { useState } from 'react';
import { Button } from '../components/ui';
import { decodeWithdrawal } from './adapters';
import type { Withdrawal } from './types';
import type { EditorMutation } from './use-mutation';

export function WithdrawalForm({ taskId, taskRevision, mutation, disabled = false, onWithdrawn }: {
  taskId: string; taskRevision: string; mutation: EditorMutation; disabled?: boolean; onWithdrawn: (result: Withdrawal) => void;
}) {
  const [reason, setReason] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  return <details className="editor-disclosure editor-withdrawal">
    <summary>Снять ошибочную задачу с новой выдачи</summary>
    <p>Задача <code>{taskId}</code>, редакция <code>{taskRevision}</code>, перестанет выдаваться в новых занятиях. Затронутые попытки исключаются из освоения с этой причиной; исходные ответы и итоговые баллы сохраняются.</p>
    <form onSubmit={event => {
      event.preventDefault();
      if (reason.trim().length < 5) { setProblem('Укажите причину снятия минимум пятью символами.'); return; }
      void mutation.run(`/tasks/${encodeURIComponent(taskId)}/withdraw`, 'POST', { task_revision: taskRevision, reason: reason.trim() }, value => onWithdrawn(decodeWithdrawal(value)));
    }}>
      <div className="editor-field"><label htmlFor="editor-withdrawal-reason">Причина для журнала и уведомления ученику</label>
        <textarea id="editor-withdrawal-reason" value={reason} onChange={event => { setReason(event.target.value); setProblem(null); }} required minLength={5} maxLength={2000} rows={3}
          disabled={disabled || mutation.locked} aria-invalid={Boolean(problem)} aria-describedby={problem ? 'editor-withdrawal-error' : undefined} />
        {problem && <p id="editor-withdrawal-error" className="editor-inline-error" role="alert">{problem}</p>}
      </div>
      <Button type="submit" className="editor-danger-button" disabled={disabled || mutation.locked}>Снять задачу и записать причину</Button>
    </form>
  </details>;
}
