import { useSyncExternalStore } from 'react';
import { LogIn } from 'lucide-react';
import { navigate } from '../app/router';
import { ActionLink, Button, ErrorNotice } from '../components/ui';
import { accountLink } from './fragment';
import { accountFlow } from './runtime';
import type { Account, AuthConfig } from './types';

export function CompleteLogin({ config, account, onComplete }: { config: AuthConfig; account: Account | null; onComplete: () => void }) {
  const flow = useSyncExternalStore(accountFlow.subscribe, accountFlow.getSnapshot);
  const busy = flow.action === 'complete';
  const error = flow.lastAction === 'complete' ? flow.error : null;
  const ready = accountLink.status() === 'ready';
  const checking = flow.completionRecovery === 'check';

  const complete = async () => {
    if (busy || (!checking && (!ready || !config.enabled))) return;
    try {
      await accountFlow.complete();
      onComplete();
      if (window.location.hash.split('?')[0] === '#/auth/complete') navigate('/account');
    } catch { /* The controller preserves the safe error across the identity remount. */ }
  };

  return <section className="worksheet account-complete" aria-labelledby="account-complete-title" aria-busy={busy}>
    <h2 id="account-complete-title">{checking ? 'Проверьте текущий вход' : ready ? 'Подтвердите вход' : 'Нужна новая ссылка'}</h2>
    {checking ? <p>Сначала проверим доступ к аккаунту. Одноразовая ссылка не отправляется повторно при этой проверке.</p> : !config.enabled ? <p>Вход по email сейчас выключен. Можно продолжить занятия без регистрации.</p> : ready ? <>
      <p>Нажмите «Войти», только если вы сами запросили письмо в этом браузере.</p>
      <p className="muted">Ссылка одноразовая и действует 15 минут. Сервер проверит её связь с запросом из этого браузера.</p>
      {account && <p>Сейчас открыт аккаунт <strong>{account.email}</strong>. Подтверждение выполнит вход в аккаунт из письма.</p>}
    </> : <p>Ссылка отсутствует, истекла или страница была перезагружена. Откройте письмо ещё раз либо запросите новую ссылку в этом браузере.</p>}
    {error && <ErrorNotice message={error} />}
    <p className="account-feedback muted" role="status" aria-live="polite">{busy ? 'Проверяем ссылку и переключаем доступ…' : ''}</p>
    <div className="row-actions">
      {(checking || (config.enabled && ready)) && <Button variant="primary" onClick={() => void complete()} disabled={busy}><LogIn aria-hidden="true" />{busy ? 'Проверяем вход…' : checking ? 'Проверить текущий вход' : 'Войти'}</Button>}
      {config.enabled && <Button disabled={busy} onClick={() => { accountFlow.discardCompletion(); navigate('/account'); }}>{account ? 'Вернуться к аккаунту' : 'Запросить новую ссылку'}</Button>}
      {!busy && <ActionLink href="/practice">К занятиям</ActionLink>}
    </div>
  </section>;
}
