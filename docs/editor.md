# Editorial workflow and integration

Implements Task 4 of the approved
[completion plan](superpowers/plans/2026-11-05-completion.md), covering the
editorial parts of FR-01, FR-14, FR-15 and NFR-03. The backend and the lazy-loaded
`#/editor` frontend are mounted in the shared application. The production-route
smoke and the verification boundaries are recorded below.

Owned implementation: `backend/app/editor/**`, migration `0005_editor`,
`backend/tests/test_editor.py`, `frontend/src/editor/**`,
`frontend/src/pages/editor.tsx`, `frontend/src/styles/editor.css`,
`frontend/tests/editor.test.ts` and this document.

## Application integration

### Backend

`backend/app/main.py` already constructs and mounts:

```python
from app.editor.api import router as editor_router
from app.editor.service import EditorService

application.state.editor = EditorService(application.state.service)
application.include_router(editor_router)
```

`LearningService.content(db=None)` already reads
`app.editor.repository.combined_content`, using the caller's transaction when
supplied. This makes publication and withdrawal visible to new issuance.
Issuance must retain its existing `allow_demo_content` eligibility filter and
freeze the selected task/profile snapshots in its own transaction.

The repository adapters are:

```python
combined_content(db, settings, candidates=None) -> ContentBundle
published_content(database, settings) -> ContentBundle
exclusions(db) -> dict[tuple[str, str], str]
notices(db, guest_ids) -> list[dict]
```

`published_content` opens its own read transaction and applies
`available_tasks(allow_demo_content=settings.allow_demo_content)`.
`combined_content` supplies the complete effective bundle for validation and
transactional selection. It does not itself filter demonstration tasks.
The shared learning evidence layer already imports `exclusions` and `notices`.
Runtime generation has its own caller contract in
[`runtime-issuance.md`](runtime-issuance.md); editorial tests do not establish
that separate helper's service integration.

Migration `0005_editor` follows `0004_learning` and adds seven tables:
`editor_revisions`, `editor_catalog`, `editor_publications`, `editor_audit`,
`editor_exclusions`, `editor_template_checks` and `editor_template_reviews`.
It seeds the catalogue singleton. Its downgrade raises before changing data.
Model initialization remains explicit to avoid a `LearningService` import
cycle; Alembic/test metadata must import `app.editor.models`.

### Frontend host

`EditorPage` is a default export with no required props. It imports
`editor.css` itself and uses the existing shared components, tokens and
worksheet-blue styling. The coordinator-owned `frontend/src/app/app.tsx`
already lazy-loads it inside the existing `Shell` at `#/editor`:

```tsx
const EditorPage = lazy(() => import('../pages/editor'));

// In the existing route switch:
else if (route.path === '/editor') page = <EditorPage />;
```

`frontend/src/accounts/staff-security.tsx` supplies the secondary
**Открыть редактор** entry after recent staff MFA. All five primary navigation
destinations remain present. The server independently enforces access. The page
does not create a guest, use student caches, or depend on the shared student
API/type adapter. Its entry request is `/api/v1/editor/meta`.

The host must account for the in-memory lifetime described below when routing,
changing identity or applying a PWA update. The production-route smoke verifies
entry and local keyboard creation; it does not establish those host lifecycle
integrations with unsaved input or an uncertain write.

## Access and transport

Every editor read, preview and mutation requires an authenticated, verified
`methodist` or `admin` account with enrolled MFA verified within the accounts
service's current 900-second window. Publishing and withdrawing require
`admin`. Account configuration and staff provisioning belong to
[`accounts.md`](accounts.md); unavailable accounts/MFA fail closed.

Authority comes from `accounts.require_staff` and the authenticated account,
never from uploaded authorship or a role in JSON. Writes repeat
`authorize_staff(..., write=True, clock=learning.clock)` inside the canonical
owner transaction, including after acquiring the editorial catalogue lock.
Thus an HTTP-level check alone cannot authorize a mutation after a lock wait.

All paths start with `/api/v1/editor`. Cookie-authenticated writes require the
shared allowed `Origin`, `X-Requested-With: math-ege` and
`Content-Type: application/json`. Every persistent POST/PUT also requires a
UUID `Idempotency-Key`. `POST /preview` is read-only and does not use a key.

The optional `X-Editor-Actor` header binds a request to the captured account
ID. A mismatch returns `403 editor_identity_changed`, including before replay.
It grants no permission. The frontend captures this ID from `/meta` and sends
it on subsequent requests. A changed account cannot replay another editor's
pending request by inheriting its cookie.

