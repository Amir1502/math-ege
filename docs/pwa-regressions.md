# Task6: bounded PWA regression handoff

**Evidence date:** 5 November 2026.

**Outcome:** the untouched original PWA file changed from **1 passed / 2 failed**
to **3 passed** on a fresh isolated runtime. The final focused/nearest unit gate
passed **61 tests in 7 files**, including all **9 new regressions**. This is not a
whole-frontend, shared E2E, authenticated-identity or physical-device acceptance
claim. The subsequent coordinator-wide local gates are recorded separately below.

## Root causes and narrow fixes

### PWA notice lost during canonical identity bootstrap

The original mobile scenario failed at `frontend/e2e/pwa.spec.ts:28`: the
installed-shell notice never appeared. Native browser instrumentation observed
registration, identity-shell removal, a second registration, successful worker
installation/activation, and **zero notices**. Per-mount `useRegisterSW` state
was lost when the canonical identity bootstrap replaced the shell.

`frontend/src/components/pwa-prompt.tsx` now registers once per document and
retains worker notification state in a small external store. A remounted prompt
subscribes to the existing state. Dismissal also survives remounting. Identity
bootstrap, shell keys, installation handling, layout and the existing active
route/durable-session update guards are unchanged.

### Opened lesson unavailable after offline reload

The original offline scenario failed at `frontend/e2e/pwa.spec.ts:55`: the lesson
heading became a numbered-topic fallback. Boundary instrumentation separately
confirmed an opened lesson stored under
`ege-math-2027-draft:2026-11-05.1.course-1:3`, followed by an offline heading
`Тема № 3` and **zero articles**. Reload had no current public profile and looked
under `unverified` instead of the exact saved catalog revision.

- `frontend/src/storage/database.ts` atomically saves the opened lesson and its
  exact public catalog-revision pointer in the existing `revision_lessons` and
  `scoped_meta` stores. The pointer key is
  `['public', 'lesson_catalog_revision']`; unverified writes do not replace it.
- `frontend/src/app/resources.ts` first attempts the current profile. A confirmed
  current profile/revision takes precedence. Only when there is no current
  profile may a lesson read consult the saved revision pointer, and it still
  requires an exact lesson key in that revision. Late responses cannot save
  under a captured revision that no longer matches the loaded profile.

The old public profile is **not** published as current. No schema migration,
history deletion, private API caching or identity/session-storage change is
introduced.

## Task-owned files

- `frontend/src/components/pwa-prompt.tsx`
- `frontend/src/app/resources.ts`
- `frontend/src/storage/database.ts`
- `frontend/tests/pwa-prompt.test.tsx` (new)
- `frontend/tests/lesson-resources.test.ts` (new)
- `docs/pwa-regressions.md` (new)

The new tests use self-contained typed fixtures; the shared
`frontend/tests/fixtures.ts` was not changed. Backend, Android, shared docs,
dependencies, original E2E assertions and runtime configuration were not edited
by this task. Existing work in the shared checkout remains uncommitted.

## Regression proof

| Evidence stage | Actual result |
| --- | --- |
| `red-original-2` | Untouched original PWA file: **1 passed / 2 failed**; source hashes unchanged during the run. |
| `red-boundaries` | Native registration/shell lifecycle and exact IndexedDB/offline mismatch observed. |
| `red-pwa-unit-ready` | Both mounted notification regressions failed at the post-remount notice assertions. |
| `green-pwa-unit` | Both mounted notification regressions passed after the document-lifetime fix. |
| `red-lesson-unit` | Numbered-topic and stable-ID offline restoration both failed with missing cached data. |
| `green-lesson-unit` | Both offline restoration regressions passed after exact revision fallback. |
| `red-late-revision-guard` | Removing only this task's save guard caused **1 failure**; the other 6 cases were excluded by a name filter, not skipped in source. The guard was restored. |
| `final-nearest-units` | **61 passed / 0 failed**, 7 files; includes all 7 lesson and both mounted PWA regressions. |
| `strict-tests-final` | Strict typing of both new test files and their imported application code: exit 0. |
| `strict-app-config` | Forced app/config TypeScript build: exit 0. |
| `frontend-lint-final` | Full frontend lint with zero allowed warnings: exit 0. |
| `production-build` | Production Vite build and generated service worker: exit 0. |
| `green-original` | Untouched original PWA file: **3 passed / 0 failed**, fresh database and runtime. |
| `green-original-final` | Repeated after fixture isolation: **3 passed / 0 failed**, another fresh database/runtime; source hashes unchanged during the run. |

