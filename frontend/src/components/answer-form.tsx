import { useEffect, useRef } from 'react';
import { AlertCircle, ArrowRight, CheckCircle2, LoaderCircle, Minus, RotateCcw, SkipForward, XCircle } from 'lucide-react';
import type { Attempt } from '../api/types';
import type { SessionController } from '../learning/session-controller';
import type { SessionSnapshot } from '../learning/model';
import { Button } from './ui';

export function AnswerForm({ controller, state, taskId, onNext, last }: { controller: SessionController; state: SessionSnapshot; taskId: string; onNext: () => void; last: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const record = state.record!;
  const draft = record.drafts[taskId];
  const attempts = record.session.attempts.filter((attempt) => attempt.task_id === taskId);
  const result = attempts.at(-1);
  const pending = record.pending_attempt;
  const locked = Boolean(state.busy || pending || record.pending_finish || state.accessDenied);
  const unchanged = Boolean(result && result.raw_answer === draft.answer);
  const settled = Boolean(result?.correct || result?.skipped || unchanged);

  useEffect(() => {
    if (state.formError) input.current?.focus();
  }, [state.formError]);

  const insert = (symbol: string) => {
    const field = input.current;
    if (!field || locked) return;
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

  return <form className="answer-form" onSubmit={(event) => { event.preventDefault(); if (!locked) void controller.actions.submit(); }}>
    <label htmlFor="answer">Ответ</label>
    <div className="answer-input-row"><input ref={input} id="answer" name="answer" type="text" inputMode="decimal" enterKeyHint="done" autoComplete="off" autoCapitalize="off" spellCheck={false} maxLength={64} value={draft.answer} onChange={(event) => controller.edit(event.target.value)} readOnly={locked} aria-invalid={Boolean(state.formError)} aria-describedby="answer-help answer-feedback" />
      <Button className="symbol-button" aria-label="Вставить или убрать минус" disabled={locked} onClick={() => insert('−')}><Minus aria-hidden="true" /></Button>
      <Button className="symbol-button" aria-label="Вставить запятую" disabled={locked} onClick={() => insert(',')}>,</Button>
      <Button className="symbol-button" aria-label="Вставить дробную черту" disabled={locked} onClick={() => insert('/')}>/</Button>
    </div>
    <p id="answer-help" className="microcopy">Целое число или дробь. Например: −2; 0,5; 1/2. Без единиц измерения.</p>
    <div className="answer-actions">
      {pending ? <Button variant="primary" disabled={Boolean(state.busy) || state.accessDenied} onClick={() => void controller.actions.submit()}><RotateCcw aria-hidden="true" />{state.busy === 'attempt' ? 'Проверяем…' : 'Повторить отправку'}</Button>
        : <Button variant={settled ? 'secondary' : 'primary'} type="submit" disabled={locked || Boolean(unchanged && result)} aria-busy={state.busy === 'attempt'}>{state.busy === 'attempt' ? <LoaderCircle className="spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}{state.busy === 'attempt' ? 'Проверяем…' : result && !result.skipped ? 'Проверить исправление' : 'Проверить'}</Button>}
      {result && !pending && <Button variant={settled ? 'primary' : 'secondary'} disabled={locked} onClick={onNext}>{last ? 'К завершению' : 'Следующая задача'}<ArrowRight aria-hidden="true" /></Button>}
      {!result && !pending && <Button variant="quiet" disabled={locked} onClick={() => void controller.actions.submit(true)}><SkipForward aria-hidden="true" />Пропустить</Button>}
    </div>
    <div id="answer-feedback" className="answer-feedback" aria-live="polite" aria-atomic="true">
      {state.formError ? <div className="feedback feedback--error" role="alert"><AlertCircle aria-hidden="true" /><div><strong>Проверьте формат, не решение</strong><p>{state.formError.message}</p><p>Математическая попытка не создана.</p></div></div>
        : pending ? <div className="feedback"><RotateCcw aria-hidden="true" /><div><strong>{state.busy === 'attempt' ? 'Ответ отправляется на проверку' : 'Проверка пока не подтверждена'}</strong><p>Исходный ответ сохранён. Повторная отправка использует тот же ключ и не создаёт дубль.</p></div></div>
        : result ? <AttemptFeedback attempt={result} />
        : <p className="feedback-placeholder">Результат появится здесь после проверки. Можно исправить ответ без потери первой попытки.</p>}
    </div>
  </form>;
}

function AttemptFeedback({ attempt }: { attempt: Attempt }) {
  const Icon = attempt.skipped ? SkipForward : attempt.correct ? CheckCircle2 : XCircle;
  const title = attempt.skipped ? 'Задача пропущена' : attempt.correct ? (attempt.first_attempt ? 'Верно' : 'Исправлено') : 'Пока неверно';
  return <div className={`feedback ${!attempt.correct && !attempt.skipped ? 'feedback--error' : ''}`}><Icon aria-hidden="true" /><div><strong>{title}</strong>
    {attempt.skipped ? <p>Пропуск учтён отдельно, не как числовой ответ. Можно вернуться и решить.</p> : <>
      <p>{attempt.correct ? `Экзаменационная запись: ${attempt.expected_answer}.` : 'Попробуйте другой ход или откройте разбор. Ваш исходный ответ сохранён.'}</p>
      <p>{!attempt.first_attempt ? 'Повторный ответ не меняет первую попытку.' : attempt.assisted ? 'Ответ с помощью: подсказка или решение открыты до первой попытки.' : 'Первая самостоятельная попытка.'}</p>
      {attempt.normalized_answer && attempt.normalized_answer !== attempt.raw_answer && <p>Введено: «{attempt.raw_answer}». Нормализовано: {attempt.normalized_answer}.</p>}
    </>}
  </div></div>;
}
