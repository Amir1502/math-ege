# Offline Appearance 0.2.1 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the approved offline appearance changes to `Amir1502/math-ege` on `main` and deliver an installable, signed `v0.2.1-offline-preview` GitHub prerelease.

**Architecture:** Keep the existing autonomous frontend, Android application ID and preview signing certificate. Increase only Android release metadata, rerun the frontend and unsigned Android gates, sign a separate APK copy with the existing external keystore, and verify the uploaded bytes against the local signed artifact.

**Tech Stack:** React/TypeScript, Vitest, Playwright Chromium, Gradle 9.5.1, AGP 9.3.3, JDK 17, Android Build Tools 36.0.0, PowerShell, Git and GitHub CLI.

**Spec:** `DESIGN.md` records the approved appearance contract; the user explicitly requested both code and APK publication. `docs/android-preview.md` and `docs/android-signature-policy.md` define the existing preview release and signing boundaries.

## Global Constraints

- Execute release operations inline in the current session; no feature development or further delegation is required.
- Keep `ru.mathege.preview`, minSdk `23`, targetSdk `37` and the existing certificate SHA-256 `e17ebff9a819267517c7605e437482fc31434b166f47145f30776c4fb44231b7`.
- Release metadata: `versionCode = 3`, `versionName = '0.2.1-offline-preview'`, tag `v0.2.1-offline-preview`.
- Preserve 845 tasks, 99 lessons and revision `offline-v1-4e62fddb949989ee8b1d63bc9368f40a42c0f45e03026a0b8eddb08209bfcaed`; do not change learning data or IndexedDB schema.
- Keep the repository private and mark the release as a prerelease. Do not deploy a server, publish to an app store or claim production/course acceptance.
- Keep the private keystore and DPAPI password file outside Git; do not log or pass a password in command-line arguments.
- Retain strict dependency verification, existing locks, lint warnings-as-errors and the exact API 23 signature-warning policy. Do not generate a new signing key, remove META-INF records or waive new warnings.
- Preserve existing user changes. Use explicit staging paths and ordinary fast-forward pushes; never force-push or replace an existing release asset.
- Real-device installation, update/data retention, OEM WebView, TalkBack, native large fonts, safe areas and IME remain unassessed.
- Checkbox state is a snapshot immediately before the release commit. Final remote publication and download verification are recorded in the GitHub release notes and external delivery evidence, not by a second documentation push that cancels the exact-SHA CI run.

## File Structure

- Modify `android/app/build.gradle`: increase Android release version metadata only.
- Modify `README.md`: link the new offline preview and correct the obsolete launcher-only description.
- Modify `docs/android-preview.md`: add the 0.2.1 release facts while retaining historical 0.2.0 and 0.1.0 evidence.
- Preserve and publish the already-approved changes in `DESIGN.md`, `frontend/src/offline/`, `frontend/src/styles/tokens.css`, `frontend/offline.html`, `frontend/offline-public/offline-theme.js`, `frontend/offline-e2e/appearance.spec.ts`, Android offline Activity/assets policy and theme resources, and `android/scripts/validate-preview.ps1`.
- Create release notes, a version-specific copy of the existing signing harness, signed APK, public certificate, checksums and verification records only beneath `%LOCALAPPDATA%\Temp\opencode`.

### Task 1: Version the approved update and rerun local gates

**Files:** Modify `android/app/build.gradle`; test the existing frontend suites and `android/scripts/build-preview.ps1`.

**Interfaces:** Consumes the approved working-tree appearance changes and the previously verified isolated `toolchain.json`; produces an unsigned code-3 APK and fresh frontend/Android verification evidence.

- [x] Change only the release values in `android/app/build.gradle`:

```groovy
versionCode = 3
versionName = '0.2.1-offline-preview'
```

- [x] Run each frontend gate from `frontend/`, checking its exit code before continuing:

```powershell
npm run lint
npm test
npm run build
npm run build:offline
npx playwright test --config playwright.offline.config.ts
```

Expected: 424 unit tests and 24 offline Chromium scenarios pass, both builds succeed, and the offline package retains the expected course revision and counts.

