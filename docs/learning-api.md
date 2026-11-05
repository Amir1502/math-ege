# Learning backend — Task 3 integration contract

Implements FR-03, FR-06–09, FR-11 and FR-13 under the approved
`superpowers/plans/2026-11-05-completion.md`. This document describes the learning
backend's public contracts and the verified integration seams.

## Coordinator hooks

- Additive migration `0004_learning` now follows `0003_assessments` and creates
  `learning_evidence`, `learning_policy_states` and `learning_annotations`.
  Downgrade is disabled to preserve learning history. `0005_editor` can follow it.
- Import `app.learning.models` before test schema creation / Alembic metadata use.
- Set `app.state.learning = LearningExtrasService(app.state.service)` from
  `app.learning.service` and mount `app.learning.api.router` once. Its prefix is
  `/api/v1/learning`.
- The service consumes core `_guest_transaction(token, write=True)`,
  `owner_ids(db, guest)`, `_history(db, guest)`, `_idempotent(...)`, `content(db)`
  and `reauthorize(db, token)`. Account ownership and the canonical Guest write
  lock remain in the accounts resolver. Dashboard and plan load the effective
  catalog inside that owner transaction, using the shared catalog read lock,
  then reauthorize and sample the injected clock. Catalog, history, exclusions
  and ledger writes therefore share one transaction and publication epoch.
- Transaction-reusing progress hook:
  `extras.dashboard_for(db, guest, bundle, *, now=None, limit=50, offset=0,
  persist=False) -> Dashboard`. It neither opens a database transaction nor
  loads content. Core progress may use its canonical counts and stable-ID slot
  projections. `persist=True` requires the existing canonical owner write lock;
  the dashboard HTTP route uses this to save the evidence/version ledger.
- Mixed selection hook: `app.learning.selection.select_tasks(db, guest, bundle,
  request, now, salt) -> list[Task]`. It does not call `LearningService.content()`
  or issue tasks. **The caller must hold the canonical owner write lock**:
  `recent_exposure` may fill legacy NULL `SeenTask.instance_key` values from
  original-owner frozen snapshots. The caller supplies the already permitted
  content bundle, persists the selected snapshots and records issuance.
  Pass the normalized idempotency key as `salt`. The helper implements filters
  `slots`, `skill_ids`, `family_ids`, `difficulty`, `repeat_task_id`, and mixed
  quotas. `selection_details(...) -> Selection` also returns `quotas`, `counts`
  and `notice`; use it when preserving the shortage/reallocation explanation.
  Both tuples are ordered **weak / review / new**. An optional `policy=` argument
  on `selection_details` supports the same configured policy as the dashboard.
  It filters recent actual IDs and canonical condition keys, and enables
  instance-aware selection even with empty history. The coordinator calls it on
  the eligible static pool, generates only the remaining shortage, then calls it
  again on the combined static/generated pool. Generation exclusions include all
  eligible static candidates and every historical continuation snapshot.
  The caller validates explicit-repeat ownership. The core retains its existing
  balanced selection when requested.
  `until_stopped` and `target_minutes` are core session options, not learning
  migration fields. Core owns append-only extension and the options snapshot.
- For immediate review reset on a hint/solution (before any submitted answer),
  call `app.learning.evidence.record_help(db, guest, session, task_id, now,
  level=level)` in the existing authorized write transaction. `level=None` means
  a full solution. The event is idempotent per session/task/help level. This
  records policy evidence only; original attempts and summaries stay immutable.
- Editorial reads use `app.editor.repository.exclusions(db)` returning
  `{(task_id, revision): reason}`. An absent editorial module is supported during
  independent subsystem tests. A present module's runtime errors are not hidden.
  Notifications use the agreed `notices(db, guest_ids)` read adapter.
- Assessment reads use the final `AssessmentRecord` release gate
  `status == 'completed' and released_at is not None`, and **only**
  `server_result` whose `source == 'server'`. The ledger namespaces original IDs
  as `practice:{attempt_id}` and `assessment:{result_row_id}`; public history
  retains the original IDs. `local_result`, active drafts and awaiting-snapshot results are
  never learning evidence, journal entries, annotations or exported results.
  Frozen `tasks_snapshot` and `profile_snapshot` supply task/skill/slot identity.