The independent fetch adapter uses `credentials: 'same-origin'`,
`cache: 'no-store'` and `redirect: 'error'`. Shared middleware sets
`Cache-Control: no-store` and `Vary: Cookie` for API responses. Editor content,
sample answers and review evidence are private; these DTOs must not become a
student-facing content endpoint.

## Identity, revisions and lifecycle

| Field | Meaning |
| --- | --- |
| `content_id` / `payload.id` | Stable material ID, preserved across editorial versions. |
| `id` | UUID of one editorial revision record. |
| `version` | Increasing version number for one `(kind, content_id)`. A fork allocates the next version. |
| `revision` | Compare-and-swap counter for that record. Successful edits, workflow/evidence events and publication advance it. |
| `content_revision` | Snapshot revision, `ed-<revision UUID>`, distinct from the CAS counter. |

Kinds are `task`, `lesson`, `profile`, `template`. States are
`draft`, `review`, `ready`, `published`, `archived`.

- A new material or fork is the authenticated author's draft. Only its author
  edits it; changing the stable ID is rejected.
- The author submits a draft. Another authenticated staff account approves it.
  The reviewer ID and review timestamp are recorded by the server.
- A review can return to draft. Once ready, only its author or recorded reviewer
  can return it. Review attribution and approval flags are cleared.
- An admin publishes a ready revision or a ready package. Replacing a published
  version archives its predecessor. Publishing an older version over a newer
  publication is rejected.
- Published payloads are immutable. Corrections use a fork and a new independent
  review. A fork does not inherit approval or template attestations.
- Authors can archive unpublished work. Admins can archive published lessons or
  templates only when the effective bundle remains valid. An active profile
  needs a published replacement; published tasks use withdrawal with a reason.

Responses include actor-specific `capabilities`; these drive the UI but do not
replace server checks. Audit entries record the account ID/role, action,
previous/new status, note and timestamp. Published payloads and historical
learning results are not rewritten by an audit or status transition.

## HTTP and DTO reference

The exact request/response models live in `backend/app/editor/schemas.py`.
All models reject unknown fields and coercive types through the shared schema
configuration. Notes are 5–2000 characters and must contain at least five
non-padding characters.

| Method and relative path | Request/query | Response |
| --- | --- | --- |
| `GET /meta` | None | `EditorMeta`: actor, current profile, kinds/statuses, limits, registered runtime families. |
| `GET /revisions` | Optional `kind`, `status`, `q`, exact `content_id`; `limit` 1–100, default 30; `offset` 0–100000. | `RevisionList` with `items`, `total`, `limit`, `offset`. |
| `POST /revisions` | `CreateRevision` | `RevisionView`. |
| `GET /revisions/{id}` | Revision UUID | `RevisionView`, including editable payload, audit and optional evidence. |
| `PUT /revisions/{id}` | `expected_revision`, `payload`, `change_note` | `RevisionView`. |
| `POST /revisions/{id}/fork` | `ChangeRequest` | New draft `RevisionView`. |
| `POST /revisions/{id}/submit` | `ReviewRequest` | `RevisionView`. |
| `POST /revisions/{id}/return_to_draft` | `ReviewRequest` | `RevisionView`. |
| `POST /revisions/{id}/approve` | `ReviewRequest` | `RevisionView`. |
| `POST /revisions/{id}/publish` | `ChangeRequest`, admin | `RevisionView`. |
| `POST /publish` | `PublishBatch`, admin | `BatchResult: {items: RevisionView[]}`. |
| `POST /revisions/{id}/archive` | `ChangeRequest` | `RevisionView`. |
| `POST /tasks/{content_id}/withdraw` | `task_revision`, `reason`, admin | `Withdrawal`. |
| `GET /base` | `kind` defaults to `task`; `q`, `offset`. | `BaseList`, up to 30 items and `total`. |
| `POST /base/{kind}/{content_id}` | `change_note` | Draft `RevisionView`, preserving stable ID and base snapshot. |
| `POST /import` | `ImportBatch`, 1–10 items | `BatchResult`. |
| `GET /export` | Repeated `ids=<revision UUID>`, 1–10 | `ImportBatch`, with server-managed fields omitted. |
| `POST /preview` | `CreateRevision` | `Preview`: kind, public task when applicable, editable payload, validation message. |
| `POST /revisions/{id}/checks` | `ChangeRequest`, template in draft/review | `CheckResult`: ID, passed, seed count, checks, failure. |
| `GET /revisions/{id}/sample` | Integer `seed`, 0–4294967295 | `TemplateSample`: seed, output hash, full private task. |
| `POST /revisions/{id}/samples` | `SampleReview` | Updated `RevisionView`. |

