import { expect, test } from '@playwright/test';
import type { LearningSession, Profile, PublicTask, StartBody } from '../src/api/types';

test.use({ serviceWorkers: 'block' });

test('каноническая диагностика ведёт к пяти новым задачам по выбранной позиции и навыкам', async ({ page }) => {
  await page.goto('/#/assessment');
  const preparedReply = page.waitForResponse((reply) => reply.url().endsWith('/api/v1/assessments') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Подготовить 13 задач', exact: true }).click();
  const preparedResponse = await preparedReply;
  expect(preparedResponse.ok(), await preparedResponse.text()).toBe(true);
  const prepared = await preparedResponse.json() as { id: string; tasks: PublicTask[] };
  expect(prepared.tasks).toHaveLength(13);
  await page.getByRole('button', { name: 'Начать диагностику', exact: true }).click();
  await expect(page.getByLabel('Ответ', { exact: true })).toBeEditable();
  await expect(page.locator('a[href*="length=5"]')).toHaveCount(0);
  await page.getByLabel('Ответ', { exact: true }).fill('1/2');
  await page.getByRole('button', { name: 'Завершить', exact: true }).click();
  const finishedReply = page.waitForResponse((reply) => reply.url().endsWith(`/${prepared.id}/finish`) && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Завершить занятие', exact: true }).click();
  const finishedResponse = await finishedReply;
  expect(finishedResponse.ok(), await finishedResponse.text()).toBe(true);
  const finished = await finishedResponse.json() as {
    status: string; server_result: { source: string; rows: { task_id: string; format_error: boolean }[] }; local_result: unknown;
  };
  expect(finished.status).toBe('completed');
  expect(finished.server_result.source).toBe('server');
  expect(finished.server_result.rows[0]).toMatchObject({ task_id: prepared.tasks[0].id, format_error: true });
  expect(finished.local_result).toBeNull();

  const result = page.getByRole('region', { name: 'Серверный результат', exact: true });
  const detail = result.locator('details').first();
  await detail.locator('summary').click();
  const followup = detail.getByRole('link', { name: /^Проверить № \d+ на 5 новых задачах$/ });
  await expect(followup).toBeVisible();
  const href = await followup.getAttribute('href');
  expect(href).toMatch(/^#\/practice\?/);
  const query = new URLSearchParams(href!.split('?')[1]);
  expect([...query.keys()]).toEqual(['slots', 'skills', 'length']);
  expect(query.get('length')).toBe('5');
  const skillIds = query.get('skills')!.split(',');
  const profile = await (await page.request.get('/api/v1/profile')).json() as Profile;
  const slot = profile.slots.find((item) => String(item.number) === query.get('slots'));
  expect(slot).toBeDefined();
  if (prepared.tasks[0].slot_id) expect(slot!.id).toBe(prepared.tasks[0].slot_id);
  expect(skillIds.length).toBeGreaterThan(0);
  expect(skillIds.every((id) => prepared.tasks[0].skill_ids.includes(id) && slot!.skills.some((skill) => skill.id === id))).toBe(true);
  await expect(page.getByRole('navigation', { name: 'Главная навигация', exact: true }).getByRole('link')).toHaveCount(5);

  await followup.click();
  await expect(page.getByRole('heading', { name: 'Практика', exact: true, level: 1 })).toBeVisible();
  await expect(page.locator('input[name="length"][value="5"]')).toBeChecked();
  await expect(page.locator('input[name="slot"]:checked')).toHaveCount(1);
  await expect(page.locator('input[name="slot"]:checked')).toHaveValue(String(slot!.number));
  const practiceReply = page.waitForResponse((reply) => reply.url().endsWith('/api/v1/sessions') && reply.request().method() === 'POST');
  await page.getByRole('button', { name: 'Начать занятие', exact: true }).click();
  const practiceResponse = await practiceReply;
  expect(practiceResponse.ok(), await practiceResponse.text()).toBe(true);
  const body = practiceResponse.request().postDataJSON() as StartBody;
  expect(body).toMatchObject({ mode: 'practice', length: 5, slots: [slot!.number], skill_ids: skillIds });
  expect(body.repeat_task_id ?? null).toBeNull();
  const practice = await practiceResponse.json() as LearningSession;
  expect(practice.tasks).toHaveLength(5);
  const diagnosticIds = new Set(prepared.tasks.map((task) => task.id));
  expect(practice.tasks.every((task) => !diagnosticIds.has(task.id) && task.slot === slot!.number && task.skill_ids.some((id) => skillIds.includes(id)))).toBe(true);
});
