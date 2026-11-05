# Account client integration

The account UI implements the approved completion plan against the published
contract in [accounts.md](accounts.md). The interface uses the existing
worksheet-blue tokens, Cyrillic Manrope/Inter, and shared UI components.
Russian copy covers explicit login, settings, sessions, export, deletion requests,
UUID-specific cancellation and authenticator setup/access.

## Ownership and integration status

Task1/6 owned paths: `frontend/src/accounts/**`, `frontend/tests/account.test.ts`,
`frontend/tests/account-data.test.tsx` and this file. The account page and CSS were
part of the earlier account milestone, but `frontend/src/pages/account.tsx` and
`frontend/src/styles/account.css` are outside this task's editing scope. Shared
identity, routing, bootstrap, backend, e2e, configuration and workflows remain
coordinator/worker-owned. Existing unrelated working-tree changes are preserved;
this task does not commit, push or deploy.

Observed on 2026-11-05:

- `frontend/src/main.tsx` eagerly imports `./accounts/fragment` first. Fragment
  capture runs synchronously before routing. Repeating capture after successful
  URL erasure preserves the captured intent.
- `frontend/src/app/app.tsx` lazy-loads the account page. `/#/account` renders
  `<AccountPage />`; `/#/auth/complete` renders `<AccountPage completion />`.
  The page imports `account.css`.
- `frontend/src/app/shell.tsx` has a secondary account/header link.
- The account's staff affordance targets `/#/editor`. The current coordinator-owned
  `app.tsx` mounts that route. This task checks the account affordance, not editor
  acceptance.

Task1/6 browser runs use these actual application modules with isolated API mocks,
not temporary replacements for bootstrap, routing or canonical identity.

## Identity boundary

`runtime.ts` connects the account controller to the coordinator's singleton in
`frontend/src/storage/identity.ts`. The shared identity boundary supplies:

```ts
transition(action: () => Promise<unknown>): Promise<void>;
refresh(): Promise<unknown>;
getSnapshot(): {
  value: { id: string; kind: 'guest' | 'account' } | null;
  ready: boolean;
  changing: boolean;
  error: string | null;
  epoch: number;
};
subscribe(listener: () => void): () => void;
```

The transport also requires `epoch` and `subscribe` through
`AccountIdentityAccess`; the flow's narrower `IdentityTransition` interface needs
the transition/refresh/snapshot methods. The runtime uses `current()` and
`subscribe` to clear an enrollment when its owner changes. Account resources are
scoped by `epoch` and canonical owner ID, not the account ID or a historical
entry in `owner_ids`.

`createAccountApi(fetcher, access)` permits an injected identity provider for
tests. Production defaults to the canonical singleton and does not relax access
checks. Ordinary scoped reads, settings, session revocation, export, deletion
requests/cancellation and MFA requests require ready, non-changing, error-free
canonical access with an owner. They pin that owner in `X-Learning-Owner`.

`guardAccountRequest()` subscribes before transport and checks access before
fetching, after the response, after JSON reading and after DTO validation. Its
abort signal is combined with the request timeout. Owner/kind/epoch changes,
verification loss, errors and every intervening `changing` transition permanently
invalidate that request, even if the original owner and epoch return. A stale
HTTP 401 cannot be converted into an absent account for a different scope.

Completion, logout, current-session revocation, MFA confirmation and MFA
verification all call `identity.transition`. The coordinator quiesces old work
before the cookie-changing request and refreshes identity in `finally`, including
failed or ambiguous requests. MFA needs this barrier even when its rotated
cookie resolves to the same owner.

For logout, current-session revocation, MFA confirmation and MFA verification,
`flow.ts` captures `api.captureAccess()` **before** quiescing identity and passes
the frozen owner/epoch to the transition request. These requests can finish while
`changing=true`, before the transition's final refresh. They cannot retarget an
owner/epoch that changes while barriers drain, and additional access changes
still invalidate their responses. MFA enrollment and other-session revocation
remain ordinary scoped requests.

`useAccountResource()` immediately hides cached account data when canonical
verification is unavailable, then reloads when availability returns, including
same-owner re-verification. `useAccountScope()` additionally latches operation
scope and component lifetime for owned async callbacks. Export, deletion,
settings, revocation, MFA and clipboard-result callbacks cannot update old UI or
start a download after unmount/scope loss. The keyed `AccountDataScope` discards
the old scope's cancellation/retry state. Intentional transition completion stays
in the flow; refreshed resources remount the current UI rather than reviving old
callbacks.

