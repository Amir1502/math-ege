# Browser integration: worksheet annotations and navigation

**Evidence date:** 5 November 2026.

**Outcome:** TSX test discovery and the duplicate worksheet sibling keys are
corrected. The original scoped annotation/navigation observations are retained
below; a later coordinator regression verifies the key fix during timer updates,
task switching and reload. Authenticated staff/MFA access and physical devices
were not exercised by this worksheet check.

## Ownership and test discovery

This worker changed only:

- `frontend/vitest.config.ts`: discover `tests/**/*.test.{ts,tsx}` and reuse the
  installed `@vitejs/plugin-react` plugin for JSX. The independent test config
  does not import Vite's PWA or development-server configuration.
- `frontend/tests/worksheet-annotations.test.tsx`: render actual JSX and add four
  regressions covering lost owner verification, failed refresh with cached marks,
  task/session isolation and restoration, and the cause-selector boundary.
- `docs/browser-integration.md`: this evidence and coordinator handoff.

No application, page, style, backend, dependency, or other worker's test file was
edited by this worker. Browser artifacts are generated, ignored files under
`output/playwright/`. Changes are uncommitted.

### Previously executed commands, not repeated on continuation

Working directory: `D:\math_ege\frontend`.

| Command | Actual recorded result |
| --- | --- |
| `npm exec -- vitest run tests/worksheet-annotations.test.tsx` before the config fix | Exit 1, `No test files found`; the reported include was `tests/**/*.test.ts`. |
| `npm exec -- vitest run tests/worksheet-annotations.test.tsx tests/extras.test.ts` after the fix | Exit 0; **2 files, 38 tests passed**: 9 worksheet tests and 29 extras tests. |
| `npm exec -- eslint vitest.config.ts tests/worksheet-annotations.test.tsx tests/extras.test.ts --max-warnings 0` | Exit 0. |
| `npm exec -- tsc -b` | Latest recorded run exited 0. An earlier unrelated account-export type error was resolved by concurrent coordinator work, not by this worker. |

The worksheet unit tests use static React rendering and mocked hooks. They prove
the rendering boundaries and TSX transform, not mounted mutation or network
behaviour; the browser checks below supply that separate evidence. Per the
coordinator's continuation instruction, completed tests were not rerun. The
coordinator separately reported a pre-restart full frontend gate of 252 tests in
14 files plus lint/build; that is not a new run or independent result from this
worker.

## Isolated verification runtime

- Backend: `http://127.0.0.1:8000`; Vite: `http://127.0.0.1:5173`.
- Fresh, initially zero-byte, worker-owned SQLite database:
  `C:\Users\user\AppData\Local\Temp\opencode\browser-integration-6ffe07ff-66c1-4983-b836-ade601c8049e\browser-6ffe07ff-66c1-4983-b836-ade601c8049e.sqlite3`.
- `DATABASE_URL` pointed only to that database. Additive Alembic upgrade ran from
  `0001_learning_core` through `0008_account_deletion_completion`;
  `alembic current` reported `0008_account_deletion_completion (head)`.
  No fulfillment, downgrade, reset, or preserved checkpoint-database operation
  was performed.
- Settings: `APP_ENV=test`, `ALLOW_DEMO_CONTENT=true`, `COOKIE_SECURE=false`,
  `ACCOUNTS_ENABLED=false`, `ACCOUNTS_POLICY_APPROVED=false`. `AUTH_MODE` was unset;
  no unsupported test-auth shortcut or fabricated staff identity was used.
- Allowed origins:
  `http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000`.
- Browser: Playwright CLI **0.1.23**, named session `sol-browser-6ffe07ff`, isolated
  context, real headless Chrome (`browserName=chromium`, channel `chrome`). Desktop
  viewport was 1440 × 900 CSS px. Mobile checks resized that desktop browser;
  they did not emulate a physical device.
- Configuration, probe scripts, PID files, and backend/Vite logs are in the same
  approved temporary directory as the database. The CLI config is
  `cli.config.json`; artifacts are in
  `output/playwright/browser-integration-6ffe07ff/`.

Executable/argument forms used for migration and startup, completed earlier:

```powershell
# Working directory: D:\math_ege\backend; isolated DATABASE_URL already set
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Working directory: D:\math_ege\frontend
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
```

On continuation, listener ownership was checked rather than inferred from the
cancelled pre-restart servers. `Get-NetTCPConnection` showed listener PIDs 17672
and 21844. `Get-CimInstance Win32_Process` confirmed the verification command
lines, with Python launcher PID 23876 parenting listener 17672.

## Browser commands and evidence

Working directory: `D:\math_ege`. All probes were invoked through this exact CLI
prefix, with `run-code --filename=` followed by the absolute probe path in the
temporary directory above. No ad-hoc `@playwright/test` suite was created.

```powershell
npx --yes --package @playwright/cli playwright-cli -s=sol-browser-6ffe07ff run-code --filename=C:\Users\user\AppData\Local\Temp\opencode\browser-integration-6ffe07ff-66c1-4983-b836-ade601c8049e\verify-editor-guest.js
npx --yes --package @playwright/cli playwright-cli -s=sol-browser-6ffe07ff snapshot --filename=output/playwright/browser-integration-6ffe07ff/editor-guest-denied.yml
```

| Probe actually run | Purpose |
| --- | --- |
| `measure-nav.js` | Loaded plan at 320/360/390; caption line counts, names, dimensions, screenshots, desktop brand. |
| `start-annotation-gate.js` | Hold and then continue the real annotation-export request during worksheet mount. |
| `inspect-key-collision.js` | Count accumulated forms/IDs, reload, and immediately pause; capture the defect. |
| `save-flags.js` | Click/check the three annotation flags and inspect real save responses. |
| `submit-wrong-and-cause.js` | Submit the actual answer form, then explicitly select and save `model`. |
| `reload-and-switch.js` | Reload and switch task 1 → task 2 → task 1. |
| `failure-and-offline.js` | Controlled failed export read, browser offline mode, and online retry. |
| `verify-main-destinations.js` | Click all five main links and assert destination, heading, title, and active navigation. |
| `verify-editor-guest.js` | Real editor access failure/retry, keyboard recovery links, account popups, and denial-page mobile widths. |

Multiline inline CLI code initially failed with `SyntaxError: Unexpected token ')'`;
file-based `run-code --filename=` was used for the completed probes. The
last two probes and the final snapshots were completed on continuation; earlier
successful annotation and plan/mobile probes were not repeated.

### Mounted worksheet annotation results

Verified session:
`#/session/532c8638-496e-4d7a-b7d3-4772546d393e`.
Task 1: `linear-function-two-points-c`, «Дробный угловой коэффициент».
Task 2: «От длин к площади».

| State/action | Actual network and DOM observation |
| --- | --- |
| Mount with export GET held | «Загружаем ваши отметки…» was visible; **0 annotation fieldsets**. The request was delayed and then continued to the real server, not replaced with an empty fixture. |
| Initial successful export read | `GET /api/v1/learning/export?offset=0&limit=100` returned 200 with 0 annotations. Only then were false flags exposed. Cause selector count was 0 before an incorrect answer. |
| Save favourite | UI action produced `POST /api/v1/learning/annotations` 200 and displayed `aria-pressed="true"`. |
| Save manual journal mark | Separate real POST returned 200 and the labelled checkbox became checked. |
| Save not-understood mark | Separate real POST returned 200 and the labelled checkbox became checked. All three flags were true; no cause selector yet. |
| Submit incorrect answer | Draft `9999999999999999` was submitted through the actual answer form. Attempts POST returned 200, `correct=false`, and a first-attempt result. This used the first scoped answer form because of the duplicate-form defect below. |
| Select cause | Explicitly selecting «Неверно построил модель» saved `cause=model` with POST 200. The server response and UI retained all three true flags. No cause was inferred automatically. |
| Reload | Export GET returned 200 with 1 saved record; all three true flags and `model` were restored. Exactly 1 annotation fieldset was observed. |
| Switch to task 2 | Export GET returned 200; flags were false, cause selector absent, and 1 annotation fieldset present. Task 1's marks did not leak. |
| Return to task 1 | Export GET returned 200; all three flags and `model` were restored, with 1 annotation fieldset. |
| Failed saved-values read | A Playwright route deliberately fulfilled only the export GET with HTTP 503, code `verification_unavailable`. The visible failure exposed **0 fieldsets, 0 checkboxes, 0 cause selectors**. The answer draft remained `9999999999999999`. This was controlled failure injection, not a spontaneous backend outage. |
| Browser offline and retry | `page.context().setOffline(true)` produced the offline banner. Retry showed «Нет связи с сервером. Проверьте соединение и повторите запрос.» with **0 fieldsets, 0 checkboxes, 0 cause selectors** and the same draft. |
| Return online and retry | Real export GET returned 200 with 1 record; all three flags and `model` returned. The offline setting and route override were removed. |

