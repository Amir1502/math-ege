# Runtime issuance and structural instance identity

This is the delegated Task 5 helper layer from the approved
[completion plan](superpowers/plans/2026-11-05-completion.md). Runtime generation
fills a shortage after the caller exhausts its eligible static pool. A structural
condition signature links aliases to the original exposure records. The caller
freezes the returned tasks in its existing transaction and idempotency record.

## Implementation and ownership

The helper and practice/core/assessment callers are integrated. Learning evidence
uses optional `instance_id` with backward-compatible immutable-ledger comparison.
The approved follow-up adds the public historical-repeat helper in
`backend/app/issuance.py`, direct regressions in
`backend/tests/test_runtime_issuance.py` and owned-history endpoint regressions in
`backend/tests/test_historical_repeat_integration.py`.

Original Task 5 artifacts: `backend/app/instances.py`, `backend/app/issuance.py`,
`backend/tests/test_runtime_issuance.py`, this document,
`backend/migrations/versions/0007_instance_exposures.py`, and the `SeenTask`
section of `backend/app/models.py`. Practice, assessments, evidence, editor,
registry and API integration belong to their respective workers.

## Identity and exposure contracts

```python
instance_key(snapshot: Task | dict) -> str
recent_exposure(db, owners, tasks, now, *, days=30, exclude=(), exclude_tasks=()) -> Exposure
aliases_for_task(db, owners, snapshot, *, tasks=()) -> TaskAliases
mark_instances(db, owner_id, tasks, now) -> tuple[SeenTask, ...]
```

`Exposure` has `ids` and `keys` frozensets; `TaskAliases` has `ids` and `records`.
Both are unpackable. IDs always mean actual original task IDs, not invented
canonical task IDs. `owners` must come from the authenticated principal's
`owner_ids(db, guest)` under the canonical owner lock.
`TaskAliases.ids` includes the supplied snapshot's ID and matching historical
IDs even when no `SeenTask` row exists yet; `records` contains only existing
original-owner rows. Use the IDs for attempt/result joins and the records for
assistance/reference flags.

The lowercase SHA-256 key covers **only** `statement`, `formula`, `table`,
`figure` and `rounding`. Optional visible fields and figure defaults are
canonicalized; string whitespace is collapsed. JSON numeric negative zero and
integral floats normalize to integers. List order and all other text stay
significant: this is not algebraic equivalence or numeric rewriting inside text.
Identity, revision, seed, title, topic, skills, difficulty, answer, provenance
and profile metadata are excluded. Task IDs and generation provenance continue
to identify the original snapshot.

Normalization precedes visible-shape validation, including integer-valued
rounding fields in legacy JSON; strict new-output validation still runs before
issuance. Historical hashing is independent of the current TeX/rendering
allowlist because it never renders or executes the original text.

Legacy NULL keys are resolved from that owner's immutable practice and assessment
snapshots first, using the earliest stored snapshot deterministically. Current
bundle tasks are a fallback only when the origin has no stored snapshot. Only
the NULL key is filled: IDs, owners, flags and timestamps are retained. Every
historical condition for a reused ID remains available to alias resolution;
existing non-NULL keys are not overwritten by a later editorial revision.

`recent_exposure` includes exposures newer than `now - 30 days`, plus explicit
exclusions regardless of age. `exclude_tasks` accepts the caller's selected
static tasks and entire continued-session snapshot, including tasks absent from
the current bundle. A legacy per-ID timestamp cannot distinguish revision-level
exposure times; all known conditions of a recently seen reused ID are excluded
conservatively. Unresolvable legacy IDs remain excluded by ID with NULL keys.

`mark_instances` writes in the supplied original session/assessment owner scope.
It preserves assistance/reference flags and first-seen time, advances last-seen
time monotonically, and never moves a merged origin's row to the root owner.
The helpers participate in the caller's transaction; they do not commit.
Persist the selected private snapshots before marking them. Subsequent alias
resolution needs those immutable snapshots to retain every condition associated
with a reused task ID, even though its single exposure row retains its first key.

## Candidate contract

```python
generate_candidates(
    learning, db, guest, request, key, bundle, *,
    exclude=frozenset(), exclude_tasks=(), limit=None, slot_limits=None,
    now=None, max_attempts=256, max_per_template=64,
) -> tuple[list[Task], str | None]
```

`request` is a validated `CreateSessionRequest`; `limit` is the remaining count
(0..20, default `request.length`). `slot_limits={slot: missing_count}` lets an
assessment request one task for each missing slot in **one bounded call**.
The helper returns additional tasks only. An unfilled positive limit has an
explicit shortage notice; `limit=0` returns `([], None)`. Unlisted slots in an
explicit `slot_limits` mapping have zero capacity. `repeat_task_id` produces no
candidates through `generate_candidates`. Explicit repeats use current static
selection first, then the public historical-repeat helper below for owned
runtime snapshots whose IDs are absent from the effective bundle.

