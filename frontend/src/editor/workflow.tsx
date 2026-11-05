import { useState } from 'react';
import { Button } from '../components/ui';
import { decodeRevision } from './adapters';
import { actionLabels, statusLabels } from './types';
import type { Capability, Revision, Withdrawal } from './types';
import type { EditorMutation } from './use-mutation';
import { WithdrawalForm } from './withdrawal';

const transitions: Capability[] = ['submit', 'approve', 'publish', 'return_to_draft', 'fork', 'archive'];
const auditLabels: Record<string, string> = { ...actionLabels, create: 'Создан черновик', supersede: 'Заменено новой редакцией' };
const dates = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' });

export function Workflow({ record, actorId, mutation, dirty, onUpdated, onWithdrawn }: {
  record: Revision; actorId: string; mutation: EditorMutation; dirty: boolean;
  onUpdated: (record: Revision) => void; onWithdrawn: (result: Withdrawal) => void;
}) {
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [formula, setFormula] = useState(false);
  const [constraints, setConstraints] = useState(false);
  const actions = transitions.filter(action => record.capabilities.includes(action));
  const disabled = mutation.locked || dirty;
  const run = (action: Capability) => {
    if (disabled) return;
    if (note.trim().length < 5) { setProblem('Напишите решение рецензента или причину действия минимум пятью символами.'); document.getElementById('editor-workflow-note')?.focus(); return; }
    if (action === 'approve' && record.kind === 'template' && (!formula || !constraints)) {
      setProblem('Перед утверждением шаблона подтвердите проверку формул и ограничений.'); return;
    }
    const body = { expected_revision: record.revision, note: note.trim(),
      ...(action === 'approve' ? { reviewed_formula: formula, reviewed_constraints: constraints } : {}) };
    void mutation.run(`/revisions/${encodeURIComponent(record.id)}/${action}`, 'POST', body, value => onUpdated(decodeRevision(value)));
  };
  return <section className="editor-workflow" aria-labelledby="editor-workflow-heading">
    <h3 id="editor-workflow-heading">Проверка и публикация</h3>
    <dl className="editor-ledger editor-attribution">
      <div><dt>Автор{record.author_id === actorId ? ' (вы)' : ''}</dt><dd><code>{record.author_id}</code></dd></div>
      <div><dt>Рецензент{record.reviewer_id === actorId ? ' (вы)' : ''}</dt><dd>{record.reviewer_id ? <code>{record.reviewer_id}</code> : 'Ещё не назначен'}</dd></div>
      <div><dt>Последнее изменение</dt><dd>{record.change_note}</dd></div>
      {record.review_note && <div><dt>Решение рецензента</dt><dd>{record.review_note}</dd></div>}
    </dl>
    {record.author_id === actorId && record.status === 'review' && <p className="editor-readonly">Предметную проверку выполняет другой авторизованный методист. Ваша редакция ожидает его решения.</p>}
    {dirty && <p className="editor-readonly">Сначала сохраните рабочий JSON. Действия ниже относятся к сохранённой редакции.</p>}
    {actions.length > 0 && <>
      <div className="editor-field"><label htmlFor="editor-workflow-note">Решение или причина действия</label>
        <textarea id="editor-workflow-note" value={note} onChange={event => { setNote(event.target.value); setProblem(null); }} rows={3} maxLength={2000} disabled={disabled}
          aria-invalid={Boolean(problem)} aria-describedby={problem ? 'editor-workflow-error' : undefined} />
        {problem && <p id="editor-workflow-error" className="editor-inline-error" role="alert">{problem}</p>}
      </div>
      {record.kind === 'template' && record.capabilities.includes('approve') && <fieldset disabled={disabled}>
        <legend>Предметная проверка шаблона</legend>
        <label className="editor-check"><input type="checkbox" checked={formula} onChange={event => setFormula(event.target.checked)} />Формулы проверены мной</label>
        <label className="editor-check"><input type="checkbox" checked={constraints} onChange={event => setConstraints(event.target.checked)} />ОДЗ и ограничения проверены мной</label>
      </fieldset>}
      <div className="row-actions editor-workflow-actions">{actions.map(action => <Button key={action} disabled={disabled}
        variant={['approve', 'publish'].includes(action) ? 'primary' : action === 'fork' || action === 'archive' ? 'quiet' : 'secondary'}
        onClick={() => run(action)}>{actionLabels[action]}</Button>)}</div>
    </>}
    {record.capabilities.includes('withdraw') && <WithdrawalForm taskId={record.content_id} taskRevision={record.content_revision} mutation={mutation} disabled={dirty} onWithdrawn={onWithdrawn} />}
    <details className="editor-disclosure editor-audit"><summary>Журнал изменений ({record.audit.length})</summary>
      <ol>{record.audit.map(event => <li key={event.id}>
        <div className="editor-audit-heading"><strong>{auditLabels[event.action] ?? event.action}</strong><time dateTime={event.created_at}>{Number.isFinite(Date.parse(event.created_at)) ? dates.format(new Date(event.created_at)) : event.created_at}</time></div>
        <p>{event.note}</p><p className="muted">{event.actor_role === 'admin' ? 'Администратор' : 'Методист'}: <code>{event.actor_id}</code></p>
        {event.to_status && <p className="muted">{event.from_status && <>{statusLabels[event.from_status as keyof typeof statusLabels] ?? event.from_status} → </>}{statusLabels[event.to_status as keyof typeof statusLabels] ?? event.to_status}</p>}
      </li>)}</ol>
    </details>
  </section>;
}
