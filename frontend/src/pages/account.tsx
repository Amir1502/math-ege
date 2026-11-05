import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { LogOut } from 'lucide-react';
import { navigate } from '../app/router';
import { Button, ErrorNotice, Loading, PageHeading } from '../components/ui';
import { identity } from '../storage/identity';
import { accountApi } from '../accounts/api';
import { CompleteLogin } from '../accounts/complete-login';
import { AccountData } from '../accounts/data-controls';
import { EmailLogin } from '../accounts/email-login';
import { accountErrorText } from '../accounts/errors';
import { accountLink } from '../accounts/fragment';
import { accountFlow } from '../accounts/runtime';
import { AccountSessions } from '../accounts/sessions';
import { AccountSettings } from '../accounts/settings';
import { StaffSecurity } from '../accounts/staff-security';
import { useAccountResource } from '../accounts/use-account-resource';
import '../styles/account.css';

export default function AccountPage({ completion = false }: { completion?: boolean }) {
  const access = useSyncExternalStore(identity.subscribe, identity.getSnapshot);
  const flow = useSyncExternalStore(accountFlow.subscribe, accountFlow.getSnapshot);
  const scope = `${access.epoch}:${access.value?.id ?? 'none'}`;
  const config = useAccountResource(accountApi.config, 'auth-config');
  const current = useAccountResource(accountApi.current, scope);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const account = current.data;
  const completing = accountLink.status() !== 'empty' || (completion && !account);

  const logout = async () => {
    if (signingOut) return;
    const route = window.location.hash;
    // Logout owns the identity transition; only this page's callbacks expire on departure.
    const currentPage = () => mounted.current && window.location.hash === route;
    setSigningOut(true); setError(null);
    try { await accountFlow.logout(); if (currentPage()) { current.retry(); navigate('/account'); } }
    catch (error) { if (currentPage()) setError(accountErrorText(error)); }
    finally { if (currentPage()) setSigningOut(false); }
  };

  return <div className="account-page">
    <PageHeading title="Аккаунт" description={account ? 'История занятий, настройки и доступ к вашим данным.' : 'Вход по email и доступ к истории занятий.'}
      action={account && !completing && <Button onClick={() => void logout()} disabled={signingOut || access.changing}><LogOut aria-hidden="true" />{signingOut ? 'Выходим…' : 'Выйти'}</Button>} />
    {error && <ErrorNotice message={error} />}
    {!error && flow.lastAction === 'logout' && flow.error && <ErrorNotice message={flow.error} />}
    {account && !completing && flow.completionRecovery === 'current' && <div className="notice" role="status"><p>После сбоя сервер подтвердил текущий доступ к <strong>{account.email}</strong>. Проверьте, что открыт нужный аккаунт. Для другого адреса выйдите и запросите новую ссылку.</p></div>}
    {config.error && <ErrorNotice message={config.error} retry={config.retry} />}
    {current.error && <ErrorNotice message={current.error} retry={current.retry} />}
    <p className="account-transition muted" role="status" aria-live="polite">{access.changing ? 'Переключаем доступ. Дождитесь завершения…' : ''}</p>
    <div inert={access.changing} aria-busy={access.changing}>
      {current.loading || (config.loading && !account) ? <Loading label="Загружаем аккаунт" /> : !current.error && <>
        {completing && config.data ? <CompleteLogin config={config.data} account={account} onComplete={current.retry} /> : account ? <div className="account-sections" key={scope}>
          <AccountSettings account={account} onChange={current.replace} />
          {account.email_verified && <StaffSecurity account={account} available={config.data?.enabled === true} onVerified={current.retry} />}
          <AccountSessions scope={scope} onSignOut={current.retry} />
          <AccountData scope={scope} email={account.email} />
        </div> : config.data && <EmailLogin config={config.data} />}
      </>}
    </div>
  </div>;
}