Seeds use the first four bytes of SHA-256 over an unambiguous JSON tuple of
algorithm version, authenticated root owner ID, normalized request key, registered
template ID and zero-based ordinal. All 32 bits are retained. Template scheduling
and candidate order are deterministic. Bounds may be lowered, never raised above
256 seed attempts total or 64 per template. A fresh result is subject to current
exposure/catalog state; durable request replay belongs to core idempotency.

The only executable generator entry point is the explicit
`app.generators.generate(template_id, seed, profile)` allowlist. The current
registry emits version `1`, revision `1` and IDs `course-{family}-{seed}`.
Static-only families cannot become runtime sources. Strict revalidation checks
bounded safe JSON, finite exact string answers, complete task shape and
profile/slot/skill/family/version/seed binding. Task conditions, help, solutions
and generation metadata are copied into detached returned snapshots.
Each generator invocation receives a separate deep copy of the profile; it
cannot mutate the expected profile used to validate its output.

Demo generation requires both `allow_demo_content` and a matching generated
task in the **effective bundle**. An old legacy bank without generation metadata
does not activate the runtime registry. A reviewed-looking task is not proof of
a published template.

Reviewed issuance requires an active, nonwithdrawn `EditorPublication` of kind
`template` pointing to the matching published `EditorRevision`: independent
author/reviewer, formula and constraint review, current payload/profile/version
binding, successful 1000-seed evidence and ten distinct approved samples from
that reviewer. The original generator returns demo data; only this verified
publication can supply the template's editorial review attribution. An issued
sample is not claimed to have received an individual human review.
The gate validates the recorded manifest and independently approved snapshots;
it does not rerun the editorial 1000-seed check inside runtime's attempt budget.

A withdrawn template blocks its generator even in demo mode. Invalid controlled
templates fail closed. Task publication IDs, tombstones, correction exclusions,
known conditions of those editorial records, recent exposures, explicit IDs and
explicit snapshot exclusions are applied before acceptance. A generated base ID
cannot bypass an edited published task. Skill/family/slot filters use the same
intersection/equality rules as practice; difficulty is checked on the output.
Every existing bundle ID and its known visible conditions remain in the static
selection domain and are excluded from generation. A malformed evidence manifest
cannot authorize its template. If editorial or owner-history exclusions cannot
be resolved safely, the whole runtime fallback returns a shortage and records a
redacted failure rather than selecting with incomplete exclusions.

Every attempted output records `learning.operation_health.record_event(
"generator", success=...)`. Invalid gate/output failures are counted and logged
with a fixed, redacted aggregate message, without exception text, answers, seeds,
request keys, owner IDs or content payloads. Cancellation signals derived from
`BaseException` (such as `KeyboardInterrupt` and
`SystemExit`) propagate. Database and authorization failures also propagate to
the caller.

## Explicit historical-repeat contract

```python
historical_repeat_candidate(
    learning, db, snapshot: Snapshot, bundle: ContentBundle, *,
    now: datetime | None = None,
) -> Task | None
```

Import this public function from `app.issuance`. The coordinator must hold the
canonical owner and editor catalog locks and verify ownership of the **original
frozen snapshot** before calling it. The helper has no owner argument and does
not perform that authorization. Core idempotent response replay precedes it.

- Any ID present in `bundle.tasks` returns `None`, including an edited current
  task that static selection rejects. Core owns current static-ID selection.
- The snapshot must bind to a registered runtime family, generator version `1`,
  task revision `1`, its original uint32 seed and `course-{family}-{seed}` ID,
  and the current profile ID, slot and registered skills. Unknown, stale or
  invalid binding returns `None` before generation.
- Current `_sources` publication/demo gates authorize reconstruction. Historical
  `review_status` and source metadata never grant authority or activate a family.
  Demo-disabled production requires an active, independently reviewed template;
  withdrawals still block demo fallback. Recorded sample checks make no generator
  calls during authorization.
- Task publication/tombstone IDs and correction exclusions block repeats. Their
  known condition keys come from editorial revision payloads/base snapshots and
  matching tasks in the current bundle. Corrected/withdrawn aliases are blocked
  too. Invalid exclusion data returns `None`.
- At most **one** registry call reconstructs the original seed with a detached
  current profile. Every validated task field except `source` and `review_status`
  must exactly equal the frozen task, including visible condition, answer,
  rounding, hints, solution, ID and generation provenance. A structural-key match
  alone is insufficient: even whitespace-only statement drift fails exact replay.