### Bootstrap exceptions

`/auth/config`, `/auth/request-link` and `/auth/complete` remain bootstrap-exempt
and send no owner pin. Their existing input, response, consent and secret
protections remain in force. Completion responses are reconciled against the
verified canonical account before the flow confirms access.

`current()` permits a minimal `GET /account` while identity is unverified but not
changing or in error. It never pins an unverified cached owner. An unchanged
HTTP 401 may return `null`; a positive account response requires verified
canonical account access and a matching `root_guest_id`. If verification changes
during that bootstrap read, the response is rejected and a fresh verified read is
needed. Bootstrap/cached account PII is never surfaced by the resource hook.

Guest-origin adoption, queued writes, storage namespaces and identity caches stay
behind this boundary. The account client never creates a guest automatically,
clears practice records, or writes canonical identity/cache values itself. The
earlier identity regression evidence below exercises preservation of original
guest records and the exact pending attempt; it was not rerun as a Task1/6 gate.

## Transport and endpoints

All paths below are prefixed by `/api/v1`. The adapter uses
`credentials: 'same-origin'`, `cache: 'no-store'`, `redirect: 'error'` and a
15-second request timeout. Mutations send JSON with
`X-Requested-With: math-ege`; the browser supplies its same-origin `Origin`.
There is no automatic mutation retry. Recognized server error codes map to local
Russian messages; arbitrary response messages and network exception details are
not displayed or retained as flow errors.

| Method and path | Client request / result |
| --- | --- |
| `GET /auth/config` | `enabled`, policy URL/version and 900-second link lifetime. |
| `POST /auth/request-link` | `{email, policy_version, accept_policy: true}`; generic delivery acknowledgement. |
| `POST /auth/complete` | `{token}`; single-use completion returning `AccountView`. No `Idempotency-Key`. |
| `POST /auth/logout` | `{}`; revoke current access through the identity transition. |
| `GET /account` | Owner-matching verified `AccountView`; only an unchanged HTTP 401 becomes an absent account. See the limited bootstrap exception above. |
| `PATCH /account` | Only `{daily_minutes: 10 \| 20 \| 30}`; returns updated account. |
| `GET /account/sessions` | Active-session list with current-device marker and dates. |
| `POST /account/sessions/{id}/revoke` | `{}`; current-device revocation uses the transition. |
| `GET /export` | Complete version-1 history: exactly `version`, `exported_at`, `profile_id`, `sessions`, `assessments`, `learning`, `account`. |
| `GET /account/deletion-request` | `{request: null}` or the existing request. |
| `POST /account/deletion-request` | `{confirm: true}`; request receipt and deadline. |
| `POST /account/deletion-request/{request_id}/cancel` | `{}`; exact five-field canceled receipt for the selected UUID. |
| `POST /auth/mfa/enroll` | `{}`; transient server-generated provisioning URI and expiry. |
| `POST /auth/mfa/confirm` | `{code}`; confirm setup through the identity transition. |
| `POST /auth/mfa/verify` | `{code}`; refresh staff MFA through the identity transition. |

The backend's `enabled` gate represents external policy approval and deployment
readiness. Enabled email login requires a usable HTTPS policy URL and current
policy version. The form collects that version's explicit consent. The only
editable account setting is `daily_minutes`; there are no analytics or
minor-specific account controls. Minor-consent guidance points to the approved
policy and the guest continuation.

### Complete history export

Both the guest/progress helper (`api.export()` or `boundApi(owner).export()`) and
`accountApi.exportHistory()` request `GET /api/v1/export`. The backend's older
`GET /api/v1/account/export` remains a compatibility-only account endpoint; neither
download helper uses it or falls back to its partial response.

`HistoryExport` in `frontend/src/api/types.ts` has exactly seven required root
fields. `AccountExport` aliases that type, not the ordinary account-access view:

