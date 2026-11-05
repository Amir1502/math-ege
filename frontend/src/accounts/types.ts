import type { HistoryExport } from '../api/types';

export interface AuthConfig {
  enabled: boolean;
  policy_version: string | null;
  policy_url: string | null;
  link_ttl_seconds: number;
}

export interface LinkRequest {
  email: string;
  policy_version: string;
  accept_policy: boolean;
}

export interface LinkComplete { readonly token: string }

export interface Account {
  id: string;
  email: string;
  email_verified: boolean;
  role: 'student' | 'methodist' | 'admin';
  root_guest_id: string;
  owner_ids: string[];
  created_at: string;
  policy_version: string;
  consented_at: string;
  daily_minutes: 10 | 20 | 30;
  mfa_enabled: boolean;
  mfa_verified_until: string | null;
}

export interface AccountSettings { daily_minutes: 10 | 20 | 30 }

export interface AccessSession {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
  mfa_verified_until: string | null;
}

export type AccountExport = HistoryExport;

export interface AccountIdentityAccess {
  getSnapshot(): {
    value: { id: string; kind: 'guest' | 'account' } | null;
    ready: boolean;
    changing: boolean;
    error: string | null;
    epoch: number;
  };
  subscribe(listener: () => void): () => void;
}

export interface AccountRequestAccess { readonly owner: string; readonly epoch: number }

export interface AccountAuthApi {
  captureAccess(): AccountRequestAccess;
  current(): Promise<Account | null>;
  requestLink(body: LinkRequest): Promise<void>;
  complete(body: LinkComplete): Promise<Account>;
  logout(access?: AccountRequestAccess): Promise<void>;
  revokeSession(id: string, access?: AccountRequestAccess): Promise<void>;
  enrollMfa(): Promise<MfaEnrollment>;
  confirmMfa(code: string, access?: AccountRequestAccess): Promise<MfaStatus>;
  verifyMfa(code: string, access?: AccountRequestAccess): Promise<MfaStatus>;
}

export interface MfaEnrollment { provisioning_uri: string; expires_at: string }
export interface MfaStatus { enabled: boolean; verified_until: string }

export interface DeletionRequest {
  id: string;
  status: 'requested';
  requested_at: string;
  deadline_at: string;
}

export interface DeletionCancellation extends Omit<DeletionRequest, 'status'> {
  status: 'canceled';
  canceled_at: string;
}

export interface AccountApi extends AccountAuthApi {
  config(): Promise<AuthConfig>;
  updateSettings(body: AccountSettings): Promise<Account>;
  sessions(): Promise<AccessSession[]>;
  exportHistory(): Promise<AccountExport>;
  deletionStatus(): Promise<DeletionRequest | null>;
  requestDeletion(confirm: boolean): Promise<DeletionRequest>;
  cancelDeletion(id: string): Promise<DeletionCancellation>;
}

export interface IdentityTransition {
  transition(action: () => Promise<unknown>): Promise<void>;
  refresh(): Promise<unknown>;
  getSnapshot(): {
    value: { id: string; kind: 'guest' | 'account' } | null;
    ready: boolean;
    changing: boolean;
    error: string | null;
  };
}
