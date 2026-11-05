# Identity/linking/export browser verification

**Coordinator result, 2026-11-05:** all four required browser scenarios passed
**together in one new isolated runtime: 4 passed, 0 skips/failures/flaky,
73.805 s, exit 0**. Application-source hashes remained unchanged. This is a
final local Windows Chromium/SQLite gate, not exact-commit Linux/PostgreSQL CI or
production release acceptance. The worker's earlier three-runtime evidence and
failures remain preserved below.

**Scope:** the identity/linking/export portion of approved completion Task 6:
mounted React UI, real FastAPI responses and an isolated production Vite bundle.
The original worker changed only the five new files listed below, not application,
storage, shared configuration, workflow or coordinator-owned files.

## Isolation and owned files

- `backend/tests/identity_browser_server.py`: guarded `APP_ENV=test` factory;
  injected `AccountService(mail_sender=...)` private file mailbox and bounded
  clock. It adds no HTTP routes or public token endpoint and sends no SMTP mail.
- `frontend/scripts/identity-browser.mjs`: additive migration of a new
  `<run-root>/identity.sqlite3`, production build into `<run-root>/dist`, and
  dedicated preview/API processes. It refuses previous database, mailbox, build
  or lock files. It never targets shared `frontend/dist`.
- `frontend/scripts/identity-browser.config.ts`: one Chromium worker, no retries,
  dedicated output directory and ports, `reuseExistingServer: false`.
- `frontend/e2e/identity.spec.ts`: opt-in mounted scenarios, real-response gates,
  owner-scoped read-only IndexedDB inspection and saved-download assertions.
  Ordinary shared runs skip it when `IDENTITY_BROWSER_RUN_ROOT` is absent; use
  the dedicated config to opt in, never a shared config with that variable set.
- `docs/identity-browser.md`: this redacted evidence record.

Only `http://127.0.0.1:5193` is authorized; the API binds to `127.0.0.1:8037`.
Coordinator ports `8000/5173` were not used. All runtime files live under the
approved `%LOCALAPPDATA%\Temp\opencode` directory, outside the repository.
Inherited account configuration is removed before launching the isolated API;
auth is enabled only by the private factory, with test policy
`identity-browser-1` and inert local `/privacy-test.txt`.

Synthetic `.invalid` email, login links, cookies and MFA provisioning data stay
in private runtime files or process/browser memory. No values are printed in
this document or test logs. Traces, videos and automatic screenshots are off;
`PLAYWRIGHT_NO_COPY_PROMPT=1` suppresses secret-bearing failure DOM snapshots in
the installed Playwright version. Private interactions replace detailed errors
with a safe message. The MFA encryption key is generated only in memory.

Verified tools: Node **24.18.0**, Playwright **1.64.1**, TypeScript **6.0.3**, Vite
**8.3.6**, Python **3.13.14** through `backend/.venv/Scripts/python.exe`.
No dependencies were installed or changed by this worker.

## Recorded runs

The following are preserved directory basenames, not directories to reuse:

| Run | Directory under the approved temporary root | Actual command/result |
| --- | --- | --- |
| A | `identity-browser-0fc0d62e-5f7e-465b-bba8-e93dbd23ac97` | `node scripts/identity-browser.mjs` in an owned background process, then `npm exec -- playwright test --config scripts/identity-browser.config.ts` with external-server mode. Claim scenario passed in **13.1 s**; race timed out at **120 s**; two later cases did not run. **Exit 1**, not a green full run. |
| B | `identity-browser-b89b8ab0-0b2b-4b8d-b5f1-a478c593ade2` | `npm exec -- playwright test --config scripts/identity-browser.config.ts --grep 'same-owner\|logout\|actual complete'`, automatic-server mode. Race passed in **6.6 s**, queues in **8.4 s**; export failed on the harness consent-count assertion in **19.6 s**. **2 passed, 1 failed; exit 1; 54.5 s total.** |
| C | `identity-browser-1a833ec9-b062-45a4-b7e3-eb314d1a9a1d` | `npm exec -- playwright test --config scripts/identity-browser.config.ts --grep 'actual complete'`, automatic-server mode. **1 passed; exit 0; 24.8 s scenario, 43.5 s total.** |
| D, coordinator final | `completion-identity-final-c6008f8f701a4c9da64d8c3380e60e91` | `npm run test:e2e -- --config scripts/identity-browser.config.ts --forbid-only --reporter=list,json`, automatic-server mode, no grep. **4 passed together, 0 skips/failures/flaky; exit 0; 73.805 s total.** |

