# Learning Core Frontend Implementation Plan

**Goal:** Deliver the approved first-stage Russian learning application without changing backend, infrastructure, root documentation, or parent-owned browser tests.

**Architecture:** A React application uses hash routes, typed same-origin API calls, and small page modules. A persistent session controller owns local drafts and immutable pending mutations independently of page navigation. IndexedDB stores current session snapshots and previously opened lessons; the service worker stores only the application shell.

**Tech Stack:** Node 24, React 19.3.1, TypeScript 6.0.3, Vite 8.3.6, vite-plugin-pwa 2.0.0, idb 8.0.4, KaTeX 0.19.1, Lucide 1.69.0, local Inter and Manrope.

**Spec:** `../docs/api-contract.md`, `../docs/superpowers/specs/2026-11-05-learning-core-design.md`, `../DESIGN.md`, and the first-stage requirements in `../technical-spec.md`.

## Global Constraints

- All API property names match the snake_case contract. Guest creation is called only from an intentional training start.
- Lengths are 5, 10, or 20 tasks. The interface does not claim interval review, an exam mode, verified content, mastery, or a predicted exam score.
- All code edits use patch operations. No git commits are made.
- Parent ownership of `e2e/`, `playwright.config.ts`, and `Dockerfile` is preserved.
- API responses are never stored by the service worker. Answer checking always requires the API.

## Implementation Sequence

1. **Application and persistence foundation.** Add the Vite/PWA configuration, API DTOs and client, IndexedDB schema, immutable pending request records, and the global CSS token contract. Add tests using `fake-indexeddb` to verify durable writes and retry bodies.
2. **Session state machine.** Implement local-first draft updates, serialized revision-aware writes, explicit conflict resolution, idempotent attempts and finish, and a visibility-aware active clock. Tests hold API responses open while new edits arrive and simulate loss of the first response.
3. **Learning surfaces.** Build the five-destination shell, plan, 13-position catalogue, cached lessons, and multiselect practice setup. Use actual API content with loading, error, and empty states; no sample statistics.
4. **Practice and history.** Build the task worksheet, accessible answer controls, three hints, separate solution, correction, skip, finish confirmation, summary, mistake journal, progress, and JSON export.
5. **Verification.** Run `npm run test`, `npm run lint`, and `npm run build`. Check the design token contrast and mechanical UI rules. The parent session owns real-backend browser integration and the required viewport screenshot round.

## Layout Regions

- **Shell:** a narrow desktop sidebar, a five-item mobile bottom bar, and a small profile-status header.
- **Plan:** an asymmetric worksheet with one start action, a factual side note, and the functional 13-position rail.
- **Catalogue and history:** hairline-separated ledgers rather than repeated decorative cards.
- **Lesson:** a readable theory column, a worked example, and a concise practice handoff.
- **Session:** a broad task worksheet, reserved answer feedback, and a clearly separate help column.

## Verification Cases

- A stale draft response acknowledges only the submitted local revision, not a newer input value.
- Reload restores raw unsent text, task position, cumulative active seconds, and the original pending request UUID and body.
- A request is persisted before it can leave the browser. Double submission cannot create a second pending attempt.
- A `409 draft_conflict` preserves local text and requires an explicit choice before overwriting the remote draft.
- Hidden-tab time and time on other routes are excluded from task active time.
- A format rejection is not a wrong mathematical answer. Network failure preserves the pending answer and never fabricates a result.
- A GET `/progress` response of 401 produces the guest empty state, not a POST `/guest`.