- A returned task is detached and retains the actual original generated ID and
  seed/version. Only a currently verified template supplies reviewed attribution;
  an independently permitted demo source returns truthful demo attribution.
  Historical snapshots are never rewritten.
- The helper performs reads under `db.no_autoflush`: it does not write, commit,
  backfill keys, mark exposures or flush pending caller changes. The caller owns
  persistence of the new repeat session and exposure marking.
- Policy/binding/exclusion denials produce **zero generator events**. A real
  reconstruction attempt produces one success event, or one failure event and
  the fixed redacted log `Historical repeat reconstruction failed.` if generation,
  validation or exact comparison fails. Content failure returns `None`; database
  errors and process cancellation propagate.

Explicit repetition intentionally permits an already-seen condition. Core must
apply its alias-aware prior-attempt/help rules, and the evidence worker's optional
`instance_id` must prevent a repeat from becoming new independent evidence. This
helper does not infer independence or inspect/modify owner exposure history.

## Coordinator hooks

1. Enter `Database.transaction(write=True)`, resolve and lock the authenticated
   canonical owner, and perform core `_idempotent` replay/body-conflict lookup.
   Inside its new-action callback, lock the editor catalog and load one coherent
   effective bundle. Hold those locks through selection, snapshot persistence,
   `mark_instances` and commit. Provide `LearningService.operation_health`.
2. Deduplicate the static selection using `instance_key` and `recent_exposure`,
   then call `generate_candidates` once for remaining capacity. Pass selected
   static snapshots via `exclude_tasks`. For continuation, also pass **every**
    previous batch snapshot, not just the currently visible batch. Mixed planning
    owns its bucket quotas; assessment preparation owns its one-per-slot rule.
   For an explicit repeat ID absent from the current bundle, resolve its owned
   immutable snapshot and call
   `historical_repeat_candidate(learning, db, snapshot, bundle, now=now)`.
   `None` means the historical repeat is unavailable; preserve the original ID
   when persisting a returned task. Core imports the public helper rather than
   `_sources` or another private gate.
3. Persist each returned `Task.model_dump(mode="json")` with its original
   generation seed/version and task values. Call `mark_instances` with the
   session/assessment's original `guest_id`, which may differ from the root after
   a merge. Core replay must return the previously frozen response before any
   new generation, including after source withdrawal or a course update.
4. For practice first-attempt/help and final assessment eligibility, use
   `aliases_for_task(db, owners, snapshot, tasks=bundle.tasks)`. Join attempts and
   canonical assessment result rows by **actual alias IDs and owner scope**.
   Aggregate assistance/reference flags over `records`; write flags in their
   original scopes. Pending frozen assessment results reserve aliases too;
   released results alone feed learning projections.
5. The evidence worker handles **optional `instance_id`** carrying
   `instance_key(original_snapshot)`. Deduplicate merged-origin achievement and
   other-instance review transitions by that key, retaining task ID/revision,
   original event identity and provenance. Derive keys during legacy replay;
   do not rewrite frozen attempts, results or prior evidence payloads just to
   add the field. The evidence worker owns backward-compatible ledger comparison.

## Security design and assumptions

Data flow: authenticated request -> locked owner/catalog -> static pool and
registered generation -> strict validation/exposure filtering -> caller's frozen
snapshot and SeenTask rows -> existing explicit public DTO.

Trust boundaries are caller authorization, stored editorial assertions, generator
outputs, original-owner history and public serialization. Controls follow Aegis
laws 3 (owner scope), 4 (fail closed), 9 (bounds), and 10 (redaction).

| STRIDE | Control and owner |
| --- | --- |
| Spoofing | Core resolves the principal and expands only its server-known origins. |
| Tampering | Issuance validates publication pointers/evidence and revalidates detached output; original snapshots remain authoritative. |
| Repudiation | Core persists the immutable response and original generation provenance; instances preserve original record IDs and timestamps. |
| Information disclosure | Issuance logs counters only; API owners serialize with public DTOs and assessment release gates. |
| Denial of service | Issuance limits generation attempts and payload shape; endpoint owners retain request/rate limits. |
| Elevation of privilege | Reviewed-looking payloads do not authorize generation; only locked active template publications do. |

Abuse cases covered by direct tests: a requester tries to obtain production
content through a demo source; an alias seed tries to gain a second independent
instance after an owner merge; a withdrawn/edited task tries to reappear through
the registered base generator. Their controls belong to issuance source gates,
instance resolution, and editorial exclusions respectively.

