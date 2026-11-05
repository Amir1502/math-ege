# Diagnostic and mock-exam backend

Backend contract for approved Task 2 of
[`superpowers/plans/2026-11-05-completion.md`](superpowers/plans/2026-11-05-completion.md),
the [completion design](superpowers/specs/2026-11-05-completion-design.md), and
FR-04, FR-10, FR-13 and FR-17 in [`technical-spec.md`](../technical-spec.md).

Implementation: `backend/app/assessments/`. The HTTP DTOs are defined in
`schemas.py`; the service owns lifecycle transitions, `grading.py` owns exact
final grading, and `presentation.py` owns the result-release boundary.
The client integration is documented in [`assessment-client.md`](assessment-client.md).

## Host integration

The coordinator-owned `backend/app/main.py` now registers the assessment service
and router after constructing the shared learning service:

```python
from app.assessments.api import router as assessments_router
from app.assessments.service import AssessmentService

application.state.assessments = AssessmentService(application.state.service)
application.include_router(assessments_router)
```

Import `app.assessments.models` before collecting migration/test metadata.
Production schema installation uses the additive Alembic migration; test schema
creation is only an isolated fixture facility. Mounting the router also adds the
assessment operations and schemas to `/openapi.json`.

### Shared ownership and transactions

`AssessmentService(learning_service)` uses the shared `database`, `settings`,
`clock`, `locked_content()`, `reauthorize()`, `owner_ids()`, `_guest_transaction()`,
`_idempotent()`, `observe_save()` and `operation_health`.
The host must preserve these contracts:

- Preparation calls `locked_content(db, token)` **inside the new-action callback
  of `_idempotent()`**, after replay/body-conflict lookup. It locks the editor
  catalog, reauthorizes against the injected clock and loads the coherent
  effective bundle in the existing transaction. Owner/catalog locks remain held
  through selection, snapshot persistence, exposure marking and commit.
- `reauthorize(db, token, *, write=True) -> Guest` refreshes access after a later
  lock wait. GET, `_mutate()` (activate/takeover/finish), and draft PUT call it
  immediately after `_owned()` acquires the assessment lock, before deadline
  freezing or other mutation. These paths use write mode because even GET may
  freeze a deadline. Expired guest/account access returns 401 and rolls back the
  outer transaction, including authentication timestamps; it creates no durable
  idempotency error or save/check counter event.
- `owner_ids(db, guest)` returns every original guest owner linked to the resolved
  principal. Assessment IDs are looked up inside that scope; foreign IDs return
  404. Historic `guest_id` values stay attached to their original records.
- `_guest_transaction(token, write=True)` resolves guest/account credentials and
  locks the canonical owner root before assessment, draft or idempotency rows.
  The account implementation is `app.accounts.principals.resolve_guest`.
- `_idempotent()` resolves keys across owned origins, preserves original stored
  responses, and rolls back a rejected action inside its savepoint. The outer
  transaction still commits a deadline freeze performed before a handled domain
  rejection. Authorization 401 is rethrown instead of being durably recorded.
- `request_uuid(key)` is the shared canonical UUID normalizer. Static ordering
  and runtime generation receive this normalized key, including for uppercase
  incoming UUIDs.
- `observe_save("draft_save")` surrounds the owner transaction, so its exit
  observes commit/rollback rather than an early response construction. The shared
  `operation_health` is the same clock-initialized object exposed on `app.state`.
- PostgreSQL uses database row locks; SQLite uses `BEGIN IMMEDIATE` for write
  transactions. An in-process mutex cannot replace this contract.

### Independent deadline reconciliation

The public synchronous worker entry point is:

```python
frozen_count = application.state.assessments.reconcile_deadlines(limit=100)
```

The host lifespan now uses `DeadlineWorker` from `backend/app/background.py`.
It awaits `worker.reconcile()` before yielding startup, then runs reconciliation
off the async event loop at a default five-second interval with health retry
backoff. Shutdown stops scheduling and drains the worker before database
disposal. Each service call scans at most `limit` candidates and handles each
in a short transaction. The limit must be positive.

The worker maps each stored origin through `accounts.principals.root_owner_id`,
locks that root first, rechecks the mapping, then locks and rechecks the
assessment. A competing worker, final submission, or account claim is safe to
retry on the next scan. Contended PostgreSQL roots are skipped; a return value
of zero is a count of transitions, not a guarantee that no due rows remain.
Expired guest credentials do not prevent this internal worker from freezing
their already-started exams.