These are scoped annotation successes. They do not establish that the surrounding
answer form or complete worksheet is correct or accessible.

### Main navigation, mobile captions, and brand

The real main-link clicks reached these unchanged destinations and headings.
Each destination also had its matching `aria-current="page"` link and document
title `<navigation label> | ЕГЭ Профиль 2027`.

| Main accessible name | Hash destination | Visible H1 |
| --- | --- | --- |
| План | `#/` | План занятий |
| Темы | `#/topics` | Темы первой части |
| Практика | `#/practice` | Практика |
| Повторение | `#/review` | Повторение |
| Прогресс | `#/progress` | Прогресс |

Every captured main navigation contained exactly these five hrefs. `/editor` was
not added as a sixth primary item.

| Configured viewport width, CSS px | Visible repeat caption on plan | Exact accessible link name/count | Plan document scrollWidth | Editor-denial document/body scrollWidth |
| --- | --- | --- | --- | --- |
| 320 | Повтор | Повторение / 1 | 305 | 305 / 305 |
| 360 | Повтор | Повторение / 1 | 345 | 345 / 345 |
| 390 | Повторение | Повторение / 1 | 375 | 375 / 375 |

On the loaded plan, every visible main caption had one measured text line at all
three widths; navigation targets were approximately 61.19 CSS px tall. The
document widths exclude the desktop browser's vertical scrollbar. No horizontal
overflow was observed on the tested plan or editor-denial page. Plan screenshots
used height 900; the editor-denial mobile probe used height 844. This does not
claim a physical-device, touch, or complete worksheet mobile pass.

At the original desktop capture, the brand's overriding name was
`ЕГЭ Профиль, Математика 2027, главная`, while its visible text was
`ЕГЭ Профиль\nМатематика 2027`. Recording both strings was not an axe pass;
the later coordinator reproduced a label-content mismatch and corrected it
as recorded below. The original desktop/mobile plan and editor-denial
screenshots were visually inspected.

### `/editor` guest denial and secondary recovery

Direct browser navigation to `http://127.0.0.1:5173/#/editor` caused a real
`GET /api/v1/editor/meta`, returning **503 `accounts_disabled`** with
«Вход по email сейчас недоступен.». Clicking «Повторить запрос» returned the same
status/code. The mounted page showed a denial alert and role/MFA guidance, with
**0 `.editor-workspace` elements and 0 editor inputs/textareas/selects**. Observed
editor requests were GETs only.

Both links had unique accessible names, were reached using Tab, and opened
`#/account` using Enter. Each was a native anchor with `target="_blank"` and
`rel="noopener noreferrer"`; the measured keyboard focus outline was solid,
3 px, `rgb(29, 78, 216)`, with a 4 px offset, and was inside the viewport.

- Header recovery: «Аккаунт и MFA».
- Denial recovery: «Открыть вход и MFA в новой вкладке».

Each resulting popup showed H1 «Аккаунт» and no «Открыть редактор» link for the
guest. Popups were closed and the original editor tab stayed on `#/editor`.
Source inspection found the conditional secondary `ActionLink href="/editor"`
in `frontend/src/accounts/staff-security.tsx:79`, within account/MFA controls,
not the primary navigation. Its actual authenticated entry was **not** exercised.

This proves fail-closed behaviour while accounts are disabled. It does **not**
prove the accounts-enabled guest 401/403 path, staff role checks, or recent/expired
MFA behaviour: `backend/app/accounts/authorization.py:50–60` rejects disabled
accounts before those checks.

