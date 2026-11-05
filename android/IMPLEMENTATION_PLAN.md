# Android Preview Implementation Plan

> Execution remains in this assigned worker. The coordinator owns signing, shared files and the release commit; no further delegation or commits are part of this plan.

**Goal:** Deliver an unsigned, nondebuggable Android preview launcher with a user-configurable HTTPS origin and default-browser continuity.

**Architecture:** One native Java Activity owns the configuration/ready states. A pure Java `Endpoint` parser accepts only HTTPS origins, and a pure Java `BrowserPolicy` prevents changing browsers during fallback. The browser owns all web requests, authentication, service workers and downloads.

**Tech Stack:** Java 17, AGP 9.3.3, Gradle 9.5.1, compile/target SDK 37, Build Tools 36.0.0, minSdk 23, AndroidX Browser 1.10.0, JUnit 4.13.2.

**Resolved graph note:** Pin direct Core to 1.13.0, the version selected by Browser's transitive Activity 1.9.0. AGP's built-in Kotlin support selects stdlib/common metadata 2.2.10; the data-only bootstrap captures it. Opt in to the release host-test component with the AGP 9.3 `HostTestBuilder` API.

**Spec:** The coordinator's approved Android delivery request; inherited visual direction in `../DESIGN.md`; delivery contract in `../docs/android-preview.md`.

## Global constraints

- Own only new `android/**` and `docs/android-preview.md` source files.
- No initial endpoint, invented deployment, WebView, JS bridge, native tokens, link capture or device installation.
- Persist only a validated HTTPS origin, with no credentials, path other than `/`, query or fragment.
- Prefer the default browser's Custom Tabs; fallback must use that same default browser package.
- No native INTERNET permission, cleartext or backup. One exported launcher Activity.
- Russian native controls, visible field label/error, system Cyrillic fonts, 48dp minimum controls, scrollable and inset-aware layout.
- Verify the official Gradle ZIP before any execution; use a fresh isolated Gradle user home. Never execute or include `.gradle/android/FakeDependency.jar`.
- Generate dependency verification metadata without applying downloaded plugins first, then build with strict verification and dependency locks.
- Deliver unsigned APK, logs, hashes and honest device/server limitations; signing belongs to the coordinator.

## Task 1: Toolchain and trust boundary

**Files:** `scripts/bootstrap-gradle.ps1`, `tooling/dependency-bootstrap.gradle`, `gradle/wrapper/gradle-wrapper.properties`, `settings.gradle`, `build.gradle`, `gradle.properties`, generated wrapper and verification metadata.

**Interfaces:** Bootstrap produces a verified Gradle executable, a fresh user home and a verified wrapper. Dependency bootstrap downloads pinned artifacts without applying AGP and produces SHA-256 metadata.

- [x] Verify the Gradle 9.5.1 ZIP against `bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f` before execution.
- [x] Generate the wrapper and verify its JAR against `497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7`.
- [x] Resolve pinned AGP/browser/core/JUnit/lint/AAPT artifacts in a separate plain Gradle project without applying AGP.
- [x] Check published AGP/browser hashes, retain generated strict metadata and lock the application graph.

## Task 2: Origin validation and browser policy

**Files:** `app/src/main/java/ru/mathege/preview/Endpoint.java`, `BrowserPolicy.java`, `BrowserLauncher.java`, corresponding local unit tests.

**Interfaces:** `Endpoint.parse(String)` returns a canonical HTTPS origin or a typed `ValidationException`. `BrowserPolicy.useCustomTabs(String, String)` returns true only for matching nonempty default/custom-tab packages. `BrowserLauncher.open(Activity, String)` either launches the chosen default browser or returns a typed failure.

- [x] Test valid DNS, IDN, canonical IPv4, IPv6 and ports.
- [x] Test rejection of HTTP, credentials, paths, tokens in query/fragment, malformed/ambiguous hosts, whitespace, encoded delimiters and invalid ports.
- [x] Test that a different Custom Tabs provider never overrides the default browser.
- [x] Implement package-pinned Custom Tabs and same-package fallback, without warm-up or native requests.

**Public SDK correction:** `ResolveInfo.handleAllWebDataURI` is not in the SDK 37 public stubs. Request `GET_RESOLVED_FILTER` and validate the resolved public HTTPS filter instead; reject missing/host/path/scheme-specific filters. Local policy tests cover the descriptor checks and SDK 37 Java compilation passes. Device browser dispatch remains unassessed.

## Task 3: Native configuration and ready states

**Files:** `MainActivity.java`, `AndroidManifest.xml`, native layout, colors/dimensions/styles, button/field drawables and launcher icon.

- [x] Keep the first-run endpoint empty and explain that this preview needs a reachable HTTPS server.
- [x] Save only a validated origin, show it untruncated, and expose an accessible change/cancel flow.
- [x] Apply native keyboard, focus, error announcements and system/IME/cutout insets; do not save unvalidated drafts.
- [x] Add press/focus/disabled states and measure contrast against the inherited worksheet palette.