The scheduler must keep retrying after recoverable failures and expose its last
success/failure through the host's job diagnostics. On shutdown, stop scheduling
and await the active reconciliation call before disposing the database. A
request-scoped background task does not supply the required independent timer.

No in-memory timer state is needed for recovery: persisted active exams and
deadlines are sufficient. A delayed worker uses the actual `deadline_at` as the
canonical snapshot time, regardless of its wake-up time.

The restart regression reads the persisted assessment immediately after the real
lifespan starts, before any GET or explicit reconciliation. It requires
`awaiting_snapshot`, a private canonical result frozen at the deadline, and an
unreleased result gate. The subsequent explicit reconciliation must return zero,
and final snapshot acceptance must preserve that exact startup-frozen result.

### History, export and learning

Use `assessment_view()` for an assessment response. Full ORM task snapshots and
stored result JSON contain private answers, even while public results are
closed. History, export, errors, favourites and learning projections must apply
the same release predicate: `status == "completed"`, non-null `released_at`, and
a canonical `server_result`. A worker freeze alone does not release anything.

The public Python evidence adapter is described below. Connect it to the
coordinator-owned projections and export integration. Keep assessment history
identified by its own assessment/result IDs rather than manufacturing practice
sessions or duplicate practice attempts.

## HTTP conventions

Base path: **`/api/v1/assessments`**. All successful operations return HTTP 200
and a complete `AssessmentView`, including draft saves.

- Authentication uses the host's existing HttpOnly guest/account cookie.
- Every write requires JSON, an allowed `Origin`, and
  `X-Requested-With: math-ege` under the shared request middleware.
- Every POST requires `Idempotency-Key: <UUID>`. Use a new UUID for each intended
  mutation, and persist the original body together with a pending request.
- GET accepts `X-Assessment-Device: <UUID>` to calculate `can_write`. Omitting it
  gives a read-only view. Device IDs identify writers; they are not credentials.
- Clients using the shared identity guard also send `X-Learning-Owner` with the
  resolved principal ID to detect a cookie/identity change in another tab.
- API timestamps are timezone-aware ISO 8601 strings. Countdown uses the
  returned `server_now` and immutable `deadline_at`.
- Objects reject unknown fields and coercions such as `true` or `"65"` for an
  integer. Answers are strings of at most 64 characters. UUIDs are JSON strings.

| Method and suffix | Body | Purpose |
| --- | --- | --- |
| `POST ""` | `PrepareRequest` | Freeze a complete 13-slot assessment. |
| `GET /{id}` | None | Restore state and reconcile a due deadline. |
| `POST /{id}/activate` | `WriterRequest` | Explicitly confirm the prepared start. |
| `PUT /{id}/draft` | `DraftRequest` | Save a partial answer map with revision CAS. |
| `POST /{id}/takeover` | `WriterRequest` | Explicitly transfer the writer generation. |
| `POST /{id}/finish` | `FinishRequest` | Accept an immutable complete final snapshot. |

### 1. Prepare

`POST /api/v1/assessments`:

```json
{
  "mode": "exam",
  "duration_minutes": 65,
  "device_id": "982f3f52-504b-4c28-a62c-7537f7d77c84"
}
```

`mode` is `diagnostic` or `exam`. `duration_minutes` is an integer from 15 to 180,
defaulting to 65. The duration is frozen at preparation; diagnostics retain the
setting but have no deadline.

The current profile must have exactly 13 distinct slots. Preparation freezes
exactly one task per slot, with 13 distinct actual task IDs and visible condition
keys, together with complete task/profile revisions. Selection proceeds as follows:

1. Select fresh allowed static tasks, deduplicating across slots by `instance_key`
   and actual ID. `recent_exposure(db, owners, bundle.tasks, now)` excludes recent
   conditions and their historical aliases across authenticated origins. Its
   default window is 30 days; final independence still checks all prior history.
2. If slots remain, call `generate_candidates()` **once** with a validated
   `CreateSessionRequest(slots=missing, length=20, mode="practice")`, a separate
   `limit=len(missing) <= 13`, and `slot_limits={number: 1}`. Pass the normalized
   request key, full effective bundle, exposure/selected IDs and complete selected
   static snapshots in `exclude_tasks`. The helper resolves full owner histories,
   including removed/revised snapshots, and enforces source, withdrawal and
   global/per-template generation limits.
3. If fresh/runtime selection still leaves a slot empty, the existing historical
   assessment behavior allows a noncolliding **current allowed static** task as a
   repeat. The prepare response's `result_notice` explicitly lists these repeated
   positions. This notice is frozen in the idempotent response; later GETs carry
   the current lifecycle notice. Repeats retain alias-aware assistance and prior
   numeric eligibility and cannot grant a second independent credit.
