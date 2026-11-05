import { useCallback } from 'react';
import { Loading, PageHeading } from '../components/ui';
import { createEditorApi } from '../editor/api';
import { EditorFailure } from '../editor/feedback';
import { EditorWorkspace } from '../editor/workspace';
import { useEditorResource } from '../editor/use-resource';
import '../styles/editor.css';

const entry = createEditorApi();

/** Mount inside the existing Shell at /editor; this page never creates a guest session. */
export default function EditorPage() {
  const load = useCallback((signal: AbortSignal) => entry.meta(signal), []);
  const access = useEditorResource(load, 'editor-access');
  return <div className="editor-page" lang="ru">
    <PageHeading title="Редактор контента" description="Редакции, предметная проверка и публикация учебного банка."
      action={<a className="text-link" href="#/account" target="_blank" rel="noopener noreferrer">Аккаунт и MFA</a>} />
    {access.loading && <Loading label="Проверяем доступ сотрудника" />}
    {access.error && <><EditorFailure error={access.error} retry={access.retry} /><p className="muted">Нужны подтверждённый аккаунт методиста или администратора и недавняя проверка MFA. После входа повторите запрос.</p></>}
    {access.data && <EditorWorkspace key={access.data.actor.id} meta={access.data} />}
  </div>;
}