| Field | Complete public DTO |
| --- | --- |
| `version` | The string `'1'`, not a numeric version or a new version. |
| `exported_at` | Export timestamp with a timezone. |
| `profile_id` | Current profile ID; it need not equal a historical session's profile ID. |
| `sessions` | All practice histories, including tasks, attempts, drafts, help, options and summaries. Extended sessions are not capped at their requested length. |
| `assessments` | Diagnostic and exam histories, including public task conditions, drafts and separately released server/local results. |
| `learning` | `algorithm_version`, all `annotations`, all `reviews` (including closed reviews), and editorial `corrections` with their history references. |
| `account` | `null` for a guest, or the minimal account DTO described below. |

Every exported practice session and assessment requires `profile_revision` and a
frozen `ProfileSource` in `profile`, matching its historical `profile_id` and
revision. This source does not contain current-bank `demo_mode`, `bank_size` or
slot `available_tasks`. Ordinary `LearningSession` responses retain optional,
nullable historical fields for backward compatibility; complete exports do not
accept missing or null frozen profiles.

The minimal account DTO contains only `id`, `email`, `created_at`,
`email_verified_at`, `role`, `daily_minutes`, `consents` and `deletion_request`.
Each consent retains `policy_version` and `accepted_at`; the nullable deletion
request retains `id`, `status: 'requested'`, `requested_at` and `deadline_at`.
It is not an `Account`: owner mappings, login/access sessions, authentication
tokens and MFA state or secrets are not export fields. The export's nested
deletion DTO remains requested-only; cancellation uses the separate
`DeletionCancellation` receipt described below.

Prepared, active and awaiting-snapshot assessments may retain conditions and
drafts, but both result fields must be `null`. Non-null results require
`status: 'completed'`, a non-null `released_at` no later than `exported_at`, and a
result snapshot no later than release. A completed label alone does not authorize
results. Released rows keep the backend wire names `raw`, `normalized` and
`expected`, solutions and first-draft/first-answer history. The public
`snapshot_hash` and `checker_revision` are preserved, and server/local results
remain separate rather than being merged into an adapted UI result. Hidden
grading rules, private snapshots and answers on public task conditions are
rejected.

`parseHistoryExport(payload: unknown)` in
`frontend/src/api/history-export.ts` validates an exact allowlisted shape and
returns fresh DTO copies. Missing/extra fields, malformed values, unsafe object
keys, inconsistent references and unreleased results reject the entire export;
there is no coercion, partial-response fallback or silent field stripping. Both
adapters turn parser failures into sanitized `502 / invalid_response` errors
before returning data to the download UI.

There is no history pagination, dashboard-sized collection cap or truncation.
All accepted entries, including false/cleared annotation flags, are retained.
Whole-document safety budgets reject oversized input instead of returning a
partial archive: at most 2,000,000 JSON values, nesting depth 16 (root depth 0),
64 Mi UTF-16 code units of aggregate string/key text and 1 Mi UTF-16 code units
per string/key. DTO-specific string bounds count Unicode characters, matching
the backend rather than incorrectly rejecting non-BMP draft text. These are
parser budgets, not guarantees about raw HTTP response size or browser memory.

Requests pin the canonical owner in `X-Learning-Owner` and observe the identity
epoch/transition boundary until the response is validated. A late response after
an identity transition is rejected, even if the final owner ID is unchanged.
Account export also requires ready, error-free canonical access. The adapters
only read identity state; they do not create guests or change storage ownership.

#### Export verification: 2026-11-05

Commands ran from `frontend`; these checks are separate from the earlier account
browser evidence below.

| Check | Observed result |
| --- | --- |
| `npm test -- tests/history-export.test.ts` | **59 passed**, including the non-BMP Unicode regression. |
| `npm test -- tests/history-export.test.ts tests/account.test.ts tests/api.test.ts tests/identity.test.ts tests/extras.test.ts tests/assessment.test.ts tests/session.test.ts` | **176 passed** across seven files. |
| `.\node_modules\.bin\eslint.cmd src/api/types.ts src/api/client.ts src/api/history-export.ts src/accounts/api.ts src/accounts/types.ts tests/history-export.test.ts --max-warnings 0` | Passed. |
| `.\node_modules\.bin\tsc.cmd --project tsconfig.app.json --noEmit` | Passed. |
| `.\node_modules\.bin\vite.cmd build --outDir "C:\Users\user\AppData\Local\Temp\opencode\math-ege-history-export-dist-20261105-1948" --emptyOutDir false` | Production bundle and PWA generation passed into the isolated artifact directory. |

