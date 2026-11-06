# Автономный Android Implementation Plan

> **For agentic workers:** Реализовать задачи параллельно по разделённым файлам;
> каждый шаг заканчивается focused-тестом и проверкой координатора.

**Goal:** Запускать уроки и практику с локальной проверкой без сервера с первого
запуска Android APK.

**Architecture:** Отдельная React-точка входа и локальное TS-ядро. Версионированная
IndexedDB хранит снимки и попытки; Android загружает только встроенные assets.
Серверный клиент и его владельцы не меняются.

**Tech Stack:** React 19, TypeScript 6, Vite 8, idb 8, BigInt, Java 17, WebView.

**Spec:** [2026-11-06-offline-android-design.md](../specs/2026-11-06-offline-android-design.md)

## Global Constraints

- 845 задач, 99 уроков, 13 позиций; `demo`/`draft`/null reviewers сохранены.
- Отдельная DB `math-ege-offline-v1`; исходные task/revision/seed не меняются.
- Не удалять старые базы, очереди, cookie, SharedPreferences и артефакты.
- 64 символа, точные рациональные числа, никаких float-допусков/округления.
- `ru.mathege.preview`, versionCode 2, versionName `0.2.0-offline-preview`.
- MinSdk 23, compile/target SDK 37, Build Tools 36.0.0, AGP 9.3.3,
  Gradle 9.5.1, JDK 17 и существующий preview-сертификат.

### Task 1: Курс и checker

**Files:** `frontend/src/offline/types.ts`, `checker.ts`, `content.ts`,
`frontend/scripts/package-offline.mjs`, `frontend/tests/offline-checker.test.ts`,
`offline-content.test.ts`.

**Interfaces:** `OfflineCourse`, `OfflineTask`, `loadOfflineCourse()`;
`checkAnswer(raw, expected, mode)` возвращает normalized/expected/correct.

- [ ] Добавить отрицательные/parity-тесты `9007199254740993`, `1/0`, `NaN`,
  `-0`, `1/3`, Unicode-пробелов и 64/65 символов; сначала получить RED.
- [ ] Реализовать BigInt checker по `backend/app/checker.py`, сверить Python.
- [ ] Упаковать неизменные три JSON и `instance_key` каждой задачи в отдельный
  build manifest. Проверить SHA-256 и все 845 эталонов.
- [ ] Запустить `npm.cmd test -- offline-checker offline-content`.

### Task 2: Транзакционное локальное ядро

**Files:** `frontend/src/offline/repository.ts`, `practice.ts`, `progress.ts`,
`frontend/tests/offline-practice.test.ts`.

**Interfaces:** `OfflineRuntime(course)` с `state/start/session/draft/attempt/
hint/solution/finish/progress`; входные DTO совместимы с учебными типами,
сохранённые снимки имеют отдельное происхождение `device`.

- [ ] Создать fake-indexeddb тесты restart/idempotency/body-conflict/помощи/
  исправления/30 дней/исчерпания; увидеть RED до реализации.
- [ ] Создать отдельную DB и UUID владельца; сохранять операции атомарно.
- [ ] Выбирать конечный банк без скрытых повторов; проверять по frozen snapshot.
- [ ] Показывать только реальные progress-счётчики, без статуса «Освоено».
- [ ] Запустить `npm.cmd test -- offline-practice`.

### Task 3: Автономный React-вход

**Files:** `frontend/offline.html`, `frontend/vite.offline.config.ts`,
`frontend/src/offline/main.tsx`, `app.tsx`, `pages/*.tsx`, `styles.css`.

**Interfaces:** Использует TaskContent, RichText, MathFormula, Button и общие
токены. Не импортирует server identity, account runtime или PWA registration.

- [ ] Уроки, настройка 5/10/20, worksheet, подсказки/решения, summary/progress.
- [ ] Сохранять ввод с задержкой до 1 с, показывать сбои хранилища и дефицит.
- [ ] `npm.cmd run build:offline`, lint и полный frontend unit suite.
- [ ] Отдельный E2E без API: пустое хранилище → урок → практика → проверка →
  прогресс → перезапуск; ширины 320/390/1440 и axe.

### Task 4: Android и проверка выпуска

**Files:** `android/app/src/main/java/ru/mathege/preview/OfflineActivity.java`,
offline asset policy/tests, manifest, Gradle asset packaging,
`android/scripts/validate-preview.ps1` и `test-tooling.ps1`.

- [ ] Только виртуальный локальный HTTPS-origin; запрет сети/file/mixed content,
  JavaScript-мостов и arbitrary navigation; DOM storage включён.
- [ ] Встроить свежий `dist-offline`, не использовать серверный `dist`.
- [ ] Сохранить application ID и ключ, увеличить versionCode до 2.
- [ ] Заменить только launcher-specific assertions новым offline-контрактом.
- [ ] Запустить strict unsigned build/lint/unit/tooling/asset inspection;
  подписать копию прежним ключом, проверить signed APK отдельно.
- [ ] Опубликовать новый private prerelease, не заменяя `v0.1.0-preview`,
  записать SHA-256, ограничения устройства и отдельный серверный CI-статус.
