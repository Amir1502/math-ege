# Accounts: API and integration contract

The accounts package implements FR-02/NFR-03 with additive ownership links. Email login is opt-in. Accounts are created only by a verified, single-use email link; every new account has role `student`. The migration is `0002_accounts`, after `0001_learning_core`.

## Application integration

The coordinator owns the application factory and the existing practice queries:

```python
from app.accounts.api import router as accounts_router
from app.accounts.service import AccountService

application.state.accounts = AccountService(application.state.service)
application.include_router(accounts_router)
```

Importing the package registers its models on the existing `Base.metadata`. Production schema changes use the explicit additive Alembic migration. Import `app.accounts.models` when constructing metadata for Alembic autogeneration. Downgrade deliberately raises before any schema/data changes.

### Existing practice ownership

Public helpers in `app.accounts.principals`:

```python
resolve_guest(
    db: Session, token: str | None, now: datetime, write: bool = False,
    *, clock: Callable[[], datetime] | None = None,
) -> Guest
account_session(
    db: Session, token: str | None, now: datetime, *, write: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> tuple[Account, AccessSession, Guest]
owner_ids(db: Session, guest: Guest) -> list[str]
root_owner_id(db: Session, guest_id: str) -> str
```

- Resolve a cookie inside `Database.transaction(write=write)`, passing the service's injected `clock`. PostgreSQL writes lock the returned root `Guest`, then its account and access session; SQLite reserves its write transaction before reading. Refreshed token binding, revocation and expiry are checked at post-lock time before updating `last_seen_at`.
- Existing positional arguments and return shapes are preserved. Omitting `clock` retains the caller-supplied fixed `now`; it does not consult a global clock. Callers that can wait for locks must pass `clock=service.clock` so authorization can refresh its time.
- An unclaimed guest resolves to its original record. An account session resolves to `Account.root_guest_id`. Account roots have **no usable guest credential** and their guest expiry is not the account-session expiry. The active `AccessSession.expires_at` governs authenticated access.
- `owner_ids` accepts an already resolved principal. It returns the root and all claimed historic guest IDs, sorted and deduplicated. `root_owner_id` maps trusted internal owner IDs for locking; it does not authenticate a supplied UUID.
- Replace every existing practice ownership equality with the appropriate `owner_ids` scope: sessions, attempts, history/export, seen-task exclusions, assistance/reference flags, first independent attempts and idempotency lookup.
- Preserve each original practice session/event ID and original idempotency record. Account linking does not copy attempts or rewrite practice rows. Writes to an existing session should retain its historic origin. New account-owned series use the root.
- Idempotency lookup must search the original owned namespaces for a matching key, operation and request hash, returning the exact stored response. An unrelated changed-body key must conflict. Keep the original origin on existing replay records.
- Seen-task flags across merged origins combine conservatively: any assistance/reference exposure applies across the scope; the latest seen timestamp governs exclusions.
- `/api/v1/guest` must recognize an active account cookie and preserve it. Return the resolved root ID and the remaining **access-session** lifetime; do not replace it with a new guest because the root's guest expiry has elapsed. An invalid/stale cookie may start a fresh guest with a new ID.

Claims require both the validated current guest cookie and the browser state captured at link initiation. Claiming rotates the historic guest digest and expires its guest credential. The legacy credential cannot access either its old data or account-wide scope. Root and candidate guest locks are acquired in stable ID order. A unique `GuestClaim.guest_id` and serialized completion prevent two accounts from claiming or connecting through the same guest.

### Staff integration

```python
from app.accounts import require_staff

principal = require_staff(request)                 # methodist or admin, recent MFA
publisher = require_staff(request, publish=True)   # admin, recent MFA
```

The return value is immutable `StaffPrincipal(id, role, root_guest_id, session_id)`; `account_id` is an alias for `id`. It contains no bearer or MFA secret. The gate is also exported from `app.accounts.api`.

For a write that must serialize against role/session revocation, repeat authorization inside the same write transaction using `app.accounts.authorize_staff(db, cookie, now, publish=True, write=True, clock=service.clock)` before the mutation. The optional `clock` keyword preserves the existing arguments and `StaffPrincipal` return value. Its returned root is the shared lock. Do not authorize from a role supplied in JSON or a previously cached client DTO.

### ACC-001: post-lock authorization time

An authorization timestamp taken before a lock wait cannot authorize a later mutation. Account code samples the injected clock after SQLite's writer reservation and after the relevant PostgreSQL row locks:

- Completion holds the rate bucket, link, sorted roots, account and affected access-session rows before checking link/claim expiry and creating claims, consent or sessions. The locked link's token/browser binding and single-use state remain protected throughout the wait.
- Principal resolution refreshes account/access state after the root lock and checks the credential again after the account/access locks. This also puts potentially blocking `last_seen_at` update locks ahead of the expiry check.
- MFA enrollment/verification and staff authorization lock/read the MFA credential, then recheck session validity and login/MFA recency, pending-enrollment expiry or the TOTP window using a fresh time. Session revocation rechecks the requesting session after locking the target session.
- Rejected completion retains its persistent attempt limit. Rejected TOTP codes retain their attempt limit without advancing the replay counter, confirming enrollment, refreshing MFA authorization or rotating a bearer. Expired sessions cannot create deletion requests.

All these times come from the injected service clock. A caller that acquires another blocking application lock after authorization must repeat authorization after that lock and before its mutation.

#### Coordinator call-site updates

The shared callers need the following integration changes:

1. In `backend/app/services.py`, `LearningService._guest_transaction` must call:

   ```python
   guest = resolve_guest(db, token, self.clock(), write=write, clock=self.clock)
   ```

2. In `LearningService.guest`, use:

   ```python
   existing = resolve_guest(db, token, self.clock(), write=True, clock=self.clock)
   ```

   Sample `now = self.clock()` again in the success branch before computing the remaining cookie lifetime, and on the fallback path immediately before creating the new guest. Replace the pre-transaction timestamp with those post-resolution samples.

3. In `backend/app/editor/service.py`, `EditorService._write` must pass the same injected clock to its transactional staff gate:

   ```python
   current = authorize_staff(
       db, token, self.learning.clock(), publish=publish, write=True,
       clock=self.learning.clock,
   )
   ```

   Its `atomic()` callback acquires `catalog = lock_catalog(db)` later. Repeat this gate immediately after that lock, before `action(db, catalog)`; apply the same rule if an action acquires a further blocking lock before mutation. Keep the transaction's root lock held throughout. The HTTP `require_staff` wrapper already propagates the injected account clock.

## Configuration

`app.accounts.config.AccountSettings.from_env()` is isolated from the core settings. `AccountService(learning_service, config=None, mail_sender=None)` accepts a public injection seam for tests. A supplied sender must implement `send_login_link(email: str, link: str, expires_at: datetime) -> None`; injection is rejected unless the core `environment` is `test`. Test delivery never bypasses the policy gate.

| Environment variable | Meaning / default |
| --- | --- |
| `ACCOUNTS_ENABLED` | Explicit `true`; default `false`. |
| `ACCOUNTS_POLICY_APPROVED` | Explicit `true` after the applicable policy/legal approval; default `false`. |
| `ACCOUNTS_POLICY_VERSION` | Required immutable version identifier, 1–64 ASCII letters/digits/`.`/`_`/`-`. |
| `ACCOUNTS_POLICY_URL` | Required public policy URL. |
| `ACCOUNTS_PUBLIC_ORIGIN` | Exact application origin, also present in core `ALLOWED_ORIGINS`; HTTPS outside isolated tests. Links use this configured value, never `Host`. |
| `ACCOUNTS_SMTP_HOST` | Required SMTP host. |
| `ACCOUNTS_SMTP_PORT` | `587` by default; set `465` for implicit TLS as appropriate. |
| `ACCOUNTS_SMTP_USERNAME` / `ACCOUNTS_SMTP_PASSWORD` | Required SMTP authentication. |
| `ACCOUNTS_SMTP_FROM` | Required sender address. |
| `ACCOUNTS_SMTP_TLS` | `starttls` (default) or `ssl`; certificate verification is enabled. |
| `ACCOUNTS_SMTP_TIMEOUT_SECONDS` | `5`, bounded to 1–10 seconds per socket operation. |
| `ACCOUNTS_MFA_ENCRYPTION_KEY` | Fernet key from the deployment's secret store; required for MFA and staff access. No built-in/default key. |

Missing approved policy/version/origin or delivery settings makes login unavailable. `COOKIE_SECURE` and the cookie name come from the core settings. SMTP delivery exceptions log only the exception class, never recipient, link, message body or credentials. New dependency pins are PyOTP 2.10.0, cryptography 50.0.2, cffi 2.1.1 and pycparser 3.12; existing pins are preserved.

## HTTP contract

All paths below start with `/api/v1`. All mutations require the existing allowed `Origin`, `X-Requested-With: math-ege`, and `Content-Type: application/json`. Unknown request fields and coercive types are rejected. Responses use the existing error envelope:

```json
{"error":{"code":"invalid_link","message":"Ссылка недействительна. Запросите новую в этом браузере.","field":null}}
```