Focused tests cover frozen profiles, released and pending results, complete
wire-field retention, null accounts, 60 annotations, extended histories, malformed
or non-public fields, whole-document budgets, both adapters and late same-owner
transitions. Earlier isolated backend-serialized exports were also parsed
losslessly and round-tripped through the backend `HistoryExport` schema. This is
DTO/adapter compatibility evidence, not a live browser-to-backend export run or
a rerun of the older mocked account browser scenarios.

## Email fragment and single-use recovery

The backend delivers
`${ACCOUNTS_PUBLIC_ORIGIN}/account#token=<opaque>`. The client also accepts
`/auth/complete#token=<opaque>` as an ingress alias. Both pathnames require the
deployment's ordinary SPA fallback to `index.html`.

`captureAccountLink()` saves the original fragment locally, immediately calls
`history.replaceState(null, '', '/#/auth/complete')`, then validates it. A query
string, failed URL erasure, wrong ingress path, missing/duplicate field or
malformed token cannot complete login. Capture performs no login POST and does
not read cookies, copy `history.state`, log the token, or persist it.

One frozen `{token}` body stays in memory. Its browser retention is bounded to
15 minutes from capture; the server still enforces expiry from issuance. Success,
final rejection, navigation away from completion, an explicit new-link action,
or `pagehide` drops it. Reloading the scrubbed page cannot restore the token.

The user must press **«Войти»**. Concurrent controller calls coalesce into one
operation. `/auth/complete` is **single-use**, and replay returns HTTP 400
`invalid_link`; it is not an HTTP-idempotent endpoint.

Recovery proceeds as follows:

1. After the explicit POST, wait for the identity transition's refresh. A received
   successful account response must match a ready, error-free account identity
   through `root_guest_id` and verified email.
2. For an ambiguous response or unconfirmed transition, read `GET /account`.
   Check identity readiness both before and after that read. The returned account
   must match the canonical account owner; a received completion response also
   pins the expected account ID.
3. If current access is confirmed, clear the token and display the current email
   with a prompt to verify that the intended account is open. When the completion
   response was lost, this confirms current access, not that the link necessarily
   established it.
4. If access remains uncertain, `completionRecovery: 'check'` offers
   **«Проверить текущий вход»**. That action only refreshes identity and reads
   `/account`, even if `complete()` is invoked again. It sends no completion POST.
5. Another explicit **«Войти»** becomes available only after the read-only check
   confirms an absent account and a ready guest/absent identity, and no successful
   completion response has been received. It reuses the retained body, subject to
   expiry. There is never an automatic second POST.
6. A definitive `invalid_link` is final, including when another account is already
   signed in. It does not turn into read-only completion success.

The observable flow state and sanitized error survive identity-driven React
remounts. Raw link data stays outside the public flow snapshot.

## Account interactions

- **Settings:** save the server-supported daily duration and focus the saved
  status after the submit button disappears.
- **Sessions:** list dates/current-device status; refresh after revoking another
  device. Logout and current-device revocation use the identity transition and
  clear transient completion/enrollment state.
- **Export:** download `ege-account-history.json` only after the complete
  `/export` response passes the shared parser and identity checks above. A
  response arriving after the account component unmounts cannot create a download
  or blob URL. The guest/progress helper uses the same complete contract.
- **Deletion request:** a native modal starts on the cancel action and requires
  an explicit checkbox. Escape/cancel restores trigger focus; successful
  submission focuses the receipt. The UI shows request date, deadline and
  `requested` status, with explicit wording that processing is pending. The
  backend retains the first request/deadline, no later than 30 days. This client
  records requests/status only; fulfillment is an operational process.
- **Cancellation:** offer **«Отменить запрос удаления»** only for a successfully
  loaded `requested` status. Focus the factual canceled receipt, refresh persisted
  status and bind any explicit uncertain-response retry to the same selected
  UUID. Cancellation does not delete the account or data.
- **MFA bootstrap:** a verified student can enroll before an operator assigns a
  staff role. The server requires recent email login and controls role assignment.
  Successful student enrollment displays preparation status. The editor link
  requires a server staff role, enabled MFA and an unexpired verification window;
  it disappears when the window expires.