- [x] Run the full existing unsigned strict Android gate from `android/`:

```powershell
.\scripts\build-preview.ps1 `
  -ToolchainState 'C:\Users\user\AppData\Local\Temp\opencode\math-ege-android-preview-repro-e1f86b24c8b04d6aa7d36a1e6fd18a28\toolchain.json' `
  -JavaHome 'C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot' `
  -AndroidHome 'C:\Android\Sdk' -Offline
```

Expected: 64 tooling checks, 144 release unit tests, successful release assembly, zero lint errors/warnings, seven exact bundled-asset checks and a successful unsigned APK validation report. Inspect the compiled manifest for code `3` and name `0.2.1-offline-preview`.

The final gate was also replayed with `--rerun-tasks`, using the same verified toolchain, strict verification, isolated cache and full task list. All 52 actionable tasks executed, all 144 release unit tests passed, and both gates produced the same unsigned APK SHA-256.

### Task 2: Sign and verify the installable APK

**Files:** Create a version-specific signing harness and a fresh evidence directory outside the repository; consume `android/app/build/outputs/apk/release/app-release-unsigned.apk`.

**Interfaces:** Consumes the verified unsigned APK and existing DPAPI-protected preview key; produces `math-ege-offline-preview-0.2.1.apk`, `preview-certificate.der`, `SHA256SUMS.txt` and `signed-result.json`.

- [x] Copy the reviewed external `sign-offline-preview.ps1` into a new version-specific harness without changing the original. Use the 0.2.1 APK filename and checksum entry; retain its stdin password transport and private-file hash/ACL checks.
- [x] Before signing, verify the unsigned APK hash matches `validation.json`, the pinned signer JAR hash remains `3716d9311e55d2b0918a2fd9d54ba9e406c5f6abeea700b287f11259bc163dec`, and no unexpected JVM/signer environment overrides are present.
- [x] Sign a separate aligned APK copy using the existing alias `math-ege-preview` with v1/v2/v3 enabled and v4 disabled. Never change or overwrite the original unsigned APK or key files.
- [x] Verify API 23+ standard signature, API 24+ warning-strict signature, signed ZIP alignment, exactly one expected certificate, compiled identity/SDK/debuggable values, all original ZIP entry hashes and lengths, and exactly the three v1 signature additions.
- [x] Preserve the raw API 23+ `-Werr` diagnostic as exit `1` with the unchanged 20 exact metadata warnings; any other warning or error blocks publication.
- [x] Independently read the signed APK and record its SHA-256, size, version, public certificate and unchanged learning-package metadata. Add release facts and honest limitations to `docs/android-preview.md`, `README.md` and the external release notes.

### Task 3: Publish the exact commit and verify delivered bytes

**Files:** Stage only the reviewed application changes, version metadata, release documentation and this plan. Do not stage APKs, logs, reports or secrets.

**Interfaces:** Consumes the reviewed source tree and verified signed assets; produces a fast-forward `main` push, tag `v0.2.1-offline-preview` and a published GitHub prerelease containing exactly the verified assets.

- [x] Fetch `origin/main`, inspect the diff and explicit staged-file inventory, run `git diff --check`, `git diff --cached --check` and `node scripts/check-source.mjs`, and verify the dependency metadata/locks have no diff.
- [ ] Commit with `feat(android): add dark theme and compact offline navigation` and push normally to `origin main`. If the remote moved incompatibly, stop rather than overwrite it.
- [ ] Verify the remote `main` SHA matches the new local commit and attach the release to that full commit SHA. Create a new draft prerelease first, without clobbering any existing tag or release.
- [ ] Check release metadata and GitHub asset digests against the local signed APK, public certificate, checksums and verification record. Publish the draft as a prerelease only after they match.
- [ ] Download the published assets into a fresh external directory and independently compare every SHA-256 to its local source. Verify the downloaded APK signature and compiled code/name once more.
- [ ] Record the exact-SHA CI status without claiming the previously failing server workload is fixed. Provide the user with the release/APK links and the real-device verification limitation.