Auth/account responses are `Cache-Control: no-store`. Authentication uses the existing `math_ege_guest` cookie: opaque 256-bit random value, `HttpOnly`, `SameSite=Strict`, `Path=/`, `Secure` according to the core setting. Only its SHA-256 digest is stored. Account sessions expire after 30 days, with at most 10 active sessions per account. Successful MFA rotates the bearer without extending that lifetime.

### Login

`GET /auth/config` — public, no mutation:

```json
{"enabled":true,"policy_version":"2026-11-05","policy_url":"https://example.org/privacy","link_ttl_seconds":900}
```

When disabled, `enabled` is `false`, and `policy_version` and `policy_url` are `null`.

`POST /auth/request-link`:

```json
{"email":"student@example.org","policy_version":"2026-11-05","accept_policy":true}
```

Returns **202** with exactly the same message for a new/existing address, throttling or SMTP delivery failure:

```json
{"message":"Если адрес доступен для входа, письмо со ссылкой отправлено."}
```

Email addresses use bounded ASCII SMTP syntax, with outer whitespace removed and case normalized. No provider-specific dot/plus alias rewriting is performed. The accepted policy version must equal the current approved version; no consent yields 422. Disabled login yields 503.

The endpoint sets/reuses `math_ege_auth_state`, a 15-minute HttpOnly/Strict cookie with the same secure setting. It does not replace the practice/access cookie. A persistent rolling limit permits at most **5 issued links per normalized address per hour**, plus **100 link requests globally per hour**. Rate state survives restarts and uses database locks; no IP address is collected. Successful issuance is counted even if SMTP fails.

The email contains `${ACCOUNTS_PUBLIC_ORIGIN}/account#token=<random-value>`. The link expires at 15 minutes and is single-use. Its token and browser state are stored as digests only. Opening the frontend page is not confirmation: the client reads the fragment, removes it from browser history, then explicitly confirms by POST. Do not put the token in a query string, analytics, a log, or a GET mutation.

`POST /auth/complete`:

```json
{"token":"the-43-character-value-from-the-fragment"}
```

Requires the initiating browser-state cookie and the same credential state as initiation. A different browser, changed guest cookie, stale claim, expired/used/invalid link or superseded policy receives 400 `invalid_link`. Failed confirmation does not consume a valid link. Completion has a persistent global cap of 500 attempts/hour (429). Success consumes the link, establishes the access cookie, clears browser state, and returns `AccountView` below. Replaying completion returns 400, not a second session.

`POST /auth/logout` with `{}` revokes the current access session and clears both cookies. It is idempotent and returns `{"ok":true}`.

### Account and export

`GET /account` and successful `/auth/complete` return exactly this `AccountView` shape (UUIDs/timestamps are illustrative):

```json
{
  "id":"account-uuid",
  "email":"student@example.org",
  "email_verified":true,
  "role":"student",
  "root_guest_id":"root-guest-uuid",
  "owner_ids":["historic-guest-uuid","root-guest-uuid"],
  "created_at":"2026-11-05T12:00:00+00:00",
  "policy_version":"2026-11-05",
  "consented_at":"2026-11-05T12:00:00+00:00",
  "daily_minutes":20,
  "mfa_enabled":false,
  "mfa_verified_until":null
}
```

`role` is `student`, `methodist`, or `admin`. `mfa_verified_until` is nullable and becomes null when the current session's 15-minute MFA window expires. Other devices do not inherit that window.

`PATCH /account` accepts only `{"daily_minutes":10}`, `20`, or `30`, and returns `AccountView`. Email, verification, owner IDs and roles are not editable through this endpoint.

`GET /account/export` returns:

```json
{
  "version":"1",
  "exported_at":"2026-11-05T12:00:00+00:00",
  "account":{},
  "sessions":[],
  "consents":[{"policy_version":"2026-11-05","accepted_at":"2026-11-05T12:00:00+00:00"}],
  "deletion_request":null
}
```

`account` is the full `AccountView` above; `sessions` contains the existing allowlisted practice `LearningSession` DTOs, including unchanged historic attempts, drafts and feedback. This endpoint does not load private assessment snapshots. It excludes tokens/digests, ciphertext, MFA secrets/attempt buckets, SMTP settings and operator audit data. The coordinator extends the existing learning export using its own released-result DTOs where needed.

### Deletion: request, cancellation and completion

Migration `0008_account_deletion_completion`, after `0007_instance_exposures`, adds durable terminal states and transactional erasure of the active cloud account scope. These endpoints are included in the existing accounts router.

`GET /account/deletion-request` returns `{"request":null}` before a request.

`POST /account/deletion-request` accepts `{"confirm":true}`. Both GET and successful POST then return:

```json
{"request":{"id":"request-uuid","status":"requested","requested_at":"2026-11-05T12:00:00+00:00","deadline_at":"2026-12-05T12:00:00+00:00"}}
```

