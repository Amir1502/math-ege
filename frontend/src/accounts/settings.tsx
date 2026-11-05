import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Button, ErrorNotice } from '../components/ui';
import { formatDate } from '../utils/format';
import { accountApi } from './api';
import { accountErrorText } from './errors';
import type { Account } from './types';
import { useAccountScope } from './use-account-scope';

export function AccountSettings({ account, onChange }: { account: Account; onChange: (account: Account) => void }) {
  const captureScope = useAccountScope({ owner: account.root_guest_id });
  const [minutes, setMinutes] = useState(account.daily_minutes);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedStatus = useRef<HTMLParagraphElement>(null);
  const dirty = minutes !== account.daily_minutes;
  useEffect(() => { if (saved) savedStatus.current?.focus(); }, [saved]);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || !dirty) return;
    let operation: ReturnType<typeof captureScope>;
    try { operation = captureScope(); }
    catch (error) { setError(accountErrorText(error)); return; }
    setBusy(true); setError(null); setSaved(false);
    try {
      const updated = await accountApi.updateSettings({ daily_minutes: minutes });
      if (operation.current()) { onChange(updated); setSaved(true); }
    } catch (error) { if (operation.current()) setError(accountErrorText(error)); }
    finally { if (operation.current()) setBusy(false); operation.close(); }
  };

  return <section className="account-region" aria-labelledby="account-settings-title">
    <div className="account-region-heading"><h2 id="account-settings-title">Аккаунт и настройки</h2><p className="muted">Параметры занятий сохраняются в аккаунте.</p></div>
    <div className="account-region-content">
      <dl className="account-ledger">
        <div><dt>Email</dt><dd>{account.email}<span className="account-detail">{account.email_verified ? 'Подтверждён' : 'Не подтверждён'}</span></dd></div>
        <div><dt>Аккаунт создан</dt><dd>{formatDate(account.created_at)}</dd></div>
        <div><dt>Согласие на обработку данных</dt><dd>Версия <span translate="no">{account.policy_version}</span><span className="account-detail">{formatDate(account.consented_at)}</span></dd></div>
      </dl>
      <form className="account-form" onSubmit={(event) => void save(event)} aria-busy={busy}>
        <fieldset disabled={busy}>
          <legend>Время на занятия в день</legend>
          <div className="segmented account-duration">{([10, 20, 30] as const).map((value) => <label className={minutes === value ? 'is-selected' : ''} key={value}>
            <input type="radio" name="daily-minutes" value={value} checked={minutes === value} onChange={() => { setMinutes(value); setSaved(false); setError(null); }} />
            <span><strong>{value}</strong> мин</span>
          </label>)}</div>
        </fieldset>
        {error && <ErrorNotice message={error} />}
        <div className="account-save-row">
          {dirty && <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Сохраняем…' : 'Сохранить настройки'}</Button>}
          <p ref={savedStatus} className="muted" role="status" aria-live="polite" tabIndex={-1}>{saved ? 'Настройки сохранены.' : dirty ? 'Есть несохранённые изменения.' : 'Настройки сохранены в аккаунте.'}</p>
        </div>
      </form>
    </div>
  </section>;
}