Each successful runtime migrated its own new SQLite database through
`0008_account_deletion_completion`. Its `api.stderr.log` records the additive
migrations and API startup; `build-evidence.json` records the temporary output
path and selected source hashes at build completion. Runs B/C had the same five
recorded source hashes. A had the same worksheet, identity, storage and export
parser hashes, but a different coordinator-owned `src/accounts/api.ts` hash.
Earlier evidence therefore does not certify every subsequent working-tree edit.

### Coordinator final run D

D refused reuse of database, mailbox, dist or lock and built into its own
`<run-root>/dist`; `shared_dist_modified=false`. `IDENTITY_BROWSER_EXTERNAL_SERVER`
was unset. All four named cases ran once, without retries or omissions:
two guest claims (**2.2 s**), same-owner MFA/stale responses (**6.0 s**),
logout/remount/relogin queue isolation (**8.0 s**) and complete closed/released
exports (**36.7 s**). Its report has zero top-level errors.

`report.json` SHA-256:
`37445f815f81fa8942bde0fde967a2ff49dc6e2b9a5b724d15674ae0ceb08bf9`.
`build-evidence.json` and the coordinator's full 323-file backend/frontend
inventory match current application bytes after all local gates. D's private
database, mailbox, downloads, explicit mounted screenshots and logs remain
outside Git; automatic screenshot/trace/video recording was disabled.

The transient startup `ECONNREFUSED 127.0.0.1:8037` preceded healthy API readiness.
Read-only final consumption confirmed 0 listeners on 8037/5193 and 0 remaining
recorded D runner/API processes; no process was stopped by the consumer.
The [central protocol](verification.md) also records the whole frontend/shared
gates and the consumption harness's self-PID selection RED/correction.

D's eight redacted `browser-evidence.jsonl` records and all four saved downloads
were subsequently consumed read-only. D contains **9 unique practice sessions**,
not C's 7, because all preceding cases ran in the same fresh runtime. Each
download retains the two original attempt DTOs/IDs and all **104 annotations**;
closed assessment results remain null, and released server/local regions remain
distinct with **13 rows each**. No raw archive contents or mailbox values were
copied into Git.

| D download | Bytes | SHA-256 |
| --- | ---: | --- |
| `closed-progress.json` | 503528 | `6651b9fde010c1b5555d78930381a3f6735822a491099ba3cb1ead8eb107adc2` |
| `closed-account.json` | 503528 | `7adf54a8fc0bf8822d80a0307fcb4293c47df90317e622ccf3ff499e3282a3fd` |
| `released-progress.json` | 546791 | `d86daf78aec4aff8a565f4de3d91bf723d3ea89fb806ec7256f31bdc408285ec` |
| `released-account.json` | 546791 | `8ca6f8b2b1c4c32195f73340e94aa4b1a24d4f62571b2ba854072a44e8223ba7` |

Both released D downloads share server snapshot hash
`2201b49903d15e7822f4fe7e958de948b8bc83b8a595c1e682d5ac68be16c278`
and local hash
`61b62909ba6b51b5039ad2e69f895a189a9d623e30351e4c867167dc8fd85e0d`.
These hashes are different from each other and from the earlier C fixture;
neither run replaces the other. The release fixture advanced only its private
bounded clock by **901 s**, without editing database timestamps or rows.