4. If a slot has no allowed noncolliding static or generated task, reject the
   entire new action with 409 `assessment_bank_incomplete`. No partial assessment,
   exposure update or legacy-key backfill survives the savepoint rollback. The
   explicit all-13 error itself remains durably replayable.

Private task snapshots are persisted before calling
`mark_instances(db, record.guest_id, tasks, now)`. Only the assessment's original
owner scope is marked. Existing row IDs, owner scopes, first-seen timestamps and
assistance/reference flags are preserved; last-seen time advances monotonically
only in that original scope. Legacy NULL keys may be filled from immutable
history. Issuance creates no numeric attempts and never relocates merged origins'
exposure records.

Runtime provenance (seed/template/version) is frozen privately with each returned
task. Public tasks still use the explicit allowlist. Demo generation remains demo;
the expanded default course has 845 tasks and 99 lessons and has no manufactured
review attestations. Source/publication gates are defined in
[`runtime-issuance.md`](runtime-issuance.md).

The initial state is `prepared`, `writer_generation: 1`, `draft_revision: 0`,
`current_index: 0`, and empty `drafts`. Both `started_at` and `deadline_at` are
null. The client persists all 13 conditions and required media before offering
explicit activation.

### 2. Activate and take over

Both endpoints accept `WriterRequest`:

```json
{
  "device_id": "982f3f52-504b-4c28-a62c-7537f7d77c84",
  "writer_generation": 1
}
```

Activation requires the current writer. It changes `prepared` to `active` and
sets `started_at` from server time. Exams get
`deadline_at = started_at + duration_minutes`; diagnostics keep a null deadline.
Repeated activation while active preserves both timestamps.

For takeover, `device_id` is the adopting device and `writer_generation` is the
generation it most recently observed. A successful takeover increments the
generation and returns the existing drafts and revision. The client uses that
new generation for subsequent writes. A stale generation conflicts, including
a competing takeover; no draft is silently overwritten. Takeover is available
while prepared, active, or awaiting a final snapshot.

### 3. Save drafts

`PUT /api/v1/assessments/{id}/draft`:

```json
{
  "device_id": "982f3f52-504b-4c28-a62c-7537f7d77c84",
  "writer_generation": 1,
  "expected_revision": 0,
  "current_index": 3,
  "answers": {
    "task-id-from-tasks": {"answer": "−", "active_seconds": 12}
  }
}
```

`answers` has at most 13 entries, keyed only by IDs in the frozen task list.
Each entry requires `answer` and integer `active_seconds` in `0..86400`, also
subject to the host's `max_active_seconds` setting. `current_index` is a zero-based
index in the returned task array (`0..12`); `expected_revision` is nonnegative.

Drafts accept empty and intermediate strings, including `−`, `2,`, and `1/2`.
They merge only the supplied task keys, retaining each task's maximum reported
cumulative active seconds. Every accepted save increments `draft_revision`,
including a position-only save with an empty map. A stale expected revision
returns `assessment_draft_conflict` with no partial change.

Draft PUT does not use an idempotency key. After a lost response, GET the current
revision and reconcile the preserved local input before sending another save.
Drafts are editing history and never create mathematical attempts or release
correctness. Diagnostics can pause and resume by restoring this state; exams
continue counting down during navigation, reloads and backgrounding.

### 4. Finish

`POST /api/v1/assessments/{id}/finish`:

```json
{
  "device_id": "982f3f52-504b-4c28-a62c-7537f7d77c84",
  "writer_generation": 1,
  "connection_lost": false,
  "answers": {
    "task-id-from-tasks": {"answer": "2,5", "active_seconds": 30}
  }
}
```

`connection_lost` is required and strictly boolean. The answer bounds are the
same as for drafts, but **finish is an authoritative complete snapshot**. Omitted
tasks become `{"answer":"","active_seconds":0}`; they do not inherit older
draft answers or times. Finish has no draft revision field. It requires
activation and the current writer device/generation.

| State at server acceptance | Canonical server snapshot | Separate local result |
| --- | --- | --- |
| Active, before the exam deadline (or diagnostic), `connection_lost: false` | Supplied final map; reason `finished`. | Null. |
| Active, before the deadline (or diagnostic), `connection_lost: true` | Last accepted online drafts; reason `connection_lost`. | Supplied final map. |
| Exam deadline reached, or already `awaiting_snapshot` | Last drafts frozen at `deadline_at`; reason `deadline`. | Supplied final map, even if the request says `connection_lost: false`. |

