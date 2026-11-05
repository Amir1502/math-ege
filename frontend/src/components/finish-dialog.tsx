import { useEffect, useRef } from 'react';
import { Button } from './ui';

export function FinishDialog({ open, unanswered, hasDraft, busy, onClose, onConfirm }: { open: boolean; unanswered: number; hasDraft: boolean; busy: boolean; onClose: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      element.showModal();
      cancel.current?.focus();
      return () => { element.close(); previous?.focus(); };
    }
  }, [open]);
  return <dialog ref={dialog} className="finish-dialog" aria-labelledby="finish-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <h2 id="finish-title">Завершить занятие?</h2>
    <p>{unanswered > 0 ? `Без отправленного ответа осталось: ${unanswered}.` : 'Все задачи получили ответ или отметку о пропуске.'}</p>
    {hasDraft && <p>В серии есть текст, который не отправлен на проверку. Он останется черновиком и не станет математической попыткой.</p>}
    <p>После завершения ответы нельзя менять. Условия, решения и история останутся доступны.</p>
    <div className="dialog-actions"><button ref={cancel} type="button" className="button button--secondary" disabled={busy} onClick={onClose}>Продолжить решать</button><Button variant="primary" disabled={busy} onClick={onConfirm}>{busy ? 'Завершаем…' : 'Завершить занятие'}</Button></div>
  </dialog>;
}