**Evidence boundary:** These checkboxes record implemented/source-checked behavior, not rendered-device acceptance. Eleven resource-color/ripple contrast checks pass; TalkBack, large fonts, keyboard and actual rendering remain unassessed.

## Task 4: Build and handoff

**Files:** `scripts/build-preview.ps1`, `scripts/validate-preview.ps1`, `../docs/android-preview.md`, generated reports/artifacts.

Run:

```powershell
.\scripts\build-preview.ps1 -ToolchainState '<verified temp root>\toolchain.json' -WriteLocks
.\scripts\build-preview.ps1 -ToolchainState '<second fresh verified temp root>\toolchain.json'
```

- [x] Require passing release unit tests and lint, with no verification bypass or lint baseline.
- [x] Check merged manifest/unsigned APK for nondebuggable, no INTERNET, no backup and exactly one exported Activity.
- [x] Record wrapper, metadata and APK SHA-256 hashes plus factual tool/log paths.
- [x] Document signing as a coordinator-only follow-up and device/server flows as not assessed.

### Coordinator final unsigned gate (2026-11-05)

- **Exit 0:** 64 tooling checks across 6 PowerShell files, ordinary strict build with unchanged metadata/locks, 62 release unit tests, 11 contrast checks and `unsigned-validation.json`. Valid decimal `"2"` permission rejection was first reproduced RED, then corrected with a 63-check GREEN; the wrapper-local lint-policy check brought the final total to 64. Nonempty `APKANALYZER_OPTS` is rejected alongside JVM overrides.
- Only `AndroidGradlePluginVersion` is classified as an informational `Hint` on `gradle/wrapper/gradle-wrapper.properties` via `gradle/wrapper/lint.xml`; `warningsAsErrors`, `IncompatibleAndroidGradlePluginVersion`, Gradle 9.5.1 and all pins remain unchanged. Evidence: `%LOCALAPPDATA%\Temp\opencode\completion-android-final-3a297d1b1da643169549564efcfcc02a`. Unsigned APK remains 78,186 bytes, SHA-256 `df2b901b34001a73963f03eddf779a95a070c11fba84dce8e42beeeab2c69204`.
- The coordinator reused the existing external preview key after aligning the actual unsigned APK. Raw API23+ warning-strict verification remains RED exit 1 for exactly 20 META-INF warnings. A separate final read-only gate passed the documented exact-warning preview policy: standard API23+ exit 0, API24+ warning-strict exit 0/no warnings, expected v1/v2/v3 signer, actual nondebuggable manifest, signed alignment and all 48 original entries unchanged. Signed APK is 90,065 bytes, SHA-256 `42199293d99b16b7003e7450e3f92a071b5971795c06c74c9ea340000f009dfd`. The API23 ordinary metadata integrity limitation remains explicit in `../docs/android-signature-policy.md`. Private delivery, installation and live-server tests remain unassessed. This documentation reconciliation changes no executable Android sources, pins, metadata, locks or APK payload.

### Historical worker handoff before wrapper-local lint policy (2026-11-05)

- Strict release compilation, R8/resource shrinking, unsigned assemble and all 62 release JVM tests pass; the tooling suite passes 18 checks across 6 PowerShell files.
- Named provider/receiver removal uses explicit `exported=false`. Startup 1.1.1 and ProfileInstaller 1.3.1 are direct compile dependencies at their already-pinned runtime versions. Data-only inventories add exactly four API records; runtime artifacts and verification metadata remain unchanged.
- Buildscript/application locks were persisted by a separate successful strict release/test/lint-analysis capture. That operation is **not** the complete lint gate. The subsequent ordinary strict build used the locks without updating them.
- At that handoff, full `lintRelease` failed with exactly one `AndroidGradlePluginVersion` advisory: pinned Gradle 9.5.1 versus suggested 9.8.2. No version upgrade, baseline, severity override or check exclusion had been applied. `validate-preview.ps1` also correctly failed on this lint finding and did not create a successful validation report.
- Primary full-gate evidence: `%LOCALAPPDATA%\Temp\opencode\math-ege-android-preview-6b03091ffb374e9aa0a1e4c03f55ac41\release-build-20261105-183652.log` and `app/build/reports/lint-results-release.xml`.
- Independent second-cache strict build also executes 51 tasks, passes all 62 release tests and fails the same one lint advisory. It does not regenerate hashes/locks. Both APKs are byte-identical: 78,186 bytes, SHA-256 `df2b901b34001a73963f03eddf779a95a070c11fba84dce8e42beeeab2c69204`.
- The archived worker evidence is `app/build/reports/android-preview/handoff.json` with `Status=blocked-lint`, `FullReleaseGatePassed=false` and `FullValidatorPassed=false`; complete hashes/tool/log paths are recorded in `../docs/android-preview.md`. `apksigner verify` returned the expected unsigned exit 1 and `zipalign` returned 0. This historical handoff is not a signed/installable or lint-clean release.
- Signing, installation and live-server tests are coordinator-only follow-ups, not completed gates. No further delegation, commit/push, deployment, device installation or existing database mutation/deletion was performed.