The mounted PWA tests bundle the real React/App, canonical identity, IndexedDB
storage and installed PWA registration clients. Only the external Workbox event
boundary is controlled; these tests are not an authenticated backend-identity
verification. The original PWA browser run uses the real worker and backend.

Earlier stages `red-original`, `red-pwa-unit`, and `red-pwa-unit-diagnostic`
were proof-harness setup failures, not valid regression REDs. The first external
test typing attempt (`strict-tests`) could not resolve Vite declarations. The
corrected external config (`strict-tests-ready`) then exposed an existing shared
fixture typing error; keeping small fixtures inside the new tests allowed the
final strict gate without altering the shared fixture or suppressing errors.

## Commands and evidence location

Evidence is retained outside the repository:

```text
C:\Users\user\AppData\Local\Temp\opencode\task6-pwa-ccbe64ef8d1f4067a84edc529f88c2b5
```

Each executed gate records its exact executable/arguments in `command.json`,
UTF-8 output in `*.log`, before/after frontend/backend SHA256 maps, and
`result.json`. Browser stages additionally retain JSON/HTML reports and failed
RED traces/screenshots. `red-boundaries/boundaries.json` holds native lifecycle
and cache observations.

The final gate commands below were run from `D:\math_ege\frontend`. The external
runner supplies isolated temporary artifact directories; it does not install
dependencies or modify source files.

```powershell
$evidence = 'C:\Users\user\AppData\Local\Temp\opencode\task6-pwa-ccbe64ef8d1f4067a84edc529f88c2b5'
node "$evidence\run-gate.mjs" final-nearest-units vitest run tests/lesson-resources.test.ts tests/pwa-prompt.test.tsx tests/storage.test.ts tests/identity.test.ts tests/api.test.ts tests/session.test.ts tests/diagnostic-followups.test.tsx --reporter=verbose
node "$evidence\run-gate.mjs" strict-tests-final tsc --project "$evidence\strict-tests-ready.tsconfig.json"
node "$evidence\run-gate.mjs" strict-app-config tsc --build --force
node "$evidence\run-gate.mjs" frontend-lint-final eslint src tests e2e scripts '*.ts' '*.js' --max-warnings 0
node "$evidence\run-gate.mjs" production-build vite build
node "$evidence\run-proof.mjs" green-original-final
```

Stages refuse to overwrite existing evidence; use a new stage name for a rerun.
The browser helper imports the unchanged `frontend/playwright.config.ts`, checks
that ports **8000/5173** are free on IPv4/IPv6, disables runtime reuse and starts a
fresh SQLite database. It changes only artifact locations, explicit server cwd
and the isolated database URL. It does not increase timeouts or retries.

`frontend/e2e/pwa.spec.ts` remains byte-identical to the pre-task copy; SHA256:

```text
BDEE218963F254A77FF29B029C60137A2BDDBCCAAA48CAFEEA730A1169011264
```

No commit, push, dependency installation or final whole shared suite was run by
this worker.

## Subsequent coordinator-wide local verification

On the same stable application sources, the coordinator ran whole frontend
lint/unit/build (**409 passed, 20 files, 17.08 s; all three exits 0**) and every
shared Chromium scenario with both identity opt-in variables unset
(**26 passed, 4 intentional identity skips; 108.515 s; exit 0**). All three
original PWA scenarios passed, with the byte-identical spec hash above.
All four dedicated identity scenarios then passed together in one different,
fresh isolated runtime (**4 passed, 0 skips; 73.805 s; exit 0**).

The reports, JUnit, unchanged-source inventory and read-only teardown consumption
are recorded in [verification.md](verification.md). The historical shared RED
(24 passed / 4 identity skips / 2 original PWA failures), this worker's regression
REDs and the focused 61-test gate remain separate evidence. These local results
do not establish two-release PWA resource switching, real-device acceptance or
exact-commit Linux/PostgreSQL CI.