- **MFA lifetime:** keep only the server-provided `otpauth://totp/` URI and expiry,
  with an explicit copy action. Drop the redundant raw secret from the DTO. The
  in-memory enrollment is account-bound, survives a rejected confirmation and
  same-owner remount, and is cleared on success, expiry, owner change, navigation
  away from account settings or `pagehide`. A late enrollment response after
  cleanup cannot restore it. URI/code data is not placed in browser persistence
  or error snapshots; the URI region is hidden in print styles. Input accepts
  pasted six-digit ASCII codes, including leading zeroes.

## Deletion cancellation contract and recovery

`accountApi.cancelDeletion(id)` validates a canonical lowercase, hyphenated UUID
before transport. It sends `POST /api/v1/account/deletion-request/{id}/cancel`
with `{}`, the verified owner pin and the existing mutation protections. The
response is a flat object with exactly these five required fields:

```ts
type DeletionCancellation = {
  id: string;
  status: 'canceled';
  requested_at: string;
  deadline_at: string;
  canceled_at: string;
};
```

The receipt ID must equal the selected UUID. Missing/extra fields, a nested
`request` envelope, other statuses and malformed dates reject the response with
a sanitized `invalid_response` error. Deletion timestamps require a valid
calendar/time, an explicit timezone and at most six fractional digits. The
deadline cannot precede the request or exceed thirty days; cancellation cannot
precede the request. `deletionInstant()` compares validated timestamps as bigint
microseconds rather than letting `Date.parse()` truncate fractional digits. The
UI also checks that request/deadline instants match its selected request; equivalent
timezone offsets are accepted, but even a one-microsecond mismatch is rejected.

While status is loading or failed, cached receipts do not enable cancellation or
a new deletion request. Unsupported statuses also fail closed at the rendering
boundary. Request/cancellation share an immediate pending-action latch to prevent
double submission. All deletion controls are unavailable while busy, including
the status-error retry during an explicit cancellation retry.

Success focuses **«Запрос удаления отменён»**, shows request/cancellation dates
and states **«Отменён только этот запрос. Это действие не удаляет аккаунт или
данные.»** It performs a read-only persisted-status refresh rather than replacing
the status with `null`, which could erase a concurrently created newer request.
A failed refresh keeps the validated cancellation receipt and offers status
recovery, not another cancellation. A stale `requested` status for the canceled
UUID offers neither another cancellation nor a new request until status is
confirmed.

For an uncertain/malformed response, the client retains a copy of the selected
request, automatically reads status, and offers **«Повторить отмену этого
запроса»** without automatically resending the mutation. If status now contains
UUID B, retrying the earlier UUID A still sends A; B remains pending. The backend
returns the persisted canceled receipt when the exact already-canceled UUID is
explicitly retried, even when a newer request exists. Scope changes/unmount
discard or suppress this recovery state rather than applying it to another owner.

## Task1/6 verification: 2026-11-05

These are the current scoped results, after the final busy-control correction.
Commands ran from `frontend` unless noted otherwise.

| Check | Observed result |
| --- | --- |
| `.\node_modules\.bin\vitest.cmd run tests/account.test.ts tests/account-data.test.tsx` | **126 passed**: 116 API/flow tests and 10 SSR rendering cases. |
| `.\node_modules\.bin\eslint.cmd src/accounts tests/account.test.ts tests/account-data.test.tsx --max-warnings 0` | Passed, no output/errors. |
| `node "C:\Users\user\AppData\Local\Temp\opencode\math-ege-account-task16-types.cjs"` | **19 owned roots, 0 diagnostics**. |
| Viora `check.mjs src/accounts src/styles/tokens.css src/styles/base.css src/styles/components.css` | **20 files, 0 errors, 0 warnings**. |
| Viora `wig.mjs` over the same paths | **20 files, passed**. |
| Viora `ru.mjs src/accounts` | **8 Russian-text files, passed**. |
| Viora `contrast.mjs src/styles/tokens.css` | **13 measured pairs, 0 failures**. |

Viora scripts were invoked with `node` at
`C:\Users\user\.config\opencode\skills\viora-design-skills\scripts`.
The temporary compiler probe uses the project's compiler options with account
sources and the two account test files as roots. Imported files are resolved but
not independently checked. This is **not** a full-project TypeScript/build pass;
no shared configuration was changed to obtain it.