Common request shapes:

```text
CreateRevision = { kind, payload, change_note }
ChangeRequest  = { expected_revision, note }
ReviewRequest  = { expected_revision, note,
                   reviewed_formula?: boolean, reviewed_constraints?: boolean }
SampleReview   = { expected_revision, note, seed, output_hash, approved }
ImportBatch    = { version: "1", items: CreateRevision[] }
PublishBatch   = { items: [{ id, expected_revision }], note }
```

`expected_revision` is a positive integer. Publication accepts 1–1000 references
and only one version of each material. Withdrawal uses the task's
`content_revision` string in `task_revision`, not its CAS integer or bare
editorial UUID. `Withdrawal` includes `historical_scores_unchanged: true`.

Search is literal, case-insensitive title/ID matching; SQL wildcard characters
are escaped. Draft creation/import does structural validation. Complete
cross-material reference validation occurs when publishing the package.

Errors use `{"error":{"code":"...","message":"...","field":null}}`.
Important recovery cases:

| Error | Recovery |
| --- | --- |
| `revision_conflict` | Preserve/download local input, load the current record and reconcile explicitly. |
| `idempotency_conflict` | A key was reused for another body or operation; do not silently generate a new key for an uncertain write. |
| `editor_identity_changed`, authentication/MFA errors | Keep the original request, restore the same account/MFA or download work before reopening under another account. |
| `invalid_import` | Correct the numbered rows; the batch created no revisions. |
| `invalid_publication`, `template_mapping` | Correct the whole candidate package and its stable bindings. |
| `template_evidence_required`, `human_review_required`, `formula_review_required` | Complete the named evidence/review step. |
| `template_rejected`, `template_evidence_stale`, `sample_changed` | Investigate the output, correct/version the source and obtain evidence for the current snapshot. |

## Data-only payloads and bounds

Tasks use the shared `Task` schema in `backend/app/content.py`; lessons and
profiles use `Lesson` and `ProfileSource` in `backend/app/schemas.py`.
Editorial input/export omits server-managed `revision`, review status and
authorship. Task `source` supplies only `origin` and `rights`; the server sets
`author` and `reviewed_by`. Lesson `author_id`/`reviewed_by` are also managed.
Profile `status` is the exam profile's own draft/approved state and is editable;
it is distinct from the editorial workflow status.

Task answers remain exact strings. Tasks/exam lessons need explicit stable
`slot_id` bindings. Foundation lessons use `kind: "foundation"`, `slot: 0`,
`slot_id: null` and nonempty `related_slot_ids`.

Template payload fields are `id`, `title`, `generator_id`, `generator_version`,
`profile_id`, optional `profile_revision_id`, `slot_id`, `family_id`,
`skill_ids`, `formula_notes`, `constraints`. These select registered server
code; they cannot upload a Python/JavaScript implementation.

Validation rejects HTML/SVG markup, prototype-related object keys, unsupported
LaTeX commands/environments, non-finite numbers, unknown schema fields and
unbounded trees. Figures use the shared bounded figure DTO. JSON trees are
limited to depth 16, 12000 nodes, 1200 elements per list, 16000 characters per
string and 131072 serialized UTF-8 bytes per payload. LaTeX in JSON requires
escaped backslashes. The preview uses the existing safe math/task renderers.

The shared request-body limit is independent and can be lower: its default is
16384 bytes, configurable through `MAX_REQUEST_BYTES` from 512 to 1048576.
`/meta.max_request_bytes` is authoritative for the frontend. The ten-item import
and thousand-reference publication caps do not override this byte limit.

All import rows are prepared/validated before revision creation, with row-indexed
structural errors. Editorial writes also run inside a savepoint, so a later
failure in audit, evidence or publication rolls back every editorial change.
The outer idempotency transaction can persist and replay that failure response.
Existing IDs are not bulk-upserted: import a file-backed ID through `/base`, or
fork its existing editorial revision. Export keeps stable IDs and returns the
import format, but importing it into the same catalogue does not overwrite its
existing records or transfer review authority.