The deadline is exactly 30 days after the first request. Repeated active requests retain the original ID and deadline. Export's `deletion_request` is the inner request object. Request creation leaves the account usable for export and cancellation until fulfillment. Existing authenticated data-rights calls also work when new email login is disabled, subject to their session and MFA requirements.

#### Cancellation

`POST /account/deletion-request/{request_id}/cancel` requires the owning account's live session and exactly `{}`. It returns **200**:

```json
{
  "id":"request-uuid",
  "status":"canceled",
  "requested_at":"2026-11-05T12:00:00+00:00",
  "deadline_at":"2026-12-05T12:00:00+00:00",
  "canceled_at":"2026-11-06T12:00:00+00:00"
}
```

The transaction moves that request ID from `account_deletion_requests` to `account_deletion_cancellations`. Status then returns `{"request":null}`, and exports contain `deletion_request: null`. Retrying cancellation returns the same terminal record. A later request receives a new UUID and deadline; retrying an old cancellation cannot cancel the replacement. Another account's or unknown request ID returns **404**. Cancellations retain their private account FK until that account is eventually erased.

#### Privileged fulfillment and receipt

| Endpoint | Input | Authorization / result |
| --- | --- | --- |
| `POST /admin/account-deletions/{request_id}/fulfill` | `{"confirm":true}` | Live administrator session, confirmed TOTP enrollment, and that session's current 15-minute MFA window; **200** with the committed receipt. |
| `GET /admin/account-deletions/{request_id}/receipt` | No body | Same administrator/MFA gate; **200** with the stored receipt, or **404** before completion. |

Both return the following allowlisted receipt shape:

```json
{
  "request_id":"request-uuid",
  "status":"completed",
  "scope":"active_cloud_v1",
  "requested_at":"2026-11-05T12:00:00+00:00",
  "deadline_at":"2026-12-05T12:00:00+00:00",
  "completed_at":"2026-11-06T12:01:00+00:00"
}
```

Fulfillment uses the persisted request to identify its target. It accepts no account, email, owner list or role supplied by the caller. A target session need not still be live. Execution may precede the deadline; overdue execution records its actual completion time and keeps the original deadline. `confirm: false` returns **422**. Invalid, expired or revoked credentials return **401**; insufficient role or recent MFA returns **403**. A persisted cancellation returns **409 `deletion_canceled`**; an unknown ID returns **404**. Invalid persisted scope/timing returns **409** and rolls back.

The receipt has one opaque request ID, three timestamps and the fixed scope; `status` is a DTO constant. Its table has no account/owner/email/credential columns or foreign keys. Repeated fulfillment of the same completed UUID returns the saved receipt, including after a process restart. It cannot erase a newly registered account that happens to reuse the old email. Retrying requires a currently authorized administrator, including when the deleted account was itself an administrator. A storage failure rolls back both erasure and receipt creation; a timeout can be reconciled by receipt lookup and a retry of the same UUID.

#### State and erasure scope

| State | Durable representation | Next behavior |
| --- | --- | --- |
| Requested | One `account_deletion_requests` row per account, still constrained to `status='requested'`. | Owner can cancel; administrator can fulfill. |
| Canceled | `account_deletion_cancellations`, keyed by the former request UUID. | That request cannot execute. The account can create a new request. |
| Completed | `account_deletion_receipts`, keyed by the executed request UUID. | Idempotent receipt retrieval; original account credentials no longer authenticate. |

`active_cloud_v1` covers the root and **every** historic origin in `GuestClaim`, revalidated inside the write transaction:

| Data | Transactional disposition |
| --- | --- |
| `learning_sessions`, `attempts`, `seen_tasks`, `idempotency_records` | Remove scoped practice history, conditions/snapshots, drafts, responses, exposure/instance flags and replay payloads. |
| `assessments` | Remove scoped prepared, active, awaiting-snapshot and completed records, including private conditions, drafts and server/local results. |
| `learning_evidence`, `learning_policy_states`, `learning_annotations` | Remove scoped evidence, derived state, review policy and personal annotations. |
| `account_magic_links` | Remove consumed and pending links matching the target email, claimed origins, durable credential-account binding or associated bearer digests. A foreign browser's link to the deleted email is included. |
| `account_totp_credentials`, `access_sessions` | Remove enrollment/secret ciphertext, replay/attempt state and all active, expired and revoked account sessions. |
| `account_consents`, `account_deletion_cancellations`, `account_deletion_requests`, `guest_claims`, `accounts`, `guests` | Remove the target's consent/request/claim rows, account and all its origins, after their dependents. |
| `account_role_audit` | Keep role transitions, timestamps and original subject UUID; move the target FK into detached `subject_id` and pseudonymize free-text operators. Matching deleted-email references in other subjects' role audits are also pseudonymized. Canonical opaque operator UUIDs are retained. |
| Editorial tables and published content | Preserve revisions, publications, reviews, editorial audit and existing pseudonymous author/reviewer attribution. Author and independent reviewer remain distinguishable. |