For each mutation, the service samples one acceptance timestamp after acquiring
the owner and assessment locks. A deadline reached at that instant is due.
The service freezes it before processing the submitted answers. A slow request
cannot receive a post-deadline timestamp with an online pre-deadline result.

Local results are labelled as educational results received after connection
loss or the deadline. Their `snapshot_at` is the server's acceptance time, not a
claimed client completion time, and all local rows are non-independent. When
the final map is accepted, both stored results become readable together,
`released_at` is set, and the assessment becomes `completed`.

The client confirms early completion when answers are blank and freezes its
local finish body and request UUID before sending. It must retain that immutable
request during offline retries.

### Replay and immutable content

The shared idempotency store returns the original response bytes for the same
operation, key and body, including stored domain errors. Reusing a key for a
different operation or body returns `idempotency_conflict`. Preserve the exact
request field set, including whether optional fields were supplied.
Preparation replay precedes catalog access and generation, so frozen conditions,
provenance and notices survive source withdrawal or a changed course.

Stored replay responses contain their original `server_now`, status, drafts
and generation. GET provides current state; a replay is not a new clock sample
or grant of writer ownership. Deadline reconciliation still commits before a
replayed or conflicting handled request is returned.

Finish also stores a content hash independently of the request key. Retrying
the same final content with a new key returns the frozen results. Any changed
raw answer, reported active time, or `connection_lost` flag returns
`assessment_snapshot_conflict`. Answer-map order is irrelevant, and omitted
entries equal explicit blank/zero entries for this content hash. Numerically
equivalent but differently written answers are still different raw snapshots.

### Operational counters

Assessment instrumentation uses the existing fixed event names, with no owner,
task, answer, request-key or seed labels:

- `generator`: `generate_candidates()` owns the shared generator instrumentation;
  the assessment adds no extra per-request event. Replay does not invoke the
  generator. Executed generation remains counted if incomplete all-13 coverage
  later rolls back the assessment action.
- `draft_save`: enter `observe_save()` outside `_guest_transaction()`. Set
  `attempted` only after writer/state/task/time/revision validation, immediately
  before the first input-history mutation; set `success` only for an accepted
  response. A successful commit counts one success, and a failed commit/rollback
  counts one failure. Pre-mutation 409/422/401 responses count neither. Intermediate
  answer text is valid draft content and can be a successful save.
- `answer_check`: count each actual nonblank server/local `check_answer()` call
  in `build_result()`. A valid-format wrong answer is a successful check; a format
  or checker exception is a failed check. Skips, first-input parsing, draft edits,
  ordinary views and replayed frozen results add no checks. Deadline freezing
  counts its actual grading once; later local grading counts its separate calls.
  These are execution counters, so checks already performed remain counted if a
  later database operation rolls back.

The internal `build_result()` interface now requires the keyword
`operation_health: OperationHealth`. Its three callers—canonical finish, local
finish and deadline freezing—pass `learning_service.operation_health`.

## State and public view

| Status | Timing and result boundary | Current writer operations |
| --- | --- | --- |
| `prepared` | No start or deadline; results null. | Activate or take over. |
| `active` | Diagnostic has no deadline; exam has an immutable deadline. Results null. | Draft, finish, take over, or repeat activation. |
| `awaiting_snapshot` | Deadline snapshot is persisted privately; public results remain null. | Submit final snapshot or take over; drafts are closed. |
| `completed` | Results released and immutable. | Identical finish replay only. |

`can_write` reports that the requesting device is the current writer and the
assessment is not completed. In `awaiting_snapshot`, it permits final snapshot
submission, not continued draft editing. Every actual mutation rechecks device,
generation and state on the server.

`AssessmentView` contains:

- Identity and frozen context: `id`, `mode`, `profile_id`, `profile_revision`,
  and the original `profile: ProfileSource`.
- Lifecycle: `status`, `created_at`, `server_now`, nullable `started_at`,
  `deadline_at`, `released_at`, and `duration_minutes`.
- Editing: `writer_generation`, `can_write`, `draft_revision`, `current_index`,
  and `drafts` using the same answer-entry shape as requests.
- Content and outcome: exactly 13 `tasks`, nullable `server_result` and
  `local_result`, and a human-readable `result_notice`.

Tasks always use the explicit `PublicTask` allowlist: `id`, `revision`, `slot`,
`topic`, `title`, `statement`, `formula`, `table`, `skill_ids`, `family_id`,
`estimated_seconds`, `review_status`, `hint_count`, `slot_id`, `figure`, and
`rounding`. Assessment `hint_count` is always zero. Task DTOs exclude answers,
hints, solutions and private source metadata, including after completion.
Released explanations appear only in result rows.

