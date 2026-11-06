import type { LearningSession, OfflineCourse, Progress } from './types';

export function localProgress(course: OfflineCourse, sessions: LearningSession[], activeSessionId: string | null): Progress {
  const history = sessions.flatMap((session) => session.attempts.map((attempt) => ({
    attempt, task: session.tasks.find((task) => task.id === attempt.task_id)!,
  })));
  const independent = history.filter(({ attempt }) => attempt.independent);
  return {
    independent_total: independent.length,
    independent_correct: independent.filter(({ attempt }) => attempt.correct).length,
    assisted_total: history.filter(({ attempt }) => attempt.assisted && !attempt.skipped).length,
    corrections_total: history.filter(({ attempt }) => !attempt.first_attempt && !attempt.skipped).length,
    skipped_total: sessions.reduce((total, session) => total + session.summary.skipped, 0),
    active_session_id: activeSessionId,
    slots: course.profile.slots.map((slot) => {
      const rows = independent.filter(({ task }) => task.slot === slot.number);
      const touched = history.some(({ task }) => task.slot === slot.number);
      return { number: slot.number, attempts: rows.length, correct: rows.filter(({ attempt }) => attempt.correct).length,
        status: touched ? 'Изучаю' : 'Нет данных', covered_skills: new Set(rows.flatMap(({ task }) => task.skill_ids)).size,
        total_skills: slot.skills.length };
    }),
    recent_sessions: sessions.slice(0, 20).map(({ id, status, created_at, summary }) => ({ id, status, created_at, summary })),
    mistakes: history.filter(({ attempt }) => attempt.first_attempt && !attempt.correct).slice(0, 100),
  };
}
