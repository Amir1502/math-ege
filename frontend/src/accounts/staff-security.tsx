import { useEffect, useReducer, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { Copy, ShieldCheck } from 'lucide-react';
import { ActionLink, Button, ErrorNotice } from '../components/ui';
import { formatDate } from '../utils/format';
import { accountErrorText } from './errors';
import { accountFlow } from './runtime';
import type { Account } from './types';
import { hasRecentMfa, isStaff, normalizeMfaCode } from './validation';
import { useAccountScope } from './use-account-scope';

export function StaffSecurity({ account, available, onVerified }: { account: Account; available: boolean; onVerified: () => void }) {
  const captureScope = useAccountScope({ owner: account.root_guest_id });
  const flow = useSyncExternalStore(accountFlow.subscribe, accountFlow.getSnapshot);
  const enrollment = accountFlow.enrollment(account.id);
  const [code, setCode] = useState('');
  const busy = flow.action?.startsWith('mfa-') === true;
  const [localError, setError] = useState<string | null>(null);
  const error = localError ?? (flow.lastAction?.startsWith('mfa-') ? flow.error : null);
  const [codeError, setCodeError] = useState(false);
  const [copyMessage, setCopyMessage] = useState('');
  const [, tick] = useReducer((value: number) => value + 1, 0);
  const codeInput = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  const recent = hasRecentMfa(account);
  const staff = isStaff(account);

  useEffect(() => {
    if (!account.mfa_verified_until) return;
    const remaining = Date.parse(account.mfa_verified_until) - Date.now();
    if (remaining <= 0) return;
    const timeout = window.setTimeout(tick, Math.min(remaining + 1, 2_147_483_647));
    return () => window.clearTimeout(timeout);
  }, [account.mfa_verified_until]);
  useEffect(() => {
    if (!enrollment) return;
    const forget = () => { accountFlow.forgetEnrollment(); setCode(''); setCopyMessage(''); };
    const timeout = window.setTimeout(() => {
      forget();
      setError('Срок настройки истёк. Начните настройку заново.');
    }, Math.max(0, Date.parse(enrollment.expires_at) - Date.now()));
    window.addEventListener('pagehide', forget);
    return () => { window.clearTimeout(timeout); window.removeEventListener('pagehide', forget); };
  }, [enrollment]);

  const enroll = async () => {
    if (pending.current) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setError(accountErrorText(error)); return; }
    pending.current = true;
    setError(null); setCode(''); setCopyMessage('');
    try { await accountFlow.enrollMfa(account.id); }
    catch (error) { if (operation.current()) setError(accountErrorText(error)); }
    finally { pending.current = false; operation.close(); }
  };
  const verify = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending.current) return;
    setError(null); setCodeError(false); accountFlow.clearError();
    let value: string;
    try { value = normalizeMfaCode(code); }
    catch (error) { setError(accountErrorText(error)); setCodeError(true); codeInput.current?.focus(); return; }
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setError(accountErrorText(error)); return; }
    pending.current = true;
    try {
      if (enrollment) await accountFlow.confirmMfa(value);
      else await accountFlow.verifyMfa(value);
      if (!operation.current()) return;
      setCode(''); setCopyMessage('');
      onVerified();
    } catch (error) { if (operation.current()) { setError(accountErrorText(error)); setCode(''); setCodeError(true); codeInput.current?.focus(); } }
    finally { pending.current = false; operation.close(); }
  };
  const copy = async () => {
    if (!enrollment) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch { return; }
    try { await navigator.clipboard.writeText(enrollment.provisioning_uri); if (operation.current()) setCopyMessage('Адрес настройки скопирован. Вставьте его только в приложение-аутентификатор.'); }
    catch { if (operation.current()) setCopyMessage('Выделите адрес настройки и скопируйте его вручную.'); }
    finally { operation.close(); }
  };

  return <section className="account-region" aria-labelledby="account-security-title">
    <div className="account-region-heading"><h2 id="account-security-title">Доступ сотрудника</h2><p className="muted">{staff ? 'Для редактора нужен свежий код подтверждения. Права на действия проверяет сервер.' : 'Подготовка аккаунта для работы с учебными материалами.'}</p></div>
    <div className="account-region-content">
      {staff ? <p>Роль: <strong>{account.role === 'admin' ? 'Администратор' : 'Методист'}</strong>.</p> : <p>Права сотрудника назначает администратор вне приложения после настройки подтверждения кодом.</p>}
      {!staff && account.mfa_enabled ? <p>Приложение-аутентификатор настроено. Администратор может назначить роль сотрудника.</p> : !available ? <p>Вход и подтверждение сотрудника сейчас недоступны на сервере.</p> : recent ? <div className="account-staff-access">
        <p><ShieldCheck aria-hidden="true" />Подтверждено до {formatDate(account.mfa_verified_until!)}.</p>
        <ActionLink href="/editor" primary>Открыть редактор</ActionLink>
      </div> : <>
        <p>{account.mfa_enabled ? 'Введите текущий код из вашего приложения-аутентификатора. Подтверждение действует 15 минут.' : 'Настройте приложение-аутентификатор. Для настройки нужен вход по email за последние 15 минут.'}</p>
        {!account.mfa_enabled && !enrollment && <Button onClick={() => void enroll()} disabled={busy}>{busy ? 'Готовим настройку…' : 'Настроить подтверждение кодом'}</Button>}
        {enrollment && <div className="account-enrollment">
          <div className="account-field account-secret" data-private="true">
            <label htmlFor="account-mfa-uri">Адрес настройки для приложения-аутентификатора</label>
            <textarea id="account-mfa-uri" name="mfa-provisioning-uri" className="account-uri" value={enrollment.provisioning_uri} readOnly rows={4} autoComplete="off" spellCheck={false} aria-describedby="account-mfa-uri-help" />
            <p id="account-mfa-uri-help" className="muted">Вставьте адрес в приложение-аутентификатор. Он содержит секрет настройки, поэтому не пересылайте его другим людям.</p>
            <Button onClick={() => void copy()} disabled={busy}><Copy aria-hidden="true" />Скопировать адрес настройки</Button>
          </div>
          <p className="account-feedback muted" role="status" aria-live="polite">{copyMessage}</p>
          <p>Завершите настройку до {formatDate(enrollment.expires_at)}. Адрес хранится только на этой открытой странице.</p>
        </div>}
        {(account.mfa_enabled || enrollment) && <form className="account-form" noValidate onSubmit={(event) => void verify(event)} aria-busy={busy}>
          <div className="account-field">
            <label htmlFor="account-mfa-code">Код из приложения</label>
            <input ref={codeInput} id="account-mfa-code" name="one-time-code" className="account-code" type="text" inputMode="numeric" autoComplete="one-time-code" spellCheck={false} enterKeyHint="done" required maxLength={32} value={code} onChange={(event) => { setCode(event.target.value); setCodeError(false); setError(null); accountFlow.clearError(); }} disabled={busy} aria-invalid={codeError || Boolean(error)} aria-describedby={codeError || error ? 'account-mfa-error' : 'account-mfa-code-help'} />
            <p id="account-mfa-code-help" className="muted">Шесть цифр. Можно вставить код целиком.</p>
          </div>
          <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Проверяем код…' : enrollment ? 'Подтвердить настройку' : 'Подтвердить доступ'}</Button>
        </form>}
      </>}
      <div id="account-mfa-error">{error && <ErrorNotice message={error} />}</div>
      {error && <Button variant="quiet" onClick={onVerified} disabled={busy}>Обновить данные аккаунта</Button>}
    </div>
  </section>;
}
