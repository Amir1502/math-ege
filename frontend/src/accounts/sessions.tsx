import { useState, useSyncExternalStore } from 'react';
/* viora-allow: loading-no-ellipsis The shared Loading component appends its own ellipsis. */
import { Button, ErrorNotice, Loading } from '../components/ui';
import { formatDate } from '../utils/format';
import { accountApi } from './api';
import { accountErrorText } from './errors';
import { accountFlow } from './runtime';
import type { AccessSession } from './types';
import { useAccountResource } from './use-account-resource';
import { useAccountScope } from './use-account-scope';

export function AccountSessions({ scope, onSignOut }: { scope: string; onSignOut: () => void }) {
  const captureScope = useAccountScope({ scope });
  const sessions = useAccountResource(accountApi.sessions, scope);
  const flow = useSyncExternalStore(accountFlow.subscribe, accountFlow.getSnapshot);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  const revoke = async (session: AccessSession) => {
    if (busy) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setError(accountErrorText(error)); return; }
    setBusy(session.id); setError(null); setMessage('');
    try {
      await accountFlow.revokeSession(session);
      if (!operation.current()) return;
      if (session.current) onSignOut();
      else { sessions.retry(); setMessage('Доступ для выбранного сеанса завершён.'); }
    } catch (error) { if (operation.current()) setError(accountErrorText(error)); }
    finally { if (operation.current()) setBusy(null); operation.close(); }
  };

  return <section className="account-region" aria-labelledby="account-sessions-title">
    <div className="account-region-heading"><h2 id="account-sessions-title">Устройства и сеансы</h2><p className="muted">Завершите сеанс, если больше не пользуетесь этим устройством.</p></div>
    <div className="account-region-content">
      {sessions.loading && <Loading label="Загружаем сеансы" />}
      {sessions.error && <ErrorNotice message={sessions.error} retry={sessions.retry} />}
      {error && <ErrorNotice message={error} />}
      {!error && flow.lastAction?.startsWith('revoke:') && flow.error && <ErrorNotice message={flow.error} />}
      <p className="account-feedback muted" role="status" aria-live="polite">{message}</p>
      {sessions.data && (sessions.data.length === 0 ? <p>Активных сеансов не найдено. Обновите список или войдите снова.</p> : <ul className="account-session-list" aria-busy={busy !== null}>{sessions.data.map((session) => <li key={session.id}>
        <div><h3>{session.current ? 'Этот браузер' : `Сеанс от ${formatDate(session.created_at)}`}</h3>
          <dl className="account-session-meta"><div><dt>Последняя активность</dt><dd>{formatDate(session.last_seen_at)}</dd></div><div><dt>Доступ до</dt><dd>{formatDate(session.expires_at)}</dd></div></dl>
        </div>
        <Button disabled={busy !== null} onClick={() => void revoke(session)} aria-label={busy === session.id ? undefined : session.current ? 'Выйти в этом браузере' : `Завершить сеанс от ${formatDate(session.created_at)}`}>
          {busy === session.id ? 'Завершаем…' : session.current ? 'Выйти в этом браузере' : 'Завершить сеанс'}
        </Button>
      </li>)}</ul>)}
      {!sessions.loading && !sessions.error && <Button variant="quiet" onClick={sessions.retry} disabled={busy !== null}>Обновить список</Button>}
    </div>
  </section>;
}
