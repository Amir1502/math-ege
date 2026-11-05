const messages = {
  accounts_disabled: 'Вход по email сейчас выключен. Можно продолжить занятия в гостевом режиме.',
  network_error: 'Нет ответа сервера. Результат запроса не подтверждён. Проверьте соединение и повторите.',
  invalid_response: 'Сервер вернул неполный ответ. Повторите запрос позже.',
  invalid_email: 'Введите email латинскими буквами, например name@example.org.',
  consent_required: 'Прочитайте и примите действующую политику обработки данных.',
  invalid_link: 'Ссылка недействительна или истекла. Запросите новую и откройте её в том же браузере.',
  completion_unconfirmed: 'Ответ на подтверждение не получен. Сначала проверьте текущий вход: эта проверка не использует ссылку повторно.',
  login_not_confirmed: 'Сервер не подтвердил вход в аккаунт. Можно снова нажать «Войти» или запросить новую ссылку.',
  auth_rate_limited: 'Слишком много запросов. Подождите и повторите позже.',
  not_authenticated: 'Сеанс входа завершён. Войдите снова, чтобы открыть данные аккаунта.',
  permission_denied: 'Для этого действия недостаточно прав.',
  invalid_code: 'Введите шесть цифр из приложения-аутентификатора.',
  mfa_invalid: 'Код не принят. Проверьте время на устройстве и введите новый код.',
  mfa_required: 'Подтвердите вход кодом из приложения-аутентификатора.',
  mfa_unavailable: 'Подтверждение для сотрудников сейчас недоступно. Повторите позже.',
  recent_login_required: 'Для настройки защиты нужен недавний вход. Выйдите и снова войдите по email.',
  mfa_already_enrolled: 'Настройка уже начата или завершена. Обновите данные аккаунта. Если адрес настройки утрачен, начните снова через 10 минут.',
  mfa_not_enrolled: 'Сначала настройте приложение-аутентификатор и подтвердите код.',
  mfa_rate_limited: 'Слишком много попыток ввода кода. Подождите пять минут и попробуйте снова.',
  confirmation_required: 'Подтвердите запрос удаления аккаунта.',
  invalid_deletion_request: 'Не удалось определить запрос удаления. Обновите статус перед отменой.',
  action_in_progress: 'Дождитесь завершения текущего действия.',
  conflict: 'Данные изменились. Обновите страницу и повторите действие.',
  request_failed: 'Сервер не выполнил запрос. Повторите позже.',
} as const;

export type AccountErrorCode = keyof typeof messages;

export class AccountError extends Error {
  constructor(public readonly status: number, public readonly code: AccountErrorCode) {
    super(messages[code]);
    this.name = 'AccountError';
  }

  get retryable() {
    return this.code !== 'accounts_disabled' && (this.status === 0 || this.status === 429 || this.status >= 500);
  }
}

export function accountErrorText(error: unknown): string {
  return error instanceof AccountError ? error.message : messages.request_failed;
}

export function responseError(status: number, code: unknown): AccountError {
  // Neither a raw server message nor an unknown error code may contain data for the UI or logs.
  if (typeof code === 'string' && Object.hasOwn(messages, code)) return new AccountError(status, code as AccountErrorCode);
  if (code === 'invalid_mfa') return new AccountError(status, 'mfa_invalid');
  if (status === 401) return new AccountError(status, 'not_authenticated');
  if (status === 403) return new AccountError(status, 'permission_denied');
  if (status === 409) return new AccountError(status, 'conflict');
  if (status === 429) return new AccountError(status, 'auth_rate_limited');
  return new AccountError(status, 'request_failed');
}
