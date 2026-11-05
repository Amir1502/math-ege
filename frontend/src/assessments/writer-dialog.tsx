import { useEffect, useRef } from 'react';
import { Button } from '../components/ui';

export function WriterDialog({ open, onClose, onConfirm }: { open: boolean; onClose(): void; onConfirm(): void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element || !open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!element.open) element.showModal();
    cancel.current?.focus();
    return () => { element.close(); previous?.focus(); };
  }, [open]);
  return <dialog ref={dialog} className="finish-dialog" aria-labelledby="assessment-writer-title" aria-describedby="assessment-writer-description" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <h2 id="assessment-writer-title">Продолжить в этой вкладке?</h2>
    <p id="assessment-writer-description">Эта вкладка получит право записи. Другая вкладка или устройство сможет только просматривать вариант.</p>
    <p>Сначала загрузится серверный черновик. Если здесь есть несохранённый ввод, вы отдельно выберете, какой черновик использовать.</p>
    <div className="dialog-actions"><button ref={cancel} className="button button--secondary" type="button" onClick={onClose}>Оставить только просмотр</button><Button variant="primary" onClick={onConfirm}>Продолжить здесь</Button></div>
  </dialog>;
}