## Passing browser evidence

### Two guest histories and claims — A

- Two separate browser contexts created five-task histories through the mounted
  practice UI, including two original attempts and server-saved drafts.
- Both histories were claimed into the same account. Session IDs, complete task
  and profile snapshots/revisions, entire attempt DTOs/IDs and server drafts were
  compared before/after without rewriting or copying them.
- Both original guest credentials returned **401** from `/identity`; their
  mounted history screens were unavailable and exposed no answer input.
- Both drafts were restored through mounted navigation. Guest B's IndexedDB
  draft was verified in the adopted account namespace.

Evidence: A's `browser-evidence.jsonl`, record `two-guest-claims`.

### Same-owner transition and stale responses — B

- Held **four real responses** obtained with `route.fetch()`: practice progress,
  learning dashboard and the two exports initiated by the mounted progress and
  account controls. These were not fabricated response bodies.
- Another account context recorded an additional attempt while the responses
  were held. Mounted MFA confirmation triggered the production identity barrier
  and transition event while owner ID, kind and owned origins stayed unchanged.
- Releasing the old responses produced **zero stale downloads**. New reads were
  also held, so a fresh response could not conceal stale-state resurrection;
  the old statistic and download control were absent during that interval.
- After releasing the new reads, the mounted independent-attempt total was **3**.
  MFA provisioning URI/code were handled privately via project-venv PyOTP stdin,
  not CLI arguments, console output or artifacts.

Evidence: B's `browser-evidence.jsonl`, record `same-owner-transition`.

### Logout/remount/relogin and queues — B

- The real API accepted one start and one attempt, then the browser deliberately
  lost each response (`route.fetch()` followed by `route.abort()`). Both pending
  operations retained their original keys and bodies in account-scoped IndexedDB.
- After mounted logout, full document reload and a new guest start, there were
  **zero cross-owner replays**, no adoption of the account snapshot and no guest
  pending-start entry. Original account queues remained intact.
- The new guest's mounted foreign-history screen exposed no answer input;
  an actual API request for that history returned **404**.
- Mounted relogin restored the original namespace. Explicit retries sent the
  **exact original request bytes and idempotency keys**, reconciled the same
  accepted session/attempt IDs, emptied both queues and created no duplicates.

Evidence: B's `browser-evidence.jsonl`, record `queue-isolation`.

### Actual complete exports and assessment release — C

- The final-only fixture created two five-task guest histories and claimed them;
  five additional twenty-task sessions were created through mounted practice.
  This was fresh scenario population, not a rerun of A/B acceptance assertions.
- **104 annotations** were populated using the normal authorized annotation POST
  route on those UI-created histories, not 104 simulated worksheet clicks. The
  paginated learning export returned **100** with total **104**; each actual
  complete download retained all **104 entire annotation DTOs**.
- The progress and account buttons each produced an actual saved JSON download,
  both while the assessment was closed and after release: **four files** total.
  All passed `parseHistoryExport` with no truncation and exactly these seven
  top-level fields: `version`, `exported_at`, `profile_id`, `sessions`,
  `assessments`, `learning`, `account`. `version` is the string **`"1"`**.
- Each file contains **7 unique practice sessions**, their original profile/task
  snapshots and revisions, and **2 original attempt DTOs/IDs**, unchanged and
  present exactly once. The account has exactly **8 fields**: `id`, `email`,
  `created_at`, `email_verified_at`, `role`, `daily_minutes`, `consents`,
  `deletion_request`. Its synthetic owner is checked privately; there is one
  valid `identity-browser-1` consent and a null deletion request.
- A mounted fifteen-minute exam saved server answer `17`, then edited the local
  answer to `−2,50` while genuinely offline. Browser clock fast-forward crossed
  the deadline. A service-worker-controlled **offline reload** preserved the
  read-only answer and the complete frozen finish key/body in IndexedDB.