- `Evidence.instance_id: str | None = None` carries the private
  `app.instances.instance_key(original_frozen_snapshot)`. The same optional field
  is appended to `TaskContext`; `Review.anchor_instance_id: str | None = None`
  retains the private anchor identity. Existing positional/default construction
  remains supported. Original task IDs, revisions, event IDs, owners and source
  flags are retained; HTTP task, review and export DTOs do not expose these keys.

### In-transaction examples

The following calls reuse the coordinator's authenticated transaction and its
already-loaded, permitted content bundle:

```python
from app.learning.evidence import record_help
from app.learning.selection import selection_details

dashboard = extras.dashboard_for(db, guest, bundle, now=now, persist=False)
# Map dashboard.slots by their stable slot_id; number is display metadata.

selection = selection_details(db, guest, bundle, request, now, salt, policy=extras.policy)
tasks, notice = list(selection.tasks), selection.notice
# The existing core mutation freezes tasks and records their issuance.

record_help(db, guest, session, task_id, now, level=level)
# Call after a successful hint/solution mutation, before that transaction commits.
```

`record_help` participates in caller rollback. Re-reading the same help level
keeps its original event timestamp. Viewing help creates review evidence
immediately; it does not invent a submitted answer or increment answer counters.

## HTTP contract

All requests use the existing HttpOnly guest/account cookie. Mutations use the
existing Origin / `X-Requested-With: math-ege` protection and a UUID
`Idempotency-Key`. No route accepts an owner ID from the client.

- `GET /dashboard` returns `algorithm_version`, `notice`, `slots`, `reviews`,
  `weak_skills`, `favourites`, `journal`, `assessment_history`, `notifications`,
  `recommendation` and explicit integer counts. Lists are bounded; response
  pagination metadata identifies truncation.
  Dashboard and learning export accept `limit=1..100` (default 50) and
  `offset=0..1000000` (default 0). The same page bounds apply to each list;
  `pagination.totals` gives each list's complete size. The 13-slot map is complete.
- A slot is `{slot_id, number, title, status, attempts, correct, covered_skills,
  total_skills, skills:[{id,title,attempts,correct}]}`. Status is one of
  `Нет данных`, `Изучаю`, `Закрепляю`, `Освоено`. Counts use globally deduplicated
  independent evidence; there is no exam-readiness percentage.
- A review is `{skill_id,family_id,slot_id,slot,due_at,interval_days,overdue}`;
  `slot` is the current display number or null for a retired stable position.
- A weak skill is `{id,title,slot,family_ids}`. A favourite is
  `{task:PublicTask,session_id}`. A journal item is
  `{id,task:PublicTask,session_id,attempt:Attempt|null,cause,manual,not_understood}`.
  Favourites and journal entries additionally carry `profile_id` and
  `profile_revision` from their original session, so renumbered positions remain
  interpretable. `task.slot` is the original number and `task.slot_id` is stable.
  Original task snapshots use the established `PublicTask` allowlist. Numeric
  legacy slots are resolved against their **frozen** profile.
- `GET /plan?minutes=10|20|30` returns
  `{minutes,length:5|10|20,estimated_seconds,slots,selection:'mixed',notice}`.
  Estimates use a personal median after five independent positive-duration
  answers; sparse history uses task estimates. A bank shortage is explicit.
- `POST /annotations` takes `{session_id,task_id,favourite?:bool,manual?:bool,
  not_understood?:bool,cause?:'theory'|'model'|'calculation'|'restriction'|'graph'|
  'format'|null}` and returns the saved annotation. Omitted fields are preserved;
  explicit false clears a flag and explicit null clears the cause. Omitted and
  explicit values are distinct idempotency payloads. Only an owned practice task
  or an owned **released** assessment task is eligible.
  Marking `not_understood=true` creates a review signal without disqualifying a
  subsequent first unassisted numeric answer. Clearing the flag preserves that
  historical signal. Repeating an already-true flag does not postpone its review.
