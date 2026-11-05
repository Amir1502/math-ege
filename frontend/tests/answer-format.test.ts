import { describe, expect, it } from 'vitest';
import { answerFormatError } from '../src/learning/answer-format';

describe('syntax-only explanations after a server format rejection', () => {
  it.each(['0', '-0', '−2', '0002,50', '2.50', '1/2', '-10/3', '  12  ', '99999999999999999999999'])('accepts valid learning syntax %s', (raw) => {
    expect(answerFormatError(raw)).toBeNull();
  });
  it.each(['', ' ', '1/0', '1/000', 'NaN', 'Infinity', '2+3', '2 см', '+2', ',5', '5,', '1,2.3', '1 000', '1e3', '1/-2'])('explains invalid syntax %s', (raw) => {
    expect(answerFormatError(raw)).not.toBeNull();
  });
  it('enforces the raw 64-character limit without trimming the field', () => {
    expect(answerFormatError('1'.repeat(65))).toContain('64');
  });
});
