import { ApiError } from '../api/client';

export function assessmentErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'identity_changed') return 'Профиль изменился. Локальный вариант сохранён в прежнем профиле. Откройте раздел заново.';
    if (error.status === 401 || error.status === 403) return 'Не удалось подтвердить доступ. Подключитесь к сети и обновите профиль. Локальный вариант сохранён.';
    if (error.status === 404) return 'Этот вариант недоступен в текущем профиле. Проверьте ссылку и выбранный профиль.';
    return error.message;
  }
  return 'Не удалось сохранить вариант на устройстве. Проверьте доступ к хранилищу браузера и повторите.';
}