## Publishing a profile or content package

The catalogue singleton serializes editorial version allocation and publication.
`combined_content` merges the file-backed bank with active publication pointers
and candidate revisions, then validates the complete profile/task/lesson graph
and lesson prerequisite cycles. PostgreSQL readers take a shared catalogue row
lock to keep separate READ COMMITTED queries in one publication epoch. SQLite
uses the existing explicit transaction behavior.

Numeric position is not identity. A changed profile must be accompanied by
explicit task/lesson mappings to the intended stable slots and skills. Legacy
items without `slot_id` remain bound to their original profile's stable slot.
They are not silently reassigned to whichever skill inherits a number. A
package may contain at most one candidate profile. Active templates are also
checked against the candidate profile; changing runtime slot mappings may
require a new server generator version.

For a methodist/admin:

1. Open **Исходный банк** for existing file-backed material, or create a new ID.
2. Edit **Рабочий JSON**, check the mobile preview and describe the change.
3. Submit it for **Предметная проверка**. A different staff account records its
   review and approval.
4. Select mutually dependent ready revisions **В пакет**. An admin supplies a
   publication reason and publishes the whole package atomically.
5. After a profile change, reopen the editor after saving/downloading local work
   so `/meta` refreshes the reference rail and new-material defaults.

Existing practice sessions, attempts and assessment results retain the original
task/profile snapshots. Publication changes the source for future selection.

## Template evidence

Only `supports_runtime` families from `app.generators.FAMILIES` are registered
for editorial execution. Both sequence/tuple and dictionary registries are
supported. Missing registrations or mismatched versions fail closed.

The template workflow is:

1. Bind the template to its generator/version and explicit profile/slot/family/
   skill mapping. `profile_revision_id` can bind checks to an available candidate
   profile before it is published.
2. Run `/checks`. The server generates twice for each of exactly 1000 distinct
   seeds: `0..997`, `4294967294`, `4294967295`. It records output hashes, payload
   hash, profile hash, generator version, actor and outcome.
3. In `review`, an independent reviewer obtains `/sample?seed=...`, checks its
   condition, solution, answer and constraints, then posts the returned hash and
   their decision to `/samples`. A repeated attestation for the same reviewer/
   revision/payload/profile/seed is rejected.
4. The reviewer who approves the template must personally own at least ten
   distinct approved samples and explicitly confirm formula and constraint
   review. A matching rejected sample from any reviewer blocks approval.
5. Approval and publication reproduce the recorded manifest and that reviewer's
   sample hashes. Changed code, output, payload or profile cannot be accepted on
   a client-provided seed count. A profile publication also revalidates evidence
   for templates that remain active.

Automated checks establish strict structure, finite exam-format answers,
determinism and profile/version/seed binding. They do **not** independently prove
mathematical correctness, the uniqueness of a solution, every domain constraint
or the correctness of a worked explanation. Generator-specific independent
oracles and real subject review remain separate evidence. Browser/unit-test
attestations are synthetic fixtures, not human acceptance of the course.

A task carrying `generation` must reproduce its mathematical snapshot from the
registered generator/version/seed when published. To author a different task,
remove that generation claim and obtain the normal independent review.

## Withdrawal and correction notices

An admin withdraws the current task revision with a reason. The transaction
creates a publication tombstone, archives the published editorial version when
present, writes an audit event and records an exclusion keyed by
`(task_id, task_revision)`. A file-backed task can also be withdrawn without
first creating an editorial revision. A tombstone prevents fallback to that
file-backed task on the next content read.

The effective read projection removes withdrawn practice links from existing
lessons so withdrawal does not make the rest of the bank unavailable. Stored
lesson payloads remain intact; newly published candidate lessons must themselves
have valid references. Publishing a corrected, newer revision reactivates that
ID while the erroneous old revision remains excluded from mastery evidence.

`exclusions(db)` supplies reasons to the learning projection. It does not mutate
attempts or frozen scores. `notices(db, guest_ids)` must receive only
server-resolved owner IDs. It returns affected attempt/session IDs and released
assessment IDs, the reason, `effect: "excluded_from_mastery"` and
`historical_scores_unchanged: true`. Assessment notices appear only for
`completed` assessments with non-null `released_at`; unreleased assessments
cannot leak task membership through the correction adapter.

## Frontend lifetime and recovery

