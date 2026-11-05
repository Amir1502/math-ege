# Learning client implementation and integration

**Status — 5 November 2026:** The approved plan, review, and progress flows for
FR-08, FR-09, FR-11, and FR-13 are implemented. Scoped code checks and browser
verification are recorded below, including identity transitions, released
results, editorial exclusions, dashboard failure/retry, and loaded mobile plans.

**Architecture:** `frontend/src/extras/` owns the HTTP/DTO boundary,
identity-scoped in-memory resources, annotation mutations, view models, and
learning-specific components. The three existing pages consume these public
interfaces and the existing worksheet components/tokens.

**Tech stack:** React 19, TypeScript, existing CSS tokens, Vitest, and Chromium
through Playwright CLI for browser evidence.

**Spec:** `technical-spec.md` sections 5.5, 5.6, 5.8, and 7;
`docs/superpowers/specs/2026-11-05-completion-design.md`; `DESIGN.md`.

## Implementation sequence

- [x] Validate and allowlist learning DTOs; verify optional annotation fields,
  private request gating, and rejection of explicitly unreleased results.
- [x] Implement identity-scoped resources, synchronous invalidation, stale-response
  rejection, and annotation retries with an identical UUID and body.
- [x] Extend the plan with 10/20/30-minute choices, continuation, due reviews,
  weak skills, and mixed-practice links.
- [x] Implement Errors/Repeat/Favourites tabs, original released task details,
  explicitly selected causes, and exact-family analogues.
- [x] Extend progress with server mastery statuses, mandatory-skill evidence,
  released assessment history, notices, dynamic counters, and history links.
- [x] Reconcile this client handoff with `docs/learning-api.md` and the integrated
  coordinator code; complete scoped code and browser checks.

## Ownership

Only `frontend/src/extras/**`, `frontend/src/pages/{plan,review,progress}.tsx`,
`frontend/src/styles/extras.css`, `frontend/tests/extras.test.ts`, and this
document are owned by this worker. Shared routing, identity, practice start,
storage, common DTOs, full-history export, and backend integration belong to the
coordinator. Disposable verification scripts, downloads, and screenshots are in
the temporary harness directory listed below.

## Routes and integrated coordinator seams

The page entry points are `#/`, `#/review`, and `#/progress`. Each page imports
`../styles/extras.css`. All navigation retains the application's hash router.

- Mixed plan links use
  `#/practice?slots=1%2C2&length=5&minutes=10&selection=mixed`. The integrated
  `learning/practice-options.ts` consumes `slots`, `length`, `minutes`,
  `selection`, `families`, and `skills`; the shared start flow preserves them.
- Exact analogues use `#/practice?slots=N&families=<encoded-family-id>`. Current
  numbers are resolved by stable `slot_id`, or by an unambiguous skill match for
  legacy tasks. Retired/ambiguous positions have no analogue/theory link.
- Explicit timed start in `extras/planned-start.ts` creates a guest when needed,
  loads the server plan, and delegates to shared `startSession`. The request is
  `{mode:'practice', slots, length, selection:'mixed', target_minutes}`. Existing
  owner-scoped pending starts retain their original body and retry semantics.
- Assessment setup uses `#/assessment`; a saved or released record uses
  `#/assessment/<encoded-id>`. Local continuation checks the assessment
  repository's owner/device scope and retains only the ID. Its action is
  “Открыть вариант”, since the assessment page confirms the current state.
- Review state is `#/review?tab=errors|repeat|favourites&slot=N&offset=N`.
  Progress pagination uses `#/progress?offset=N`. Query offsets are bounded to
  `0..1000000`; filter counts explicitly describe the current page.
- `identity.subscribe` and `math-ege:identity-change` are connected to the extras
  store. The shared identity readiness/error state participates in access gating.
- The current production `create_app(settings)` mounts the learning endpoints.
  Browser runs use that factory directly. Mixed starts, exact-family selection,
  assessment links, and the shared full-history parser are integrated.
- The five primary navigation items remain intact. The coordinator's compact
  mobile “Повтор” label retains the accessible name “Повторение”; all five labels
  fit on one line at the tested widths.

## HTTP boundary

`extras/api.ts` reuses the common `request` transport and copies only allowlisted
fields into extras DTOs. It retains no raw responses. The transport supplies the
same-origin cookie, `cache: 'no-store'`, owner binding, mutation headers, and UUID
idempotency keys. `docs/learning-api.md` defines the server policy and contracts.