## Reproduced and corrected: duplicate worksheet children

**Present at the original worker handoff:** `frontend/src/pages/session.tsx:69–70` gave sibling
`AnswerForm` and `WorksheetAnnotations` the same `key={task.id}`.

Reproduction against this isolated runtime:

1. Start a practice session and open a task while its timer/rerenders run.
2. Observe React's repeated `Encountered two children with the same key` error
   naming `linear-function-two-points-c`.
3. Count `form.answer-form`, `[id="answer"]`, and annotation fieldsets. One
   captured state had **402 answer forms, 402 answer IDs, and 1 annotation
   fieldset**.
4. Reload and immediately click «Пауза». The separate probe still measured
   **4 forms and 4 answer IDs**, with 1 annotation fieldset.
5. The continuation snapshot also retained duplicated forms; its first textbox
   accessible name was «Ответ Ответ Ответ Ответ Ответ Ответ».

Expected: one answer form, one unique answer input ID, and one annotation region
for the current task. Actual duplication makes labels and controls ambiguous and
causes visible DOM accumulation. The scoped wrong-answer precondition used
`page.locator('form.answer-form').first()` as an explicit workaround; it is not
evidence that normal unscoped answer entry passes.

The coordinator reproduced this defect in the new regression
`frontend/e2e/app.spec.ts`, «сохраняет одну форму ответа при работе таймера и смене
задачи»: the unchanged page accumulated **60 answer forms** and the test failed.
The page now uses distinct stable keys `answer:${task.id}` and
`annotations:${task.id}`. No timer, draft, annotation or selection semantics were
changed.

Fresh focused proof, from `D:\math_ege\frontend`:

```powershell
npm run test:e2e -- --project=chromium -g "сохраняет одну форму"
```

**1 passed in 27.1s, exit 0.** The test checks exactly one answer form, one answer
input ID and one annotation group after a real timer update, task switching and
reload; it preserves a saved draft and favourite, checks keyboard focus, finds
zero tagged axe violations and captures no duplicate-key console error. The
failing artifacts were preserved under ignored `output/playwright/worksheet-key-red-*`.
This focused proof is not a replacement for the final whole-project gate.

## Complete twenty-task practice series

The coordinator added `frontend/e2e/app.spec.ts`, «проходит все 20 задач одной
серии и сохраняет исходную историю после reload». It uses the mounted application
and real API, selects the existing **20 задач** option, and completes one series
without creating a replacement session.

Fresh focused command, from `frontend/`:

```powershell
$env:IDENTITY_BROWSER_RUN_ROOT = $null
$env:IDENTITY_BROWSER_EXTERNAL_SERVER = $null
npm.cmd run test:e2e -- --grep 'проходит все 20 задач' --output '<new-private-artifact-directory>'
```

Observed result: **1 passed in 25.0 s, exit 0**; the scenario took **9.6 s**.
Scoped ESLint and strict TypeScript for `e2e/app.spec.ts` also returned exit 0.
The browser run migrated a new isolated SQLite database through
`0008_account_deletion_completion` and built the production Vite/PWA bundle.

The proof checks one answer form, one answer input ID and one annotation group
for each of twenty distinct tasks; task 10's acknowledged draft and current
position survive reload. All twenty original independent attempt DTOs and IDs,
the task snapshots and the frozen profile survive finalization unchanged. The
completed summary has twenty answered tasks, no assistance/corrections/skips,
survives another reload, and renders twenty history rows with no active answer
form. Exactly one session-start POST is observed; page errors and duplicate-key
console errors are empty.

Artifacts are preserved outside Git under
`%LOCALAPPDATA%\Temp\opencode\completion-final-a2b33cf56f6345279476eb687fac14a2`:
`e2e-20-proof.log`, `e2e-20-proof-report/` and `e2e-20-proof-results/`.
An earlier invocation failed **before test execution** because PowerShell's
`ErrorActionPreference='Stop'` classified Alembic INFO stderr as
`NativeCommandError`. Inspection found no surviving matching process or listener;
the preserved successful invocation used `Continue` and converted stderr records
to strings before `Tee-Object`. This was a harness failure, not a passing test.
The focused result is not a final whole-frontend or fixed-commit CI gate.

