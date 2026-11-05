import { useRef, useState, type FormEvent } from 'react';
import { Mail } from 'lucide-react';
import { ActionLink, Button, ErrorNotice } from '../components/ui';
import { emailResponseMessage } from './api';
import { accountErrorText } from './errors';
import { accountFlow } from './runtime';
import type { AuthConfig } from './types';
import { normalizeEmail, safePolicyUrl } from './validation';

export function EmailLogin({ config }: { config: AuthConfig }) {
  const [email, setEmail] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [field, setField] = useState<'email' | 'policy' | null>(null);
  const emailInput = useRef<HTMLInputElement>(null);
  const policyInput = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const policyUrl = safePolicyUrl(config.policy_url);
  const legalReady = Boolean(config.enabled && policyUrl && config.policy_version);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending.current || !legalReady) return;
    setError(null);
    setField(null);
    let address: string;
    try { address = normalizeEmail(email); }
    catch (error) { setError(accountErrorText(error)); setField('email'); emailInput.current?.focus(); return; }
    if (!accepted) {
      setError('Прочитайте и примите политику обработки данных.');
      setField('policy'); policyInput.current?.focus(); return;
    }
    pending.current = true;
    setBusy(true);
    setSent(false);
    try {
      await accountFlow.requestLink(config, { email: address, policy_version: config.policy_version!, accept_policy: true });
      setSent(true);
    } catch (error) { setError(accountErrorText(error)); }
    finally { pending.current = false; setBusy(false); }
  };

  return <div className="account-entry">
    <section className="worksheet account-login" aria-labelledby="email-login-title">
      <h2 id="email-login-title">Вход по email</h2>
      {!legalReady ? <>
        <p>{!config.enabled ? 'Вход по email сейчас выключен.' : 'Условия регистрации пока недоступны. Вход временно закрыт.'}</p>
        <p className="muted">Можно продолжить решать без регистрации. Запрос на отправку письма не выполнялся.</p>
        <ActionLink href="/practice" primary>Заниматься без регистрации</ActionLink>
      </> : <>
        <p className="muted">Один аккаунт для истории занятий на ваших устройствах. Пароль не нужен.</p>
        <form className="account-form" noValidate onSubmit={(event) => void submit(event)} aria-busy={busy}>
          <div className="account-field">
            <label htmlFor="account-email">Email</label>
            <input ref={emailInput} id="account-email" name="email" type="email" inputMode="email" autoComplete="email" autoCapitalize="none" spellCheck={false} enterKeyHint="send" maxLength={254} required value={email}
              onChange={(event) => { setEmail(event.target.value); setError(null); setField(null); setSent(false); }}
              disabled={busy} aria-invalid={field === 'email'} aria-describedby={field === 'email' ? 'account-login-error' : 'account-email-help'} />
            <p id="account-email-help" className="muted">Ссылка действует 15 минут. Откройте её в том браузере, где запросили вход.</p>
          </div>
          <div className="account-policy">
            <p><a className="text-link" href={policyUrl!} target="_blank" rel="noopener noreferrer">Политика обработки данных</a><br />Версия: <span translate="no">{config.policy_version}</span>.</p>
            <p className="muted">Для несовершеннолетних действуют условия согласия из политики. Если нужное согласие ещё не оформлено, продолжайте без регистрации.</p>
            <label className="account-check" htmlFor="account-policy">
              <input ref={policyInput} id="account-policy" name="accept-policy" type="checkbox" required checked={accepted}
                onChange={(event) => { setAccepted(event.target.checked); setError(null); setField(null); }} disabled={busy}
                aria-invalid={field === 'policy'} aria-describedby={field === 'policy' ? 'account-login-error' : undefined} />
              <span>Я принимаю политику обработки данных этой версии.</span>
            </label>
          </div>
          <div id="account-login-error">{error && <ErrorNotice message={error} />}</div>
          <div className="account-feedback" role="status" aria-live="polite">{sent && <><strong>{emailResponseMessage}</strong><p>Проверьте почту и папку «Спам». Если письма нет, можно повторить запрос позже.</p></>}</div>
          <Button type="submit" variant="primary" className="account-submit" disabled={busy}><Mail aria-hidden="true" />{busy ? 'Отправляем запрос…' : sent ? 'Запросить ссылку ещё раз' : 'Получить ссылку для входа'}</Button>
        </form>
      </>}
    </section>
    <aside className="account-entry-note" aria-labelledby="account-guest-title">
      <h2 id="account-guest-title">Можно без аккаунта</h2>
      <p>Для практики регистрация не нужна. Гостевая история доступна по cookie этого браузера. После очистки данных браузера доступ к ней может пропасть.</p>
      <p>При входе текущая гостевая история привязывается к аккаунту. Сохранённые ответы и черновики продолжают принадлежать вам.</p>
      {legalReady && <ActionLink href="/practice">Продолжить без входа</ActionLink>}
      <a className="text-link" href="#/help">Как хранятся данные</a>
    </aside>
  </div>;
}
