import { useCallback, useState } from 'react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, Loading } from '../components/ui';
import { RichText } from '../components/math';
import { TaskContent } from '../components/task-content';
import type { EditorApi } from './api';
import { decodeCheck, decodeRevision } from './adapters';
import { parseSeed } from './drafts';
import { EditorFailure } from './feedback';
import type { CheckResult, Revision, TemplateSample } from './types';
import type { EditorMutation } from './use-mutation';
import { useEditorResource } from './use-resource';

const checkLabels: Record<string, string> = {
  strict_schema: 'Строгая схема результата', finite_exam_answer: 'Конечный ответ экзаменационного формата',
  deterministic_snapshot: 'Воспроизводимость снимка', profile_binding: 'Привязка к профилю', version_seed: 'Версия генератора и seed',
};

export function TemplateEvidencePanel({ api, record, mutation, dirty, onUpdated, onChecked }: {
  api: EditorApi; record: Revision; mutation: EditorMutation; dirty: boolean;
  onUpdated: (record: Revision) => void; onChecked: (result: CheckResult) => void;
}) {
  const evidence = record.evidence;
  const next = Array.from({ length: 20 }, (_, index) => index).find(seed => !evidence?.reviewed_seeds.includes(seed)) ?? 20;
  const [input, setInput] = useState(String(next));
  const [seed, setSeed] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [decision, setDecision] = useState('');
  const [note, setNote] = useState('');
  const [reviewProblem, setReviewProblem] = useState<string | null>(null);
  const load = useCallback((signal: AbortSignal): Promise<TemplateSample | null> => seed === null
    ? Promise.resolve(null) : api.sample(record.id, seed, signal), [api, record.id, seed]);
  const sample = useEditorResource(load, `${record.id}:${seed}`);
  const disabled = mutation.locked || dirty;

  return <section className="editor-evidence" aria-labelledby="editor-evidence-heading">
    <h3 id="editor-evidence-heading">Доказательства проверки шаблона</h3>
    <dl className="editor-ledger"><div><dt>Автоматический протокол</dt><dd>{evidence?.automated_passed ? 'Пройден' : 'Не подтверждён'}; seed: {evidence?.automated_seeds ?? 0} из 1000</dd></div>
      <div><dt>Одобренные seed всех рецензентов</dt><dd>{evidence?.reviewed_seeds.length ? evidence.reviewed_seeds.join(', ') : 'Пока нет'}</dd></div>
      <div><dt>Отклонённые seed</dt><dd>{evidence?.rejected_seeds.length ? evidence.rejected_seeds.join(', ') : 'Пока нет'}</dd></div>
    </dl>
    {evidence?.failure && <p className="editor-inline-error" role="alert">{evidence.failure}</p>}
    {evidence?.checks.length ? <ul className="editor-check-results">{evidence.checks.map(check => <li key={check}>{checkLabels[check] ?? check}</li>)}</ul> : null}
    <p className="muted">Сервер проверяет структуру, воспроизводимость и конечный ответ на 1000 seed, включая границы uint32. Это не независимая математическая проверка.</p>
    {record.capabilities.includes('run_checks') && <Button disabled={disabled} onClick={() => void mutation.run(
      `/revisions/${encodeURIComponent(record.id)}/checks`, 'POST',
      { expected_revision: record.revision, note: 'Запущен серверный протокол 1000 seed с граничными значениями.' },
      value => onChecked(decodeCheck(value)),
    )}>Проверить 1000 seed</Button>}
    <p className="editor-evidence-help">Рецензент, который утверждает шаблон, должен лично проверить минимум 10 разных результатов, формулы и ограничения. Отклонённый результат блокирует публикацию.</p>
    <form className="editor-sample-form" onSubmit={event => {
      event.preventDefault();
      try { const value = parseSeed(input); setProblem(null); if (value === seed) sample.retry(); else setSeed(value); }
      catch (failure) { setProblem(failure instanceof Error ? failure.message : 'Проверьте seed.'); }
    }}>
      <div className="editor-field"><label htmlFor="editor-sample-seed">Seed экземпляра</label>
        <input id="editor-sample-seed" inputMode="numeric" autoComplete="off" value={input} maxLength={10} required disabled={disabled}
          aria-invalid={Boolean(problem)} aria-describedby={`editor-seed-help${problem ? ' editor-seed-error' : ''}`}
          onChange={event => { setInput(event.target.value); setSeed(null); setProblem(null); setDecision(''); setNote(''); }} />
        <p id="editor-seed-help" className="muted">Целое число от 0 до 4294967295.</p>
        {problem && <p id="editor-seed-error" className="editor-inline-error" role="alert">{problem}</p>}
      </div>
      <Button type="submit" disabled={disabled || (seed !== null && sample.loading)}>Получить экземпляр</Button>
    </form>
    {seed !== null && sample.loading && <Loading label="Воспроизводим экземпляр шаблона" />}
    {sample.error && <EditorFailure error={sample.error} retry={sample.retry} />}
    {sample.data && <div className="editor-sample">
      <h4>Результат для seed {sample.data.seed}</h4>
      <TaskContent task={sample.data.task} />
      <p className="editor-sample-answer">Эталон: <strong>{sample.data.answer}</strong></p>
      <h5>Решение</h5><ol>{sample.data.solution.map((step, index) => <li key={index}><RichText text={step} /></li>)}</ol>
      <h5>Подсказки</h5><ol>{sample.data.hints.map((hint, index) => <li key={index}><RichText text={hint} /></li>)}</ol>
      <details className="editor-disclosure"><summary>SHA-256 снимка</summary><code>{sample.data.output_hash}</code></details>
      {record.capabilities.includes('review_sample') && <form onSubmit={event => {
        event.preventDefault();
        const shown = sample.data;
        if (!shown || disabled) return;
        if (!decision || note.trim().length < 5) { setReviewProblem('Выберите решение и опишите проверку минимум пятью символами.'); return; }
        void mutation.run(`/revisions/${encodeURIComponent(record.id)}/samples`, 'POST', {
          expected_revision: record.revision, seed: shown.seed, output_hash: shown.output_hash,
          approved: decision === 'approved', note: note.trim(),
        }, value => onUpdated(decodeRevision(value)));
      }}>
        <fieldset disabled={disabled}><legend>Ваше решение об этом экземпляре</legend>
          <label className="editor-check"><input type="radio" name="sample-decision" value="approved" required checked={decision === 'approved'} onChange={event => { setDecision(event.target.value); setReviewProblem(null); }} />Условие, решение и эталон корректны</label>
          <label className="editor-check"><input type="radio" name="sample-decision" value="rejected" required checked={decision === 'rejected'} onChange={event => { setDecision(event.target.value); setReviewProblem(null); }} />Обнаружена ошибка</label>
        </fieldset>
        <div className="editor-field"><label htmlFor="editor-sample-note">Что проверено или какая ошибка найдена</label>
          <textarea id="editor-sample-note" value={note} onChange={event => { setNote(event.target.value); setReviewProblem(null); }} required minLength={5} maxLength={2000} rows={3} disabled={disabled}
            aria-invalid={Boolean(reviewProblem)} aria-describedby={reviewProblem ? 'editor-sample-error' : undefined} />
          {reviewProblem && <p id="editor-sample-error" className="editor-inline-error" role="alert">{reviewProblem}</p>}
        </div>
        <Button type="submit" disabled={disabled}>Сохранить рецензию экземпляра</Button>
      </form>}
    </div>}
  </section>;
}