There are no assessment hint, solution or immediate-attempt endpoints. Passing
an assessment ID to practice session endpoints returns 404. History/export
integration must not expose a private deadline snapshot through another route.

## Grading and result fields

Both modes grade only final values using the exact checker in `exam` mode.
Accepted forms are integers and finite decimals; outer whitespace, the Unicode
minus, dot/comma decimal separators and leading zeros are normalized. For
example, `0002.50` becomes `2,5`, and `−0` becomes `0`. Arithmetic uses exact
rational comparison without floating-point tolerance or implicit rounding.

- Empty or whitespace-only text is a skip, worth zero and distinct from `0`.
- Fractions (`1/2`), expressions, scientific notation, units, internal spaces,
  and incomplete decimals (`2,`) produce a format-error row, worth zero.
- Format errors are not wrong numeric attempts: `normalized` is null,
  `format_error` is true, and `independent` is false. A final snapshot containing
  them still succeeds and shows the per-row format message after release.
- `score` counts correct rows out of 13. `answered` counts valid numeric rows;
  `answered + skipped + format_errors == 13`.

`AssessmentResult` includes:

| Fields | Meaning |
| --- | --- |
| `source`, `reason`, `label` | `server`/`local`, `finished`/`deadline`/`connection_lost`, and educational wording. |
| `score`, `total`, `answered`, `skipped`, `format_errors` | Score and distinct outcome counts; `total` is always 13. |
| `independent_total`, `independent_correct`, `assisted_total` | Frozen final-eligibility counts, separate from score. |
| `active_seconds`, `elapsed_seconds` | Sum of snapshot task times and wall time from activation to this snapshot. Diagnostic wall time includes pauses. |
| `snapshot_at`, `snapshot_hash`, `checker_revision` | Snapshot timestamp, SHA-256 of frozen profile/tasks/answer map, and `fraction-v1-exam`. |
| `connection_lost` | True for local results or an early server freeze explicitly caused by lost connection. |
| `rows` | Exactly 13 `ResultRow` objects in frozen task order. |
| `weak_skill_ids`, `recommendation` | Original skill IDs for non-correct rows and a preliminary learning recommendation. |

Each `ResultRow` has:

- Stable `id`, `task_id`, `task_revision`, original `slot`, stable `slot_id`,
  `family_id`, and `skill_ids`.
- `raw`, nullable `normalized`, `expected`, `correct`, `skipped`, `format_error`,
  nullable `format_message`, and `label` (`Верно`, `Неверно`, `Пропущено`, or
  `Ошибка формата`). These wire names differ from practice's `raw_answer`,
  `normalized_answer` and `expected_answer`.
- `independent`, `assisted`, `first_attempt`, `active_seconds`, and `solution`
  as a list of explanation steps.
- Nullable `first_draft` and `first_answer`, each shaped as
  `{answer, active_seconds, recorded_at}`. The former preserves the earliest
  recorded draft, including intermediate text; the latter preserves the first
  valid numeric input as immutable editing history. The final `raw` answer is
  what is graded.

`first_attempt` identifies canonical server rows; it is not by itself proof of
a valid numeric or independent answer. Final eligibility is sampled separately
from first-input history when the canonical result is created, under the shared
owner root lock:

- `aliases_for_task(db, owners, frozen_task, tasks=record.tasks_snapshot)` resolves
  actual original alias IDs and owner-scoped exposure records from immutable
  snapshots. Today's task ID, revision or content loader is not the identity of a
  frozen condition. Unrelated owners' aliases do not affect the result.
- The service aggregates `SeenTask.assistance_seen` and `reference_seen` across
  those alias records and all currently owned origins, including newly linked
  histories. A hint, full practice solution or released assessment reference after
  the first numeric draft makes the final row assisted and non-independent.
  First-input assistance uses the same alias aggregation when its context is
  first recorded; later exposure or an owner merge does not rewrite that context.
- `prior_numeric_ids(db, owners, at=snapshot_time,
  exclude_assessment_id=record.id)` supplies valid normalized practice answers and
  pending/released canonical **server** rows. The assessment maps intersections
  with actual alias IDs back to its own frozen task IDs. Both practice time and
  server snapshot time honor the cutoff; a later pending snapshot does not
  retroactively reserve an earlier deadline. Local rows and current-assessment
  draft edits do not count as earlier numeric answers.
