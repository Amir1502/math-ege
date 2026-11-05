import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Download } from 'lucide-react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, ErrorNotice, Loading } from '../components/ui';
import { downloadJson, formatDate } from '../utils/format';
import { accountApi } from './api';
import { deletionInstant } from './deletion-time';
import { AccountError, accountErrorText } from './errors';
import type { DeletionCancellation, DeletionRequest } from './types';
import { useAccountResource } from './use-account-resource';
import { useAccountScope } from './use-account-scope';

export function AccountData({ scope, email }: { scope: string; email: string }) {
  return <AccountDataScope key={scope} scope={scope} email={email} />;
}

function AccountDataScope({ scope, email }: { scope: string; email: string }) {
  const deletion = useAccountResource(accountApi.deletionStatus, scope);
  const captureScope = useAccountScope({ scope });
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exported, setExported] = useState(false);
  const [open, setOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canceling, setCanceling] = useState(false);
  const [cancellation, setCancellation] = useState<{
    request: DeletionRequest; receipt: DeletionCancellation | null; error: string | null;
  } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const confirmation = useRef<HTMLInputElement>(null);
  const receipt = useRef<HTMLElement>(null);
  const canceledReceipt = useRef<HTMLElement>(null);
  const pendingAction = useRef<object | null>(null);
  const exportingAction = useRef(false);
  const loaded = !deletion.loading && !deletion.error;
  const requested = loaded && deletion.data?.status === 'requested' ? deletion.data : null;
  const canceled = cancellation?.receipt;
  const staleStatus = requested !== null && requested.id === canceled?.id;
  const currentRequest = staleStatus ? null : requested;
  const deletionBusy = busy || canceling;
  useEffect(() => { if (cancellation?.receipt) canceledReceipt.current?.focus(); }, [cancellation?.receipt]);
  useEffect(() => {
    const element = dialog.current;
    if (!element || !open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal();
    cancel.current?.focus();
    return () => { element.close(); if (previous?.isConnected) previous.focus(); };
  }, [open]);

  const exportHistory = async () => {
    if (exportingAction.current) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setExportError(accountErrorText(error)); return; }
    exportingAction.current = true;
    setExporting(true); setExportError(null); setExported(false);
    try {
      const data = await accountApi.exportHistory();
      if (operation.current()) { downloadJson(data, 'ege-account-history.json'); setExported(true); }
    } catch (error) { if (operation.current()) setExportError(accountErrorText(error)); }
    finally { if (operation.current()) setExporting(false); exportingAction.current = false; operation.close(); }
  };
  const requestDeletion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pendingAction.current) return;
    if (!confirmed) { setError('Отметьте подтверждение, чтобы отправить запрос.'); confirmation.current?.focus(); return; }
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setError(accountErrorText(error)); return; }
    const action = {};
    pendingAction.current = action;
    setBusy(true); setError(null);
    try {
      const requested = await accountApi.requestDeletion(true);
      if (operation.current()) { deletion.replace(requested); setCancellation(null); setOpen(false); }
    } catch (error) { if (operation.current()) setError(accountErrorText(error)); }
    finally { if (operation.current()) setBusy(false); if (pendingAction.current === action) pendingAction.current = null; operation.close(); }
  };
  const cancelDeletion = async (request: DeletionRequest) => {
    if (pendingAction.current) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch { return; }
    const action = {};
    pendingAction.current = action;
    // Retain this exact request for explicit retries, even if a refresh returns a newer request.
    const selected = { ...request };
    setCanceling(true); setCancellation({ request: selected, receipt: null, error: null });
    try {
      const result = await accountApi.cancelDeletion(selected.id);
      if (!operation.current()) return;
      if (deletionInstant(result.requested_at) !== deletionInstant(selected.requested_at)
        || deletionInstant(result.deadline_at) !== deletionInstant(selected.deadline_at)) throw new AccountError(502, 'invalid_response');
      setCancellation({ request: selected, receipt: result, error: null });
      // Do not replace a concurrently refreshed/newer request with null. Read persisted status instead.
      deletion.retry();
    } catch (error) {
      if (operation.current()) {
        setCancellation({ request: selected, receipt: null, error: accountErrorText(error) });
        deletion.retry();
      }
    } finally { if (operation.current()) setCanceling(false); if (pendingAction.current === action) pendingAction.current = null; operation.close(); }
  };

  return <section className="account-region" aria-labelledby="account-data-title">
    <div className="account-region-heading"><h2 id="account-data-title">История и данные</h2><p className="muted">Скачайте свою историю или отправьте запрос на удаление аккаунта.</p></div>
    <div className="account-region-content">
      <div className="account-export">
        <h3>Копия истории</h3>
        <p>JSON содержит данные аккаунта, историю занятий и согласия на обработку данных.</p>
        <Button onClick={() => void exportHistory()} disabled={exporting}><Download aria-hidden="true" />{exporting ? 'Готовим файл…' : 'Скачать историю JSON'}</Button>
        {exportError && <ErrorNotice message={exportError} retry={() => void exportHistory()} />}
        <p className="account-feedback muted" role="status" aria-live="polite">{exported ? 'Файл подготовлен. Сохраните его в надёжном месте.' : ''}</p>
      </div>
      <div className="account-deletion" aria-busy={deletionBusy}>
        <h3>Удаление аккаунта</h3>
        <p>Можно отправить запрос на удаление данных аккаунта. Срок обработки: не более 30&nbsp;дней с момента запроса.</p>
        {deletion.loading && <Loading label="Проверяем статус запроса" />}
        {deletion.error && <ErrorNotice message={deletion.error} retry={deletionBusy ? undefined : deletion.retry} />}
        <div role="status" aria-live="polite">{currentRequest && <div className="account-receipt">
          <strong ref={receipt} tabIndex={-1}>Запрос на удаление принят</strong>
          <dl className="account-ledger"><div><dt>Дата запроса</dt><dd>{formatDate(currentRequest.requested_at)}</dd></div><div><dt>Обработка не позднее</dt><dd>{formatDate(currentRequest.deadline_at)}</dd></div></dl>
          <p>Статус: ожидает обработки. Принятие запроса ещё не означает, что данные удалены.</p>
        </div>}{canceled && <div className="account-receipt">
          <strong ref={canceledReceipt} tabIndex={-1}>Запрос удаления отменён</strong>
          <dl className="account-ledger"><div><dt>Дата запроса</dt><dd>{formatDate(canceled.requested_at)}</dd></div><div><dt>Дата отмены</dt><dd>{formatDate(canceled.canceled_at)}</dd></div></dl>
          <p>Отменён только этот запрос. Это действие не удаляет аккаунт или данные.</p>
        </div>}</div>
        {cancellation?.error && <>
          <ErrorNotice message={cancellation.error} />
          <p className="account-feedback muted">Повтор относится только к ранее выбранному запросу от {formatDate(cancellation.request.requested_at)}. Более новый запрос не будет отменён этим повтором.</p>
          <Button onClick={() => void cancelDeletion(cancellation.request)} disabled={deletionBusy}>Повторить отмену этого запроса</Button>
        </>}
        {staleStatus && <ErrorNotice message="Отмена подтверждена, но текущий статус ещё не обновлён. Повторите проверку статуса." retry={deletionBusy ? undefined : deletion.retry} />}
        <div className="account-save-row">
          {loaded && !deletion.data && <Button className="account-danger" disabled={deletionBusy} onClick={() => { setConfirmed(false); setError(null); setOpen(true); }}>Запросить удаление аккаунта</Button>}
          {currentRequest && <Button onClick={() => void cancelDeletion(currentRequest)} disabled={deletionBusy}>{canceling ? 'Отменяем запрос…' : 'Отменить запрос удаления'}</Button>}
          {(currentRequest || cancellation) && <Button variant="quiet" onClick={deletion.retry} disabled={deletionBusy || deletion.loading}>Обновить статус</Button>}
        </div>
      </div>
    </div>
    <dialog ref={dialog} className="account-dialog" aria-labelledby="account-deletion-title" aria-describedby="account-deletion-description" onClose={() => receipt.current?.focus()} onCancel={(event) => { event.preventDefault(); if (!busy) setOpen(false); }}>
      <form onSubmit={(event) => void requestDeletion(event)} noValidate aria-busy={busy}>
        <h2 id="account-deletion-title">Отправить запрос удаления?</h2>
        <p id="account-deletion-description">Запрос относится к аккаунту <strong>{email}</strong> и связанным с ним данным. Обработка займёт не более 30&nbsp;дней. Перед отправкой можно скачать историю.</p>
        <label className="account-check" htmlFor="account-deletion-confirm">
          <input ref={confirmation} id="account-deletion-confirm" name="confirm-deletion" type="checkbox" required checked={confirmed} onChange={(event) => { setConfirmed(event.target.checked); setError(null); }} disabled={busy} aria-invalid={Boolean(error && !confirmed)} aria-describedby={error ? 'account-deletion-error' : undefined} />
          <span>Я прошу удалить этот аккаунт и связанные данные.</span>
        </label>
        <div id="account-deletion-error">{error && <ErrorNotice message={error} />}</div>
        <div className="account-dialog-actions">
          <button ref={cancel} className="button button--secondary" type="button" disabled={busy} onClick={() => setOpen(false)}>Оставить аккаунт</button>
          <Button type="submit" className="account-danger" disabled={busy}>{busy ? 'Отправляем запрос…' : 'Подтвердить запрос удаления'}</Button>
        </div>
      </form>
    </dialog>
  </section>;
}