- `GET /export` exports safe annotation and review DTOs with algorithm version
  and pagination. It does not export auth state or unreleased assessment values.

### Dashboard counts

All six counts cover the complete canonical owner's history, including claimed
guest origins, independently of list pagination. Editorially excluded events
are omitted from the visible counts and reported in `excluded_total`.

| Field | Meaning |
| --- | --- |
| `independent_total` | Visible independent evidence after canonical event-ID and instance-identity deduplication. |
| `independent_correct` | Correct evidence within `independent_total`. |
| `assisted_total` | Visible, non-skipped source attempts with `assisted=true`, including a first assisted answer. |
| `corrections_total` | Visible numeric answers after an earlier numeric answer on the same instance, across task aliases, practice/released assessments, sessions and claimed origins. |
| `skipped_total` | Distinct visible `(session_id, task_id)` pairs with a skipped attempt. |
| `excluded_total` | Canonical evidence events excluded by an editorial task/revision rule. |

A numeric answer has `normalized_answer is not None` and `skipped=false`.
Canonical event-ID deduplication precedes repeat counting. Help-only signals,
skips and assessment format errors do not consume the first numeric answer.
An earlier excluded numeric result still establishes repetition for a later
visible answer; metadata or revision changes do not reset that history. When no earlier
numeric answer exists, an answer after help or a skip is not a correction.
Assisted answers and corrections can overlap; these fields are not disjoint
categories.

`corrections_total` is derived from history rather than source `first_attempt`
flags. Original attempt/task IDs, `first_attempt`, `independent`, `assisted`,
answers and frozen results remain source facts. In particular, two pre-claim
independent answers can project as one independent achievement and one repeat
while both original HTTP attempts still say `independent=true`.

Achievement and numeric-repeat identity is **`Evidence.instance_id or
Evidence.task_id`**. The private key covers visible `statement`, `formula`,
`table`, `figure` and `rounding`, using the helper's structural normalization.
Renaming a task, changing its revision, seed, provenance, skills or answer does
not make an unchanged visible condition independent again. Historical keys come
from frozen practice/released-assessment snapshots, including help and
`not_understood` signals; current catalog edits do not replace that identity.
Pure legacy events without a key retain task-ID fallback.

Example annotation request (use IDs returned by an owned session):

```http
POST /api/v1/learning/annotations
Content-Type: application/json
Origin: http://localhost:5173
X-Requested-With: math-ege
Idempotency-Key: 93b3ef62-71a7-462d-aa14-2bcb2022c622

{"session_id":"3028a33e-1114-4383-bbbd-63fb7f99e8bd","task_id":"task-1","favourite":true,"cause":"calculation"}
```

`Origin` must match the deployment's configured allowed origin. The browser
supplies the existing HttpOnly cookie. A later body containing only
`session_id`, `task_id`, and `cause: null` clears the cause and preserves flags;
it uses a new idempotency key.

## Policy and verification seams

`Evidence` and `LearningPolicy` are immutable public pure-policy inputs.
`replay(...)` deterministically applies event-ID and global task-instance
deduplication. Editorial exclusions are applied without altering original
evidence. Review intervals are 1, 3, 7, 14, 30 days; only the first independent,
unassisted answer on another instance at/after the exact due time advances.
Early successes do not advance; an error/help resets; a 30-day success closes;
a later error reopens. Mastery thresholds and time/selection thresholds belong
to the stored algorithm version.

`learning-v1` requires 20 independent attempts, 8 correct among the last 10,
3 families, 2 UTC calendar days, successful coverage of every mandatory skill,
and an unassisted delayed check after at least 3 days. A delayed check can also
confirm an already-correct family without first requiring an error to open a
queue item. Scheduled early successes do not substitute for a due check.
A failed/helped delayed check records failed retention once the gap since the
last evidence for that skill/family reaches `retention_days`, even if an active
review's scheduled due date is still in the future. With the default policy,
the exact three-day boundary qualifies. In the regression fixture, a successful
day-4 check schedules day 11; a wrong/helped day-8 check demotes `Освоено` to
`Закрепляю` and resets the review to day 9. A day-8 success leaves both the review
and retention evidence unchanged. Repeating an exposed instance never earns
another independent achievement. Equal timestamps prioritize the original
independent answer over its corrections.