| Endpoint | Client contract |
| --- | --- |
| `GET /api/v1/learning/dashboard?offset=N&limit=N` | Canonical counters, `algorithm_version`, `notice`, complete stable-position/mandatory-skill detail, reviews, weak skills, favourites, journal, released assessment summaries, notifications, and per-collection pagination totals. Default page size is 50; accepted sizes are 1–100. |
| `GET /api/v1/learning/plan?minutes=10\|20\|30` | Matching `minutes`, server-selected `length: 5\|10\|20`, `estimated_seconds`, current `slots`, `selection:'mixed'`, and shortage/estimate `notice`. Minutes are never converted into a hard-coded task count. |
| `POST /api/v1/learning/annotations` | Identifiers plus only the changed `favourite`, `manual`, `not_understood`, or `cause` fields. The complete saved response is validated, including matching task/session IDs and all four values. |
| `GET /api/v1/learning/export?offset=N&limit=100` | Independent annotation index. Every page is joined by `(session_id, task_id)`; journal/favourite pagination cannot turn an unknown saved flag into false. Only annotation DTOs are retained by this adapter. |
| `GET /api/v1/progress` | Canonical fallback counters, algorithm/exclusion metadata, active practice/assessment IDs, and allowlisted recent practice summaries with frozen profile metadata. Legacy answer-bearing `mistakes`, full tasks, drafts, and help are discarded. |
| `GET /api/v1/export` | Explicit full-history download through shared `boundApi(owner).export()` and its strict parser. This document is downloaded rather than cached in extras. |

Malformed counts, impossible correct/attempt or coverage totals, duplicate
stable positions, invalid plans, and explicitly unreleased result records fail
the boundary. Public task snapshots preserve safe figures, rounding instructions,
and original task/profile revisions. Unknown grading/drawing fields are dropped.

The backend authorizes answer/solution release. Journal answer fields are read
only from the authorized dashboard contract; assessment summaries require a
release timestamp and a valid 0–13 score. The adapter also rejects explicit
unreleased/incomplete state markers. A favourite without its journal entry on
the current page says that its explanation is **not loaded**; it does not claim
the result is unpublished.

### Annotation semantics and retry

- Causes are chosen by the user: `theory`, `model`, `calculation`, `restriction`,
  `graph`, or `format`; `null` clears a cause. No cause is inferred from an answer.
- Omitted fields remain omitted. Explicit `false` clears a flag; explicit `null`
  clears a cause. The saved server response reconciles all displayed values.
- `AnnotationWriter` serializes one task's writes. Retryable failures retain the
  same UUID and frozen request body; controls wait for confirmation before a
  different change. Permanent failures clear the pending request and expose the
  server error.
- Annotation export pagination rejects duplicates, inconsistent totals,
  incomplete/non-advancing pages, and offsets outside the server range. Identity
  or generation changes stop pagination and discard its partial result.

## Private resource lifetime

`confirmedLearningOwner` returns an owner only when identity is ready, is not
changing, and has no confirmation error. An unconfirmed cached owner grants no
access to private learning resources. A visitor without an identity makes no
journal, annotation-index, dashboard, progress, or plan request before explicit
practice start.

`ScopedResource` tracks owner, readiness, loading, errors, and a generation.
Identity changes synchronously clear dashboard pages, practice progress, all
three plan caches, annotations, and pending writers. Generation checks reject
late responses even across A → B → A. Readiness prevents an empty/error state
from automatically retrying on every render; retry remains explicit.

Extras caches are in memory. Local practice/assessment continuation reads the
coordinator's scoped repository and retains only a checked pointer. Shared
session/draft storage remains responsible for its own persistence.

A history download requires a confirmed owner at click time and completion.
Losing confirmation permanently invalidates that pending download, including a
failed identity refresh followed by recovery to the same owner. A fresh explicit
download after recovery works normally.

## Page behaviour

- **Plan — FR-11:** 10/20/30-minute choices, server estimates and shortage
  notices, practice/assessment continuation, the existing 13-position map,
  currently due reviews, weak skills, and mixed-practice configuration. Time is
  an estimate; the copy explains that the current task will not be interrupted.
- **Review — FR-08/09:** Errors, Repeat, and Favourites tabs with labelled
  filters and page controls. Tabs support arrow keys, Home/End, roving focus,
  and associated panels. Original conditions, submitted/released answers,
  explanations, manual/not-understood flags, causes, and frozen profiles remain
  available. Exact-family links request another instance. Due dates and
  1/3/7/14/30-day intervals come from the server; early practice is distinguished
  from delayed review. Missing a day does not erase results.
