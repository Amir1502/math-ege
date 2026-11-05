import { AccountError } from './errors';
import type { Account } from './types';

export function normalizeEmail(value: string): string {
  const email = value.trim().toLowerCase();
  const split = email.lastIndexOf('@');
  const local = email.slice(0, split);
  const domain = email.slice(split + 1);
  if (split < 1 || local.length > 64 || email.length > 254
    || !/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
    || local.startsWith('.') || local.endsWith('.') || local.includes('..')
    || !domain.includes('.')
    || domain.split('.').some((label) => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
    throw new AccountError(422, 'invalid_email');
  }
  return email;
}

export function normalizeMfaCode(value: string): string {
  const code = value.trim();
  if (!/^[0-9]{6}$/.test(code)) throw new AccountError(422, 'invalid_code');
  return code;
}

export function safePolicyUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function isStaff(account: Account): boolean {
  return account.role === 'methodist' || account.role === 'admin';
}

export function hasRecentMfa(account: Account, now = Date.now()): boolean {
  return isStaff(account) && account.mfa_enabled && account.mfa_verified_until !== null
    && Date.parse(account.mfa_verified_until) > now;
}