The registry is trusted server code, not uploaded executable content. Its
version changes must also change the issuance version contract. Automated shape
and reproducibility evidence is not an independent mathematical oracle; the
registry's independent tests and recorded editorial review remain distinct.

## Verification boundary

Direct helper tests use copies of the explicit legacy files at `backend/content`
and synthetic minimal generated banks; they do not rely on the default bundle
path, which the coordinator has switched to the expanded course. Migration checks
run only on new populated test databases. No existing database or verification
artifact is deleted.

The direct tests below assess helper contracts separately from endpoint
integration. Synthetic editorial review fixtures are test data, not real human
reviews of the course. Whole-project and exact-SHA CI results are recorded in
[`verification.md`](verification.md), not inferred from these focused runs.

### Initial helper gate verified on 2026-11-05

Executed from `D:\math_ege\backend` using the existing virtual environment:

```powershell
.venv/Scripts/python.exe -B -m pytest tests/test_runtime_issuance.py -q --tb=short -p no:cacheprovider --basetemp "C:\Users\user\AppData\Local\Temp\opencode\runtime-issuance-check-$([guid]::NewGuid().ToString('N'))"
.venv/Scripts/python.exe -B -m ruff check --no-cache app/instances.py app/issuance.py tests/test_runtime_issuance.py migrations/versions/0007_instance_exposures.py app/models.py
```

- Direct helper suite: **76 passed in 45.60s**, exit code 0. Includes a populated
  `0006` -> `0007` migration, immutable snapshot preservation, original-scope
  backfill, publication/withdrawal gates, malformed evidence/exclusions, bounded
  generation, filters, alias shortages and the core-idempotency adapter contract.
- Scoped Ruff: **All checks passed**, exit code 0.
- Each pytest invocation used a fresh unique artifact directory; prior artifacts
  and databases were retained. Changes are uncommitted; no commits or pushes.

An earlier real multi-template fixture failed before entering issuance because
the registry/editor safe-content validator rejected `displacement-length`'s
`\overrightarrow` formula. This was reported during the task. The final
multi-template tests in that initial gate used synthetic banks as required.

### Historical-repeat follow-up verified on 2026-11-05

The focused repeat gate passed **43 tests** with the original 76 deselected.
After the helper and focused regressions were added, the final combined gate ran
once with a **300000 ms** command timeout:

```powershell
.venv/Scripts/python.exe -B -m pytest tests/test_runtime_issuance.py -q --tb=short -p no:cacheprovider --basetemp "C:\Users\user\AppData\Local\Temp\opencode\runtime-issuance-repeat-final-$([guid]::NewGuid().ToString('N'))"
.venv/Scripts/python.exe -B -m ruff check --no-cache app/issuance.py tests/test_runtime_issuance.py
```

- Combined direct suite: **119 passed in 58.79s** (76 existing + 43 new), exit 0.
- Scoped Ruff: **All checks passed**, exit 0.
- New proof covers caller-owned frozen `Task`/dict reconstruction, exact visible
  and grading/help fields, original uint32 identity, current review attribution,
  demo/production gates, stale bindings, withdrawals, correction aliases, current
  static-ID deferral, one-attempt health accounting, and no database writes or
  autoflush of pending caller changes.

The follow-up edits only issuance, its direct test file and this document.

### Owned-history caller and canonical learning integration

`backend/app/practice.py:_owned_repeat_snapshot` now searches only the resolved
owner's immutable practice snapshots or completed, released assessments whose
canonical result is marked `source=server`. Pending, foreign and local-only
assessment results cannot authorize reconstruction. The caller applies current
slot/skill/family/difficulty and editorial exclusion gates before invoking the
public helper, preserving actual IDs, seeds, versions and frozen old history.

After three endpoint 404 failures were reproduced and this caller was connected,
the focused/nearby historical-repeat gate recorded **43 passed**, exit 0.
Canonical learning integration then exposed an obsolete synthetic selection
fixture: its many IDs shared one visible condition. The fixture now provides
distinct, correctly answered triangle conditions; quota and alias-exclusion
assertions remain unchanged.

Fresh coordinator learning gate:

```powershell
.venv/Scripts/python.exe -m ruff check tests/test_learning.py
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_learning.py tests/test_learning_instances.py tests/test_learning_regressions.py tests/test_learning_integration.py tests/test_runtime_integration.py -q --tb=short
```

**123 passed in 66.84s**, with scoped Ruff exit 0. Original task/attempt IDs,
owner namespaces and snapshots are retained; missing additive `instance_id` is
normalized only in detached comparison memory. Neither this run nor runtime
issuance supplies the independent human methodological review required by the ТЗ.