Other-instance checks compare `instance_id or task_id` to
`anchor_instance_id or anchor_task_id`; the actual `anchor_task_id` remains in
the exported review. A `not_understood` signal does not consume answer
independence, but an alias of its condition cannot satisfy the review's
other-instance requirement. A genuinely different condition under a reused task
ID can advance when the source event is independent and the due-time rule holds.

`LearningProjection.encountered_instance_ids: tuple[str, ...] = ()` is an
additive canonical encountered set populated by `replay`, including excluded
events and signals. Each member is `instance_id or task_id`.
`encountered_task_ids` continues to retain the actual historical task IDs.

Mixed quotas use largest-remainder rounding: lengths 5, 10, 20 produce
`(3,1,1)`, `(5,3,2)`, `(10,6,4)`. Candidate groups are disjoint. Due fresh
instances take precedence, new families have no independent attempt, and weak
skills are ranked by missing coverage, recent accuracy, then age of practice.
Shortages redistribute to weak, then new; remaining shortages are explicit.
Instance-aware selection deduplicates conditions before filling quotas, including
aliases spanning the static/generated pool or different candidate groups. Due
freshness uses the canonical encountered set, so an old or editorially excluded
alias does not become another review instance after the exposure window ends.

The pure seam is:

```python
mixed_candidates(
    bundle, request, projection, seen_at, now, salt, *, owner_id="", instance_aware=False,
) -> Selection
```

Keyed projections enable instance-aware behavior automatically. Explicit
`instance_aware=True` also enables it for empty or legacy history; database-backed
selection and plans always pass it. Unkeyed pure calls retain task-ID behavior.
In instance-aware mode `seen_at` accepts canonical keys and legacy actual IDs.
Explicit repeats continue to select the requested actual task ID after filters;
the owning core caller validates repeat ownership.

Issuance in any claimed origin excludes the instance for 30 days by default;
`instance_exclusion_days` supplies the configured window. Exposure exactly at the
cutoff is eligible, while anything newer is excluded. Plans use the same
owner-locked helper and condition deduplication, without recording new issuance.
An exhausted alias-only pool reports a shortage and zero selected-task seconds.
Plans use the median of the latest 30 positive-duration independent answers once at least five
exist; otherwise they use task estimates. Estimates are whole seconds.

The ledger stores answer-free source facts exactly once in their original
ownership namespace. Replay recomputes projections after a merge, an editorial
exclusion, or a policy update. Source answers, task/profile snapshots and frozen
summaries stay intact. Policy/version checks inspect **all owned policy states**,
including newly claimed origins when the account root already has the current
version. Any owned state with the current version but different thresholds
returns `503 policy_version_conflict`.

New ledger payloads include the private `instance_id`. An existing payload that
**lacks** that field is compared using a detached dictionary with only the
frozen-context identity added. The normalized dictionary is never assigned back
to the mapped JSON: old payload bytes/values, row metadata, event IDs and original
owners remain unchanged through dashboard, plan, export and restart reads.
An explicitly stored null or different key is not an absent field and produces
`503 evidence_conflict` when it disagrees with the frozen context. Every other
payload difference remains a conflict; no other field is normalized away by the
compatibility comparison. Auxiliary signals hydrate missing identity in memory
under the same rule.

Prior origin versions produce a durable explanation on the root. Existing
explanations for the current version are retained, and only previously
unexplained versions are appended. Versions already covered by a grouped
explanation remain covered after updating the root's version; repeated reads and
application restarts return the same notice. The original origin states are
preserved. `dashboard_for(..., persist=False)` computes the notice without
writing; `persist=True` saves it under the caller's canonical owner write lock.

