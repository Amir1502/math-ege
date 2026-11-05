# Assessment client integration

Implements approved completion-design Task 2. Owned files are
`frontend/src/assessments/**`, `frontend/src/pages/assessment.tsx`,
`frontend/src/styles/assessment.css`, `frontend/tests/assessment.test.ts`,
`frontend/e2e/assessment.spec.ts`, and this document. Backend semantics are in
[`assessments-api.md`](assessments-api.md).

## Integrated entry points

The default export is `AssessmentPage({ id?, ownerId? })`. The coordinator has
integrated its lazy import and both hash routes in `frontend/src/app/app.tsx`:

- `#/assessment`: mode selection, preparation and the last saved assessment.
- `#/assessment/<encoded-id>`: prepared start, worksheet, pending snapshot or
  released results, according to the durable lifecycle state.

The host supplies the canonical `identity.current()` as `ownerId`; the page
also subscribes to the identity store. It imports `assessment.css` itself and
uses the shared tokens and base/component styles.

`frontend/src/app/shell.tsx` associates these routes with **Практика**, retains
five primary destinations, and treats an assessment run as an active task for
PWA update handling. The backend assessment router, service and independent
`DeadlineWorker` are mounted in `backend/app/main.py`. The browser suite uses
this integrated application.

## Identity and local ownership

`createAssessmentApi(ownerId, fetcher?)`, `AssessmentController` and
`AssessmentPreparation` capture a canonical owner when constructed. Every
assessment request sends that captured ID in `X-Learning-Owner`, with
same-origin cookie credentials and `cache: no-store`.

Guest creation is an intentional setup action: `prepareAssessment()` calls the
existing `api.guest()`, then awaits `identity.refresh()` and uses the resolved
canonical identity. The guest endpoint's returned ID is not the partition key.
Pending settings, busy state and preparation errors live in an external store
so feedback survives the identity-driven setup remount.

The `identity.beforeChange()` barrier suspends preparations and controllers,
stops retained timers and persists the old controllers before the identity
transition proceeds. Disposed controllers ignore late network responses.
Old partitions remain attached to their original owner; a new identity cannot
relabel or replay their queued requests. Assessment storage contains public
conditions, answers and pending request metadata, never cookie or guest tokens.

### Storage layout

The separate IndexedDB database **`math-ege-assessments-v1`**, version 1, has:

| Store | Key | Value |
| --- | --- | --- |
| `records` | `JSON.stringify([ownerId, assessmentId, deviceId])` | Full assessment record, drafts, clock anchor, conflict and pending lifecycle requests. |
| `creates` | `JSON.stringify([ownerId, deviceId])` | Exact pending preparation body and idempotency UUID, or null. |
| `meta` | `JSON.stringify([ownerId, 'last'])` | Last prepared assessment ID for the resume link. |

The synchronous localStorage journal uses
`math-ege:assessment:v1:<record-key>` and
`math-ege:assessment:v1:create:<create-key>`. A monotonically increasing record
`sequence` selects the newest journal/database copy and prevents queued older
database saves from overwriting newer data.

The per-tab UUID is stored in sessionStorage as
`math-ege:assessment-device-v1`. A held Web Lock detects an already-open tab
whose sessionStorage was copied by `window.open`; the duplicate gets a new
device ID. BroadcastChannel supplies the fallback. Server writer generations
remain authoritative for write permission.

## Lifecycle and durability

Both modes contain exactly 13 tasks, with initially empty answer strings.
Diagnostics have no countdown. Exams default to 65 minutes, accept only integer
limits from 15 through 180 before preparation, and identify this as a trainer
setting rather than a FIPI regulation.

| Phase | Client behavior |
| --- | --- |
| `prepared` | All 13 public conditions are durably saved. A separate explicit activation starts the assessment. |
| `active` | Raw drafts and task navigation are available; only the confirmed writer can edit. |
| `awaiting_snapshot` | Answers are frozen and read-only. A final snapshot can be submitted by its writer; results and explanations remain closed. |
| `completed` | Server-released, immutable result ledgers and explanations are available. |