Owner-change settings, intentional logout, missing cancellation API and missing
cancellation UI regressions were observed RED before their fixes. The focused
command `.\node_modules\.bin\vitest.cmd run tests/account.test.ts -t "one microsecond"`
also reproduced **2 failures** before the precision fix: a deadline one
microsecond beyond thirty days and cancellation one microsecond before the
request. The temporary busy-recovery browser script failed before removing the
enabled status-error retry during cancellation; its corrected run passed below.

API/flow tests exercise verified pins on every scoped endpoint, pre-transport
rejection, late response/body rejection, transient/same-owner changes, bootstrap
PII suppression, pre-transition pins, sanitized errors and the existing
single-use magic-link/MFA behavior. SSR tests mock only the resource boundary and
verify action visibility for loaded, loading, error, absent and unsupported
statuses. They do not exercise DOM events, focus or effects: Vitest's configured
environment is Node, and no DOM environment/configuration was added.

### Current mocked-browser evidence

Playwright CLI drove Chromium against the task-owned Vite server at
`http://127.0.0.1:5197`, in session `account-task16`. Each scenario creates a fresh,
nonpersistent context with service workers blocked, Russian locale and UTC
timezone. API routes are installed before navigation and match paths starting
with `/api/`, not Vite source paths containing `api`. All API responses are mocked;
unexpected API routes fail in the fixture and are checked, never passed through
to a backend. No existing database, SMTP server or deletion/fulfillment process
was used. The identitybrowser agent's ports `8037` and `5193` were not used or
stopped.

After verification, the task-owned `account-task16` browser session and Vite
process were closed. Temporary scripts/screenshots were retained; this task did
not stop shared-agent resources. The Vite completion notification's exit code 1
reflects its intentional process shutdown, not a failed verification gate.

Artifacts are temporary, not committed CI/e2e tests, under
`C:\Users\user\AppData\Local\Temp\opencode`:

| Script | Observed result |
| --- | --- |
| `math-ege-account-task16-cancellation.js` | **46 checks passed**: busy/double-submit behavior, verified headers, receipt focus, persisted-status refresh, UUID A retry after UUID B appears, malformed receipts and stale/failed refreshes. |
| `math-ege-account-task16-busy.js` | **4 checks passed**: no enabled deletion control during uncertain-response retry after a failed status read; same selected UUID. |
| `math-ege-account-task16-scope.js` | **40 checks passed**: valid late-export/download suppression, cancellation unmount suppression, cross-tab owner changes, same-owner/same-epoch transition latching and cached/bootstrap PII suppression. |
| `math-ege-account-task16-transitions.js` | **25 checks passed**: MFA confirmation/verification, rejected-confirmation enrollment retention, late-enrollment cleanup, other/current-session revocation and logout through intentional transitions. |
| `math-ege-account-task16-layout.js` | **36 checks passed**, including five account-surface axe scans, keyboard order/focus, six viewport widths, 44-pixel action targets, reduced motion, zoom simulations, working export and deletion-modal behavior. |
| `math-ege-account-task16-accessibility.js` | **13 account/manual-review checks passed**, with supplemental full-page scan results and computed dialog contrast recorded separately below. This is not an all-page accessibility pass. |

The CLI configuration is `math-ege-account-task16-cli.json`; setup runs
`math-ege-account-task16-fixtures.js`. Each scenario script is then invoked from
the temporary directory with:

```powershell
npx.cmd --yes --package @playwright/cli playwright-cli -s=account-task16 --raw run-code --filename "<absolute script path>"
```

Counts include the per-context checks for no uncaught page errors and no unmocked
API passthrough. Deliberate mocked HTTP/network failures are expected. This phase
does not rerun the earlier browser magic-link scenarios; their evidence below is
historical, while the current API/flow suite retains those regressions.