- The final answer can still be correct and contribute to `score`. Its original
  `first_answer`, active time and input timestamp remain the recorded history.

`SeenTask` exposure flags have no event timestamps. A delayed deadline worker
therefore conservatively uses exposure known when it acquires the owner lock and
freezes the result; `snapshot_at` still records the exam's deadline. Once frozen,
canonical eligibility is immutable. Exposure after that freeze can be reflected
in a later local result, whose rows are always non-independent, without changing
the canonical result. The assessment's own reference exposure is recorded only
after its results have been built and its final snapshot accepted, on task rows
in `record.guest_id` only. Other origins' historical flags are not rewritten;
future alias resolution derives the combined exposure.

Frozen pending server snapshots reserve their numeric instances against a
second independent assessment result, while remaining excluded from public
learning evidence until release. Score can still be 13 for a familiar set with
zero independent rows. Recommendations do not mark a skill mastered from one
correct diagnostic answer and never convert 0–13 to a full EGE test score.

## Released evidence adapter

```python
from app.assessments.evidence import released_evidence

with learning_service._guest_transaction(token) as (db, guest):
    rows = released_evidence(db, learning_service.owner_ids(db, guest))
```

`released_evidence(db, guest_ids) -> list[dict]` returns detached deep-copied
canonical server rows for completed, released assessments in the supplied owner
scope. It is an internal read adapter; caller-supplied IDs do not authenticate
an HTTP request. Duplicate owner IDs do not duplicate rows.

Each item contains all `ResultRow` fields plus:

| Field | Value |
| --- | --- |
| `assessment_id`, `guest_id`, `sequence` | Original assessment and owner IDs, and zero-based task position. |
| `mode`, `source`, `result_source` | `diagnostic`/`exam`, `assessment`, and `server`. |
| `at`, `released_at` | Aware Python datetimes for canonical snapshot time and final acceptance time. |
| `checker_revision` | Frozen checker version. |
| `profile_id`, `profile_revision`, `profile_snapshot` | Complete original profile context. |
| `task_snapshot` | Complete original task revision, including its private reference data. |

The canonical event ID is the persisted row `id`, generated as
`uuid5(UUID(assessment_id), "server:" + task_id)`. Repeated reads, restarts and
account linking preserve it. Never use the receipt time or a new UUID as a
replacement event ID.

Consumers must:

1. Read only released canonical evidence. Local rows do not create an additional
   attempt, review success or mastery achievement.
2. Preserve skip and format-error labels. The adapter returns all 13 rows;
   exclude `normalized is None`/`format_error` rows from numeric accuracy and
   mastery denominators rather than counting them as wrong numeric answers.
3. Deduplicate both original event IDs and task instances across practice,
   assessments and merged owner origins. Do not rewrite historic result JSON
   when projecting a newly merged account.
4. Map skills/families and stable positions from frozen context. A numeric slot
   in today's profile is not a historical join key.
5. Use public task/result DTOs when serializing history or export. Full adapter
   snapshots are for internal projections, not direct HTTP serialization.

## Errors and recovery

Errors use the shared envelope:

```json
{
  "error": {
    "code": "assessment_draft_conflict",
    "message": "Черновик уже изменён. Сохраните локальный ввод и обновите сессию.",
    "field": null
  }
}
```

| HTTP | Code | Meaning / recovery |
| --- | --- | --- |
| 401 | `guest_required` | Missing or expired authentication. |
| 404 | `not_found` | Unknown assessment or foreign owner. |
| 409 | `assessment_bank_incomplete` | At least one slot lacks an available task. |
| 503 | `assessment_profile_invalid` | Current profile does not have exactly 13 distinct slots. |
| 409 | `assessment_writer_conflict` | Wrong device or stale generation; reload and explicitly decide whether to take over. |
| 409 | `assessment_draft_conflict` | Stale draft revision; preserve local input and reconcile. |
| 409 | `assessment_not_active` | Drafts are closed, or finish was sent before activation. |
| 409 | `assessment_closed` | Activation/takeover is not allowed in the current state. |
| 409 | `assessment_snapshot_conflict` | A different final snapshot is already accepted. |
| 409 | `idempotency_conflict` / `idempotency_ambiguous` | Key/body reuse or conflicting historic keys after an owner merge. |
| 409 | `identity_changed` | Shared identity guard detected a different current principal. |
| 422 | `assessment_unknown_task` | An answer-map key is absent from the frozen tasks. |
| 422 | `invalid_active_seconds` | The configured active-time limit was exceeded. |
| 422 | `validation_error` / `invalid_idempotency_key` | Invalid fields, bounds, types or UUID. |