Preparation stores the exact request body and UUID before HTTP, then journals
and saves the complete returned condition set before offering activation.
Activation and confirmed takeover also persist their exact bodies and UUIDs
before sending. A lost response is retried with its original request.

Each edit updates the full-record synchronous journal immediately. IndexedDB
persistence is scheduled at 750 ms. Online draft flushing is throttled at
1,200 ms from the first dirty change, so continuous typing cannot postpone it;
task navigation and leaving the route also request a flush. Storage failures
are visible and make editing read-only until persistence succeeds.

Draft PUTs are serialized with `expected_revision` and `writer_generation`.
Acknowledgements advance only the local version they actually sent. Newer
input survives older acknowledgements and concurrent GETs. A GET that observes
the exact in-flight draft can acknowledge that version without inventing a CAS
conflict. Responses with older lifecycle status, generation or revision cannot
regress established state.

Finishing clones all 13 raw answers, active times, the connection-loss flag and
writer generation into a frozen body with a UUID before HTTP. Editing stops
immediately, including offline. After persistence and any in-flight draft,
submission rechecks connectivity, conflicts and ownership. Reload and
reconnection resume that exact saved snapshot, including when the document
reloads already online.

### Time

`ServerClock` anchors to `server_now`, advances using `performance.now()` and
nonnegative wall-clock elapsed time, and persists a nondecreasing floor.
Restore and subsequent server observations never move that floor backwards.
The runtime retains controllers and their 500 ms deadline checks across route
navigation. Visibility changes, page restoration and user actions also check
the deadline; hiding the tab does not pause the exam. Per-task
`active_seconds` is counted separately while the worksheet is visible.

At expiry the client freezes the latest input. Backend `awaiting_snapshot`
also triggers freezing even if `can_write` is true: that permission allows
final submission, not another draft. The server decides the canonical result
and grades both result ledgers; there is no client-side/offline scoring.

### Explicit recovery

| Condition | Recovery |
| --- | --- |
| `assessment_draft_conflict` | Keep local input, become read-only, and require a choice between the local and server drafts. A frozen local final can only be submitted as originally saved. |
| `assessment_writer_conflict` / another writer | Keep local input and require the native takeover confirmation. After takeover, divergent local input still needs an explicit draft choice. |
| Uncertain takeover response | Retry its saved body/UUID. If the observed generation has become obsolete, discard the pending claim and require fresh confirmation. |
| `assessment_not_active`, `assessment_closed`, `assessment_snapshot_conflict` | GET current state and reconcile its lifecycle or released result. These are not automatically classified as writer conflicts. |
| 401, 403, 404 or `identity_changed` | Suspend writes while preserving the partition. A successful refresh under the same captured owner can restore access. |
| Network failure | Preserve local data and the original pending requests. Retry explicitly or once on an actual reconnect. |

## HTTP and presentation contracts

All assessment paths begin with `/api/v1/assessments`. Mutations send
`X-Requested-With: math-ege`; POSTs send a persisted `Idempotency-Key`.
GET sends `X-Assessment-Device`. Draft PUT uses revision CAS rather than an
idempotency key.

`api.ts` validates the complete 13-task public view and rejects result payloads
before `completed`. Backend result fields `raw`, `normalized` and `expected`
map to `raw_answer`, `normalized_answer` and `expected_answer`. Although the
backend returns a complete view for draft PUT, the adapter exposes only
`draft_revision` to the controller, preventing an acknowledgement from
replacing newer input.

The worksheet reuses `TaskContent`; released explanations reuse `RichText`.
Raw answer text, including intermediate strings, remains intact. Format errors,
skips and wrong numeric answers have distinct labels after release. The UI
reports `independent` and `assisted` without interpreting every non-independent
row as a repeated task: format errors and local snapshots also lack independent
credit. Server and local educational results are separate ledgers, with an
explicit connection-loss notice and no conversion of 0–13 to an exam score.

Task navigation focuses the new task heading. Finish and takeover dialogs use
native modal behavior, focus cancellation first, support Escape and return
focus to the trigger. Assessment controls use at least 44 CSS-pixel targets.

## Verification recorded on 2026-11-05

