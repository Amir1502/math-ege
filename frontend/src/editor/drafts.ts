import { EditorError, jsonObject } from './adapters';
import type { EditorMeta, JsonObject, Kind } from './types';

export function parsePayload(source: string, maxBytes: number): JsonObject {
  if (new TextEncoder().encode(source).length > maxBytes) {
    throw new Error('JSON превышает допустимый размер. Сократите запись или пакет.');
  }
  try { return jsonObject(JSON.parse(source)); }
  catch { throw new Error('Нужен JSON-объект: проверьте кавычки, запятые и удвоенные обратные слеши в LaTeX.'); }
}

export function parseImport(source: string, maxBytes: number, maxItems: number): JsonObject {
  const body = parsePayload(source, maxBytes);
  if (body.version !== '1' || !Array.isArray(body.items) || !body.items.length || body.items.length > maxItems) {
    throw new Error(`Нужны version: "1" и массив items от 1 до ${maxItems} записей. Ошибки строк проверит сервер.`);
  }
  return body;
}

export function parseSeed(value: string): number {
  if (!/^\d{1,10}$/.test(value) || Number(value) > 4_294_967_295) throw new Error('Введите целый seed от 0 до 4294967295.');
  return Number(value);
}

export function starter(kind: Kind, meta: EditorMeta): JsonObject {
  const slot = meta.profile.slots[0];
  if (!slot || !slot.skills.length) throw new EditorError('В текущем профиле нет позиций с навыками. Обновите профиль.', 'empty_profile');
  if (kind === 'task') return {
    id: '', title: '', slot: slot.number, slot_id: slot.id, topic: slot.title,
    profile_id: meta.profile.id, skill_ids: [slot.skills[0].id], family_id: '', difficulty: 1,
    statement: '', formula: null, table: null, figure: null, rounding: null, estimated_seconds: 120,
    answer: '', hints: ['', '', ''], hint_count: 3, solution: [''], source: { origin: '', rights: '' }, generation: null,
  };
  if (kind === 'lesson') return {
    id: '', title: '', kind: 'exam', slot: slot.number, slot_id: slot.id,
    skill_ids: [slot.skills[0].id], minutes: 5, sections: [{ heading: '', body: '', formula: null }],
    example: { statement: '', steps: [''], answer: '' }, examples: [], takeaway: '',
    family_ids: [], practice_task_ids: [], prerequisite_ids: [], related_slot_ids: [],
  };
  if (kind === 'profile') {
    const value = jsonObject(meta.profile); delete value.revision;
    return { ...value, id: '', title: '', status: 'draft' };
  }
  const family = meta.templates[0];
  return {
    id: '', title: '', generator_id: family?.id ?? '', generator_version: '',
    profile_id: meta.profile.id, profile_revision_id: null,
    slot_id: meta.profile.slots.find(slot => slot.number === family?.slot)?.id ?? '',
    family_id: family?.id ?? '', skill_ids: family?.skill_ids ?? [], formula_notes: '', constraints: [''],
  };
}

export function downloadText(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = name;
  document.body.append(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadJson(name: string, value: unknown): void { downloadText(name, JSON.stringify(value, null, 2)); }