The integration keeps the existing public signatures and DTOs: `replay(...)`,
`slot_progress(...)`, `LearningExtrasService.dashboard_for(...)`, and the HTTP
routes above. Its counting helper is private:
`LearningExtrasService._corrections_total(history: History, visible: set[str]) -> int`.

Tests use the agreed pure-policy, public HTTP, injected server clock and isolated
restart seams. Test apps attach the router only if it is not already mounted.
Commands run from `D:\math_ege\backend` with `.venv\Scripts\python.exe`.

## Runtime visible-alias verification — 5 November 2026

The continuation changes `backend/app/learning/{policy,evidence,selection,service}.py`,
adds `backend/tests/test_learning_instances.py`, and updates this document. The
50 instance tests exercise:

- Practice/practice and practice/released-assessment aliases across linked
  origins, canonical achievement and numeric repeats, editorial exclusion,
  source IDs/flags/results, and application restarts.
- Help and `not_understood` review anchors, delayed retention on another
  condition, reused actual task IDs, and private-key omission from public DTOs.
- Legacy ledger payloads for all four evidence sources: raw SQLite JSON and row
  metadata stay identical after hydration, catalog edits, reads and restarts.
  Fifteen non-identity payload-conflict cases and eight explicit-null/different-key
  cases retain `503 evidence_conflict` rather than rewriting the ledger.
- Explicit and automatically inferred pure instance-aware selection, duplicate
  condition shortages, canonical due freshness including excluded evidence,
  exact 30-day exposure boundaries, and actual-ID explicit repeats.
- Owner-locked linked-origin exposure filtering and NULL-key backfill, distinct
  condition quotas and editorial exclusions after a merge, outsider isolation,
  and alias-exhausted plans without new issuance.
- Dashboard/plan catalog reads in one owner write transaction, with valid and
  expiring guest/account credentials. The real SQLAlchemy query boundary advances
  the injected clock after the catalog read. Expired requests return 401 and
  leave the ledger/policy state unchanged; valid requests use post-read time.

### Recorded red–green paths

| Slice | Observed RED | Focused GREEN |
| --- | --- | --- |
| Linked practice/assessment aliases and numeric counters | 2 failed | 8 passed, 11 deselected in 6.35s, including prior numeric regressions. |
| Alias review anchors and other-condition retention | 4 failed | 30 passed, 36 deselected in 4.30s, including nearest review/mastery tests. |
| Legacy identity hydration and immutable ledger comparison | 8 failed, 19 passed, 6 deselected | 31 passed, 45 deselected in 21.83s, including migration, assessment, export and merge neighbors. |
| Selection, owner-scoped exposure and coherent catalog reads | 14 failed, 33 deselected | 23 passed, 74 deselected in 7.16s, including legacy pure selection and actual static/runtime mixed issuance. |
| Automatic instance awareness for keyed/excluded pure evidence | 2 failed, 47 deselected | Both pass in the final 50-case focused gate below. |

### Historical worker focused and nearest results