Screenshots were generated and inspected in
`C:\Users\user\AppData\Local\Temp\opencode\math-ege-account-task16-browser`:
`account-desktop.png`, `account-mobile.png`, `account-mobile-top.png`,
`account-mobile-viewport.png`, `account-canceled-mobile.png`,
`account-retry-mobile.png`, `account-retry-mobile-viewport.png` and
`account-deletion-modal-mobile.png`. Desktop/mobile captures use 1440/390 CSS
pixels; horizontal fit was checked at 320, 360, 390, 768, 1024 and 1440. Full-page
captures can include fixed chrome at the current viewport position; viewport
captures additionally confirm the unfocused skip link is hidden and the old-UUID
retry can receive unobscured focus. The worksheet-blue tokens, Cyrillic fonts and
five-item navigation were retained without shared CSS/navigation edits.

Five account-surface axe scans used WCAG 2.0/2.1 A/AA and 2.2 AA tags for requested
status on desktop/mobile, canceled receipt, uncertain cancellation with a newer
request and the mobile deletion dialog. They reported **0 violations**. The
native dialog has a `color-contrast` incomplete result on four text nodes because
axe reports `elmPartiallyObscuring`; it is not an automatic pass. The opaque white
dialog was inspected, and computed-color measurements are **15.77:1** for the
heading/body/checkbox text and **6.95:1** for the submit label. Supplemental
full-page requested/retry mobile scans reported no violations/incompletes; the
desktop shared-shell finding remains below.

### Coordinator handoffs and limits

- **Late logout navigation:**
  `math-ege-account-task16-shared-logout.js` reproduced this with a fresh mocked
  context: start logout, hold `/auth/logout`, navigate to `#/help`, then release
  the response. At that worker handoff the final route became `#/account`. The then-unguarded callback in
  `frontend/src/pages/account.tsx:33` calls `current.retry()` and
  `navigate('/account')` after the original page has unmounted; catch/finally also
  retained page-local state callbacks. The coordinator subsequently added the
  page-lifetime/unchanged-route guard without blocking intentional canonical
  logout. [Durable mounted proof](account-boundaries.md) records 20 mounted and
  13 real IdentityManager tests, including a portable 33-test run. Successful
  logout updates canonical identity, while the departed page cannot override the
  chosen `#/help` route. The historical worker RED remains unchanged; this worker
  did not edit that page.
