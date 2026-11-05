import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const origin = process.env.APP_ORIGIN ?? 'http://127.0.0.1:8080';
const course = JSON.parse(await readFile(new URL('../backend/content/course/manifest.json', import.meta.url), 'utf8'));
let cookie;

const page = await fetch(origin, { signal: AbortSignal.timeout(15_000) });
assert.equal(page.status, 200);
assert.equal(page.headers.get('x-content-type-options'), 'nosniff');
assert.equal(page.headers.get('x-frame-options'), 'DENY');
assert.match(page.headers.get('content-security-policy') ?? '', /frame-ancestors 'none'/);
const html = await page.text();
assert.match(html, /lang="ru"/);
assert.match(html, /<div id="root"/);

async function request(path, body, idempotencyKey) {
  const response = await fetch(`${origin}/api/v1${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      'X-Requested-With': 'math-ege',
      Origin: origin,
      ...(cookie ? { Cookie: cookie } : {}),
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(15_000),
  });
  const setCookie = response.headers.get('set-cookie');
  if (setCookie) cookie = setCookie.split(';', 1)[0];
  const result = await response.json();
  assert.ok(response.status === 200 || response.status === 201, `${path}: ${response.status} ${JSON.stringify(result)}`);
  return result;
}

assert.deepEqual(await request('/health'), { status: 'ok' });
const profile = await request('/profile');
assert.equal(profile.status, 'draft');
assert.equal(profile.slots.length, 13);
assert.equal(profile.id, course.profile_id);
assert.equal(profile.revision, course.profile_revision);
assert.equal(profile.bank_size, course.task_count);
const curriculum = await request('/curriculum');
assert.equal(curriculum.lessons.length, course.lesson_count);
await request('/guest', {});
assert.ok(cookie);

const creationKey = randomUUID();
const config = { mode: 'practice', slots: [6], length: 5 };
const session = await request('/sessions', config, creationKey);
assert.deepEqual(await request('/sessions', config, creationKey), session);
assert.equal(session.tasks.length, 5);
const task = session.tasks[0];
for (const hidden of ['answer', 'solution', 'hints']) {
  assert.equal(Object.hasOwn(task, hidden), false);
}

const hint = await request(`/sessions/${session.id}/hints`, { task_id: task.id, level: 1 });
assert.ok(hint.text);
const solution = await request(`/sessions/${session.id}/solution`, { task_id: task.id });
const body = { task_id: task.id, answer: solution.answer, active_seconds: 12, skipped: false };
const attemptKey = randomUUID();
const attempt = await request(`/sessions/${session.id}/attempts`, body, attemptKey);
assert.equal(attempt.correct, true);
assert.equal(attempt.assisted, true);
assert.equal(attempt.independent, false);
assert.deepEqual(await request(`/sessions/${session.id}/attempts`, body, attemptKey), attempt);

const concurrentTask = session.tasks[1];
const concurrentKey = randomUUID();
const concurrentBody = { task_id: concurrentTask.id, answer: '9999999999999999', active_seconds: 8, skipped: false };
const concurrent = await Promise.all([
  request(`/sessions/${session.id}/attempts`, concurrentBody, concurrentKey),
  request(`/sessions/${session.id}/attempts`, concurrentBody, concurrentKey),
]);
assert.deepEqual(concurrent[0], concurrent[1]);
assert.equal(concurrent[0].independent, true);
assert.equal(concurrent[0].correct, false);

const finishKey = randomUUID();
const complete = await request(`/sessions/${session.id}/finish`, {}, finishKey);
assert.equal(complete.status, 'completed');
assert.equal(complete.summary.assisted, 1);
assert.equal(complete.summary.independent_total, 1);
assert.deepEqual(await request(`/sessions/${session.id}/finish`, {}, finishKey), complete);

const annotation = await request('/learning/annotations', {
  session_id: session.id, task_id: task.id, favourite: true,
}, randomUUID());
assert.equal(annotation.favourite, true);
const dashboard = await request('/learning/dashboard');
assert.equal(dashboard.algorithm_version, 'learning-v1');
assert.ok(dashboard.favourites.some(item => item.task.id === task.id));

const device = randomUUID();
const preparation = { mode: 'exam', device_id: device, duration_minutes: 15 };
const prepareKey = randomUUID();
const assessment = await request('/assessments', preparation, prepareKey);
assert.deepEqual(await request('/assessments', preparation, prepareKey), assessment);
assert.equal(assessment.tasks.length, 13);
assert.equal(new Set(assessment.tasks.map(item => item.slot)).size, 13);
assert.equal(assessment.deadline_at, null);
assert.equal(assessment.server_result, null);
for (const condition of assessment.tasks) {
  for (const hidden of ['answer', 'solution', 'hints', 'generation', 'source', 'instance_key']) {
    assert.equal(Object.hasOwn(condition, hidden), false);
  }
}
const writer = { device_id: device, writer_generation: assessment.writer_generation };
const active = await request(`/assessments/${assessment.id}/activate`, writer, randomUUID());
assert.equal(active.status, 'active');
assert.ok(active.deadline_at);
assert.equal(active.server_result, null);
const finalized = await request(`/assessments/${assessment.id}/finish`, {
  ...writer, answers: {}, connection_lost: false,
}, randomUUID());
assert.equal(finalized.status, 'completed');
assert.equal(finalized.server_result.score, 0);
assert.equal(finalized.server_result.skipped, 13);
assert.equal(finalized.local_result, null);

const exported = await request('/export');
assert.deepEqual(Object.keys(exported).sort(), [
  'account', 'assessments', 'exported_at', 'learning', 'profile_id', 'sessions', 'version',
]);
assert.equal(exported.version, '1');
assert.equal(exported.sessions.length, 1);
assert.equal(exported.assessments.length, 1);
assert.equal(exported.learning.annotations.length, 1);
assert.equal(exported.account, null);
assert.deepEqual(exported.assessments[0].server_result, finalized.server_result);
for (const privateField of ['token', 'token_hash', 'cookie', 'guest_id', 'user_id']) {
  assert.equal(Object.hasOwn(exported, privateField), false);
}

const originalCookie = cookie;
cookie = undefined;
await request('/guest', {});
assert.notEqual(cookie, originalCookie);
const denied = await fetch(`${origin}/api/v1/sessions/${session.id}`, {
  headers: { Cookie: cookie },
  signal: AbortSignal.timeout(15_000),
});
assert.equal(denied.status, 404);
assert.equal((await denied.json()).error.code, 'not_found');
console.log('PostgreSQL + API + nginx: smoke checks passed.');
