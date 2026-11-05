# Account boundary regression proof

## Scope

This completes the approved late-logout handoff in
[`account-client.md`](account-client.md#coordinator-handoffs-and-limits).
The only production change is `frontend/src/pages/account.tsx`. The new durable
tests are `frontend/tests/account-boundaries.test.tsx` and
`frontend/tests/account-transitions.test.ts`.

No account API, DTO, flow, identity-manager, backend, dependency, configuration,
shared routing, shell or stylesheet was changed. The other worker's
`src/accounts/**`, `account.test.ts`, `account-data.test.tsx` and
`docs/account-client.md` remain outside this patch's ownership. New files are
left in the working tree for the coordinator; no commit or push was performed.

## Late logout: observed RED, then narrow fix

The first durable mounted regression was written before changing AccountPage.
After correcting the fixture's HTML charset, this command produced the actual
behavioral RED, not a harness timeout:

```powershell
# Working directory: frontend
.\node_modules\.bin\vitest.cmd run tests/account-boundaries.test.tsx
```

Observed result: **exit 1, one test failed**. The test clicked the real logout
button, held `POST /api/v1/auth/logout`, navigated to `#/help`, and released a
successful response. The real canonical identity had already become
`guest-after-logout`, with `ready: true`, `changing: false`, no error, and epoch
2. Nevertheless, the final hash was `#/account` instead of the asserted
`#/help`.

The old AccountPage awaited the canonical flow, then unconditionally called
`current.retry()` and `navigate('/account')`. Its error and finally handlers
also retained page-local callbacks after departure.

AccountPage now tracks its mounted lifetime and captures the hash when logout
starts. Only its retry/navigation, local error, and local busy-reset callbacks
are conditional on that lifetime and unchanged route. `accountFlow.logout()`
still runs to completion, including the canonical identity refresh and flow
cleanup. There is deliberately no owner/epoch guard around that intentional
logout transition.

Immediately after the fix, the same focused command returned **exit 0, one
test passed**. The expanded suite now also proves route changes before unmount,
canonical failure handling after departure, and normal logout when the visitor
stays on the account route. Page cases use React StrictMode and the transition
unmount behavior used by App; they do not mount the shared shell.

## Public seams and durable coverage

### Real IdentityManager transitions: 13 tests

`account-transitions.test.ts` uses the real `IdentityManager`, account API,
account flow and link implementation. Only the external identity resolver and
HTTP transport are supplied as test fixtures. No transition implementation,
identity snapshot, hook or private method is mocked.

- **Four intentional transitions:** MFA confirmation, MFA verification, logout
  and current-session revocation. Each captures verified owner/epoch before a
  real `beforeChange` barrier starts draining. Transport remains deferred until
  the barrier is released, runs with `changing: true`, and sends the previous
  verified owner. Same-owner MFA completes at epoch 1; logout/revocation adopt
  the new guest at epoch 2. Duplicate intents coalesce into one transport.
- **Eight draining conflicts:** each of those four operations rejects before
  transport if a public identity refresh changes the owner, or changes away
  and back to the original owner at a newer epoch while the barrier is held.
  These checks detect recapturing access only after draining.
- **One same-owner latch:** a pending valid export rejects after a real
  transition finishes with exactly the previous owner and epoch. The external
  transport deliberately ignores abort, so checking only the final snapshot
  cannot make the test pass.

### Mounted account boundaries: 20 tests

`account-boundaries.test.tsx` mounts real AccountPage, AccountData,
AccountSettings and StaffSecurity components in the installed Chromium browser.
It uses the real singleton identity manager, account API, flow, resource hooks,
scope guards and hash-route hook. A small consumer receives the public settings
callback and updates its real React state; callback observations do not replace
an internal collaborator.

- **Four logout cases:** departed page cannot replace `#/help`; an old route
  cannot navigate even before unmount; canonical failure remains observable
  without an off-route page error; staying on account still opens the signed-out
  email view.
- **Four interactive cancellation cases:** R1 loses its cancellation response,
  persisted status returns R2, and an explicit retry still posts exactly R1's
  UUID and empty body. A valid receipt triggers another persisted-status GET
  rather than replacing R2 with null. Receipt focus, factual copy, busy latching,
  initial/refresh loading, failed reads, and stale R1 after accepted cancellation
  are checked through rendered controls and HTTP observations.
- **Four export cases:** the live native download contains the exact complete
  seven-field DTO (`version`, `exported_at`, `profile_id`, `sessions`,
  `assessments`, `learning`, `account`), including account consent data. The same
  valid payload cannot create a Blob, object URL or download after unmount,
  another owner, or a completed same-owner/same-epoch transition.
- **Two positive panel controls:** a valid settings response reaches the mounted
  consumer and focuses saved status; a valid enrollment appears in the real
  security panel. These establish that the delayed-response fixtures and
  observable consumers work when their lifetimes are current.
- **Six delayed panel cases:** settings, enrollment and cancellation responses
  cannot repopulate data after route unmount or same-owner transition. Settings
  consumer callbacks stay unused, enrollment remains absent from both the
  public flow and rendered textarea, and cancellation cannot add an old receipt
  or issue an obsolete status refresh over persisted R2.

Current-request deletion actions are withheld while status is loading or has
failed. An explicit uncertain-response retry is intentionally different: it
retains its known R1 UUID even if current status is unavailable. During that
retry, every deletion action is unavailable, including generic status retries.
Two native clicks in one event turn test the in-flight latch before React can
merely disable the button on a later render.

Only external HTTP responses are mocked in the mounted suite. Blob and object
URL observers delegate to the native implementations, and the positive export
is read from a real browser download stream. Unrecognized requests abort and
fail the fixture; there is no backend passthrough. Every mounted case checks for
uncaught page errors. Waits use observed request completion/abort, public flow
settlement and React frames, not arbitrary network sleeps.

## Harness and environment

The Vite virtual-entry harness follows the existing pattern in
`frontend/tests/diagnostic-followups.test.tsx`. It uses `configFile: false` and
`build.write: false`, then injects the in-memory bundle into an intercepted test
document. It adds no jsdom dependency, Vitest configuration, persistent fixture
bundle or listening server.

Chromium must already be installed for the project's Playwright version before
`npm test`; the tests do not install browsers or dependencies. Normal runs need
neither `LOCALAPPDATA` nor an artifact/screenshot environment variable. When
`LOCALAPPDATA` is present, the temporary base is `%LOCALAPPDATA%\Temp\opencode`.
Otherwise it is `resolve(tmpdir(), 'opencode')`: on Ubuntu, normally
`/tmp/opencode`, or beneath the caller's existing `TMPDIR` when supplied.

Each browser run creates a unique `math-ege-account-boundaries-*` directory
beneath that base. Cache/output paths and downloads point into that run, and
Chromium receives it as `TMP`, `TEMP` and `TMPDIR`. The bundle remains in memory.
The intercepted `http://account-boundaries.test/` origin does not require DNS
resolution or a listening server. No ports, including 8000, 5173, 8037 or 5193, were bound or
other processes stopped. The existing `math-ege-account-task16-*` worker scripts
were read only and not rerun. No live or existing database, mail service or
deletion executor was used; browser storage belongs to fresh isolated
mocked-origin contexts.

Portable focused command, using the existing `test` script and installed tools:

```sh
# Working directory: frontend; Chromium already installed
npm test -- tests/account-boundaries.test.tsx tests/account-transitions.test.ts
```

## Observed verification: 2026-11-05

Commands ran on Windows from `frontend` using the already installed tooling.
Ubuntu 24.04 execution itself has not been observed by this worker; the
coordinator owns the integrated CI run with Chromium installed before `npm test`.

| Check | Exit | Observed result |
| --- | --- | --- |
| Focused two-file suite below | 0 | **33 passed:** 20 mounted, 13 real-manager tests. |
| Nearby five-file account/identity suite below | 0 | **164 passed**, five files. |
| Scoped ESLint below | 0 | No errors or warnings. |
| Scoped strict TypeScript below | 0 | No diagnostics. |
| Viora `check.mjs` with existing style context below | 0 | Four files, **0 errors, 0 warnings**. |
| Viora `wig.mjs src/pages/account.tsx` | 0 | One file, pass. |

The latest focused rerun omitted `LOCALAPPDATA` and `ACCOUNT_BOUNDARY_SHOTS`
from its child-process environment and returned **exit 0, 33 passed**. Scoped
ESLint and strict TypeScript were rerun alongside it and both returned exit 0.
This exercises the temporary-directory fallback on Windows, not Linux execution.
The nearby 164-test gate and visual-check rows retain the earlier observed
evidence; they were not rerun for this portability handoff.

```powershell
.\node_modules\.bin\vitest.cmd run tests/account-boundaries.test.tsx tests/account-transitions.test.ts

.\node_modules\.bin\vitest.cmd run tests/account-boundaries.test.tsx tests/account-transitions.test.ts tests/account.test.ts tests/account-data.test.tsx tests/identity.test.ts

.\node_modules\.bin\eslint.cmd src/pages/account.tsx tests/account-boundaries.test.tsx tests/account-transitions.test.ts --max-warnings 0

.\node_modules\.bin\tsc.cmd --ignoreConfig --noEmit --strict --skipLibCheck --target ES2022 --lib ES2022,DOM,DOM.Iterable --module ESNext --moduleResolution Bundler --jsx react-jsx --allowImportingTsExtensions --verbatimModuleSyntax --noUnusedLocals --noUnusedParameters --noFallthroughCasesInSwitch --types vite/client,vite-plugin-pwa/client,node src/pages/account.tsx tests/account-boundaries.test.tsx tests/account-transitions.test.ts

node "C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\check.mjs" src/pages/account.tsx src/styles/tokens.css src/styles/base.css src/styles/components.css

node "C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\wig.mjs" src/pages/account.tsx
```

The first page-only design-check invocation returned `tokens-missing`; adding
only tokens then reported missing focus styles. The final invocation supplies
the actual shared token/base/component style context, read only, and passes
without stylesheet changes. These were incomplete checker inputs, not reasons
to add a parallel style system to this lifetime fix.

Optional screenshots use `ACCOUNT_BOUNDARY_SHOTS=1` and write beneath the same
portable per-run temporary base; on Ubuntu, a caller may supply an existing
temporary base through `TMPDIR`. Neither setting is needed for normal tests.
One desktop/mobile round was generated and inspected at 1440/390 CSS pixels in
`C:\Users\user\AppData\Local\Temp\opencode\math-ege-account-boundaries-I2hgmz`:
`logout-account-1440.png` and `logout-account-390.png`. These show the isolated
real AccountPage fixture, not the shared shell or a full-page accessibility
certification. No visual design or copy change was needed for this fix.

## Coordinator boundary

The focused and nearest-account gates above are not a full-project build, full
test suite, real-backend E2E run, SMTP/cookie-binding proof, deletion execution,
accessibility audit or field-performance measurement. The coordinator subsequently
completed whole-frontend lint/unit/build (**409 tests**), shared Chromium
(**26 passed / 4 intentional identity skips**) and all four dedicated real-API
identity scenarios together (**4 passed / 0 skips**). These are separate final
local gates in [verification.md](verification.md), not sums of the scoped counts.
The fresh whole-backend gate is recorded there separately; exact-SHA Linux CI,
commit and push remain coordinator-owned. Existing backend evidence was not
changed or rerun by this worker. The
CI browser-before-`npm test` ordering is already corrected by the coordinator;
this patch makes no CI or configuration changes.