All commands used the existing backend virtual environment, a timeout of
300000 ms, disabled pytest/Ruff caches, and fresh unique pytest directories.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -p no:cacheprovider `
  tests/test_learning_instances.py -q --tb=short `
  --basetemp (Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' ('learning-instances-final-' + [guid]::NewGuid().ToString('N')))

.\.venv\Scripts\python.exe -B -X utf8 -m pytest -p no:cacheprovider `
  tests/test_learning_regressions.py tests/test_learning.py `
  tests/test_learning_integration.py tests/test_runtime_integration.py -q --tb=short `
  --basetemp (Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' ('learning-instances-nearest-final-' + [guid]::NewGuid().ToString('N')))

.\.venv\Scripts\python.exe -B -X utf8 -m ruff check --no-cache `
  app/learning tests/test_learning_instances.py tests/test_learning_regressions.py `
  tests/test_learning.py tests/test_learning_integration.py tests/test_runtime_integration.py `
  migrations/versions/0004_learning.py
```

- **Focused: 50 passed in 29.78s**, exit code 0.
- **Nearest: 72 passed, 1 failed in 34.97s**, exit code 1. All 17 delivered
  three-defect regressions, all six learning integration cases and all seven
  runtime integration cases passed.
- **Ruff: all checks passed**, exit code 0.

At that worker handoff the remaining nearest failure was
`tests/test_learning.py::test_mixed_selection_hook_uses_merged_http_history_and_editorial_exclusions`.
Its `selection_bank` fixture clones one visible condition across 36 task IDs.
After that condition is exposed, canonical selection correctly returns
`counts == (0, 0, 0)`; the older assertion expects `(5, 3, 2)`. This coordinator-owned
fixture needs distinct visible conditions. The owned regression
`test_mixed_quotas_and_editorial_exclusions_use_distinct_conditions_after_owner_merge`
verifies the same HTTP-history/selection boundary with distinct conditions and
passes its exact `(5, 3, 2)` quotas, exclusion, frozen-source and outsider checks.
The unfiltered worker gate therefore reported the fixture failure above.

The coordinator subsequently repaired `selection_bank` with distinct valid
triangle conditions, preserving the exact quotas and surrounding assertions.
The [five-file learning gate](runtime-issuance.md#owned-history-caller-and-canonical-learning-integration)
recorded **123 passed in 66.84 s**, with Ruff exit 0; the fixture failure is no
longer an active handoff. The historical 50-pass and 72-pass/1-fail results above
are retained, not summed with this gate or the whole-backend protocol.

## Confirmed-defect verification — 5 November 2026

This section records the delivered three-defect patch before runtime alias
integration; its earlier 66-case gate is historical, not the later coordinator result.

The approved seams are `replay`/`slot_progress` for retention, and public HTTP
dashboard/history reads for repeat counts and policy notices. The new
`backend/tests/test_learning_regressions.py` imports existing learning and
assessment fixtures/helpers. Its 17 cases include exact-gap controls, source
immutability, idempotency replay, account claims, format errors, editorial
exclusions, repeated reads and SQLite application restarts.

### Recorded red–green paths

Each RED run preceded its corresponding production fix. Paths below are relative
to `backend`; selectors refer to `tests/test_learning_regressions.py`.

| Slice | Regression selectors | Observed RED | Focused GREEN with nearest tests |
| --- | --- | --- | --- |
| Retention | `test_failed_retention_demotes_at_required_gap_before_scheduled_due` plus `test_early_success_after_required_gap_does_not_advance_review_or_retention` | 4 failed, 3 passed: exact-gap/day-8 wrong and helped checks incorrectly stayed mastered. | 22 passed, 28 deselected in 0.53s. |
| Numeric repeats | `test_cross_session_numeric_repeat_is_counted_and_source_flags_stay_frozen`; `test_merged_origins_count_numeric_repeat_once_without_rewriting_source_flags`; `test_first_assisted_numeric_answer_is_not_a_repeat_and_skips_stay_separate` | 3 failed, 1 passed, 7 deselected: cross-session/merged repeats were missing, and skip-then-first-numeric was mislabeled. | 14 passed, 40 deselected in 10.14s. |
| Claimed policy states | `test_current_root_explains_newly_claimed_old_policy_and_keeps_notice_after_restart` (both parameters); `test_current_root_rejects_newly_claimed_same_version_with_different_thresholds` | 3 failed, 11 deselected: no new-origin explanation and no same-version conflict. | 7 passed, 50 deselected in 7.97s. |
| Grouped-notice stability | `test_policy_upgrade_notice_is_stable_when_root_and_claimed_origin_had_different_versions` | 1 failed in 0.90s: a second read appended a redundant explanation. | 8 passed, 52 deselected in 7.24s, including the notice/merge neighbors. |

The numeric boundary guards
`test_assessment_format_error_does_not_consume_first_numeric_answer` and
`test_excluded_earlier_numeric_revision_still_makes_later_numeric_answer_a_repeat`
passed together: **2 passed, 14 deselected in 1.02s**.

The focused GREEN runs used `tests/test_learning_regressions.py` and
`tests/test_learning.py` with these exact `-k` selections respectively:

```text
retention or mastery or review or delayed_recheck or early_success
numeric or repeat or merged_origins or dashboard_projects or assessment_learning or editorial_exclusion or equal_clock
current_root or algorithm_version or first_account_projection or merged_origins
current_root or algorithm_version or first_account_projection or merged_origins or policy_upgrade_notice
```

### Final scoped gate

Executed from `D:\math_ege\backend` through the existing virtual environment;
each pytest run used a fresh isolated `--basetemp` and disabled the pytest cache.

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -p no:cacheprovider `
  tests/test_learning_regressions.py tests/test_learning.py `
  tests/test_learning_integration.py -q `
  --basetemp (Join-Path 'C:\Users\user\AppData\Local\Temp\opencode' ('learning-scoped-final-' + [guid]::NewGuid().ToString('N')))

.\.venv\Scripts\python.exe -B -X utf8 -m ruff check --no-cache `
  app/learning tests/test_learning_regressions.py tests/test_learning.py `
  tests/test_learning_integration.py migrations/versions/0004_learning.py
```

**66 passed in 26.85s**: 17 new regression cases, 43 existing learning cases and
6 existing core-integration cases. Ruff: **all checks passed**.

### Earlier handoff verification record

The following records the earlier handoff, rather than the confirmed-defect
patch's scoped gate above:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_learning.py tests/test_operations.py::test_populated_initial_migration_preserves_ids_history_and_frozen_snapshots -q
```

**44 passed, 1 skipped in 20.68s.** This includes 43 learning cases plus the
coordinator's populated initial-migration SQLite check. The live PostgreSQL
recovery variant is skipped unless `OPS_RUN_POSTGRES_VERIFY=1` is configured.

```powershell
.venv\Scripts\python.exe -m ruff check app/learning migrations/versions/0004_learning.py tests/test_learning.py
.venv\Scripts\python.exe -m alembic history
```

Ruff: **all checks passed**. At that handoff, Alembic history resolved the chain
`0001_learning_core → 0002_accounts → 0003_assessments → 0004_learning →
0005_editor → 0006_practice_options`.

That earlier verification covered:

- Review boundaries/reset/closure/reopening and all mastery gates, including
  demotion, duplicate instances and delayed checks of error-free history.
- Real account login/claim: globally deduplicated achievement, original attempts
  and summaries, original idempotency replay, stale-credential rejection and
  cross-owner isolation.
- Real assessment prepare/activate/draft/deadline/finish: no learning exposure
  before release, only canonical server rows afterward, local results excluded,
  annotation gating and restart stability.
- Durable annotations, optional-field semantics, user-selected causes, bounded
  exports, median plans, original profile context after renumbering, editorial
  notices and policy-version notices.
- Public mixed-selection and help/progress hooks over real authenticated
  transactions; help rollback and retry behavior.
- `0004_learning` against populated predecessor tables, schema/model agreement,
  downgrade refusal, preservation through the full chain, and learning HTTP
  reads/writes against the migrated database without test schema creation.

## Integration status and assessment limits

The six current core-integration tests verify mounted learning routes, immediate
help evidence, editorial exclusions in progress, stable-slot mapping, mixed
selection and released canonical assessment evidence. Standalone learning
fixtures attach missing services/routers only when needed.

- Learning uses the finalized `app.instances.instance_key` and owner-locked
  `recent_exposure` contracts. The helper worker owns `app/instances.py`,
  `app/issuance.py`, nullable `SeenTask.instance_key` and migration `0007`.
- The coordinator owns source privacy/full-history export and configured-policy
  hook integration. Learning's focused gates cover the documented adapter seams.
- The current gate uses isolated SQLite and server-clock/restart seams. Live
  PostgreSQL recovery, frontend flows and full runtime/course readiness are outside
  its evidence. The seven runtime integration cases cover their fixture-backed
  endpoint flows; the earlier migration command above is historical verification.
- These are automated behavioral checks of the documented policy. No human
  methodological review or exam-readiness validation is claimed.
