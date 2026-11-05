import type { Profile } from '../api/types';
import type { AssessmentView } from './types';

export type DiagnosticFollowup = { task_id: string; slot: number; skill_ids: string[]; href: string };

// A single diagnostic answer remains preliminary, including a correct independent answer.
export function diagnosticFollowups(view: AssessmentView, profile: Profile | null): DiagnosticFollowup[] {
  if (!profile || view.mode !== 'diagnostic' || view.status !== 'completed' || !view.server_result) return [];
  return view.server_result.rows.flatMap((row) => {
    const task = view.tasks.find((item) => item.id === row.task_id);
    if (!task) return [];
    const matches = task.slot_id
      ? profile.slots.filter((slot) => slot.id === task.slot_id)
      : profile.slots.filter((slot) => slot.skills.some((skill) => task.skill_ids.includes(skill.id)));
    if (matches.length !== 1) return [];
    const slot = matches[0];
    if (!Number.isInteger(slot.number) || slot.number < 1 || slot.number > 13 || !(slot.available_tasks > 0)
      || profile.slots.filter((item) => item.number === slot.number).length !== 1) return [];
    const skill_ids = [...new Set(task.skill_ids)].filter((id) => id.trim() && !id.includes(',')
      && slot.skills.some((skill) => skill.id === id));
    if (!skill_ids.length) return [];
    const query = new URLSearchParams({ slots: String(slot.number), skills: skill_ids.join(','), length: '5' });
    return [{ task_id: row.task_id, slot: slot.number, skill_ids, href: `/practice?${query}` }];
  });
}
