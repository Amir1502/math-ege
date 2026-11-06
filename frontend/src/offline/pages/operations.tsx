import type { Failure } from './shared';

export type PendingOperation<T> = { version: '1'; key: string; body: T };
const prefix = 'math-ege-offline-ui-v1';

export function operationKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
}

export function failure(error: unknown): Failure {
  if (error && typeof error === 'object') {
    const value = error as { code?: unknown; message?: unknown };
    return {
      code: typeof value.code === 'string' ? value.code : 'storage_unavailable',
      message: typeof value.message === 'string' ? value.message : 'Не удалось сохранить или прочитать данные на устройстве.',
    };
  }
  return { code: 'storage_unavailable', message: typeof error === 'string' ? error : 'Не удалось сохранить или прочитать данные на устройстве.' };
}

function storageFailure(error: unknown): Failure {
  return {
    code: 'ui_storage_unavailable',
    message: `Не удалось сохранить ключ операции на устройстве. Действие не отправлено повторно с новым ключом. ${failure(error).message}`,
  };
}

function storageKey(kind: 'start' | 'attempt' | 'finish', id: string) {
  return `${prefix}:${kind}:${id}`;
}

export function readOperation<T>(kind: 'start' | 'attempt' | 'finish', id: string): PendingOperation<T> | null {
  let raw: string | null;
  try {
    raw = localStorage.getItem(storageKey(kind, id));
  } catch (error) {
    throw storageFailure(error);
  }
  if (raw === null) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object') throw new Error('Неверный формат ключа операции.');
    const pending = value as Partial<PendingOperation<T>>;
    if (pending.version !== '1' || typeof pending.key !== 'string'
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(pending.key)
      || pending.body === undefined) throw new Error('Неверный формат ключа операции.');
    return pending as PendingOperation<T>;
  } catch {
    throw { code: 'ui_queue_invalid', message: 'Сохранённый ключ операции повреждён. История не удалялась. Не начинайте вторую копию занятия; попробуйте снова прочитать историю.' } satisfies Failure;
  }
}

export function writeOperation<T>(kind: 'start' | 'attempt' | 'finish', id: string, pending: PendingOperation<T>) {
  try {
    localStorage.setItem(storageKey(kind, id), JSON.stringify(pending));
  } catch (error) {
    throw storageFailure(error);
  }
}

export function acknowledgeOperation(kind: 'start' | 'attempt' | 'finish', id: string) {
  try {
    localStorage.removeItem(storageKey(kind, id));
  } catch (error) {
    throw {
      code: 'ui_queue_acknowledgement_failed',
      message: `Действие сохранено, но не удалось убрать его подтверждённый ключ. Повтор с тем же ключом не создаёт дубль. ${failure(error).message}`,
    } satisfies Failure;
  }
}

export function isAnswerFormatFailure(error: Failure) {
  return /(?:format|invalid_answer|answer_invalid|answer_too_long|empty_answer|zero_denominator|invalid_number|answer_syntax)/i.test(error.code);
}