From `frontend`:

```powershell
npm run test -- tests/assessment.test.ts
node node_modules/eslint/bin/eslint.js src/assessments src/pages/assessment.tsx tests/assessment.test.ts e2e/assessment.spec.ts --max-warnings 0
npm run test:e2e -- e2e/assessment.spec.ts --max-failures=1 --output C:\Users\user\AppData\Local\Temp\opencode\assessment-e2e-confirmed
```

- **26 Vitest tests passed**: HTTP adaptation, durable preparation, journal
  recovery, stale acknowledgements/GETs, CAS resolution, writer transfer,
  identity suspension, deadline recovery and lifecycle/persistence races.
- **Scoped ESLint passed**, exit 0.
- **6 Chromium browser tests passed in 48.3 s** after the final presentation
  changes. The suite started the real backend with a fresh temporary SQLite
  database, applied migrations through `0006_practice_options`, and completed
  `tsc -b && vite build` before starting production preview.

Browser scenarios cover diagnostic release and format errors; all 13 conditions
and drafts through offline navigation/reload; immutable offline completion and
separate result ledgers after reconnection; duplicate-tab device isolation and
confirmed takeover; client deadline freezing across route exit and reload;
accepted preparation with a lost response followed by exact replay; and
responsive/accessibility behavior. The last case checks worksheet overflow and
44 px targets at 320, 360, 390, 768, 1024 and 1440 CSS px, five navigation links,
and the worksheet at 320 px with root text set to 200%. The tested worksheet
and released-result axe scans reported no violations.

The deadline browser case advances **the client clock** by `15:01`; it verifies
client freezing, not 15 real minutes of backend worker execution. The
lost-preparation case forwards the request to the real server before aborting
its response and disables service workers only for that test. Browser evidence
is from Chromium with demo content enabled.

### Design checks and visual review

Individual design checks were run from the repository root:

```powershell
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\check.mjs' frontend/src/assessments frontend/src/pages/assessment.tsx frontend/src/styles/assessment.css frontend/src/styles/tokens.css frontend/src/styles/base.css
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\wig.mjs' frontend/src/assessments frontend/src/pages/assessment.tsx frontend/src/styles/assessment.css
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\ru.mjs' frontend/src/assessments frontend/src/pages/assessment.tsx
```

