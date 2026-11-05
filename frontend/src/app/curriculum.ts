import { request } from '../api/client';
import { Resource } from './resources';

export type Curriculum = {
  profile_id: string;
  revision: string;
  families: { id: string; title: string; slot: number; skill_ids: string[]; available_tasks: number; difficulties: number[]; lesson_ids: string[] }[];
  lessons: { id: string; title: string; slot: number; kind: 'exam' | 'foundation'; minutes: number; family_ids: string[]; prerequisite_ids: string[]; related_slot_ids: string[] }[];
};

export const curriculumResource = new Resource(() => request<Curriculum>('/curriculum'));
