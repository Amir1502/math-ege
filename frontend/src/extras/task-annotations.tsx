import { useEffect, useId } from 'react';
import { Bookmark, Check, LoaderCircle } from 'lucide-react';
import { Button, ErrorNotice } from '../components/ui';
import { useTaskAnnotations } from './hooks';
import { causeLabels } from './view-models';
import type { AnnotationValues, ErrorCause } from './types';

export function TaskAnnotations({ sessionId, taskId, values, showCause = true }: {
  sessionId: string;
  taskId: string;
  values: AnnotationValues;
  showCause?: boolean;
}) {
  const id = useId();
  const annotation = useTaskAnnotations(sessionId, taskId);
  const { reconcile, confirmed, saving } = annotation;
  const { cause, favourite, manual, not_understood } = values;
  useEffect(() => { reconcile({ cause, favourite, manual, not_understood }); }, [reconcile, confirmed, saving, cause, favourite, manual, not_understood]);
  const displayed = { ...values, ...annotation.confirmed, ...annotation.pending?.body };
  const blocked = !annotation.available || annotation.pending !== null;

  return <div className="learning-annotations">
    <fieldset disabled={blocked} aria-describedby={`${id}-help`}>
      <legend>Ваши отметки</legend>
      <div className="learning-annotation-flags">
        <Button aria-pressed={displayed.favourite} onClick={() => void annotation.save({ favourite: !displayed.favourite })}>
          <Bookmark aria-hidden="true" />{displayed.favourite ? 'В избранном' : 'В избранное'}
        </Button>
        <label className="learning-check"><input type="checkbox" checked={displayed.manual} onChange={(event) => void annotation.save({ manual: event.target.checked })} /><span>Добавить в журнал вручную</span></label>
        <label className="learning-check"><input type="checkbox" checked={displayed.not_understood} onChange={(event) => void annotation.save({ not_understood: event.target.checked })} /><span>Не понимаю тему</span></label>
      </div>
      {showCause && <div className="learning-cause-field"><label htmlFor={`${id}-cause`}>Какую причину вы заметили?</label>
        <select id={`${id}-cause`} value={displayed.cause ?? ''} aria-describedby={`${id}-help`} onChange={(event) => void annotation.save({ cause: event.target.value ? event.target.value as ErrorCause : null })}>
          <option value="">Причина не выбрана</option>
          {Object.entries(causeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select>
      </div>}
    </fieldset>
    <p id={`${id}-help`} className="microcopy">{annotation.available
      ? 'Причину выбираете вы. По одному ответу нельзя определить ход решения.'
      : 'Начните занятие, чтобы сохранять отметки в своей истории.'}</p>
    <p className="learning-save-status" role="status">{annotation.saving ? <><LoaderCircle className="spin" aria-hidden="true" />Сохраняем отметку…</>
      : annotation.pending ? 'Ожидает повторной отправки. Другие отметки будут доступны после подтверждения.'
        : annotation.saved ? <><Check aria-hidden="true" />Отметка сохранена</> : null}</p>
    {annotation.error && <ErrorNotice message={annotation.error} retry={annotation.pending ? annotation.retry : undefined} />}
  </div>;
}
