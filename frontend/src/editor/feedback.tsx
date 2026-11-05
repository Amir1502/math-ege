import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui';
import type { EditorError } from './adapters';

export function EditorFailure({ error, retry }: { error: EditorError; retry?: () => void }) {
  const access = error.status === 401 || error.status === 403 || ['accounts_disabled', 'mfa_unavailable'].includes(error.code);
  return <div className="notice notice--error editor-error" role="alert">
    <AlertCircle aria-hidden="true" />
    <div><p>{error.message}</p>
      {error.field && <p className="editor-field-path">Поле: <code>{error.field}</code></p>}
      <div className="row-actions">
        {retry && <Button onClick={retry}><RefreshCw aria-hidden="true" />Повторить запрос</Button>}
        {access && <a className="text-link" href="#/account" target="_blank" rel="noopener noreferrer">Открыть вход и MFA в новой вкладке</a>}
      </div>
    </div>
  </div>;
}