The shared middleware also enforces origin, media type and body-size limits;
content/database availability errors retain the shared 503 envelope. A 409 from
a handled assessment request does not imply the deadline transition rolled back:
GET may now show `awaiting_snapshot` even when the attempted write failed.

## Migration

`backend/migrations/versions/0003_assessments.py` has revision
`0003_assessments` and predecessor `0002_accounts`. It adds the `assessments`
table and owner/date and status/deadline indexes. Constraints enforce bounded
duration/revision/index/generation, mode-specific deadlines, final-only local
results, and consistent prepared/active/pending/released state. Full snapshots,
drafts, first-input metadata, writer state and distinct results live in this
table. Destructive downgrade raises `RuntimeError` before modifying data.

The historical Task 2 migration regression applied the actual `0001`–`0003`
files from an isolated version directory. It created completed practice history
and a prepared assessment through HTTP in a separate current-schema test database,
copied predecessor-schema fields using reflected tables, and compared all five
legacy tables across `0002 → 0003`. It then transferred the prepared assessment
row, preserving SQL NULL for unreleased JSON results. At that stage, restoration,
activation and finalization passed on `0003`, and the disabled downgrade preserved
the original practice/idempotency history and assessment result.

Later shared schema additions relevant to this fixture are:

- `0005_editor` supplies the `editor_catalog` lock used during preparation.
- `0006_practice_options` supplies `options_snapshot` on the current practice ORM,
  which is why the historical storage proof copies reflected predecessor fields.
- `0007_instance_exposures` supplies `seen_tasks.instance_key` for exposure and
  alias resolution during preparation, first-input capture and final grading.

The coordinator adaptation retains the reflected `0002 → 0003` data-preservation
and disabled-downgrade assertions, then upgrades that isolated database to the
current head before exercising the current HTTP lifecycle. The raw prepared row
and all reflected legacy rows must remain identical across that upgrade. GET is
compared in full with GET on the source database, and its tasks are also compared
with preparation: a prepare-only repeat notice is not a persisted state field.

## Executed verification — 5 November 2026

### Runtime/alias integration

The new `backend/tests/test_assessment_instances.py` uses the actual mounted app,
isolated content/database fixtures, the real account login/claim flow and injected
clock/commit-failure seams. It covers:

- Depletion of two slots and all 13 slots, one bounded generator call, normalized
  UUIDs, private reproducible provenance, source withdrawal and byte-identical
  replay; fresh static aliases, labelled repeats and atomic incomplete coverage.
- Alias help before/after first numeric input, online/deadline eligibility, prior
  practice answers, private pending-server reservations and snapshot-time cutoff.
- Merged-origin exposure ID/scope/time/flag preservation, legacy NULL-key-only
  backfill, immutable first-input context, unrelated-owner isolation, and separate
  late-local grading without a second released-evidence stream.
- Guest/account expiry after actual assessment ORM lock queries on all routes and
  on replay, catalog-lock expiry with rollback, accepted/failed draft commits,
  and actual server/local check counters.

Initial regression proof: **39 failed in 20.46s**, then **39 passed in 28.17s**.
After adding five owner/history regressions, the nearest combined gate reported
**185 passed, 3 failed in 121.69s**. Two failures were test assumptions that the
account root reused its first guest ID; the actual account flow creates a distinct
root. Correcting those owned fixtures produced **2 passed, 42 deselected in
1.59s**. The remaining historical migration conflict is reported below.

After both fixture corrections, the consolidated owned gate passed:
**44 passed in 34.77s**, exit code 0.

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -B -m pytest tests/test_assessment_instances.py -q --tb=short -p no:cacheprovider --basetemp "C:\Users\user\AppData\Local\Temp\opencode\assessment-final-$([guid]::NewGuid().ToString('N'))"
```

The earlier combined-gate and scoped-lint commands were:

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -B -m pytest tests/test_assessments.py tests/test_assessment_instances.py tests/test_runtime_integration.py tests/test_operation_integration.py tests/test_learning_instances.py tests/test_authorization_integration.py -q --tb=short -p no:cacheprovider --basetemp "C:\Users\user\AppData\Local\Temp\opencode\assessment-integration-gate-$([guid]::NewGuid().ToString('N'))"
D:\math_ege\backend\.venv\Scripts\python.exe -B -m ruff check --no-cache app/assessments tests/test_assessment_instances.py
```