Foreign accounts, their history, credentials and unrelated links are preserved. A contradictory cross-owner FK causes rollback rather than a cascade into foreign data. Shared authentication-rate buckets contain only global event timestamps and remain shared. The eventual purge also removes earlier canceled request IDs: those IDs subsequently return **404**, never authorize another account's erasure.

New magic links record `credential_account_id` so a later MFA bearer rotation cannot orphan their cleanup association. Migration `0008` backfills links recoverable from current access digests or claimed guest origins without changing original bindings. An association already lost before migration through bearer rotation cannot be reconstructed from an unmatched digest alone; target-email and surviving-origin matching still apply.

#### Serialization and migration

Fulfillment acquires the existing `complete-link` then `request-link` barriers without consuming quota, before acquiring all target-origin and administrator roots in sorted UUID order. Account rows are then locked in sorted order, followed by the request and affected credential/link/audit rows. The administrator is reauthorized with the injected clock after the blocking locks and before erasure. Owner cancellation uses the same canonical root/account boundary and rechecks its session after locking the request/cancellation rows. Other mutations must continue to acquire their canonical owner root first.

The winner of a cancellation/fulfillment race commits its terminal state. If linking wins first, its newly claimed origin joins the deletion scope. If fulfillment wins first, the pending target link is gone and completion returns `invalid_link`. Two fulfillments converge on one receipt. All dependent removals, audit pseudonymization and receipt insertion share one `Database.transaction(write=True)` with FK enforcement enabled.

Migration `0008` creates the two terminal tables, adds the nullable magic-link account binding, and permits exactly one linked or detached subject in each role-audit row. The active request table and its existing constraints are preserved. The populated migration regression verifies every original column, metadata parity and enabled SQLite FK enforcement, followed by actual fulfillment and receipt retrieval through a recreated service/engine. Downgrade raises before making changes.

#### Coordinator integration

The current `backend/app/main.py` already provides the necessary mounting points:

```python
application.state.accounts = AccountService(application.state.service)
application.include_router(accounts_router)
```

The service seams for an authenticated caller are:

```python
canceled = application.state.accounts.cancel_deletion(owner_credential, cancellation_request_id)
receipt = application.state.accounts.fulfill_deletion(
    admin_credential, active_request_id, confirm=confirmed,
)
receipt = application.state.accounts.deletion_receipt(admin_credential, completed_request_id)
```

Each mutation owns its transaction. Invoke it before acquiring any external account/root lock, so the login barriers retain their canonical position. Pass the live opaque cookie, not a `StaffPrincipal` or a stored account UUID. Scheduling/operator selection must use persisted request UUIDs and handle expired MFA, cancellation and uncertain responses through these seams. The existing `backend/app/history.py:account_data` reads the active queue and naturally returns a null deletion request after cancellation. Core callers retain the ACC-001 clock propagation documented above.

`backend/app/operations/rights.py` exposes a read-only status/plan. Its current capability check reflects the deployed tables, columns, nullability, primary/foreign keys and terminal/audit constraints. `fulfillment_available` is true only for a compatible completion schema; otherwise the blocker remains `durable_completion_schema_required`. It never assumes availability from the migration name alone.

Status includes nullable `completed_receipt_count` and `retained_cancellation_count`, without returning identity fields. The exact-account plan uses `inventory_scope="active_cloud_v1"`, counts retained cancellations, reports role-audit **detachment** with `rows_deleted=0`, and matches magic links through email, surviving origins, credential-account binding and credential digests. These predicates now agree with the executor after bearer rotation.

This narrow coordinator adaptation is included in the recorded whole-backend gate. Planning remains read-only; execution still goes through `AccountService.fulfill_deletion` with a live administrator and recent MFA. Deadline scheduling remains external and unobserved. `restore_replay_available=false` and its independent-scope-mapping blocker are unchanged; the inventory is not erasure authority or authorization for production promotion.

#### Backup and restore boundary

The receipt proves completion of the active-cloud transaction. The existing maximum 30-day backup retention and the post-restore erasure obligation in [operations.md](operations.md) still govern older copies. Browser-local data, external mail delivery and retained backups are outside `active_cloud_v1`.