`check.mjs`: **0 errors, 0 warnings across 19 files**. `wig.mjs`: **17 files,
pass**. `ru.mjs`: **0 errors, 1 decided warning** for the official acronym
`ФИПИ`. The shared token contrast baseline records **13 measured pairs, 0
failures**, using `contrast.mjs src/styles/tokens.css` from `frontend`; see
[`verification.md`](verification.md#визуальная-проверка).

The three warning decisions are documented next to their affected lines:

- `text-wrap-missing`: assessment headings inherit `text-wrap: balance` from
  `frontend/src/styles/base.css`.
- `touch-action-missing`: the same base stylesheet supplies
  `touch-action: manipulation` to interactive elements.
- `caps-shouting`: retain the institute's official uppercase acronym. The
  Russian checker still reports it despite the explanatory comment.

Opened and visually reviewed setup and worksheet captures at 1440 and 390 px,
released results, and the offline-deadline state. They follow the light
worksheet/blue direction in `DESIGN.md`, with the 13-cell task rail, empty
answer field, readable Cyrillic and visibly distinct pending/result states.
The review removed the unsupported repeated-task claim from result copy.
Screenshot capture now scrolls to the document top first, avoiding misplaced
fixed-sidebar and offscreen skip-link artifacts. Confirming images were opened
after the final browser run.

Artifacts are under
`C:\Users\user\AppData\Local\Temp\opencode\assessment-e2e-confirmed`, in
test-specific subdirectories: `assessment-setup-{1440,390}.png`,
`assessment-worksheet-{1440,390}.png`, `assessment-results.png` and
`assessment-offline-deadline.png`. These are full-page captures; the fixed
mobile navigation appears once at the viewport bottom within the longer image.

**Historical navigation observation:** the original 390 px capture showed the
last letter of `Повторение` wrapping. Shared navigation now uses nowrap and a
compact visible caption below 380 px while retaining the full accessible name.
The [later browser record](browser-integration.md#main-navigation-mobile-captions-and-brand)
measured one line at 320/360/390 on the checked pages; it is not a physical-device pass.
There are no outstanding assessment route/API integration blockers.

## FR-04 targeted diagnostic follow-up handoff (2026-11-05)

This approved Task 2/3 addition is limited to these files:

- Updated `frontend/src/assessments/results.tsx`.
- Added `frontend/src/assessments/followups.ts`.
- Added `frontend/tests/diagnostic-followups.test.tsx`.
- Added `frontend/e2e/diagnostic-followup.spec.ts`.
- Appended this section to `docs/assessment-client.md`; the earlier handoff is
  unchanged.

No shared practice, start-panel, API-type, router, application, storage or style
files were edited for this addition. No dependencies, commits, pushes or
deletions were made. No listeners were started on coordinator ports
`8000/5173` or identity ports `8037/5193`.

### Follow-up contract

`diagnosticFollowups(view, profile)` derives links only from a released,
`completed` diagnostic's canonical `server_result.rows`. Each link requests
`/practice?slots=<current-number>&skills=<stable-skill-ids>&length=5`.
Correct answers also receive an offer: one diagnostic answer remains
preliminary, not proof of mastery. Wrong, skipped, format-error, assisted and
non-independent rows retain their existing outcome labels without a new
mastery claim.

An explicit task `slot_id` must match exactly one current profile position.
Legacy conditions without that ID use only an unambiguous current stable-skill
match, never the historical numeric position. Retired and outside-position
skills are filtered; skill IDs are deduplicated and URL-encoded. Empty or
comma-containing skill IDs, unavailable positions, unsupported numbers,
ambiguous mappings and unknown result tasks do not produce a link. The frozen
assessment is not mutated. Links contain no original task ID or repeat control;
the existing practice parser receives `repeat_task_id: null`.

The action lives inside the existing result `<details>` alongside its solution,
not in another card or a prominent list of 13 buttons. The existing profile
resource supplies loading feedback and retryable errors. Only a loaded,
uncached, error-free profile snapshot supplies follow-ups; unavailable mappings
have an inline explanation instead of silently broadening the filters. A failed
profile refresh removes the old links, and a successful retry applies the new
stable-ID mapping. Exam and local-only results do not load follow-up filters;
local educational ledgers never receive targeted links. A defensive result
guard also keeps answers, solutions and follow-ups closed before `completed`.

### Scoped verification

Red-before-fix evidence was observed for the missing helper, lifecycle gates,
legacy renumbering, unsafe filter values, absent mounted links, profile
loading/error recovery, unavailable mappings and unreleased result ledgers.
The final type-check also exposed `TS2339` in the test harness's Vite build
output handling; an explicit watcher guard narrowed that return type before
the green run. TypeScript 6 requires `--ignoreConfig` for this explicit-file
check; the first invocation without it stopped at `TS5112` before checking
source files.

Final commands, run from `frontend`:

```powershell
$env:ASSESSMENT_FOLLOWUP_SHOTS = 'C:\Users\user\AppData\Local\Temp\opencode\diagnostic-followup-fr04-8a603c'
npm run test -- tests/diagnostic-followups.test.tsx tests/assessment.test.ts tests/practice-options.test.ts --reporter=json --outputFile=C:\Users\user\AppData\Local\Temp\opencode\diagnostic-followup-fr04-report.json
node node_modules/eslint/bin/eslint.js src/assessments/results.tsx src/assessments/followups.ts tests/diagnostic-followups.test.tsx e2e/diagnostic-followup.spec.ts --max-warnings 0
node node_modules/typescript/bin/tsc --ignoreConfig --noEmit --strict --skipLibCheck --target ES2023 --module ESNext --moduleResolution Bundler --jsx react-jsx --types vite/client,node --allowImportingTsExtensions --resolveJsonModule --verbatimModuleSyntax --noUnusedLocals --noUnusedParameters --noFallthroughCasesInSwitch src/assessments/results.tsx src/assessments/followups.ts tests/diagnostic-followups.test.tsx e2e/diagnostic-followup.spec.ts
```

- **62/62 tests passed across 3 files**, with **0 failed and 0 pending**:
  new follow-ups **33**, nearest assessment gate **26**, practice-options **3**.
- **Scoped ESLint passed**, exit 0, with `--max-warnings 0`.
- **Scoped strict TypeScript passed**, exit 0; this is not a full-app build.
- The new suite covers pure-helper rules and genuine Chromium mounts of
  `AssessmentResults`, actual hash-link navigation, canonical/local separation,
  release guards, profile failure/retry and changed mappings, keyboard focus,
  44 CSS-pixel targets, widths 320/360/390/768/1024/1440 and 200% root text.
  Vite builds the mounted component in memory; intercepted
  `http://assessment-unit.test/` requests require no listening server or extra
  DOM test dependency.

Individual design commands, run from the repository root except the last:

```powershell
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\check.mjs' frontend/src/assessments/results.tsx frontend/src/assessments/followups.ts frontend/src/styles/tokens.css frontend/src/styles/base.css frontend/src/styles/components.css frontend/src/styles/assessment.css
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\wig.mjs' frontend/src/assessments/results.tsx frontend/src/assessments/followups.ts
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\ru.mjs' frontend/src/assessments/results.tsx frontend/src/assessments/followups.ts
# From frontend:
node 'C:\Users\user\.config\opencode\skills\viora-design-skills\scripts\contrast.mjs' src/styles/tokens.css
```

`check.mjs`: **0 errors, 0 warnings across 6 files**. `wig.mjs`: **2 files,
pass**. `ru.mjs`: **1 Russian-text file, pass**. Contrast: **13 measured pairs,
0 failures**. Shared styles were verification inputs only, not edited files.
The fresh 1440 px and 390 px captures were opened and visually reviewed:
`C:\Users\user\AppData\Local\Temp\opencode\diagnostic-followup-fr04-8a603c\diagnostic-followup-{1440,390}.png`.
They preserve the light worksheet/blue direction and show the action in one
expanded result row. These are isolated mounted-component screenshots, not
evidence for the integrated application shell or its five navigation items.
The test JSON report is at
`C:\Users\user\AppData\Local\Temp\opencode\diagnostic-followup-fr04-report.json`.

### Worker handoff and subsequent coordinator integration

The new E2E file contains **1 authored scenario, not run by this worker**.
It completes a real diagnostic, follows a canonical result action, checks the
five primary navigation links, verifies the practice filters and outgoing
five-task request without a repeat ID, and requires five returned tasks in the
selected position/skills with IDs disjoint from the original diagnostic.

Coordinator-only command, from `frontend`, after reserving its normal browser
ports:

```powershell
npm run test:e2e -- e2e/diagnostic-followup.spec.ts --max-failures=1 --output C:\Users\user\AppData\Local\Temp\opencode\diagnostic-followup-e2e-confirmed
```

The existing browser configuration starts the real backend on `8000` and the
built client on `5173` with fresh temporary storage and demo content. This
worker did not run it. No new route wiring is needed for the existing practice
URL/parser. Issuance freshness and honest shortages remain the existing server's
responsibility; this change requests five new tasks rather than replaying or
grading them locally.

The coordinator subsequently ran the real-API scenario together with the
brand-label regression: **2 passed in 21.1 s, exit 0**. The diagnostic action
issued five new correctly filtered tasks with IDs disjoint from the diagnostic
and retained exactly five primary navigation links. The command was
`npm run test:e2e -- --grep 'имя главной ссылки|каноническая диагностика ведёт' --max-failures=1`
with fresh temporary storage. Evidence is `followup-brand-green.log` and
`followup-brand-green.json` under the private temporary
`completion-delivery-cd5fa110dec1446492fe710ce731c53c` directory. This is a focused
coordinator proof, not a whole frontend/E2E or exact-commit CI result. The
worker's overlapping 62-test gate is not added to it; independent control tasks,
methodological review and recommendation pilot remain separate acceptance gates.