## Desktop brand-label regression

The coordinator's `frontend/e2e/app.spec.ts` scenario
«имя главной ссылки совпадает с видимым названием проекта» reproduced a serious
axe `label-content-name-mismatch` against the expanded overriding `aria-label`.
The narrow shell fix removes that override and explicitly separates the visible
text; the link's natural accessible name is now `ЕГЭ Профиль Математика 2027`.
Its `href="#/"` and five primary destinations are unchanged.

The combined focused real-API brand/diagnostic-follow-up command passed
**2 tests in 21.1 s, exit 0**. A later run exercised the newly added focus and
desktop/mobile screenshot lines: **1 passed in 18.1 s, exit 0**, scenario 1.9 s.
It verified the exact name, native link destination, keyboard focus and zero
violations for this brand rule only. Captures at 1440 × 900 and 390 × 844 were
opened and visually inspected; the worksheet-blue layout and five navigation
items remain. These are browser viewports, not physical-device checks or a
clean full-page accessibility verdict.

Evidence is outside Git under
`%LOCALAPPDATA%\Temp\opencode\completion-delivery-cd5fa110dec1446492fe710ce731c53c`:
`brand-red.log`, `followup-brand-green.log`, `brand-capture.log` and
`brand-capture-results/**/brand-{desktop,mobile}.png`. Earlier failed scans remain
historical; this focused GREEN does not replace the final integrated gate.

## Local artifacts and limits

Evidence directory: `output/playwright/browser-integration-6ffe07ff/`.

- Plan: `plan-1440.png`, `plan-320.png`, `plan-360.png`, `plan-390.png`,
  `plan-desktop.yml`.
- Annotation loading/save: `annotations-loading.png`, `annotations-initial.yml`,
  `annotation-flags-saved.png`, `annotation-cause-saved.png`.
- Isolation/recovery: `annotations-second-task.png`, `annotations-returned.png`,
  `annotations-read-failure.png`, `annotations-offline.png`.
- Defect: `key-collision.png`, `resumed-remaining-gates.yml`,
  `console-2026-11-05T16-37-17-155Z.log` (duplicate-key errors start at line 4).
- Navigation/editor: `main-nav-after-practice.yml`, `editor-guest-denied.yml`,
  `editor-guest-denied-1440.png`, `editor-guest-denied-390.png`.

Artifacts are local, ignored by Git, and were not committed. Backend request
evidence is also in the temporary `uvicorn.stdout.log`, including the real
annotation save/attempt/export 200s and editor metadata 503s.

Not exercised by the original worker: real staff credentials/email login/MFA,
separate annotation save-response failure injection, production/PWA/service
worker behaviour, a physical mobile device, another browser engine, a screen
reader, zoom, a full-app keyboard/contrast review, or an axe scan. Its historical
console contains the reproduced duplicate-key errors, expected unauthenticated
reads and deliberately exercised failure responses. The later coordinator axe
and keyboard checks cover only the corrected worksheet regression. None of
these scoped observations is a new full frontend lint/unit/build run.

## Owned-process cleanup

After the browser proof was captured, the coordinator reserved ports 8000 and
5173 for the final integrated suite. No further manual server was started and no
finalized proof was repeated. Any future manual run must use the coordinator's
isolated port pairs 8017/5174 or 8027/5184, not the reserved ports.

Actual cleanup:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=sol-browser-6ffe07ff close
```

The CLI reported `Browser 'sol-browser-6ffe07ff' closed`. Before stopping each
server PID, its command line and creation time were checked against this worker's
startup record. Vite PID 21844 and uvicorn child PID 17672 were stopped; launcher
PID 23876 was already absent by the time it was checked. No process was selected
for termination merely because it owned a reserved port.

The final `Get-NetTCPConnection -State Listen -LocalPort 8000,5173` check reported
**no listeners**. A separate process check confirmed PIDs 21844, 17672, and 23876
were absent. These are observations at cleanup time, not an assumption about
later coordinator servers. The database, probe scripts, logs, and screenshots
were preserved; no deletion, reset, or commit was performed.