A request-ID-only receipt cannot recover deleted account/origin IDs, and a backup may predate the request itself. The coordinator's restore integration therefore needs an independently preserved, access-controlled erasure-scope ledger or equivalent authoritative mapping. It must replay completed erasures against the original account/origin IDs before restored data becomes accessible; matching by reusable email is insufficient. Scope capture must be coordinated with completion before the account mapping disappears. This replay mechanism and operational scheduling remain pending; the receipt alone is not evidence of backup/recovery compliance.

#### Verification evidence — 2026-11-05 deletion completion

The combined gate passed **149 tests in 76.72s**, including all **52 deletion regressions**. Coverage includes unauthorized/foreign requests, durable cancellation, replacement requests, every linked origin and private store, foreign preservation, expired/revoked/MFA-rotated credentials, both login/fulfillment race orders, all cancel/fulfill race outcomes, post-lock expiry, atomic rollback after data removal and receipt insertion, restart/retry behavior, migrated data, late completion, disabled-login data rights and preserved publication/attribution. The nearest account, ACC-001, shared authorization and editorial suites are part of this gate.

Exact PowerShell test command, from `backend`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -c @'
import os
import smtplib
from pathlib import Path
from uuid import uuid4
for key in tuple(os.environ):
    if key.startswith('ACCOUNTS_'):
        os.environ.pop(key)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
def no_smtp(*args, **kwargs):
    raise AssertionError('Real SMTP is disabled in deletion verification')
smtplib.SMTP = smtplib.SMTP_SSL = no_smtp
import pytest
base = Path(r'C:\Users\user\AppData\Local\Temp\opencode') / ('account-deletion-gate-' + uuid4().hex)
assert not base.exists()
raise SystemExit(pytest.main([
    'tests/test_account_deletion.py', 'tests/test_account_expiry.py',
    'tests/test_accounts.py', 'tests/test_account_integration.py',
    'tests/test_authorization_integration.py', 'tests/test_editor.py',
    '-q', '--tb=short', '-p', 'no:cacheprovider', '--basetemp', str(base),
]))
'@
```

Fulfillment in this verification runs only on newly created pytest databases explicitly populated by the fixtures. SQLite writer-contention tests use real held transactions; the PostgreSQL-specific lock boundaries are checked through ORM queries compiled with `FOR UPDATE` and an advancing injected clock.

Scoped Ruff passed with `All checks passed!`. Exact lint and scanner commands:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m ruff check --no-cache app/accounts tests/test_account_deletion.py migrations/versions/0008_account_deletion_completion.py
.\.venv\Scripts\python.exe -X utf8 -B C:\Users\user\.config\opencode\skills\viora-aegis\scripts\viora.py scan --path app/accounts --no-baseline --fail-on high --format markdown
```

The focused Aegis scan inspected **14 account files** and returned **0 critical, 0 high, 17 medium heuristic leads**. Manual review followed the cookie/request input through strict DTOs, role/MFA authorization and parameterized, owner-scoped database mutations (Laws 2–4), then checked credential disposal, atomic rollback and secret-free responses/logging (Law 10). No vulnerability was confirmed among the scanner leads:

- **10 `AUTH-005` — FALSE POSITIVE at Q2/Q3:** eight matches are parameterized SHA-256 bearer lookups; two are equality rechecks of already-looked-up digests. The inputs are attacker-controlled cookies/link tokens, but they do not reach a plaintext-password comparison. The 256-bit random bearer and one-way digest prevent a token-prefix recovery path from the reported comparisons.
- **7 `DOS-001` — FALSE POSITIVE at Q2:** the route-only heuristic omits the persistent global/email issuance and completion limits, shared TOTP attempt limits and enrollment's single-live-credential/recent-login checks. Configuration is a bounded database-free read; logout is a bounded idempotent revocation. The leads establish no missing authentication-attempt limit.

**Not assessed:** live PostgreSQL contention, post-restore erasure replay and deployed scheduling; these require coordinator integration and an isolated PostgreSQL acceptance environment. This focused review did not inspect dependency advisories, git history or deployment infrastructure. The existing SMTP/secret-store and policy acceptance boundaries below also apply.

### Sessions

`GET /account/sessions` returns active, unexpired sessions only:

```json
{"sessions":[{"id":"session-uuid","created_at":"2026-11-05T12:00:00+00:00","last_seen_at":"2026-11-05T12:00:00+00:00","expires_at":"2026-12-05T12:00:00+00:00","current":true,"mfa_verified_until":null}]}
```

`POST /account/sessions/{id}/revoke` with `{}` returns `{"ok":true}`. A foreign ID returns 404. Revoking the current session also clears its cookies. No IP address, user-agent fingerprint or bearer is exposed.

### MFA

`POST /auth/mfa/enroll` with `{}` requires verified email login within the last 15 minutes. It returns the enrollment secret **once**:

```json
{"secret":"generated-base32-secret","provisioning_uri":"otpauth://totp/...","expires_at":"2026-11-05T12:10:00+00:00"}
```

Store/display this transiently for enrollment, never in local persistence, logs or analytics. The pending credential is Fernet-encrypted in the database and expires after 10 minutes. Existing confirmed or live pending enrollment yields 409.

`POST /auth/mfa/confirm` accepts `{"code":"123456"}` in the initiating access session. `POST /auth/mfa/verify` accepts the same shape for an already enrolled account. Both successful endpoints rotate the access cookie and return:

```json
{"enabled":true,"verified_until":"2026-11-05T12:15:00+00:00"}
```

Codes are six ASCII digits, verified by PyOTP with at most one 30-second tick of drift either way. The accepted tick must be newer than the last successful tick for that account. Five attempts per rolling five minutes are permitted across all sessions/workers; rejected codes commit throttle state. A replay/invalid code yields 400; throttling yields 429. MFA enrollment never changes a role. This package does not issue recovery codes or expose a public MFA-reset endpoint.

## Local role bootstrap

The local operator first has the intended person complete email login and MFA enrollment. On the deployment host, with its explicit `DATABASE_URL`, run the following **manually** from `backend`:

```powershell
.\.venv\Scripts\python.exe -m app.accounts.bootstrap --email person@example.org --role methodist --operator operator-id --confirm-role-change
```

All four arguments are mandatory; roles are `student`, `methodist`, `admin`. There is no default administrator, seeded email/secret, startup role assignment or HTTP role-grant route. Staff assignment requires an existing verified account with confirmed MFA. A change writes `account_role_audit` and revokes every existing access session. The user signs in again and verifies a fresh authenticator code before editorial access. The CLI prints the account UUID, not email or credentials.

## Security design and verification boundaries

Flow: browser credential + consent → same-origin account API → hashed link/browser state → TLS email → explicit browser-bound POST → account/root claim → opaque access cookie. Authenticator codes → PyOTP/Fernet → root-serialized MFA state → staff gate. Local operator → role assignment → audit and session revocation.

Trust boundaries are the browser/API, mail recipient/browser, application/database, deployment secret store/application, and local operator/runtime role boundaries. Controls follow Aegis Laws 3 (ownership), 4 (fail closed), 7 (library cryptography), 9 (bounded abuse), and 10 (secret-free logging).

- Spoofing: verified link plus initiating browser/credential binding; opaque cookie lookup.
- Tampering: strict request DTOs, origin protection, parameterized SQL, root locks, authenticated Fernet ciphertext.
- Repudiation: immutable consent, claimed-at timestamps, role audit, deletion-request deadline.
- Disclosure: allowlisted DTOs, fragment-only links, no-store, no secret/email logging.
- Denial: bounded request bodies from core middleware, persistent global/email/MFA rates, socket timeouts, 10 active sessions.
- Elevation: staff role assignment only through local operator; recent per-session MFA; administrative publication gate.

Abuse cases covered: forwarding an attacker's login link to a victim cannot attach the attacker's account to that browser; retaining a guest cookie after claim cannot acquire the account's history; reusing a TOTP or adding a role field cannot grant administrative publication.

Verification commands (from `backend`):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_account_expiry.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_accounts.py tests/test_account_integration.py -q
.\.venv\Scripts\python.exe -m ruff check app/accounts tests/test_account_expiry.py tests/test_accounts.py migrations/versions/0002_accounts.py
.\.venv\Scripts\python.exe -m pip check
```

Tests use fresh SQLite databases, the actual app factory/router and injected mail. They cover link single-use/expiry/binding, privacy and rolling rates, competing claims, immutable attempt IDs/drafts, session revocation, consent gates, role/MFA gates and replay, encrypted storage, safe deletion requests, and populated additive migration with blocked downgrade. Privileged assignments in tests target only newly created test databases.

`tests/test_account_expiry.py` contains the four ACC-001 reproductions. Each holds a real SQLite writer transaction, uses cursor events to observe the queued request's `BEGIN IMMEDIATE`, advances the fixture clock across the boundary, then releases the writer. The tests assert 400 for an expired link, 403 for stale login recency, 400 for an out-of-window TOTP and 401 for an expired deletion-request session, along with absence of authentication/deletion effects. The invalid-TOTP check also verifies persisted attempt accounting without replay-counter advancement or bearer/MFA elevation.

Supplemental cases advance the same injected clock after actual ORM queries compiled with PostgreSQL `FOR UPDATE`: link, root, account, old/active access and MFA credential locks. They exercise post-lock ordering and session/MFA revalidation on SQLite; they do not substitute for live PostgreSQL contention tests.

The migration test copies the actual Alembic environment and revisions `0001_learning_core`/`0002_accounts` into an isolated test directory. It reflects the historical schema rather than using today's ORM, seeds all five original practice tables, verifies all nine account tables, and compares every original row before/after upgrade and the rejected downgrade. Later revisions are checked by the coordinator's full-chain migration gate.

### Verification evidence — 2026-11-05 accounts handoff

| Check (from `backend`) | Observed result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_accounts.py -q` | **32 passed** in 14.87s. |
| `.\.venv\Scripts\python.exe -m pytest tests/test_accounts.py tests/test_api.py tests/test_concurrency.py tests/test_security.py tests/test_foundations.py tests/test_identity_integration.py -q --tb=short` | **174 passed** in 47.13s with the coordinator's core accounts wiring. |
| `.\.venv\Scripts\python.exe -m pytest tests/test_account_integration.py -q --tb=short` | **4 passed** in 1.68s. These integration tests belong to the coordinator. |
| Ruff: `app/accounts tests/test_accounts.py migrations/versions/0002_accounts.py` | Passed. |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements. |
| `.\.venv\Scripts\python.exe -m alembic heads` | Passed: `0006_practice_options (head)`. The earlier missing-`0004_learning` graph blocker is resolved. |