- Only the private bounded clock file advanced backend time (**901 s**); no
  database timestamps or rows were edited. The real API reached
  `awaiting_snapshot`. Both closed downloads had null `server_result`,
  `local_result` and `released_at`, with no answer/solution task fields and zero
  hint counts.
- Reconnection submitted the original frozen key and complete JSON body. Both
  mounted result regions rendered **13 rows**: server answer `17`, local answer
  `−2,50`. Released downloads retained distinct server/local sources and
  snapshot hashes; the server reason was `deadline`, and the local result marked
  connection loss. **Both scores happened to be 0/13**; different raw answers and
  hashes, not different scores, prove the snapshots differ.
- The complete released result objects matched across both export controls and
  a real API read after the final mounted document reload.

Evidence: C's five `browser-evidence.jsonl` records, four saved downloads, two
mounted screenshots and `redacted-artifact-manifest.json`. No raw download or
mailbox content is copied into the repository.

## Final artifacts and integrity

All paths below are relative to **C**. Hashes were independently recomputed from
the preserved file bytes after browser/process cleanup.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `downloads/closed-progress.json` | 448551 | `4b410f28e694f7ba8652aaa2cd5ec80fa14287447f33fa029ba1a152a27a6476` |
| `downloads/closed-account.json` | 448551 | `d4750e514535cbc75a7a456b34c0e9e945a1a7717384b19618418628e255f120` |
| `downloads/released-progress.json` | 489941 | `e45af0f36156d9c2f875aba0697b3aa572f2b742ce80e1b330880c3535838286` |
| `downloads/released-account.json` | 489941 | `b0ae952a26da5f9453823f65034e719c36608f0f606cebbac8e3bf827a5d758c` |
| `mounted-offline-pending.png` | 147617 | `e9cb185db8df85eff3331019239a9a5d6fec8d1449864ddf033884657d2af234` |
| `mounted-distinct-results.png` | 280427 | `8b4d12a52d278ed99bb93ba1150fed1704b986ff0417a73049abdb5b0369270d` |

Both released files contain server snapshot hash
`cc4115d63ad748fa35848d198a7777b0a4648c5f8d7626797a1a80226f66d561`
and local snapshot hash
`98a5b66416163368fb9fca22c81764bacf9c68539e3b9a179075268b8ef4ddb3`.
Download file hashes need not match across controls: `exported_at` differs.

C's `verification-source-metadata.json` records the installed versions and four
owned executable/config source hashes. The final spec SHA-256 is
`e342406daedf0a2d1a5e3e5780c48e4b378da1c7ae5fb49ff4b130defa60032e`.

## Reproduce safely

Use the existing installed project dependencies and project Python environment.
From `frontend`, the following PowerShell command repeats only the final scenario
in a **new** runtime; never substitute any preserved A/B/C directory:

```powershell
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8037,5193 -ErrorAction SilentlyContinue)
if ($listeners.Count -ne 0) { throw 'Owned ports are not free; do not stop another worker.' }
$root = Join-Path $env:LOCALAPPDATA ('Temp\opencode\identity-browser-' + [guid]::NewGuid().ToString())
[void][System.IO.Directory]::CreateDirectory($root)
$env:IDENTITY_BROWSER_RUN_ROOT = $root
$env:IDENTITY_BROWSER_EXTERNAL_SERVER = 'false'
$env:npm_config_loglevel = 'error'
npm exec -- playwright test --config scripts/identity-browser.config.ts --grep 'actual complete' 2>&1 |
  Tee-Object -FilePath (Join-Path $root 'playwright.log')
exit $LASTEXITCODE
```

The dedicated config starts the fresh production preview and API automatically.
To run the whole four-scenario flow intentionally in another new runtime, omit
`--grep`. The worker did not rerun that full command after C's correction;
the coordinator subsequently ran all four together as D above.
Common guest/account population is in `beforeAll`, so grep-selected scenarios
do not depend on executing already-proven acceptance cases.