`EditorMutationQueue` permits one in-flight/uncertain writer per open editor.
It serializes and freezes the body and UUID before the first send. Network
failure, an unreadable response, server failure or failed response decoding
retains that exact request. Retrying reuses its bytes, key, path and actor.
Intervening 401/403/429 responses do not erase an already uncertain request:
those gates precede the server's replay lookup and cannot disprove an earlier
commit. Other mutations remain blocked until the uncertainty resolves.

The server namespaces operations by authenticated editor account and action,
uses the canonical owner lock, and returns the original stored status/body for
a matching replay. A changed-body reuse conflicts. Authorization is still
required for replay. The editor adds no separate expiry to the shared durable
idempotency records.

Draft JSON, import input, selection, package and filters live **only in memory**.
They survive recoverable request failures in the mounted editor, including CAS
conflicts. They do not survive reload, unmount, a process crash or a lost tab.
The queue does not persist a request for replay after reload. Downloads preserve
raw draft/import text; they are not a durable pending-request journal.

The UI offers **Скачать ввод**, explicit CAS reload confirmation, a native
`beforeunload` guard and confirmation on intercepted same-tab hash-link clicks.
Switching the selected material also confirms dirty input. These guards are not
a general browser-history/host-remount barrier. Catalogue filters have no URL
deep links. After a lost tab, inspect the server's current revision/audit before
starting another write. MFA recovery can be opened in another tab to retain the
current editor and its pending request.

## Verification recorded on 2026-11-05

Latest recorded scoped commands from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor.py -q
.\.venv\Scripts\python.exe -m ruff check app/editor migrations/versions/0005_editor.py tests/test_editor.py
```

**33 pytest tests passed in 23.36 s; scoped Ruff passed.** Coverage includes
actual mounted account/MFA gates, actor binding, independent review/admin
publication, CAS and exact replay, late-failure rollback, immutable publication,
stable profile remapping, historical snapshots, withdrawal issuance, owner/release
scoped corrections, template evidence/rejection/staleness, false generation
claims and migration/model parity.

From `frontend`:

```powershell
npm test -- tests/editor.test.ts
node node_modules/eslint/bin/eslint.js src/editor src/pages/editor.tsx tests/editor.test.ts --max-warnings 0
npm run build
```

**34 Vitest tests passed in 841 ms; scoped ESLint passed.** These cover private
DTO parsing, data-only JSON/seed handling, transport and immutable queue/retry
behavior. The latest recorded **full frontend build passed** after the coordinator
mounted the editor route and reconciled account export through
`parseHistoryExport`. It produced `editor-BXyt9EJJ.js` and `editor-C7P4c2h7.css`;
both assets were subsequently loaded by the integrated browser smoke below.
The completed unit, lint, migration and build checks were retained across the
verification-server restart; the resumed work exercised the production route
and updated this handoff.

The isolated actual Alembic chain `0001_learning_core` through `0005_editor`
preserved populated predecessor data, added exactly the seven editorial tables
and refused downgrade. PostgreSQL locking/concurrency was not exercised by that
SQLite proof.

### Browser and interface evidence

Playwright CLI exercised the editor mounted in a temporary standalone entry,
using the real editor/account services, a new SQLite database, fixture staff
accounts, a fixed test clock and a synthetic registered generator. The shared
backend mount/issuance hook was verified separately by the latest pytest run;
that standalone harness predates the shared wiring.

- Author: search/filter/empty recovery, validation and preview, edit/submission/
  audit, atomic import and downloaded export.
- Committed response loss: the request reached the backend, its response was
  aborted, an MFA rejection intervened, and the original body/key replayed.
- Real CAS conflict: a competing write produced 409; local JSON remained,
  a backup downloaded, and confirmed reload showed the newer server revision.
- Reviewer: independent approval, required-note focus, methodist publication
  restriction, absent-evidence gates, recorded 1000-seed run, ten synthetic
  sample attestations and formula/constraint confirmation.
- Admin: two-item publication, template publication, reasoned withdrawal/audit,
  fork and draft archival, with the published predecessor payload preserved.

The confirming UI run measured widths **320, 360, 390, 768, 1024 and 1440 CSS
pixels**: no horizontal document overflow and no measured editor control target
below 44 × 44. Checkbox/radio targets were measured using their associated
clickable labels. Catalogue source labels stayed on one line at all six widths.
Axe scans of `.editor-page` found **zero violations at 320 and 1440 px** after
the profile-reference heading was corrected from `h3` to `h2`.

Keyboard search/selection and slot switching passed. A follow-up full Tab pass
reached **50/50 enabled editor controls**, with visible outlines and successful
hit tests at their viewport-intersection centres. The tall JSON field extended
below the viewport; its focused first line and 3 px ring were visible above the
fixed navigation. The initial whole-rectangle-centre probe was offscreen for
that field and was corrected. This proves minimum focus visibility, not full
control visibility or the enhanced AAA criterion.

Reduced-motion emulation produced zero-second button/catalogue transitions.
CDP device metrics also checked a **720 × 450 CSS-pixel viewport at DPR 2**,
representing 200% desktop reflow of 1440 × 900 device pixels; no overflow or
undersized targets were measured. This is device-metrics emulation, not native
browser-zoom or physical-device evidence. Opened desktop/mobile and grayscale
confirmation screenshots retained the shared worksheet/blue hierarchy.

### Integrated production-route evidence

After the verification-server restart, `serve_integrated_api.py` created a separate
new SQLite fixture with the current shared backend mount, fixture staff accounts,
a fixed clock and a synthetic registered generator. The earlier fixture database
and workflow artifacts were preserved. `serve_integrated.mjs` served the existing
production build at `http://127.0.0.1:5294`, using the real Vite configuration and
an `/api` proxy to the isolated API on port 8194.