- **Desktop shared-brand label:** the supplemental full-page desktop axe scan
  at this worker handoff reported `label-content-name-mismatch` on `.brand` in
  `frontend/src/app/shell.tsx:30`, despite the then-expanded `aria-label`.
  There are no account targets for this finding. The full-page desktop scan is
  **not clean**, and the coordinator-owned label was not changed by this worker.
  The coordinator later removed the override and separated the visible text:
  the natural name is now `ЕГЭ Профиль Математика 2027`. The focused real-API
  brand-rule proof passed; see [the coordinator record](browser-integration.md#desktop-brand-label-regression).
  This does not turn the historical full-page scan into a clean result.

The worker's Task1/6 gates above are scoped, not full-project lint/test/TypeScript/build or
real-backend/e2e acceptance. Half-width reflow and CSS `zoom: 2` are simulations,
not real-device browser-zoom certification. No live SMTP, HttpOnly browser-binding,
guest-claim migration, deletion execution, screen-reader/real-device certification
or field performance measurement is claimed. Earlier broader results below do
not establish a current full-project pass.

The coordinator subsequently completed whole-frontend lint/unit/build
(**409 tests**), shared Chromium (**26 passed / 4 intentional identity skips**)
and all four dedicated real-API identity scenarios together in one fresh runtime
(**4 passed / 0 skips**). See [the final local protocol](verification.md) and
[the dedicated identity record](identity-browser.md). These results do not turn
the mocked worker checks into live SMTP, deletion-execution or device acceptance.

## Earlier account milestone verification: 2026-11-05

Commands were run from `frontend` unless noted otherwise.

| Check | Observed result |
| --- | --- |
| `npm test -- tests/account.test.ts tests/identity.test.ts` | **49 passed**: 44 account and 5 identity tests. |
| `.\node_modules\.bin\eslint.cmd src/accounts src/pages/account.tsx tests/account.test.ts --max-warnings 0` | Passed. |
| `.\node_modules\.bin\tsc.cmd --project tsconfig.app.json --noEmit` | Passed. |
| `.\node_modules\.bin\vite.cmd build --outDir C:\Users\user\AppData\Local\Temp\opencode\math-ege-account-dist --emptyOutDir false` | Production bundle and PWA generation passed into the isolated artifact directory. |
| Viora `check.mjs` over account sources with shared token/base/component CSS | 19 files, **0 errors, 0 warnings**. |
| Viora `wig.mjs` over the same paths | 19 files, passed. Shared `Loading`-import heuristic suppressions have local explanations. |
| Viora `ru.mjs` over account sources/page/CSS | 9 files with Russian text, passed. |
| Viora `contrast.mjs src/styles/tokens.css` | **13 measured pairs, 0 failures**. |

Account tests cover generic email handling, consent/input validation, safe errors,
fragment erasure/expiry, explicit transition calls, single-use recovery and final
rejection, MFA retention/cleanup and deletion-request confirmation. The two latest
controller regressions were observed failing before their fixes: identity becoming
uncertain during the read-only account check, and enrollment surviving successful
current-session revocation.

### Earlier browser evidence

Playwright CLI drove Chromium at `http://127.0.0.1:5176` with **all API requests
mocked**. The real shell, routes, eager import and identity manager were used.
The isolated scripts live in `C:\Users\user\AppData\Local\Temp\opencode` and are
ad-hoc verification artifacts, not committed CI tests:

- `math-ege-account-browser.js`: install API fixtures before navigation.
- `math-ege-account-interactions.js`: **24 checks passed**, including settings,
  saved/receipt focus, JSON download, deletion confirmation/cancel, student MFA
  bootstrap, same-owner remount, staff-window expiry, navigation cleanup,
  revocation/logout and mutation headers.
- `math-ege-account-login-checks.js`: **20 checks passed**, including the policy
  gate, local validation, immediate fragment erasure, explicit completion,
  lost-response recovery, read-only checking, explicit retry and used-link rejection.
- `math-ege-account-final-checks.js`: **14 additional interaction/layout checks
  passed**, including keyboard reach/focus outlines, native modal background
  exclusion, 44-pixel account action targets, reduced motion, late-export
  suppression, alternate ingress and navigation cleanup. Six axe scans are
  described separately below.

Each script is invoked after fixture setup with
`npx --yes --package @playwright/cli playwright-cli -s=account-ui run-code --filename <script>`.
The three scenario scripts were run in the order above. Recorded uncaught page
errors were empty; deliberate mocked HTTP/network failures appeared in the console.

Account and login screenshots were inspected at 1440 and 390 CSS pixels, plus the
mobile deletion modal. Horizontal fit was checked at 320 and 390 pixels. Zoom
checks used a half-width 720-pixel viewport and CSS `zoom: 2` at 1440 pixels;
these are reflow/zoom simulations, not real-device browser-zoom certification.
Images use `math-ege-account-{desktop,mobile}.png`,
`math-ege-account-login-{desktop,mobile}.png` and
`math-ege-account-deletion-mobile.png` in the artifact directory.

### Accessibility findings and verification limits

Axe WCAG 2.0/2.1 A/AA scans covered desktop/mobile account, desktop/mobile email
login, the mobile deletion dialog and the explicit completion prompt. They found
**0 violations in the owned account surface** after correcting the current-session
button's visible/accessibility label mismatch.

Those full-page desktop scans reported `label-content-name-mismatch` on the
shared `.brand` link in `frontend/src/app/shell.tsx`, whose label then omitted
«Математика 2027». A subsequent expanded label also failed the supplemental
Task1/6 scan. Both are historical RED observations; the later coordinator
natural-text fix and focused GREEN are linked above. No clean full-page desktop
result is claimed by this worker.

Axe marked four dialog contrast checks incomplete because it could not determine
the background through overlapping native-modal layers. The rendered opaque
white dialog was inspected, and computed-color measurements were **15.77:1** for
its heading/body/checkbox text and **6.95:1** for its submit label. The incomplete
axe result is not presented as an automatic pass.

The aggregate Viora `verify.mjs` invocation did not pass: it treated component
CSS as token files and lacked a screenshot URL. Evidence above comes from the
individual checkers, measured contrast and the mocked-browser screenshot work.

This handoff does not claim a real-backend account end-to-end run, SMTP delivery,
HttpOnly browser-binding verification, live guest-claim migration, deletion
execution, screen-reader/real-device acceptance or field performance metrics.
Backend regression evidence is maintained in `accounts.md`; broader integration,
editor acceptance and the shared page/brand-label corrections belong to the
coordinator.
