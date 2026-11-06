import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { checkAnswer, parseAnswer } from '../src/offline/checker';
import type { AnswerMode } from '../src/offline/checker';
import { courseRoot, pythonJson } from './offline-core-python';

describe('offline exact answer checker', () => {
  it('compares integers beyond the Number range without a tolerance', () => {
    expect(checkAnswer('9007199254740993', '9007199254740993')).toEqual({
      correct: true, normalized_answer: '9007199254740993', expected_answer: '9007199254740993',
    });
    expect(checkAnswer('9007199254740993', '9007199254740992').correct).toBe(false);
    expect(parseAnswer('−0002/0004').normalized_answer).toBe('-0,5');
  });

  it('matches Python for Unicode stripping, code point length, exact rationals, and error messages', () => {
    const pythonSpace = [9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
      ...Array.from({ length: 11 }, (_, index) => 8192 + index), 8232, 8233, 8239, 8287, 12288];
    const raw: unknown[] = [
      '0', '-0', '−0', '-000.000', '0002,50', '−00010.0500', '1/2', '2/4', '-2/4',
      '0/7', '-0/7', '4/2', '1/3', '2/6', '-10/6', '1/40', '7/8',
      '1/1000000000000000000000000', '9007199254740993', '9'.repeat(64),
      '0,' + '0'.repeat(61) + '1', '0'.repeat(65), ' ' + '9'.repeat(64), '9'.repeat(64) + ' ',
      '😀'.repeat(32), '😀'.repeat(65), '1\ud800', '1\u0085', '1\u001c', '\u001f−2.5\u001c',
      ...pythonSpace.flatMap((point) => {
        const space = String.fromCodePoint(point);
        return [space + '−2.50' + space, '1' + space + '000'];
      }),
      '', ' ', '\t\r\n', '1/0', '1/00', '0/0', '1/-2', '-1/-2', '1/−2', '1/+2',
      '1/', '/2', '1/2/3', '1.5/2', '1/2.5', '1,5/2', '1 /2', '1/ 2',
      'NaN', 'nan', 'Infinity', 'inf', '-Infinity', '2+3', '2-3', '2*3', '2^3', '2**3',
      'sqrt(4)', '(2)', '2 кг', '+1', '＋1', ',5', '.5', '1,', '1.', '1,2,3', '1.2.3',
      '1,2.3', '1.2,3', '--1', '−-1', '–1', '—1', '1-', '1e3', '0x10', '１２', '١٢',
      '²', '1\0', '1\u200b', '1\ufeff', '\ufeff1', '1\u180e', '1/２', '1／2', '1\\2', '-',
      null, 0, 0.5, true, [], {},
    ];
    const cases = raw.flatMap((answer) => (['training', 'exam'] as const).map((mode) => ({ answer, mode })));
    const expected = pythonJson<unknown[]>(`
import json
from app.checker import parse_answer
results = []
for case in json.load(sys.stdin):
    try:
        parsed = parse_answer(case['answer'], case['mode'])
        results.append({'normalized_answer': parsed.normalized_answer,
                        'numerator': str(parsed.value.numerator), 'denominator': str(parsed.value.denominator)})
    except Exception as error:
        results.append({'code': getattr(error, 'code', None), 'message': str(error),
                        'field': getattr(error, 'field', None)})
print(json.dumps(results, ensure_ascii=True))
`, cases);
    const actual = cases.map(({ answer, mode }) => {
      try {
        const parsed = parseAnswer(answer, mode);
        return { normalized_answer: parsed.normalized_answer,
          numerator: parsed.value.numerator.toString(), denominator: parsed.value.denominator.toString() };
      } catch (error) {
        const rejected = error as { code: string; message: string; field: string };
        return { code: rejected.code, message: rejected.message, field: rejected.field };
      }
    });
    expect(actual).toEqual(expected);
  });

  it('matches Python comparison for all 845 original references in both modes', () => {
    const tasks = JSON.parse(readFileSync(resolve(courseRoot, 'tasks.json'), 'utf8')) as { answer: string }[];
    expect(tasks).toHaveLength(845);
    const cases = tasks.flatMap((task) => (['training', 'exam'] as const).map((mode) => ({
      raw: task.answer, expected: task.answer, mode,
    })));
    const expected = pythonJson<unknown[]>(`
import dataclasses, json
from app.checker import check_answer
print(json.dumps([dataclasses.asdict(check_answer(item['raw'], item['expected'], item['mode']))
                  for item in json.load(sys.stdin)], ensure_ascii=True))
`, cases);
    expect(cases.map(({ raw, expected, mode }) => checkAnswer(raw, expected, mode))).toEqual(expected);
  });

  it('never rounds fractions, tiny values, or the supplied finite reference', () => {
    expect(checkAnswer('1/3', '0,33')).toEqual({
      correct: false, normalized_answer: '1/3', expected_answer: '0,33',
    });
    expect(checkAnswer('0,' + '0'.repeat(61) + '1', '0').correct).toBe(false);
    expect(checkAnswer('9007199254740992,01', '9007199254740992,02').correct).toBe(false);
    expect(() => checkAnswer('1/3', '1/3')).toThrow();
    expect(() => parseAnswer('0', 'unknown' as AnswerMode)).toThrow("mode must be 'training' or 'exam'");
  });
});
