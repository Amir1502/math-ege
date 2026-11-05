# Application Completion Implementation Plan

> **For agentic workers:** Execute the independently testable tasks below with a fresh worker per owned subsystem and coordinator review before integration. The named superpowers execution skills are not installed; use the available general subagents and the same test/review gates. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved remaining software while preserving existing guest history and distinguishing software evidence from independent release acceptance.

**Architecture:** Extend the modular monolith with additive account, assessment, learning and editorial tables. Preserve original practice snapshots and namespace idempotency. Use strict public DTOs, a shared owner lock and separate immutable assessment results.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/SQLite, React, TypeScript, Vite, IndexedDB, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-05-completion-design.md`, `technical-spec.md`.

## Global Constraints

- `Числа передаются строками и сравниваются точно через десятичную или рациональную арифметику.`
- `Старые попытки сохраняют исходный профиль и версии задач.`
- `Автор не должен быть единственным проверяющим собственной задачи.`
- `Секреты не хранятся в репозитории и не попадают в логи.`
- `Максимальная длина исходного поля — 64 символа.`
- Original data and verification databases must not be deleted. Only additive migrations, new temporary test databases and normal pushes are allowed.
- Python runs through `backend/.venv/Scripts/python.exe`; no global dependency installation.
- Public task fields remain an explicit allowlist. Assessment results cannot leak through history, export or practice routes.
- Only the coordinator changes shared `app/services.py`, `app/main.py`, `app/schemas.py`, `app/content.py`, frontend routing and existing storage.
- Migration order: `0002_accounts` → `0003_assessments` → `0004_learning` → `0005_editor`, following `0001_learning_core`.

---

## Task 1: Account ownership and authenticated sessions

**Files:** create `backend/app/accounts/{models,schemas,service,api,principals,mail}.py`, `backend/migrations/versions/0002_accounts.py`, `backend/tests/test_accounts.py`; coordinator integrates `backend/app/services.py` and `backend/app/main.py`.

**Interfaces:** `resolve_guest(db, token, now, write=False) -> Guest`, `owner_ids(db, guest) -> list[str]`, `root_owner_id(db, guest_id) -> str`; `AccountService(learning_service)`; `router` mounted under `/api/v1/auth` and `/api/v1/account`. Original practice events are linked, not copied. Staff authorization is `require_staff(request, publish=False)` and verifies recent MFA on the server.

- [ ] Write account tests exercising the actual app and injectable mail delivery. Prove generic email response, five requests/hour, 15-minute single-use link, browser binding, logout/revocation, repeated linking, competing claims and no extra attempt IDs.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_accounts.py -q` and observe missing-feature failures before implementation.
- [ ] Implement account tables, strict DTOs, hashed random secrets, generic mail requests and role/MFA gates. A claim changes ownership relations, never historic primary keys or answers.

```python
assert before_attempt_ids == after_attempt_ids
assert client.get(f"/api/v1/sessions/{foreign_session_id}").status_code == 404
assert client.post("/api/v1/auth/complete", json=consumed_link).status_code == 400
```

- [ ] Integrate resolver and owner scope into all practice queries. Preserve idempotency records in their original scope; lookup matching operation/body across owned origins, reject a reused key with an unrelated body.
- [ ] Run account, concurrency, security and existing API suites, then commit only this task's files and integration.

## Task 2: Prepared assessments, writer ownership and frozen results

**Files:** create `backend/app/assessments/{models,schemas,service,api}.py`, `backend/migrations/versions/0003_assessments.py`, `backend/tests/test_assessments.py`, `frontend/src/assessments/`, `frontend/src/pages/assessment.tsx`, `frontend/e2e/assessment.spec.ts`.

**Interfaces:** `AssessmentService(learning_service)` with `prepare`, `activate`, `get`, `draft`, `takeover`, `finish`, `reconcile_deadlines`. Routes live under `/api/v1/assessments`, separate from practice. Prepare request: `{mode: 'diagnostic'|'exam', duration_minutes: 15..180, device_id: UUID}`; activation confirms persisted conditions. Views contain public `tasks`, `server_now`, nullable `deadline_at`, revision, writer generation, drafts and nullable released results. All writer mutations include device and generation; draft includes expected revision. Finish supplies a bounded immutable answer map and request UUID.

- [ ] Add tests for 13 distinct slots, no deadline before activation, no answers before release, no practice-route access, format errors, owner isolation, writer takeover and exact request replay.
- [ ] Run the assessment tests and record the failing cases before adding the service.
- [ ] Add additive models/migration; grade with `parse_answer(raw, "exam")`, never practice fractions. Persist server/local snapshots separately and expose neither before final snapshot acceptance.

```python
assert prepared["deadline_at"] is None
assert active["server_result"] is None
clock[0] += timedelta(minutes=66)
service.reconcile_deadlines()
assert pending["status"] == "awaiting_snapshot"
assert finished["server_result"]["score"] <= 13
```

- [ ] Register a lifespan-owned periodic deadline reconciliation worker; cancellation finishes before database disposal. Test restart and concurrent finish/deadline requests.
- [ ] Implement local preparation/activation, synchronous draft journal, revision queue, immutable offline finish, countdown from server deadline and read-only second device. Check keyboard access, loading, failure and pending-result states.
- [ ] Run API, frontend unit and browser offline/reload tests; commit the subsystem.