Latest recorded scoped Ruff: **All checks passed** after correcting two test line
lengths. No Python code changed after that lint run. Every runtime-integration
command used the explicit backend virtual environment and a timeout of at least
300000 ms; pytest artifacts used fresh unique directories. The combined result
above is the observed pre-fixture-correction run. Final full-suite and exact-SHA
CI verification belong to the coordinator.

**Coordinator integration:** the migration assertion was reproduced failing on
the prepare-only notice, then adapted as described above without weakening
historical row, snapshot or disabled-downgrade checks. A fresh gate ran:

```powershell
.venv/Scripts/python.exe -m ruff check app/assessments tests/test_assessments.py tests/test_assessment_instances.py
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_assessments.py tests/test_assessment_instances.py tests/test_runtime_integration.py tests/test_operation_integration.py tests/test_learning_instances.py tests/test_authorization_integration.py -q --tb=short -p no:cacheprovider --basetemp "C:\Users\user\AppData\Local\Temp\opencode\assessment-integration-green-$([guid]::NewGuid().ToString('N'))"
```

**188 passed in 128.89s**, scoped Ruff exit 0. No shared caller interface is
pending: `locked_content`, `reauthorize`, `observe_save`, shared
clock-initialized health, `prior_numeric_ids`, instance helpers and bounded
generation are available and used directly. `build_result()`'s required health
argument is supplied by all three assessment callers.

### Earlier Task 2 / ASSESS-001 verification

The approved seams are public HTTP, an injected server clock, durable app
restarts, and concurrent requests through separate application/database engines.
Assessment fixtures mount their own router/service when the host has not yet
registered them. Account-scope fixtures bind the real account principal functions
through a test-only service contract, then exercise claims and takeover via HTTP.

Observed red–green regressions include newly linked origin exposure, the clock
crossing the deadline during finalization, the predecessor-schema migration
setup described above, and **ASSESS-001** (later same-owner exposure incorrectly
retaining independent final credit). The migration-only check at that earlier
stage passed: **1 passed in 1.31s**, before runtime/alias integration.

Commands below ran from `D:\math_ege\backend` with its explicit Python virtual
environment, on Windows/Python 3.13 and isolated SQLite databases:

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -m pytest tests/test_assessments.py -q -k "reference_after_first_numeric_draft or practice_help_after_first_numeric_draft or deadline_eligibility"
```

ASSESS-001 regression proof: **8 failed in 5.04s before the fix**, then **8 passed
in 4.57s**. Cases cover references from another assessment in both modes, practice
hints/full solutions before online or connection-lost completion, and exposure
before versus after deadline freezing. They assert original `first_answer`
values/times, canonical `released_evidence`, the private pending boundary, and
separate late-local results without rewriting frozen server eligibility.

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -m pytest tests/test_assessments.py -q
```

Result: **72 passed in 40.77s** with the integrated deadline worker, learning and
editor routes. Coverage includes complete-slot preparation,
frozen revisions, strict input, first/final answers, no pre-release leaks, exact
grading, pause/resume, writer/CAS races, idempotent conflicts, separate offline
results, restart-safe deadlines, deadline commits on rejected/replayed requests,
claimed origins, final exposure eligibility, canonical evidence, and
populated-database preservation.

Earlier post-integration runs recorded `UnsupportedFieldAttributeWarning` during
concurrent route-schema construction (**64 passed, 1 failed**) and worker health
`out_of_order_job_observation` during startup (**64 passed, 1 error**). Neither
appeared in that earlier full run. After catalog integration, the first full
ASSESS-001 run had **71 passed, 1 failed** because the historical migration fixture
lacked `editor_catalog`; transferring the real prepared snapshot resolved that
fixture incompatibility as described above.

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_checker.py tests/test_concurrency.py tests/test_content.py tests/test_security.py -q
```

Result: **423 passed in 35.20s**. These existing core suites were not edited by
this subsystem. The pre-implementation baseline was **423 passed in 22.52s**.

```powershell
D:\math_ege\backend\.venv\Scripts\python.exe -m ruff check app/assessments tests/test_assessments.py migrations/versions/0003_assessments.py
```

Result: **All checks passed**.

An earlier pre-integration OpenAPI smoke check generated the schema from an isolated app:
**6 assessment routes**, with a required `Idempotency-Key` on **all 4 POST
operations**.

This record is backend SQLite verification. Startup persistence is covered by
the restart regression; detailed worker scheduling/shutdown checks belong to
the coordinator-owned `backend/tests/test_background.py`. Current-head SQLite
migration preservation is included in the later 188-case gate. PostgreSQL lock
behavior and browser offline/reload flows require separate coordinator
integration verification. No PostgreSQL runtime or browser run is
claimed by this subsystem record.