The email-rate race initializes each test app's lazy route schemas through a read-only configuration request before issuing the six concurrent mutations. This avoids overlapping FastAPI warning-filter contexts across test app threads on Python 3.13; the database race and five-message assertion remain exercised.

At this handoff, the coordinator's application factory mounts the accounts router/service, and core practice authentication/ownership uses the account resolver and owner scope. The four core-account integration tests verify historic access and exact idempotent replay, original event origins, preserved account cookies/access lifetime in `/guest`, merged assistance/exposure, and changed-body key conflicts. The `alembic heads` result checks the revision graph; populated full-chain migrations remain part of the coordinator's operational verification.

Completion is intentionally single-use: an uncertain completion response should be reconciled with `GET /account`; a repeated token does not issue another session.

### ACC-001 verification — 2026-11-05

Before the fix, all four held-writer boundary tests failed with the reproduced HTTP 200 responses. After the fix:

| Check | Observed result |
| --- | --- |
| `tests/test_account_expiry.py` | **18 passed** in 4.70s: four real held-writer regressions and 14 modeled PostgreSQL lock-boundary cases. |
| `tests/test_accounts.py tests/test_account_integration.py` | **37 passed** in 23.02s, including the coordinator's fifth integration case. |
| `ruff check --no-cache app/accounts tests/test_account_expiry.py tests/test_accounts.py migrations/versions/0002_accounts.py` | All checks passed. |

These runs used `backend/.venv/Scripts/python.exe`, pytest with `-q --tb=short -p no:cacheprovider`, and unique temporary test directories. Inherited `ACCOUNTS_*` settings were cleared before imports; the import-time database was in-memory SQLite, fixture databases were fresh file-backed SQLite, and real SMTP constructors were disabled while fixtures injected mail. Live PostgreSQL contention remains unverified. The shared-call integration requirements are listed under **Coordinator call-site updates** above.

### Focused security review

Scope: all 12 files in `app/accounts`, with manual inspection of the migration, HTTP tests, request protection, and integration boundaries. Viora Aegis scanned the entire new accounts package; its offline dependency check inspected the pinned backend requirements. The scan produced 0 critical, 0 high, and 14 medium heuristic leads. Manual source-to-sink review confirmed no vulnerability among those leads:

- Seven `AUTH-005` leads matched indexed SQLAlchemy equality predicates on SHA-256 digests. Q1: the cookie/link input is attacker-controlled. Q2: it reaches parameterized digest lookup, not a plaintext password-comparison sink. Q3: these predicates expose no recoverable token prefix; the bearer has 256 bits of randomness. Verdict: false positive at Q2.
- Seven `DOS-001` leads matched route names without inspecting their services. Q1: callers control requests. Q2: email issuance/completion and TOTP attempts reach persistent limits; enrollment requires a recent session and permits only one live pending credential. Configuration is a bounded, database-free read, and logout is a bounded idempotent revocation. Q3: no unbounded authentication work or throttle bypass was established by these matches. Verdict: false positive for the reported missing-control claim.

### Not assessed

Not assessed here: real SMTP deliverability, deployment secret-store operation, legal/minor-data approval, and live PostgreSQL concurrency. Broader core/frontend integration is owned by the coordinator and must retain its regression evidence. No bootstrap or deletion execution against existing user data is part of this task.

The final dependency check was offline and did not query vulnerability advisory databases. The focused scanner did not assess git history, infrastructure, or other agents' packages.