`integrated_smoke.js` passed with the fixture author's saved authentication state:

- `#/editor` loaded both production editor assets and the authenticated catalogue.
- The host requested `/api/v1/identity`; the editor requested `/meta` and
  `/revisions`, with `X-Editor-Actor` present on the catalogue request.
- All five primary navigation links were present. Keyboard activation of
  **Создать** opened a local worksheet and focused its heading.
- All observed API requests were GETs. There were no API failures or page errors.

`integrated_navigation.js` then confirmed the coordinator's shared mobile-label
fix at **320 and 390 px**: five single-line labels, each fitting its own target,
and no document overflow. The smallest target measured approximately
**59.39 × 61.19 CSS px**. At 320 px, the compact **Повтор** caption retained the
accessible name **Повторение**. The 320/390/1440 px production screenshots were
opened and inspected. The previously reported shared mobile word-wrapping issue
is resolved in this build.

### Mechanical and source checks

The six scoped design-warning decisions are recorded beside their affected
code: four shared-loading ellipsis decisions, in-memory catalogue URL state and
inherited touch behavior. Latest individual results: design checker **0 errors,
0 warnings across 21 files**; WIG **21 files passed**; token contrast **13 pairs
passed**; Russian-copy check **16 files passed**. The combined
`verify.mjs` invocation did **not** pass: it attempted contrast analysis on
token-free `editor.css` and lacked a URL. Its individual subcheck results must
not be described as a passing combined pipeline.

Existing scoped Aegis reports record zero static findings across eight backend
and eighteen frontend editor files. These are bounded scanner results, not a
claim of exhaustive security coverage. Targeted executable-content,
browser-storage and logging searches supplement those reports.

The resumed repository source-hygiene run checked **354 files** with
`node scripts/check-source.mjs`, finding no matching secret formats or unpinned
workflow actions.

Browser scripts, screenshots, downloads, migration proof and scanner reports
are under
`C:\Users\user\AppData\Local\Temp\opencode\editor-task4-20261105-1859`.
Key artifacts: `confirm_ui.js`, `confirm_focus.js`, `editor-after-{320,390,1440}.png`,
`editor-document-after-{390,1440}.png`, `editor-document-squint-1440.png`,
`editor-focus-probe-320.png`, `browser-export.json`,
`browser-conflict-input.json`, `migration-result.json`,
`security-backend.json`, `security-frontend.json`, `integrated_smoke.js`,
`integrated_navigation.js`, `integrated-smoke-result.json` and
`editor-integrated-{320,390,1440}.png`.
Temporary browser authentication states stay outside the repository.

## Coordinator handoff

1. Verify host identity changes, PWA updates and browser-history/remount behavior
   with dirty editor input and an uncertain write. The current in-memory lifetime
   and the scope of the navigation guards are documented above.
2. Verify PostgreSQL catalogue/owner locking, simultaneous publication/issuance
   and the deployed environment; the SQLite and local browser evidence does not
   cover these conditions.
3. Obtain real independent content/template acceptance. Automated fixture
   attestations do not supply it.
