import type { StartBody } from '../api/types';

const values = (query: URLSearchParams, key: string) => [...new Set((query.get(key) ?? '').split(',').filter(Boolean))];

export function practiceOptions(query: URLSearchParams): StartBody {
  const length = query.get('length');
  const minutes = query.get('minutes');
  const difficulty = query.get('difficulty');
  return {
    mode: 'practice',
    slots: values(query, 'slots').filter((value) => /^[1-9]\d*$/.test(value)).map(Number).filter((value) => value <= 13),
    length: length === '10' ? 10 : length === '20' ? 20 : 5,
    target_minutes: minutes === '10' ? 10 : minutes === '20' ? 20 : minutes === '30' ? 30 : null,
    difficulty: difficulty === '1' ? 1 : difficulty === '2' ? 2 : difficulty === '3' ? 3 : null,
    family_ids: values(query, 'families'), skill_ids: values(query, 'skills'),
    selection: query.get('selection') === 'mixed' ? 'mixed' : 'balanced',
    until_stopped: query.get('until_stopped') === 'true', repeat_task_id: query.get('repeat') || null,
  };
}