- **Progress — FR-11/13:** Server statuses “Нет данных”, “Изучаю”, “Закрепляю”,
  and “Освоено”; mandatory-skill coverage and independent evidence; assistance,
  repeat, and skip counters; frozen practice history; and released diagnostic/
  exam scores with active time, elapsed time, and original profiles. The only
  percentage is the rounded correct/independent-answer ratio, with no percentage
  when its denominator is zero. It is not an exam-readiness score.

Dashboard counters take precedence. If the dashboard fails, canonical
`/progress` retains counters, `algorithm_version`, `notice`, `excluded_total`,
practice profiles/history links, and export. Complete mandatory-skill detail and
released assessment rows render after the dashboard is available; numeric
fallback slots are not used to reconstruct missing skill data. Editorial
exclusions change the evidence projection while original answers and frozen
session/assessment results remain available in history.

## Verification

### Scoped code gate

Executed from `D:\math_ege\frontend` after the final owned styling/typography edit:

```powershell
npm exec -- vitest run tests/extras.test.ts
npm exec -- eslint src/extras src/pages/plan.tsx src/pages/review.tsx src/pages/progress.tsx tests/extras.test.ts --max-warnings 0
npm exec -- tsc -p tsconfig.app.json --noEmit
```

Results: **29 tests passed**, ESLint **zero warnings/errors**, application
TypeScript check **passed**. Tests cover the DTO boundary, release markers,
canonical fallback metadata/frozen profiles, exact request bodies, annotation
pagination, identity readiness, stale completions, retry UUIDs, stable-slot
mapping, and evidence-based view models. The canonical-progress boundary defect
and failed-confirmation pending-export defect were reproduced before their fixes.

Individual design checks also passed: `check.mjs` **0 errors/0 warnings across
20 scoped files**; `wig.mjs` **20 files**; `ru.mjs` **14 files**; and
`contrast.mjs` **13 colour pairs**. These scripts are under
`C:\Users\user\.config\opencode\skills\viora-design-skills\scripts`.

The aggregate `verify.mjs` invocation is not a passing gate: `--help` triggered a
whole-frontend scan, encountered generated `playwright-report/index.html`, and
had no screenshot URL. The passing visual evidence is the individual scoped
checks and inspected browser captures below.

### Browser flows

The isolated harness serves production `create_app(settings)` at
`http://127.0.0.1:8013` and Vite at `http://127.0.0.1:5183`, using its own SQLite
fixture with demonstration content. Playwright CLI scripts exercise real HTTP
and browser storage, with route interception for delayed responses/failures.

| Flow | Observed result |
| --- | --- |
| Anonymous/startup identity | No private learning requests before confirmation or explicit start. Failed confirmation clears private data; retry restores the confirmed owner. |
| Real guest A → B → A | Every resource cache clears synchronously. Delayed dashboard, annotation-index, and annotation-write responses are rejected. |
| Pending downloads | Owner changes, same-owner transitions, and failed confirmation followed by recovery block stale downloads. A fresh explicit export succeeds. |
| Timed practice | Real 10/20/30-minute starts requested lengths **5/10/10**, respectively, matching the server plan, with matching `target_minutes` and `selection:'mixed'`. These are fixture observations, not a fixed mapping. |
| Review/analogue | A different task from the exact `right-triangle-area` family was issued. Released answer `999`, expected `120`, calculation cause, favourite/manual/not-understood flags, persistence, same-UUID/body retry, and keyboard tab navigation were verified. |
| Assessment history | Real diagnostic and exam flows supported continuation and release gating. Both released summaries retained **0/13**, **3 active seconds**, **4 elapsed seconds**, and original profile `ege-math-2027-draft`, year `2027`, revision `2026-11-05.1`. |
| Active assessment export | The owner's draft was preserved in the full-history export while results/grading fields were withheld. Learning dashboard/export and visible evidence remained empty (**0/0**). |
| Editorial exclusions | Two notices excluded **3 evidence records**; visible independent counters changed **0/3 → 0/1**. **24 skips**, **27 journal entries**, **4 practice sessions**, and **2 released assessments** remained. Original annotated practice time remained **219 seconds**. |
| Dashboard 503/retry | Canonical **0/1**, **24 skips**, the exclusion notice/count, four frozen practice profiles/history links, and JSON download stayed available. Retry restored 13-position skill coverage, two assessment rows, and both detailed notices. |
| Export comparison | Whole practice snapshots, whole assessment snapshots, and saved annotations match before/after exclusions. Two correction records were added. The fallback export equals the post-exclusion export except for `exported_at`. |