Focused gates rerun after the final spec change, all **exit 0**:

```powershell
# From frontend
npm exec -- eslint scripts/identity-browser.mjs scripts/identity-browser.config.ts e2e/identity.spec.ts --max-warnings 0
npm exec -- tsc --ignoreConfig --noEmit --strict --skipLibCheck --target ES2023 --module ESNext --moduleResolution Bundler --lib ES2023,DOM,DOM.Iterable --types node e2e/identity.spec.ts scripts/identity-browser.config.ts

# From backend
.\.venv\Scripts\python.exe -m ruff check tests/identity_browser_server.py
```

TypeScript 6 explicit-file checking requires `--ignoreConfig`; an earlier command
without it returned TS5112. Ruff reported `All checks passed!`; ESLint had zero
warnings. These are owned-file gates, not whole-repository lint/type/test/CI claims.
The runner uses Vite's isolated production build, not a shared `npm run build`.

## Failures, observations and remaining boundaries

- Initial startup directory
  `identity-browser-749725ae-d893-413c-8581-43d47e9d438e` is also preserved. The
  harness's fragment-bearing `/#/help` policy URL failed account URL validation;
  replacing it with inert `/privacy-test.txt` enabled later fresh runtimes. No
  browser acceptance ran in that directory.
- A's race timeout was a harness lifecycle mistake: production
  `frontend/src/accounts/runtime.ts` intentionally erases MFA enrollment when
  leaving `/account`. Enrollment was moved to the final account visit; B then
  passed the race without an application change.
- B's export stopped after saving `closed-progress.json`: the harness incorrectly
  expected at least two consents. `backend/app/accounts/models.py` makes consent
  unique by `(account_id, policy_version)`, and
  `backend/app/accounts/service.py` inserts only an absent version. One consent
  is correct. C passed after correcting this expectation and adding original
  attempt DTO/ID assertions to every saved file. B's partial file is not claimed
  as successful four-control export acceptance.
- B/C emitted a transient Vite `ECONNREFUSED 127.0.0.1:8037` during the readiness
  probe before API startup. The API subsequently became healthy and the recorded
  scenarios ran; this was not a browser acceptance failure.
- The completed-results screenshot retains the earlier offline
  identity-confirmation warning after result synchronization succeeded. The
  warning comes from the failed offline identity refresh
  (`frontend/src/storage/identity.ts`); `frontend/src/app/app.tsx` exposes an
  explicit retry. Automatic warning clearing on reconnect was **not proved**
  or fixed by this worker. The final reload/result immutability assertion still
  passed. This is a visible UX observation, not evidence of foreign/stale data.
- This is software proof on local Windows Chromium/SQLite with synthetic data,
  a test policy, injected mail delivery and bounded clocks. Real SMTP, legal
  approval, other browsers/devices, production HTTPS/PostgreSQL, full CI and
  independent release acceptance are outside this verification scope. A
  non-null deletion request and duplicate mastery-credit behavior were not
  exercised here. No worksheet sibling-key regression was rerun.

## Preservation and cleanup

No preserved database was reused, mutated or deleted. All preserved runtime
directories retain their databases, temporary production builds and logs;
successful runs also retain their private mailboxes and redacted ledgers.
Saved downloads and screenshots remain outside the repository.

A's runner/API launcher/API child were stopped only after validating their
recorded ancestry. Playwright terminated its owned automatic runtime trees for
B/C. Final inspection returned **0 listeners on 8037/5193** and **0 remaining
recorded C runner/API processes**. D's recorded runner/API processes and dedicated
listeners were also absent at coordinator consumption. No coordinator process
was stopped. Do not
resume preserved runtimes: closed contexts lost in-memory credentials, and the
stopped API lost its ephemeral MFA encryption key.

There were no commits, pushes, destructive commands or changes to shared
application/configuration files by this worker. Unrelated concurrent worktree
changes remain untouched.
