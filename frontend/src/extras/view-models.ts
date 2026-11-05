import type { PublicTask, StartBody } from '../api/types';
import type {
  AnnotationValues, ErrorCause, Favourite, JournalEntry, LearningDashboard,
  OriginalProfile, PracticeHistory, PracticeProgress, SavedAnnotation, ScheduledReview, SlotEvidence, TimePlan,
} from './types';

export const causeLabels: Record<ErrorCause, string> = {
  theory: 'Не знаю теорию',
  model: 'Неверно построил модель',
  calculation: 'Ошибка в вычислении',
  restriction: 'Не учёл ограничение',
  graph: 'Неверно прочитал график',
  format: 'Нарушил формат ответа',
};

export function familyPracticePath(slot: number | null, familyId: string): string | null {
  if (slot === null || !Number.isInteger(slot) || slot < 1 || slot > 13 || !familyId.trim()) return null;
  return `/practice?slots=${slot}&families=${encodeURIComponent(familyId)}`;
}

export function currentTaskSlot(task: PublicTask, dashboard: LearningDashboard): number | null {
  if (task.slot_id) return dashboard.slots.find((slot) => slot.slot_id === task.slot_id)?.number ?? null;
  const matches = dashboard.slots.filter((slot) => slot.skills.some((skill) => task.skill_ids.includes(skill.id)));
  return matches.length === 1 ? matches[0].number : null;
}

export function pageOffset(value: string | null): number {
  const number = Number(value);
  return Number.isSafeInteger(number) && number >= 0 && number <= 1_000_000 ? number : 0;
}

export function mixedPracticePath(plan: TimePlan): string {
  const query = new URLSearchParams({
    slots: plan.slots.join(','), length: String(plan.length), minutes: String(plan.minutes), selection: 'mixed',
  });
  return `/practice?${query}`;
}

export function mixedStartBody(plan: TimePlan): StartBody & { selection: 'mixed' } {
  return { mode: 'practice', slots: [...plan.slots], length: plan.length, selection: 'mixed', target_minutes: plan.minutes };
}

export function orderedReviews(reviews: ScheduledReview[]): ScheduledReview[] {
  return [...reviews].sort((a, b) => Date.parse(a.due_at) - Date.parse(b.due_at) || a.skill_id.localeCompare(b.skill_id));
}

export function dueReviews(reviews: ScheduledReview[], now = Date.now()): ScheduledReview[] {
  return orderedReviews(reviews).filter((review) => review.overdue || Date.parse(review.due_at) <= now);
}

export function skillTitle(dashboard: LearningDashboard, skillId: string): string {
  return dashboard.slots.flatMap((slot) => slot.skills).find((skill) => skill.id === skillId)?.title
    ?? dashboard.weak_skills.find((skill) => skill.id === skillId)?.title
    ?? 'Повторение навыка';
}

export function entryDescription(entry: JournalEntry): string {
  const attempt = entry.attempt;
  if (!attempt) return 'Ответ ещё не отправлен';
  if (attempt.skipped) return 'Пропуск';
  if (!attempt.first_attempt) return `Повторный ответ: ${attempt.raw_answer}`;
  if (attempt.assisted) return `Ответ с помощью: ${attempt.raw_answer}`;
  if (attempt.independent) return `Первый самостоятельный ответ: ${attempt.raw_answer}`;
  return `Ответ: ${attempt.raw_answer}. Без независимого зачёта`;
}

export function journalForFavourite(dashboard: LearningDashboard, favourite: Favourite): JournalEntry | null {
  return dashboard.journal.find((entry) => entry.session_id === favourite.session_id && entry.task.id === favourite.task.id) ?? null;
}

export function annotationValues(records: SavedAnnotation[], sessionId: string, taskId: string): AnnotationValues {
  const saved = records.find((item) => item.session_id === sessionId && item.task_id === taskId);
  return { favourite: saved?.favourite ?? false, cause: saved?.cause ?? null, manual: saved?.manual ?? false, not_understood: saved?.not_understood ?? false };
}

export function coverageSlots(dashboard: LearningDashboard | null): SlotEvidence[] {
  // Only the dashboard supplies stable positions with their full mandatory-skill detail.
  return dashboard?.slots ?? [];
}

export function originalProfileLabel(profile: OriginalProfile | null): string {
  if (!profile) return 'Исходный профиль не указан в записи';
  const label = profile.title ?? `Профиль ${profile.id}`;
  return [label, profile.year, profile.revision ? `редакция ${profile.revision}` : null].filter(Boolean).join(', ');
}

export function practiceHistoryPath(session: PracticeHistory): string {
  return `/${session.status === 'active' ? 'session' : 'summary'}/${encodeURIComponent(session.id)}`;
}

export function independentAccuracy(progress: Pick<PracticeProgress, 'independent_correct' | 'independent_total'>): number | null {
  if (progress.independent_total === 0) return null;
  return Math.round(100 * progress.independent_correct / progress.independent_total);
}