Correction-link comparison follows the actual export contract: `attempt_ids`
contains practice attempts; assessment corrections identify the released
assessment through `assessment_ids` plus task ID/revision. The comparison script
was corrected to use those separate references.

### Responsive evidence and fixture recovery

Nine page/width measurements covered Plan, Review, and Progress at requested
**1440, 390, and 320px**: no horizontal overflow, split tab/action words, or
undersized visible controls. At requested 320px Chromium reported `innerWidth`
321 and document content width 305; the measurement records that rounding rather
than relabelling the requested viewport. Control checks allow a `1/64px`
tolerance for Chromium's 44px layout rounding and exclude hidden elements.

Focused assessment-history and next-step captures include complete headings and
content. Their capture-only style hides fixed navigation/skip-link overlays and
adds padding around the full section. Normal page captures retain the shell.

The reused create-all SQLite fixture initially lacked the newly integrated
`0007_instance_exposures` column/index, causing the plan request to return
`503 database_unavailable`. It has no `alembic_version` table. A backup was taken,
then only nullable `seen_tasks.instance_key` and
`ix_seen_tasks_guest_instance(guest_id, instance_key)` were added to that fixture.
Before/after comparison preserved **138 original rows across 25 tables**;
integrity checking returned **ok** with **zero foreign-key violations**.

The visible plan retry then loaded **5 tasks, estimated 11 min 40 s**. The three
plan captures were replaced with loaded-state assertions and no unexpected
alerts. Additional full-worksheet crops at all three widths show the complete
heading, estimate, shortage notice, and start/configuration actions; each was
visually inspected. The temporary repair is fixture recovery, not a production
migration test.

### Artifact index and reproduction

Harness root:
`C:\Users\user\AppData\Local\Temp\opencode\learning-client-check-20261105`.
Paths below are relative to that directory; `{1440,390,320}` denotes three files.

| Artifacts | Evidence |
| --- | --- |
| `output/playwright/{plan,review,progress}-confirmed-{1440,390,320}.png` | Final page captures and five-item navigation. |
| `output/playwright/plan-worksheet-confirmed-{1440,390,320}.png` | Complete loaded plan, estimate, and actions. |
| `output/playwright/plan-next-confirmed-{1440,390,320}.png` | Complete next-step sections. |
| `output/playwright/assessment-history-confirmed-{1440,390,320}.png` | Complete released assessment history with scores/times/profiles. |
| `output/playwright/identity-{unconfirmed,B-empty,A-restored}.png` | Identity gating and owner isolation. |
| `output/playwright/progress-exclusions-1440.png`, `output/playwright/exclusion-notices.png` | Revised evidence and original-history explanation. |
| `output/playwright/progress-fallback-{1440,390,320}.png` | Dashboard-failure fallback. |
| `output/playwright/history-{before-exclusion,after-exclusion,fallback,unreleased}.json` | Full-history downloads used in release and preservation checks. |
| `output/playwright/exclusion-comparison.json` | Passing before/after/fallback comparison. |
| `output/playwright/fixture-schema-repair.json` | Additive repair, backup path, table fingerprints, and integrity results. |
| `output/playwright/plan-responsive-check.log`, `output/playwright/loaded-plan-captures.log` | Final loaded-plan assertions and capture measurements. |

Browser scripts include `identity-check.cjs`, `review-check.cjs`,
`plan-check.cjs`, `assessment-check.cjs`, `history-release-check.cjs`,
`export-identity-check.cjs`, `export-transition-check.cjs`,
`exclusion-check.cjs`, `fallback-check.cjs`, `responsive-check.cjs`, and
`loaded-plan-captures.cjs`. Run a selected script from the harness root:

```powershell
npm exec --yes --package=@playwright/cli -- playwright-cli -s=learning-client run-code --filename=responsive-check.cjs
node compare-history.cjs
```

`responsive-check.cjs` currently selects only the repaired Plan page; the earlier
Review/Progress checks and captures were already complete. Stateful flow scripts
create history or replace downloads: in particular,
`export-transition-check.cjs` writes the pre-exclusion baseline. Preserve that
baseline when comparing the existing exclusion fixture.