## Task 3: Versioned evidence, reviews and practice planning

**Files:** create `backend/app/learning/{models,schemas,evidence,policy,service,api}.py`, `backend/migrations/versions/0004_learning.py`, `backend/tests/test_learning.py`; extend practice selection, progress and review/plan pages.

**Interfaces:** `LearningPolicy` contains immutable versioned thresholds; `LearningExtrasService(learning_service)` provides dashboard, plan, review queue, annotations and favourites. Evidence adapters read practice attempts and released canonical assessment results. Return skill/family IDs and original profile context, not numeric-slot joins alone.

- [ ] Test pure time rules before database projection: due/early/other-instance/wrong/help/reset/close/reopen and all mastery thresholds/demotion.

```python
assert REVIEW_INTERVALS == (1, 3, 7, 14, 30)
assert early_success.next_due == previous.next_due
assert assisted.next_due == now + timedelta(days=1)
assert repeated_instance.independent is False
```

- [ ] Implement deterministic replay and one active review per owner/skill/family. Deduplicate evidence by original event and instance, preserve source history and exclude withdrawn erroneous revisions with a visible reason.
- [ ] Implement non-overlapping weak/review/new quotas (5/3/2 for ten), explicit shortages, filters, same-family analogues, timed plans, continued practice and user-selected error causes.
- [ ] Connect the five existing navigation sections without adding a sixth main item. Test no implicit advancement from immediate analogues or theory views.
- [ ] Run policy/API/browser regression suites and commit.

## Task 4: Editorial workflow and data-only publication

**Files:** create `backend/app/editor/{models,schemas,repository,service,api}.py`, `backend/migrations/versions/0005_editor.py`, `backend/tests/test_editor.py`, `frontend/src/pages/editor.tsx`; coordinator updates content schema/repository hooks.

**Interfaces:** `published_content(database, settings) -> ContentBundle`; service receives `LearningService`; routes use `accounts.require_staff`. Revision kinds: task, lesson, profile, template. Workflow: draft → review → ready → published → archived. Author/reviewer are authenticated distinct IDs; only administrator publishes.

- [ ] Write tests rejecting self-review, methodist publication, no MFA, executable/unknown payloads, malformed batches, changed-body replay and revision conflicts.

```python
assert self_review.status_code == 403
assert malformed_import.status_code == 422
assert count_revisions_after == count_revisions_before
assert withdrawn_id not in newly_issued_ids
assert old_session_snapshot == snapshot_before_correction
```

- [ ] Validate the full bounded import before writes; use a savepoint for atomic failures with persisted replay. Publish only a referentially valid current package. Preserve withdrawn base IDs as tombstones, not fallback to the demo version.
- [ ] Add search, filters, mobile preview, JSON import/export, reviewer attribution, revision audit and explicit result-exclusion notices.
- [ ] Test stable slot/skill mapping after profile renumbering and revision-aware lesson cache keys. Run security and source-hygiene checks, then commit.

## Task 5: Expanded authored draft course and supported generators

**Files:** create `backend/app/generators/`, `backend/content/course/`, `backend/tests/test_generators.py`, `backend/tests/test_course.py`; preserve the original 65-task package as a regression fixture. Add safe figure DTO/rendering and multiple lessons/prerequisites.

**Interfaces:** each content shard exports deterministic `build_tasks(profile)`, `build_lessons(profile)` and exactly two supported template IDs per slot. `generate(template_id, seed)` returns the task, version and seed from one mathematical model. Returned task shape extends existing `Task` only with agreed optional generation/figure/stable-slot metadata.

- [ ] Write independent arithmetic/schema/coverage tests, including domain boundaries and finite decimal output, before enabling the expanded package.

```python
assert len(tasks) >= 650
assert all(count >= 50 for count in per_slot.values())
assert all(count >= 5 for count in families_per_slot.values())
assert len(supported_templates) >= 26
assert all(task.source.reviewed_by is None for task in draft_tasks)
```

- [ ] Author materially distinct families, theory, worked examples, three-level hints and at least three independent tasks per taught type. Do not inflate diversity by counting numeric changes.
- [ ] Commit the static candidate bank and generator sources; run at least 1000 distinct seeds/template and an independently calculated oracle. Keep external human review status unset and export a review worksheet.
- [ ] Check all profile skills against genuine content and list any uncovered requirement rather than fabricating coverage.

## Task 6: Operational proof and delivery

**Files:** extend `.github/workflows/ci.yml`, `compose.yaml`, `infra/`, `scripts/`, `docs/verification.md`, `docs/acceptance-status.md`, `README.md` and deployment/admin documentation.

- [ ] Add isolated populated-database migration and restore tests. Restore only into a newly created verification database, never overwrite an existing one.
- [ ] Add scheduled backup configuration, bounded retention instructions, health/worker diagnostics and a reproducible 500-user/30-RPS ten-minute load scenario. Do not run destructive retention against user data.
- [ ] Run pytest/Ruff/pip check, lint/unit/build, browser scenarios, dependency and source checks, and Linux PostgreSQL/Compose tests. Record actual measurements; do not infer acceptance from scripts being present.
- [ ] Reconcile every FR/NFR/AC with code and evidence. Keep independent review, real-device, legal and unavailable production-environment gates explicit.
- [ ] Commit verified changes, push normally to the private repository, watch the exact commit's CI and confirm remote HEAD and clean worktree.
